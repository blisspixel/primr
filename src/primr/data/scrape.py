"""
Web Scraper - Refactored to use new modular scraping architecture.

This module provides the high-level scraping API used by the rest of Primr.
It wraps the new modular scraping system in primr.data.scraping.
"""

import logging
import random
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from primr.config.config import PROJECT_ROOT
from primr.utils.console import console
from primr.utils.logging_config import get_logger

# Import from new modular scraping system
from primr.data.scraping import (
    ScrapeOrchestrator,
    ScrapeCache,
    ScrapeResult,
    RateLimiter,
    RateLimitConfig,
    TraceLogger,
    discover_links,
    score_links_heuristically,
    DiscoveredLink,
    normalize_url as normalize_url_new,
)

logger = get_logger("scrape")

# =============================================================================
# Console Output Helpers
# =============================================================================

def out_step(msg):
    console.step(msg)

def out_ok(msg, show_time=True):
    console.ok(msg, show_time=show_time)

def out_warn(msg):
    console.warn(msg)

def out_err(msg):
    console.error(msg)

def out_info(msg):
    console.info(msg)

def out_progress(current, total, msg=""):
    console.progress(current, total, msg)

def out_progress_done():
    console.progress_done()


# =============================================================================
# Caching Setup
# =============================================================================

CACHE_DIR = Path(PROJECT_ROOT) / "logs" / "scrape_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Global orchestrator instance (lazy initialized)
_orchestrator: Optional[ScrapeOrchestrator] = None


def get_orchestrator(enable_vision: bool = False, use_cache: bool = False) -> ScrapeOrchestrator:
    """Get or create the global scrape orchestrator.
    
    Args:
        enable_vision: Enable vision tier for image-heavy pages
        use_cache: Use cached content (default: False for fresh data)
    """
    global _orchestrator
    
    if _orchestrator is None or (_orchestrator and enable_vision):
        _orchestrator = ScrapeOrchestrator(
            cache=ScrapeCache(cache_dir=str(CACHE_DIR)),
            rate_limiter=RateLimiter(RateLimitConfig()),
            enable_vision=enable_vision,
            max_page_time=30.0,  # Max 30s per page to avoid hanging on protected sites
            use_cache=use_cache,
        )
    
    return _orchestrator


# =============================================================================
# URL Utilities
# =============================================================================

def normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    if not url:
        return url
    return normalize_url_new(url)


def is_valid_url_string(s: str) -> bool:
    """Check if a string is a valid HTTP(S) URL."""
    try:
        parsed = urlparse(s)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except (ValueError, AttributeError):
        return False


def validate_url(url: str, base_url: str = None) -> Optional[str]:
    """Validate and normalize a URL."""
    if not isinstance(url, str) or len(url) < 5:
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url.lstrip('/')}"
    return url if "http" in url else None


# =============================================================================
# Main Scraping Functions
# =============================================================================

