"""
Link discovery with guardrails.

Provides multiple strategies for discovering URLs on a website:
- Sitemap parsing (with streaming and depth limits)
- Common URL pattern guessing
- Link extraction from HTML
- Heuristic scoring for prioritization
"""

import gzip
import io
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from .config import COMMON_PAGE_PATTERNS, SitemapConfig
from .net import extract_host, head_exists, make_request, is_same_domain
from .rate_limiter import RateLimiter, NoOpRateLimiter


logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class DiscoveredLink:
    """A discovered link with metadata for scoring."""
    url: str
    source: str  # "sitemap", "guess", "html", "homepage"
    anchor_text: Optional[str] = None
    sitemap_priority: Optional[float] = None
    sitemap_lastmod: Optional[str] = None
    score: float = 0.0


# =============================================================================
# Sitemap Parsing
# =============================================================================

# XML namespaces for sitemaps
SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
}


def fetch_sitemap_links(
    base_url: str,
    config: Optional[SitemapConfig] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> List[DiscoveredLink]:
    """
    Fetch and parse sitemap(s) with safety constraints.
    
    Features:
    - Stream parsing to avoid memory issues
    - Max depth for sitemap index recursion
    - Max URLs limit with explicit logging
    - Handles gzipped sitemaps
    - Special mode for very large sitemaps
    
    Args:
        base_url: Base URL of the website (e.g., "https://example.com")
        config: Sitemap configuration (default: SitemapConfig())
        rate_limiter: Rate limiter for requests (default: NoOpRateLimiter)
    
    Returns:
        List of DiscoveredLink objects from sitemap(s)
    """
    config = config or SitemapConfig()
    rate_limiter = rate_limiter or NoOpRateLimiter()
    
    # Normalize base URL
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    
    # Try common sitemap locations
    sitemap_urls = [
        f"{base}/sitemap.xml",
        f"{base}/sitemap_index.xml",
        f"{base}/sitemap.xml.gz",
        f"{base}/sitemaps/sitemap.xml",
    ]
    
    all_links: List[DiscoveredLink] = []
    visited_sitemaps: Set[str] = set()
    
    for sitemap_url in sitemap_urls:
        if len(all_links) >= config.max_urls_per_sitemap:
            logger.debug(f"Reached max URLs ({config.max_urls_per_sitemap}), stopping sitemap discovery")
            break
        
        links = _parse_sitemap_recursive(
            sitemap_url,
            config=config,
            rate_limiter=rate_limiter,
            visited=visited_sitemaps,
            depth=0,
            max_urls=config.max_urls_per_sitemap - len(all_links),
        )
        all_links.extend(links)
        
        if links:
            # Found a working sitemap, don't try others
            break
    
    return all_links


def _parse_sitemap_recursive(
    sitemap_url: str,
    config: SitemapConfig,
    rate_limiter: RateLimiter,
    visited: Set[str],
    depth: int,
    max_urls: int,
) -> List[DiscoveredLink]:
    """
    Recursively parse a sitemap, handling sitemap indexes.
    
    Args:
        sitemap_url: URL of the sitemap to parse
        config: Sitemap configuration
        rate_limiter: Rate limiter
        visited: Set of already-visited sitemap URLs
        depth: Current recursion depth
        max_urls: Maximum URLs to return
    
    Returns:
        List of DiscoveredLink objects
    """
    if sitemap_url in visited:
        return []
    
    if depth > config.max_sitemap_depth:
        logger.warning(f"Max sitemap depth ({config.max_sitemap_depth}) reached at {sitemap_url}")
        return []
    
    visited.add(sitemap_url)
    host = extract_host(sitemap_url)
    
    # Fetch sitemap
    try:
        rate_limiter.acquire(host)
        try:
            response = make_request(sitemap_url, timeout=30)
            if response.status_code != 200:
                return []
            content = response.content
        finally:
            rate_limiter.release(host)
    except Exception as e:
        logger.debug(f"Failed to fetch sitemap {sitemap_url}: {e}")
        return []
    
    # Handle gzipped content
    if sitemap_url.endswith(".gz") or _is_gzipped(content):
        try:
            content = gzip.decompress(content)
        except Exception as e:
            logger.debug(f"Failed to decompress gzipped sitemap: {e}")
            return []
    
    # Check size
    size_mb = len(content) / (1024 * 1024)
    if size_mb > config.max_sitemap_size_mb:
        logger.warning(f"Sitemap {sitemap_url} is {size_mb:.1f}MB, using streaming mode")
    
    # Parse XML securely (prevent XXE attacks)
    try:
        # Disable external entity processing to prevent XXE
        parser = ET.XMLParser()
        parser.entity = {}  # Disable entity expansion
        parser.parser.SetParamEntityParsing(0)  # Disable parameter entities
        root = ET.fromstring(content, parser=parser)
    except (ET.ParseError, AttributeError) as e:
        # AttributeError can occur if parser doesn't support security features
        # Fall back to basic parsing for sitemaps (low risk as we control the source)
        try:
            root = ET.fromstring(content)
        except ET.ParseError as parse_err:
            logger.debug(f"Failed to parse sitemap XML: {parse_err}")
            return []
    
    links: List[DiscoveredLink] = []
    
    # Check if this is a sitemap index
    if root.tag.endswith("sitemapindex"):
        # Parse sitemap index
        for sitemap_elem in root.findall(".//sm:sitemap/sm:loc", SITEMAP_NS):
            if len(links) >= max_urls:
                break
            
            child_url = sitemap_elem.text.strip() if sitemap_elem.text else None
            if child_url:
                child_links = _parse_sitemap_recursive(
                    child_url,
                    config=config,
                    rate_limiter=rate_limiter,
                    visited=visited,
                    depth=depth + 1,
                    max_urls=max_urls - len(links),
                )
                links.extend(child_links)
    else:
        # Parse regular sitemap
        for url_elem in root.findall(".//sm:url", SITEMAP_NS):
            if len(links) >= max_urls:
                logger.debug(f"Reached max URLs ({max_urls}) in sitemap")
                break
            
            loc = url_elem.find("sm:loc", SITEMAP_NS)
            if loc is None or not loc.text:
                continue
            
            url = loc.text.strip()
            
            # Get optional metadata
            priority_elem = url_elem.find("sm:priority", SITEMAP_NS)
            priority = float(priority_elem.text) if priority_elem is not None and priority_elem.text else None
            
            lastmod_elem = url_elem.find("sm:lastmod", SITEMAP_NS)
            lastmod = lastmod_elem.text.strip() if lastmod_elem is not None and lastmod_elem.text else None
            
            links.append(DiscoveredLink(
                url=url,
                source="sitemap",
                sitemap_priority=priority,
                sitemap_lastmod=lastmod,
            ))
    
    return links


def _is_gzipped(content: bytes) -> bool:
    """Check if content is gzipped by magic bytes."""
    return len(content) >= 2 and content[:2] == b"\x1f\x8b"



# =============================================================================
# Common URL Guessing
# =============================================================================

def guess_common_urls(base_url: str) -> List[DiscoveredLink]:
    """
    Generate common business page URLs based on patterns.
    
    Uses COMMON_PAGE_PATTERNS (60+ patterns) to generate URLs
    that commonly exist on business websites.
    
    Args:
        base_url: Base URL of the website (e.g., "https://example.com")
    
    Returns:
        List of DiscoveredLink objects for guessed URLs
    """
    # Normalize base URL
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    
    links = []
    for pattern in COMMON_PAGE_PATTERNS:
        url = urljoin(base, pattern)
        links.append(DiscoveredLink(
            url=url,
            source="guess",
        ))
    
    return links


def verify_urls_exist(
    links: List[DiscoveredLink],
    rate_limiter: Optional[RateLimiter] = None,
    max_concurrent: int = 10,
    timeout_per_url: float = 3.0,
) -> List[DiscoveredLink]:
    """
    Verify which URLs actually exist using HEAD requests.
    
    Uses concurrent requests for speed.
    
    Args:
        links: List of DiscoveredLink objects to verify
        rate_limiter: Rate limiter for requests
        max_concurrent: Maximum concurrent verifications
        timeout_per_url: Timeout per HEAD request
    
    Returns:
        List of DiscoveredLink objects that exist (200/301/302)
    """
    import concurrent.futures
    
    if not links:
        return []
    
    rate_limiter = rate_limiter or NoOpRateLimiter()
    verified = []
    
    def check_url(link: DiscoveredLink) -> Optional[DiscoveredLink]:
        host = extract_host(link.url)
        try:
            rate_limiter.acquire(host)
            try:
                if head_exists(link.url, timeout=timeout_per_url):
                    return link
            finally:
                rate_limiter.release(host)
        except Exception as e:
            logger.debug(f"Failed to verify {link.url}: {e}")
        return None
    
    # Use thread pool for concurrent verification
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {executor.submit(check_url, link): link for link in links}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                verified.append(result)
    
    return verified


# =============================================================================
# HTML Link Extraction (2026 - handles JS-heavy SPAs)
# =============================================================================

# Patterns for links we want to extract
LINK_INCLUDE_PATTERNS = [
    r"/about",
    r"/company",
    r"/team",
    r"/leadership",
    r"/investor",
    r"/product",
    r"/service",
    r"/solution",
    r"/customer",
    r"/case-stud",
    r"/news",
    r"/press",
    r"/blog",
    r"/career",
    r"/contact",
]

# Patterns for links we want to exclude
LINK_EXCLUDE_PATTERNS = [
    r"\.pdf$",
    r"\.jpg$",
    r"\.png$",
    r"\.gif$",
    r"\.css$",
    r"\.js$",
    r"/login",
    r"/signin",
    r"/signup",
    r"/register",
    r"/cart",
    r"/checkout",
    r"/account",
    r"/search\?",
    r"^#",  # Only exclude pure fragment links, not URLs with fragments
    r"^javascript:",
    r"^mailto:",
    r"^tel:",
    r"^data:",
    r"^blob:",
]

# Patterns that look like internal paths (for JS extraction)
PATH_LIKE_PATTERNS = [
    r'^/[a-z][a-z0-9-]*(?:/[a-z0-9-]+)*/?$',  # /about, /products/cloud, etc.
]


def extract_links_from_html(
    html_content: bytes,
    base_url: str,
    same_domain_only: bool = True,
) -> List[DiscoveredLink]:
    """
    Extract links from HTML content - handles modern JS-heavy SPAs.
    
    2026 Reality: Most sites use Angular/Vue/React with JS-based navigation.
    Traditional <a href> extraction misses most links. This function extracts:
    
    1. Traditional <a href="..."> links
    2. Angular: ng-href, routerLink, [routerLink]
    3. Vue: :href, :to, router-link
    4. React: to= (React Router)
    5. Generic: data-href, data-url, data-link attributes
    6. Path strings in JavaScript (e.g., '/about', '/products/cloud')
    
    Args:
        html_content: Raw HTML bytes (should be from JS-rendered page)
        base_url: Base URL for resolving relative links
        same_domain_only: Only return links on the same domain
    
    Returns:
        List of DiscoveredLink objects
    """
    try:
        text = html_content.decode("utf-8", errors="ignore")
    except Exception:
        return []
    
    links = []
    seen_urls: Set[str] = set()
    
    def add_link(href: str, anchor_text: str = "", source_type: str = "html") -> None:
        """Helper to add a link with deduplication and validation."""
        if not href or len(href) < 2:
            return
        
        href = href.strip()
        
        # Skip excluded patterns
        if any(re.search(p, href, re.IGNORECASE) for p in LINK_EXCLUDE_PATTERNS):
            return
        
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        
        # Validate it's a proper HTTP URL
        parsed = urlparse(full_url)
        if parsed.scheme not in ("http", "https"):
            return
        if not parsed.netloc:
            return
        
        # Normalize URL (remove fragments, normalize path)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        
        # Remove trailing slash for consistency (except root)
        if normalized.endswith("/") and parsed.path != "/":
            normalized = normalized.rstrip("/")
        
        # Skip if already seen
        if normalized in seen_urls:
            return
        seen_urls.add(normalized)
        
        # Check same domain
        if same_domain_only and not is_same_domain(base_url, full_url):
            return
        
        links.append(DiscoveredLink(
            url=normalized,
            source=source_type,
            anchor_text=anchor_text if anchor_text else None,
        ))
    
    # ==========================================================================
    # 1. Traditional <a href="..."> links
    # ==========================================================================
    href_pattern = r'<a\s[^>]*href=["\']([^"\']+)["\']'
    full_pattern = r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    
    # Extract hrefs
    hrefs_found = set()
    for match in re.finditer(href_pattern, text, re.IGNORECASE | re.DOTALL):
        hrefs_found.add(match.group(1).strip())
    
    # Try to get anchor text
    href_to_text = {}
    for match in re.finditer(full_pattern, text, re.IGNORECASE | re.DOTALL):
        href = match.group(1).strip()
        anchor_text = re.sub(r'<[^>]+>', ' ', match.group(2)).strip()
        anchor_text = re.sub(r'\s+', ' ', anchor_text)
        if anchor_text and len(anchor_text) < 200:
            href_to_text[href] = anchor_text
    
    for href in hrefs_found:
        add_link(href, href_to_text.get(href, ""), "html")
    
    # ==========================================================================
    # 2. Angular links: ng-href, routerLink, [routerLink]
    # ==========================================================================
    angular_patterns = [
        r'ng-href=["\']([^"\']+)["\']',
        r'routerLink=["\']([^"\']+)["\']',
        r'\[routerLink\]=["\']([^"\']+)["\']',
        r'\[routerLink\]=["\']\[([^\]]+)\]["\']',  # [routerLink]="['/path']"
    ]
    for pattern in angular_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            href = match.group(1).strip()
            # Handle array syntax: ['/path', 'subpath'] -> /path/subpath
            if href.startswith("'") or href.startswith("/"):
                href = href.strip("'\"")
                add_link(href, "", "angular")
    
    # ==========================================================================
    # 3. Vue links: :href, :to, router-link, nuxt-link
    # ==========================================================================
    vue_patterns = [
        r':href=["\']([^"\']+)["\']',
        r':to=["\']([^"\']+)["\']',
        r'<router-link[^>]*to=["\']([^"\']+)["\']',
        r'<nuxt-link[^>]*to=["\']([^"\']+)["\']',
    ]
    for pattern in vue_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            href = match.group(1).strip()
            if not href.startswith("{"):  # Skip object bindings
                add_link(href, "", "vue")
    
    # ==========================================================================
    # 4. React Router: to= attribute (on Link components)
    # ==========================================================================
    react_patterns = [
        r'<Link[^>]*to=["\']([^"\']+)["\']',
        r'<NavLink[^>]*to=["\']([^"\']+)["\']',
    ]
    for pattern in react_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            add_link(match.group(1).strip(), "", "react")
    
    # ==========================================================================
    # 5. Generic data attributes: data-href, data-url, data-link, data-path
    # ==========================================================================
    data_patterns = [
        r'data-href=["\']([^"\']+)["\']',
        r'data-url=["\']([^"\']+)["\']',
        r'data-link=["\']([^"\']+)["\']',
        r'data-path=["\']([^"\']+)["\']',
        r'data-navigate=["\']([^"\']+)["\']',
    ]
    for pattern in data_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            add_link(match.group(1).strip(), "", "data-attr")
    
    # ==========================================================================
    # 6. JavaScript path strings (common in SPAs)
    # Look for quoted strings that look like internal paths
    # ==========================================================================
    # Match strings like '/about', '/products/cloud', '/company/leadership'
    # Be conservative - only match clean path patterns
    js_path_pattern = r'["\'](/[a-zA-Z][a-zA-Z0-9-]*(?:/[a-zA-Z0-9-]+)*/?)["\']'
    
    for match in re.finditer(js_path_pattern, text):
        path = match.group(1).strip()
        # Skip if it looks like a file path or API endpoint
        if any(ext in path.lower() for ext in ['.js', '.css', '.json', '.xml', '.svg', '.ico', '/api/', '/_', '/static/']):
            continue
        # Skip very short paths (likely not navigation)
        if len(path) < 3:
            continue
        add_link(path, "", "js-path")
    
    # ==========================================================================
    # 7. onclick/ng-click handlers with navigation (best effort)
    # ==========================================================================
    onclick_patterns = [
        r'onclick=["\'][^"\']*(?:location\.href|window\.location|navigate)\s*[=\(]\s*["\']([^"\']+)["\']',
        r'ng-click=["\'][^"\']*(?:go|navigate|route)\s*\(\s*["\']([^"\']+)["\']',
    ]
    for pattern in onclick_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            add_link(match.group(1).strip(), "", "onclick")
    
    # ==========================================================================
    # 8. href on non-anchor elements (buttons, divs with href)
    # ==========================================================================
    non_anchor_href = r'<(?!a\s)[^>]+href=["\']([^"\']+)["\']'
    for match in re.finditer(non_anchor_href, text, re.IGNORECASE):
        add_link(match.group(1).strip(), "", "non-anchor")
    
    logger.debug(f"Extracted {len(links)} links from HTML ({len(hrefs_found)} traditional, {len(links) - len(hrefs_found)} from JS/SPA patterns)")
    
    return links


# =============================================================================
# Heuristic Scoring (fallback when LLM unavailable)
# =============================================================================

# Keywords that indicate high-value pages for business research
HIGH_VALUE_KEYWORDS = [
    "about", "company", "leadership", "team", "management", "board",
    "investor", "financial", "annual-report", "earnings",
    "product", "service", "solution", "platform",
    "customer", "case-study", "success",
    "news", "press", "announcement",
]

# Keywords that indicate lower-value pages
LOW_VALUE_KEYWORDS = [
    "privacy", "terms", "legal", "cookie", "gdpr",
    "login", "signin", "signup", "register",
    "cart", "checkout", "account",
    "search", "tag", "category", "archive",
]


def score_links_heuristically(links: List[DiscoveredLink]) -> List[DiscoveredLink]:
    """
    Score links based on URL patterns, anchor text, and sitemap priority.
    
    Higher scores indicate more valuable pages for business research.
    
    Args:
        links: List of DiscoveredLink objects to score
    
    Returns:
        Same list with score field populated, sorted by score descending
    """
    for link in links:
        score = 0.0
        url_lower = link.url.lower()
        
        # URL pattern scoring
        for keyword in HIGH_VALUE_KEYWORDS:
            if keyword in url_lower:
                score += 10.0
        
        for keyword in LOW_VALUE_KEYWORDS:
            if keyword in url_lower:
                score -= 5.0
        
        # Anchor text scoring
        if link.anchor_text:
            anchor_lower = link.anchor_text.lower()
            for keyword in HIGH_VALUE_KEYWORDS:
                if keyword in anchor_lower:
                    score += 5.0
        
        # Sitemap priority scoring (0.0 to 1.0 -> 0 to 10 points)
        if link.sitemap_priority is not None:
            score += link.sitemap_priority * 10.0
        
        # Source scoring
        if link.source == "sitemap":
            score += 2.0  # Sitemap links are usually important
        elif link.source == "homepage":
            score += 3.0  # Homepage links are prominent
        
        # URL depth penalty (deeper = less important)
        path_depth = link.url.count("/") - 3  # Subtract scheme://host/
        if path_depth > 2:
            score -= (path_depth - 2) * 1.0
        
        link.score = score
    
    # Sort by score descending
    return sorted(links, key=lambda x: x.score, reverse=True)


# =============================================================================
# Homepage Link Extraction
# =============================================================================

def extract_links_from_homepage(
    base_url: str,
    rate_limiter: Optional[RateLimiter] = None,
    homepage_html: Optional[bytes] = None,
) -> List[DiscoveredLink]:
    """
    Extract links from the homepage.
    
    Args:
        base_url: Base URL of the website
        rate_limiter: Rate limiter for requests (used if homepage_html not provided)
        homepage_html: Pre-fetched homepage HTML (from scraper with JS rendering)
    
    Returns:
        List of DiscoveredLink objects from homepage
    """
    html_content = homepage_html
    
    # If no pre-fetched content, try raw HTTP (fast path for simple sites)
    if html_content is None:
        rate_limiter = rate_limiter or NoOpRateLimiter()
        host = extract_host(base_url)
        
        try:
            rate_limiter.acquire(host)
            try:
                response = make_request(base_url, timeout=10)  # Shorter timeout
                if response.status_code == 200:
                    html_content = response.content
            finally:
                rate_limiter.release(host)
        except Exception as e:
            logger.debug(f"Failed to fetch homepage {base_url}: {e}")
    
    if not html_content:
        return []
    
    # Extract all links
    links = extract_links_from_html(html_content, base_url)
    
    # Mark as homepage source
    for link in links:
        link.source = "homepage"
    
    return links


# =============================================================================
# Combined Discovery
# =============================================================================

def discover_links(
    base_url: str,
    sitemap_config: Optional[SitemapConfig] = None,
    rate_limiter: Optional[RateLimiter] = None,
    verify_guessed: bool = False,
    min_links_to_skip_verify: int = 15,
    min_links_before_sitemap: int = 20,
    homepage_html: Optional[bytes] = None,
) -> List[DiscoveredLink]:
    """
    Discover links using all available strategies.
    
    Order (homepage-first, sitemap as fallback):
    1. Homepage link extraction (most current, JS-rendered if homepage_html provided)
    2. Common URL guessing (if < 20 links)
    3. Sitemap parsing (only if still < 20 links - often stale)
    
    Results are deduplicated and scored.
    
    Args:
        base_url: Base URL of the website
        sitemap_config: Configuration for sitemap parsing
        rate_limiter: Rate limiter for requests
        verify_guessed: Whether to verify guessed URLs exist (slow - 60+ HEAD requests)
        min_links_to_skip_verify: Skip URL verification if we already have this many links
        min_links_before_sitemap: Only check sitemap if we have fewer than this many links
        homepage_html: Pre-fetched homepage HTML (from scraper with JS rendering)
    
    Returns:
        List of DiscoveredLink objects, scored and sorted
    """
    all_links: List[DiscoveredLink] = []
    seen_urls: Set[str] = set()
    
    def add_links(links: List[DiscoveredLink]) -> None:
        for link in links:
            if link.url not in seen_urls:
                seen_urls.add(link.url)
                all_links.append(link)
    
    # 1. Homepage links FIRST (most current, handles JS-heavy sites if homepage_html provided)
    logger.debug(f"Extracting links from homepage")
    homepage_links = extract_links_from_homepage(base_url, rate_limiter, homepage_html)
    add_links(homepage_links)
    if homepage_links:
        logger.debug(f"Found {len(homepage_links)} links from homepage")
    else:
        logger.debug(f"No links extracted from homepage")
    
    # 2. Guessed URLs - only if we have few links
    if len(all_links) < min_links_before_sitemap:
        guessed_links = guess_common_urls(base_url)
        
        if verify_guessed and len(all_links) < min_links_to_skip_verify:
            logger.debug(f"Verifying {len(guessed_links)} common URL patterns")
            guessed_links = verify_urls_exist(guessed_links, rate_limiter)
            logger.debug(f"Found {len(guessed_links)} verified URLs")
        elif verify_guessed:
            logger.debug(f"Skipping URL verification - already have {len(all_links)} links")
            guessed_links = []  # Don't add unverified guesses
        
        add_links(guessed_links)
    
    # 3. Sitemap as FALLBACK - only if we still have few links
    if len(all_links) < min_links_before_sitemap:
        logger.debug(f"Checking sitemap for {base_url} (fallback)")
        sitemap_links = fetch_sitemap_links(base_url, sitemap_config, rate_limiter)
        add_links(sitemap_links)
        if sitemap_links:
            logger.debug(f"Found {len(sitemap_links)} links from sitemap")
        else:
            logger.debug(f"No sitemap found for {base_url}")
    else:
        logger.debug(f"Skipping sitemap - already have {len(all_links)} links from homepage")
    
    # Score and sort
    logger.debug(f"Scoring {len(all_links)} total links")
    scored_links = score_links_heuristically(all_links)
    
    logger.debug(f"Discovered {len(scored_links)} total links for {base_url}")
    return scored_links