def scrape_page(
    url: str,
    silent: bool = False,
    pbar=None,
    use_vision: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """
    Scrape a single page using tiered approach.
    
    Args:
        url: URL to scrape
        silent: Suppress console output
        pbar: Progress bar (unused, kept for compatibility)
        use_vision: Enable vision tier for hard-to-scrape pages
    
    Returns:
        Tuple of (extracted_text, tier_name) or (None, error_reason)
    """
    orchestrator = get_orchestrator(enable_vision=use_vision)
    
    result = orchestrator.scrape_url(url)
    
    if result.success:
        return result.extracted_text, result.tier
    else:
        return None, result.error


def fetch_web_content(
    website: str,
    company_name: str,
    max_pages: Optional[int] = None,
    use_vision: bool = False,
) -> dict[str, str]:
    """
    Discover and scrape pages from a company website.
    
    Args:
        website: Base URL of the website
        company_name: Company name (for logging)
        max_pages: Maximum pages to scrape (default: no limit)
        use_vision: Enable vision tier for hard-to-scrape pages
    
    Returns:
        Dict mapping URL -> extracted text
    """
    out_step(f"Scraping {website}")
    
    # Discover links using new discovery module
    orchestrator = get_orchestrator(enable_vision=use_vision)
    
    try:
        discovered = discover_links(
            website,
            rate_limiter=orchestrator.rate_limiter,
            verify_guessed=True,
        )
    except Exception as e:
        logger.warning(f"Link discovery failed: {e}")
        out_warn(f"Link discovery failed, trying homepage only")
        discovered = [DiscoveredLink(url=website, source="fallback")]
    
    if not discovered:
        out_warn("No pages found, trying homepage only")
        discovered = [DiscoveredLink(url=website, source="fallback")]
    
    # Score and sort links
    scored_links = score_links_heuristically(discovered)
    
    total_found = len(scored_links)
    out_info(f"Found {total_found} pages to scrape")
    
    # Apply max_pages limit if specified
    if max_pages and max_pages < total_found:
        pages_to_scrape = [link.url for link in scored_links[:max_pages]]
        out_info(f"Limiting to top {max_pages} pages")
    else:
        pages_to_scrape = [link.url for link in scored_links]
    
    # Scrape pages
    scraped_content = {}
    success_count = 0
    total = len(pages_to_scrape)
    
    for i, page_url in enumerate(pages_to_scrape):
        normalized = normalize_url(page_url)
        if normalized in scraped_content:
            continue
        
        path = urlparse(page_url).path or "/"
        out_progress(i + 1, total, path[:40])
        
        # Small delay between requests
        time.sleep(random.uniform(0.3, 0.8))
        
        result = orchestrator.scrape_url(page_url)
        
        if result.success and result.extracted_text:
            scraped_content[normalized] = result.extracted_text
            success_count += 1
            logger.debug(f"Scraped {page_url} via {result.tier}")
        else:
            logger.debug(f"Failed to scrape {page_url}: {result.error}")
    
    out_progress_done()
    
    if success_count == total:
        out_ok(f"{success_count} pages scraped")
    elif success_count > 0:
        out_warn(f"{success_count}/{total} pages scraped")
    else:
        out_err("Could not scrape any pages")
    
    return scraped_content


def scrape_external_sources(
    search_results: list[dict],
    max_sources: int = 2,
    allowed_domains: Optional[list[str]] = None,
) -> dict[str, str]:
    """
    Scrape external sources from search results.
    
    Args:
        search_results: List of search result dicts with 'url' key
        max_sources: Maximum sources to scrape
        allowed_domains: Optional list of allowed domain substrings
    
    Returns:
        Dict mapping URL -> extracted text
    """
    orchestrator = get_orchestrator()
    scraped_sources = {}
    count = 0
    
    for result in search_results:
        url = result.get("url")
        if not url:
            continue
        
        # Filter by allowed domains if specified
        if allowed_domains:
            domain = urlparse(url).netloc.lower()
            if not any(allowed in domain for allowed in allowed_domains):
                continue
        
        scrape_result = orchestrator.scrape_url(url)
        
        if scrape_result.success and scrape_result.extracted_text:
            text = scrape_result.extracted_text.strip()
            if len(text) > 100:
                scraped_sources[url] = text
                count += 1
        
        if count >= max_sources:
            break
    
    return scraped_sources


def scrape_external_sources_validated(
    search_results: list[dict],
    company_name: str,
    website: str,
    max_sources: int = 2,
) -> dict[str, str]:
    """
    Scrape external sources with LLM validation to ensure they're about the right company.
    
    This prevents including content from similarly-named but unrelated companies
    (e.g., "EverTrue" fundraising software vs "EverTrue" senior living).
    
    The LLM is instructed to be DEFENSIVE - assume it's wrong unless clearly right.
    But it's also smart about mergers, subsidiaries, and name changes.
    
    Args:
        search_results: List of search result dicts with 'url' key
        company_name: Name of the target company
        website: Target company's website (for context)
        max_sources: Maximum validated sources to return
    
    Returns:
        Dict mapping URL -> extracted text (only for validated sources)
    """
    from primr.ai.llm import llm
    
    orchestrator = get_orchestrator()
    validated_sources = {}
    count = 0
    
    # Extract domain from website for context
    target_domain = urlparse(website).netloc.lower().replace("www.", "") if website else ""
    
    for result in search_results:
        url = result.get("url")
        title = result.get("title", "")
        if not url:
            continue
        
        # Skip if it's the company's own website
        source_domain = urlparse(url).netloc.lower()
        if target_domain and target_domain in source_domain:
            continue
        
        # Scrape the content
        scrape_result = orchestrator.scrape_url(url)
        
        if not scrape_result.success or not scrape_result.extracted_text:
            continue
        
        text = scrape_result.extracted_text.strip()
        if len(text) < 100:
            continue
        
        # Use LLM to validate this is about the RIGHT company
        # Use a small snippet to save tokens
        snippet = text[:2000]
        
        validation_prompt = f"""You are a fact-checker. Your job is to determine if this article is about a SPECIFIC company.

TARGET COMPANY:
- Name: {company_name}
- Website: {website}
- Domain: {target_domain}

ARTICLE TO CHECK:
- Title: {title}
- URL: {url}
- Content snippet:
{snippet}

CRITICAL RULES - BE DEFENSIVE:
1. ASSUME IT'S THE WRONG COMPANY unless you find clear evidence it's the right one
2. Many companies share similar names (e.g., "EverTrue" is both a fundraising software company AND a senior living company)
3. Look for SPECIFIC identifiers that match: website mentions, domain references, product names, leadership names, headquarters location
4. A company might be mentioned due to: merger, acquisition, subsidiary, parent company, or former name - these ARE valid matches
5. Generic industry news that doesn't specifically reference the target company = WRONG
6. If the article mentions a DIFFERENT website/domain than {target_domain} = WRONG

ANSWER FORMAT:
First line: YES or NO
Second line: Brief reason (one sentence)

Example good matches:
- Article mentions {target_domain} or {website}
- Article discusses specific products/services that match the target company
- Article names executives known to work at the target company
- Article about a merger/acquisition involving the target company

Example bad matches:
- Article about a different company with a similar name
- Article mentions a different website (e.g., evertrueliving.org instead of evertrue.com)
- Generic industry article that doesn't specifically identify the target company"""

        try:
            response = llm(validation_prompt, model_type="research", streaming=False).strip()
            lines = response.split('\n', 1)
            decision = lines[0].strip().upper()
            reason = lines[1].strip() if len(lines) > 1 else ""
            
            if decision.startswith("YES"):
                validated_sources[url] = text
                count += 1
                logger.info(f"External source VALIDATED: {url} - {reason}")
            else:
                logger.info(f"External source REJECTED (wrong company): {url} - {reason}")
                
        except Exception as e:
            logger.warning(f"Failed to validate external source {url}: {e}")
            # Skip on validation failure - better to miss a source than include wrong company
            continue
        
        if count >= max_sources:
            break
    
    return validated_sources


# =============================================================================
# Legacy Compatibility Exports
# =============================================================================

# Import the new tier functions (they return ScrapeResult with raw_content)
from primr.data.scraping import (
    scrape_with_requests as _scrape_with_requests_new,
    scrape_with_httpx as _scrape_with_httpx_new,
    scrape_with_curl_cffi as _scrape_with_curl_cffi_new,
    scrape_with_playwright as _scrape_with_playwright_new,
    scrape_with_playwright_aggressive as _scrape_with_playwright_aggressive_new,
    scrape_with_drissionpage as _scrape_with_drissionpage_new,
    scrape_with_drissionpage_stealth as _scrape_with_drissionpage_stealth_new,
    scrape_with_vision as _scrape_with_vision_new,
    extract_clean_text as _extract_text,
)


def _wrap_tier_function(tier_fn):
    """Wrap a new-style tier function to return old-style tuple with extracted text."""
    def wrapper(url: str, timeout: int = 30) -> tuple[Optional[str], Optional[str]]:
        result = tier_fn(url, timeout)
        if result.success and result.raw_content:
            # Extract text from raw content
            text = _extract_text(result.raw_content)
            if text:
                return text, None
            else:
                return None, "Failed to extract text"
        elif result.success and result.extracted_text:
            # Vision tier returns extracted_text directly
            return result.extracted_text, None
        else:
            return None, result.error
    return wrapper


# Wrapped tier functions that return tuple[str | None, str | None]
scrape_with_requests = _wrap_tier_function(_scrape_with_requests_new)
scrape_with_httpx = _wrap_tier_function(_scrape_with_httpx_new)
scrape_with_curl_cffi = _wrap_tier_function(_scrape_with_curl_cffi_new)
scrape_with_playwright = _wrap_tier_function(_scrape_with_playwright_new)
scrape_with_playwright_aggressive = _wrap_tier_function(_scrape_with_playwright_aggressive_new)
scrape_with_drissionpage = _wrap_tier_function(_scrape_with_drissionpage_new)
scrape_with_drissionpage_stealth = _wrap_tier_function(_scrape_with_drissionpage_stealth_new)
scrape_with_vision = _wrap_tier_function(_scrape_with_vision_new)

# Re-export detection functions (with signature adaptation)
from primr.data.scraping import (
    detect_soft_block as _detect_soft_block_new,
    check_success_signal,
)


def detect_soft_block(text: str, url: str = "") -> tuple[bool, Optional[str]]:
    """
    Detect if response is a soft block.
    
    Wrapper for new detection function that accepts bytes.
    """
    if not text:
        return True, "Empty response"
    
    # Convert string to bytes for new function
    raw_content = text.encode("utf-8", errors="ignore")
    return _detect_soft_block_new(raw_content, host=url)

# Re-export discovery functions (with signature adaptation)
from primr.data.scraping import (
    fetch_sitemap_links as _fetch_sitemap_links_new,
    guess_common_urls as _guess_common_urls_new,
    verify_urls_exist as _verify_urls_exist_new,
    extract_links_from_html as _extract_links_from_html_new,
)


def fetch_sitemap_links(base_url: str) -> set[str]:
    """Fetch links from sitemap."""
    links = _fetch_sitemap_links_new(base_url)
    return {link.url for link in links}


def guess_common_urls(base_url: str) -> set[str]:
    """Generate common business page URLs."""
    links = _guess_common_urls_new(base_url)
    return {link.url for link in links}


def verify_urls_exist(urls: set[str], timeout_per_url: float = 3.0) -> set[str]:
    """Verify which URLs exist."""
    from primr.data.scraping import DiscoveredLink
    links = [DiscoveredLink(url=url, source="verify") for url in urls]
    verified = _verify_urls_exist_new(links)
    return {link.url for link in verified}


def extract_links_from_html(html_content: str, base_url: str) -> set[str]:
    """Extract links from HTML content."""
    # Convert string to bytes
    if isinstance(html_content, str):
        html_bytes = html_content.encode("utf-8", errors="ignore")
    else:
        html_bytes = html_content
    links = _extract_links_from_html_new(html_bytes, base_url)
    return {link.url for link in links}


# Re-export extract_links_from_homepage
from primr.data.scraping import (
    extract_links_from_homepage as _extract_links_from_homepage_new,
)


def extract_links_from_homepage(base_url: str, company_name: str = "") -> list[str]:
    """Extract links from homepage."""
    links = _extract_links_from_homepage_new(base_url)
    return [link.url for link in links]

# Re-export cache functions
from primr.data.scraping import (
    ScrapeCache,
    LRUCache,
)


def get_cached_content(url: str) -> Optional[str]:
    """Get cached content for a URL."""
    orchestrator = get_orchestrator()
    cached = orchestrator.cache.get_extracted(url)
    return cached


def cache_content(url: str, content: str) -> None:
    """Cache content for a URL."""
    orchestrator = get_orchestrator()
    orchestrator.cache.set_extracted(url, content)


def clear_cache(max_age_hours: Optional[float] = None) -> None:
    """Clear the scrape cache (both memory and disk)."""
    global _orchestrator
    if _orchestrator:
        _orchestrator.cache.clear_all()
    else:
        # Clear disk cache even if orchestrator not initialized
        cache = ScrapeCache(cache_dir=str(CACHE_DIR))
        cache.clear_all()


# =============================================================================
# Cleanup
# =============================================================================

def cleanup_browser():
    """Clean up browser resources."""
    # The new architecture handles cleanup automatically
    pass


# Register cleanup (no-op for now, new arch handles it)
import atexit
atexit.register(cleanup_browser)


# =============================================================================
# Additional Legacy Exports (for test compatibility)
# =============================================================================

from primr.config.config import EXCLUDED_SITES
from primr.utils.files import get_cache_key

# Re-export from new modules
from primr.data.scraping import WAF_SIGNATURES
from primr.data.scraping.profiles import HTTP_PROFILES

# Legacy names
SOFT_BLOCK_INDICATORS = [sig[0] for sig in WAF_SIGNATURES]
USER_AGENTS = [p.user_agent for p in HTTP_PROFILES]

# Global cache reference for tests
_SCRAPE_CACHE = LRUCache(max_size=100)


def is_excluded_site(url: str) -> bool:
    """Check if URL is in excluded sites list."""
    return any(excluded in url.lower() for excluded in EXCLUDED_SITES)


# Re-export COMMON_PAGE_PATTERNS
from primr.data.scraping import COMMON_PAGE_PATTERNS


def detect_waf_block(html_content: str) -> tuple[bool, str]:
    """
    Detect if we're seeing a WAF/bot protection page.
    
    Wrapper for new detection function.
    """
    if not html_content:
        return True, "Empty response"
    
    raw_content = html_content.encode("utf-8", errors="ignore")
    is_blocked, reason = _detect_soft_block_new(raw_content)
    return is_blocked, reason or ""


def extract_clean_text(soup_or_bytes):
    """Extract clean text from BeautifulSoup object or bytes."""
    if hasattr(soup_or_bytes, 'get_text'):
        # It's a BeautifulSoup object
        from bs4 import BeautifulSoup
        for tag in soup_or_bytes(["script", "style", "noscript", "meta", "header", "footer",
                         "form", "aside", "nav", "iframe", "svg", "canvas"]):
            tag.extract()
        text = soup_or_bytes.get_text(separator="\n")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        cleaned = []
        prev_line = None
        for line in lines:
            if line != prev_line:
                cleaned.append(line)
                prev_line = line
        return "\n".join(cleaned)
    else:
        # It's bytes, use new function
        return _extract_text(soup_or_bytes)
