"""
Structured Content Extraction

A formalized extraction pipeline that produces structured output with quality metrics.
Designed for downstream LLM summarization and semantic search.

Output Contract (what "good output" means):
{
    "url": "...",
    "final_url": "...",
    "title": "...",
    "meta_description": "...",
    "lang": "en",
    "published_date": "...",
    "byline": "...",
    "blocks": [
        {"type": "h1", "text": "..."},
        {"type": "p", "text": "..."},
        {"type": "li", "text": "...", "list_type": "ul"},
        {"type": "quote", "text": "...", "attribution": "..."},
    ],
    "text": "...",           # Clean, human-readable (boilerplate removed)
    "raw_text": "...",       # Before boilerplate cleanup
    "metrics": {
        "char_count": 12345,
        "word_count": 2000,
        "link_density": 0.04,
        "boilerplate_ratio": 0.12,
        "dup_line_ratio": 0.03,
        "heading_count": 11,
        "paragraph_count": 25,
        "list_item_count": 15,
    },
    "quality": {
        "score": 0.87,       # 0-1, higher is better
        "flags": ["cta_removed", "high_link_density_blocks_removed"],
    }
}

Multi-pass Pipeline:
1. DOM Sanitization - Remove obvious non-content (nav, footer, modals, etc.)
2. Main Content Selection - Score containers, pick best one
3. Structured Extraction - Walk container, emit typed blocks
4. Boilerplate Filtering - Link density + repetition + cross-page fingerprinting
5. Quality Scoring - Compute metrics and flags
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional
from bs4 import BeautifulSoup, NavigableString, Tag


# =============================================================================
# PASS A: DOM SANITIZATION CONFIGURATION
# =============================================================================

# Tags to always remove (noise)
REMOVE_TAGS = [
    "script", "style", "noscript", "meta", "link", "svg", "canvas", "iframe",
    "template", "picture", "source", "video", "audio", "object", "embed",
]

# Layout regions to remove by tag
LAYOUT_REMOVE_TAGS = ["header", "footer", "nav", "aside", "form"]

# Class/ID patterns that indicate layout regions to remove (case-insensitive)
# These are generic patterns that work across sites
# IMPORTANT: Be careful not to match content containers (e.g., "widget" matches Elementor content)
LAYOUT_REMOVE_PATTERNS = [
    # Navigation - be specific to avoid matching content
    r"\bnav\b", r"navbar", r"navigation", r"main-menu", r"site-menu", r"breadcrumb",
    # Header/Footer - match specific patterns
    r"site-header", r"site-footer", r"masthead", r"page-header", r"page-footer",
    # Sidebars - be specific
    r"sidebar", r"side-bar",
    # CTAs and banners
    r"\bcta\b", r"call-to-action", r"promo-banner", r"hero-banner",
    # Modals and popups
    r"\bmodal\b", r"\bpopup\b", r"\boverlay\b", r"lightbox", r"\bdialog\b", r"drawer",
    # Social and sharing
    r"social-share", r"share-buttons", r"follow-us",
    # Comments
    r"comment-section", r"comments-area", r"disqus",
    # Related content
    r"related-posts", r"recommended-posts",
    # Cookie/consent/GDPR
    r"cookie-banner", r"cookie-notice", r"consent-banner", r"gdpr-banner", r"privacy-banner",
    # Ads
    r"advertisement", r"ad-container", r"sponsor-content",
    # Login/signup/subscribe - be specific
    r"login-form", r"signup-form", r"newsletter-signup", r"subscribe-form",
    # Search
    r"search-form", r"search-box", r"site-search",
    # Back to top, pagination
    r"back-to-top", r"scroll-to-top",
]

# Compile patterns for efficiency
LAYOUT_REMOVE_RE = re.compile("|".join(LAYOUT_REMOVE_PATTERNS), re.IGNORECASE)

# Main content selectors (priority order for Pass B)
MAIN_CONTENT_SELECTORS = [
    "main",
    "article",
    "[role='main']",
    ".entry-content",
    ".post-content", 
    ".article-content",
    ".page-content",
    ".content-area",
    "#main-content",
    "#content",
    "#main",
    ".content",
]


# =============================================================================
# DATA MODELS (Output Contract)
# =============================================================================

@dataclass
class ContentBlock:
    """A single content block with type information."""
    type: str  # h1-h6, p, li, quote, cta
    text: str
    list_type: Optional[str] = None  # ul, ol (for li blocks)
    attribution: Optional[str] = None  # For quotes
    link_density: float = 0.0  # Ratio of link text to total text


@dataclass
class ExtractionMetrics:
    """Quality metrics for extracted content."""
    char_count: int = 0
    word_count: int = 0
    link_density: float = 0.0  # Overall link text / total text
    boilerplate_ratio: float = 0.0  # Removed / original
    dup_line_ratio: float = 0.0  # Duplicate lines / total lines
    heading_count: int = 0
    paragraph_count: int = 0
    list_item_count: int = 0
    quote_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            "char_count": self.char_count,
            "word_count": self.word_count,
            "link_density": round(self.link_density, 3),
            "boilerplate_ratio": round(self.boilerplate_ratio, 3),
            "dup_line_ratio": round(self.dup_line_ratio, 3),
            "heading_count": self.heading_count,
            "paragraph_count": self.paragraph_count,
            "list_item_count": self.list_item_count,
            "quote_count": self.quote_count,
        }


@dataclass
class QualityScore:
    """Quality assessment with score and flags."""
    score: float = 0.0  # 0-1, higher is better
    flags: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "flags": self.flags,
        }


@dataclass 
class StructuredContent:
    """Full structured content from a page - the output contract."""
    url: str
    final_url: Optional[str] = None
    title: Optional[str] = None
    meta_description: Optional[str] = None
    lang: Optional[str] = None
    published_date: Optional[str] = None
    byline: Optional[str] = None
    blocks: list = field(default_factory=list)
    text: str = ""  # Clean, human-readable
    raw_text: str = ""  # Before boilerplate cleanup
    metrics: ExtractionMetrics = field(default_factory=ExtractionMetrics)
    quality: QualityScore = field(default_factory=QualityScore)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "url": self.url,
            "final_url": self.final_url,
            "title": self.title,
            "meta_description": self.meta_description,
            "lang": self.lang,
            "published_date": self.published_date,
            "byline": self.byline,
            "blocks": [
                {k: v for k, v in {
                    "type": b.type,
                    "text": b.text,
                    "list_type": b.list_type,
                    "attribution": b.attribution,
                }.items() if v is not None}
                for b in self.blocks
            ],
            "text": self.text,
            "raw_text": self.raw_text,
            "metrics": self.metrics.to_dict(),
            "quality": self.quality.to_dict(),
        }
    
    def to_plain_text(self, include_cta: bool = False) -> str:
        """Convert to plain text, optionally excluding CTAs."""
        lines = []
        
        if self.title:
            lines.append(f"# {self.title}")
            lines.append("")
        
        for block in self.blocks:
            if block.type == "cta" and not include_cta:
                continue
            
            if block.type == "quote":
                lines.append(f"> {block.text}")
                if block.attribution:
                    lines.append(f"  — {block.attribution}")
            elif block.type == "li":
                bullet = "-" if block.list_type == "ul" else "•"
                lines.append(f"  {bullet} {block.text}")
            elif block.type.startswith("h"):
                level = int(block.type[1]) if len(block.type) > 1 else 2
                prefix = "#" * level
                lines.append("")
                lines.append(f"{prefix} {block.text}")
            else:
                lines.append(block.text)
            
            # Add spacing after paragraphs
            if block.type == "p":
                lines.append("")
        
        return "\n".join(lines)


# =============================================================================
# BOILERPLATE FILTER (Cross-page fingerprinting)
# =============================================================================

@dataclass
class BoilerplateFilter:
    """
    Learns and removes boilerplate text across multiple pages.
    
    Uses three generic strategies:
    1. Cross-page fingerprinting (lines appearing in >X% of pages)
    2. Within-page repetition (duplicate lines)
    3. Link density filtering (blocks with >50% link text)
    """
    
    line_counts: Counter = field(default_factory=Counter)
    page_count: int = 0
    boilerplate_lines: set = field(default_factory=set)
    allowlist: set = field(default_factory=set)  # Lines to never remove
    
    def normalize_line(self, line: str) -> str:
        """Normalize line for comparison."""
        line = line.lower()
        line = re.sub(r"[^\w\s]", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        return line
    
    def add_page(self, text: str) -> None:
        """Add a page's text to learn boilerplate."""
        self.page_count += 1
        seen_on_page = set()
        
        for line in text.split("\n"):
            normalized = self.normalize_line(line)
            if normalized and len(normalized) > 5 and normalized not in seen_on_page:
                seen_on_page.add(normalized)
                self.line_counts[normalized] += 1
    
    def compute_boilerplate(self, threshold: float = 0.3) -> set:
        """Compute boilerplate lines appearing in >threshold of pages."""
        if self.page_count < 2:
            return set()
        
        min_occurrences = max(2, int(self.page_count * threshold))
        
        self.boilerplate_lines = {
            line for line, count in self.line_counts.items()
            if count >= min_occurrences and line not in self.allowlist
        }
        
        return self.boilerplate_lines
    
    def remove_boilerplate(self, text: str) -> tuple[str, float]:
        """
        Remove boilerplate lines from text.
        
        Returns:
            (cleaned_text, boilerplate_ratio)
        """
        if not self.boilerplate_lines:
            return text, 0.0
        
        original_lines = text.split("\n")
        clean_lines = []
        removed_count = 0
        
        for line in original_lines:
            normalized = self.normalize_line(line)
            if normalized in self.boilerplate_lines:
                removed_count += 1
            else:
                clean_lines.append(line)
        
        ratio = removed_count / max(len(original_lines), 1)
        return "\n".join(clean_lines), ratio
    
    def get_boilerplate_examples(self, limit: int = 20) -> list:
        """Get examples of detected boilerplate for debugging."""
        return sorted(
            [(line, self.line_counts[line]) for line in self.boilerplate_lines],
            key=lambda x: -x[1]
        )[:limit]


# =============================================================================
# PASS A: DOM SANITIZATION
# =============================================================================

def prune_dom(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Pass A: Aggressively prune DOM to remove layout regions.
    
    Removes by tag type AND by class/id keyword patterns.
    This is critical - do it BEFORE text extraction.
    """
    # Remove noise tags
    for tag in REMOVE_TAGS:
        for element in soup.find_all(tag):
            element.decompose()
    
    # Remove layout tags
    for tag in LAYOUT_REMOVE_TAGS:
        for element in soup.find_all(tag):
            element.decompose()
    
    # Collect elements to remove (don't modify during iteration)
    to_remove = []
    for element in soup.find_all(True):
        if element is None or not hasattr(element, 'get'):
            continue
        
        try:
            classes = element.get("class", []) or []
            element_id = element.get("id", "") or ""
            role = element.get("role", "") or ""
            
            attrs = " ".join(classes) + " " + element_id + " " + role
            
            if LAYOUT_REMOVE_RE.search(attrs):
                to_remove.append(element)
        except (AttributeError, TypeError):
            continue
    
    # Now remove them
    for element in to_remove:
        try:
            element.decompose()
        except Exception:
            pass
    
    return soup


# =============================================================================
# PASS B: MAIN CONTENT SELECTION (Container Scoring)
# =============================================================================

def compute_link_density(element: Tag) -> float:
    """Compute ratio of link text to total text."""
    if not element:
        return 0.0
    
    total_text = element.get_text(strip=True)
    if not total_text:
        return 0.0
    
    link_text = ""
    for a in element.find_all("a"):
        link_text += a.get_text(strip=True)
    
    return len(link_text) / len(total_text)


def score_container(element: Tag) -> float:
    """
    Score a container for main content likelihood.
    
    Higher score = more likely to be main content.
    """
    if not element:
        return 0
    
    text = element.get_text(strip=True)
    text_len = len(text)
    
    if text_len < 100:
        return 0
    
    # Positive signals
    paragraphs = len(element.find_all("p"))
    lists = len(element.find_all(["ul", "ol"]))
    headings = len(element.find_all(["h1", "h2", "h3", "h4"]))
    
    score = text_len + (paragraphs * 50) + (lists * 30) + (headings * 40)
    
    # Negative signals
    links = len(element.find_all("a"))
    buttons = len(element.find_all("button"))
    forms = len(element.find_all("form"))
    
    score -= (links * 5) + (buttons * 20) + (forms * 50)
    
    # Link density penalty (nav-heavy blocks)
    link_density = compute_link_density(element)
    if link_density > 0.5:
        score *= 0.3
    elif link_density > 0.3:
        score *= 0.6
    
    # Check for "navish" keywords in classes
    classes = " ".join(element.get("class", []) or []).lower()
    if any(kw in classes for kw in ["nav", "menu", "sidebar", "footer", "header"]):
        score *= 0.2
    
    return max(0, score)


def find_main_content(soup: BeautifulSoup) -> Tag:
    """
    Pass B: Find the main content container using scoring.
    """
    # Try semantic selectors first
    for selector in MAIN_CONTENT_SELECTORS:
        element = soup.select_one(selector)
        if element and len(element.get_text(strip=True)) > 200:
            return element
    
    # Fall back to container scoring
    best_element = None
    best_score = 0
    
    for element in soup.find_all(["div", "section", "article", "main"]):
        score = score_container(element)
        if score > best_score:
            best_score = score
            best_element = element
    
    return best_element or soup.find("body") or soup


# =============================================================================
# CTA DETECTION (Generic, not phrase-based)
# =============================================================================

# CTA patterns - but we also use link density as a signal
CTA_PATTERNS = [
    r"request\s+(?:a\s+)?demo",
    r"schedule\s+(?:a\s+)?(?:demo|call|meeting)",
    r"book\s+(?:a\s+)?(?:demo|call|meeting)",
    r"get\s+started",
    r"start\s+(?:your\s+)?free\s+trial",
    r"sign\s+up",
    r"contact\s+(?:us|sales)",
    r"talk\s+to",
    r"learn\s+more",
    r"see\s+(?:it\s+)?in\s+action",
    r"watch\s+(?:the\s+)?(?:demo|video)",
    r"download",
    r"try\s+(?:it\s+)?(?:now|free|today)",
    r"subscribe",
    r"join\s+(?:us|now|today)",
]

CTA_RE = re.compile("|".join(CTA_PATTERNS), re.IGNORECASE)


def is_cta_block(text: str, link_density: float = 0.0) -> bool:
    """
    Check if text is a CTA block.
    
    Uses both pattern matching AND link density.
    Short text with high link density is likely a CTA.
    """
    text = text.strip()
    
    # Short text matching CTA pattern
    if len(text) < 100 and CTA_RE.search(text):
        return True
    
    # Short text with very high link density
    if len(text) < 50 and link_density > 0.8:
        return True
    
    return False


# =============================================================================
# METADATA EXTRACTION
# =============================================================================

def extract_metadata(soup: BeautifulSoup) -> dict:
    """Extract page metadata (title, description, date, etc.)."""
    metadata = {
        "title": None,
        "meta_description": None,
        "lang": None,
        "published_date": None,
        "byline": None,
    }
    
    # Title
    title_tag = soup.find("title")
    if title_tag:
        metadata["title"] = title_tag.get_text(strip=True)
    
    # OG title fallback
    og_title = soup.find("meta", property="og:title")
    if og_title and not metadata["title"]:
        metadata["title"] = og_title.get("content", "")
    
    # Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        metadata["meta_description"] = meta_desc.get("content", "")
    
    # OG description fallback
    og_desc = soup.find("meta", property="og:description")
    if og_desc and not metadata["meta_description"]:
        metadata["meta_description"] = og_desc.get("content", "")
    
    # Language
    html_tag = soup.find("html")
    if html_tag:
        metadata["lang"] = html_tag.get("lang", "")
    
    # Published date (multiple sources)
    date_sources = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "date"}),
        ("meta", {"name": "publish-date"}),
        ("time", {"datetime": True}),
    ]
    
    for tag, attrs in date_sources:
        element = soup.find(tag, attrs)
        if element:
            date_val = element.get("content") or element.get("datetime") or element.get_text(strip=True)
            if date_val:
                metadata["published_date"] = date_val
                break
    
    # Byline/author
    author_sources = [
        ("meta", {"name": "author"}),
        ("meta", {"property": "article:author"}),
        (".author", {}),
        (".byline", {}),
    ]
    
    for selector, attrs in author_sources:
        if selector.startswith("."):
            element = soup.select_one(selector)
        else:
            element = soup.find(selector, attrs)
        if element:
            byline = element.get("content") or element.get_text(strip=True)
            if byline:
                metadata["byline"] = byline
                break
    
    return metadata


# =============================================================================
# PASS C: STRUCTURED BLOCK EXTRACTION
# =============================================================================

def extract_blocks(element: Tag) -> list[ContentBlock]:
    """
    Pass C: Walk container and emit typed blocks.
    
    Preserves structure: headings, paragraphs, lists, quotes.
    """
    blocks = []
    seen_texts = set()  # For within-page deduplication
    
    def add_block(block_type: str, text: str, **kwargs):
        """Add block if not duplicate."""
        text = text.strip()
        if not text or len(text) < 3:
            return
        
        # Normalize for dedup check
        normalized = re.sub(r"\s+", " ", text.lower())
        if normalized in seen_texts:
            return
        seen_texts.add(normalized)
        
        blocks.append(ContentBlock(type=block_type, text=text, **kwargs))
    
    # Process direct children and key descendants
    for child in element.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "blockquote", "div"]):
        if not isinstance(child, Tag):
            continue
        
        tag_name = child.name.lower()
        
        # Headings
        if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            text = child.get_text(strip=True)
            add_block(tag_name, text)
        
        # Paragraphs
        elif tag_name == "p":
            text = child.get_text(strip=True)
            link_density = compute_link_density(child)
            
            if is_cta_block(text, link_density):
                add_block("cta", text, link_density=link_density)
            else:
                add_block("p", text, link_density=link_density)
        
        # Lists
        elif tag_name in ["ul", "ol"]:
            list_type = tag_name
            for li in child.find_all("li", recursive=False):
                text = li.get_text(strip=True)
                add_block("li", text, list_type=list_type)
        
        # Blockquotes
        elif tag_name == "blockquote":
            text = child.get_text(strip=True)
            
            # Try to find attribution
            cite = child.find("cite")
            attribution = cite.get_text(strip=True) if cite else None
            
            # Check for attribution pattern in text
            if not attribution:
                lines = text.split("\n")
                if len(lines) > 1:
                    last_line = lines[-1].strip()
                    if last_line.startswith(("—", "–", "-")) or re.match(r"^[A-Z][a-z]+\s+[A-Z]", last_line):
                        attribution = last_line.lstrip("—–- ")
                        text = "\n".join(lines[:-1])
            
            add_block("quote", text, attribution=attribution)
        
        # Divs with testimonial/quote classes
        elif tag_name == "div":
            classes = " ".join(child.get("class", []) or []).lower()
            if "testimonial" in classes or "quote" in classes:
                text = child.get_text(strip=True)
                add_block("quote", text)
    
    return blocks


# =============================================================================
# PASS D: TEXT NORMALIZATION + DEDUPLICATION
# =============================================================================

def normalize_text(text: str) -> str:
    """Normalize whitespace and clean up text."""
    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple spaces
    text = re.sub(r"[ \t]+", " ", text)
    # Strip lines
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines)


def remove_duplicate_lines(text: str) -> tuple[str, float]:
    """
    Remove duplicate adjacent lines.
    
    Returns:
        (cleaned_text, dup_ratio)
    """
    lines = text.split("\n")
    clean_lines = []
    prev_normalized = None
    dup_count = 0
    
    for line in lines:
        normalized = re.sub(r"\s+", " ", line.lower().strip())
        
        if normalized == prev_normalized and normalized:
            dup_count += 1
        else:
            clean_lines.append(line)
            prev_normalized = normalized
    
    ratio = dup_count / max(len(lines), 1)
    return "\n".join(clean_lines), ratio


# =============================================================================
# PASS E: QUALITY SCORING
# =============================================================================

def compute_quality_score(
    metrics: ExtractionMetrics,
    blocks: list[ContentBlock],
) -> QualityScore:
    """
    Compute quality score and flags.
    
    Score inputs:
    - Content length (too short is bad)
    - Heading presence
    - Paragraph count
    - Link density (high is bad)
    - Boilerplate ratio (high is bad)
    - Repetition ratio (high is bad)
    """
    flags = []
    score = 1.0  # Start at perfect, deduct for issues
    
    # Content length
    if metrics.char_count < 500:
        score -= 0.3
        flags.append("low_text")
    elif metrics.char_count < 1000:
        score -= 0.1
    
    # Headings
    if metrics.heading_count == 0:
        score -= 0.1
        flags.append("no_headings")
    
    # Paragraphs
    if metrics.paragraph_count < 3:
        score -= 0.1
    
    # Link density
    if metrics.link_density > 0.5:
        score -= 0.3
        flags.append("high_link_density")
    elif metrics.link_density > 0.3:
        score -= 0.1
    
    # Boilerplate ratio
    if metrics.boilerplate_ratio > 0.5:
        score -= 0.2
        flags.append("high_boilerplate")
    elif metrics.boilerplate_ratio > 0.3:
        score -= 0.1
    
    # Duplicate lines
    if metrics.dup_line_ratio > 0.3:
        score -= 0.2
        flags.append("excessive_repetition")
    elif metrics.dup_line_ratio > 0.1:
        score -= 0.1
    
    # CTA blocks removed
    cta_count = sum(1 for b in blocks if b.type == "cta")
    if cta_count > 0:
        flags.append(f"cta_removed:{cta_count}")
    
    # Quote presence (positive signal for testimonials)
    if metrics.quote_count > 0:
        flags.append(f"quotes:{metrics.quote_count}")
    
    return QualityScore(
        score=max(0.0, min(1.0, score)),
        flags=flags,
    )


# =============================================================================
# MAIN EXTRACTION FUNCTION
# =============================================================================

def extract_structured_content(
    raw_html: bytes,
    url: str,
    boilerplate_filter: Optional[BoilerplateFilter] = None,
    final_url: Optional[str] = None,
) -> StructuredContent:
    """
    Extract structured content using multi-pass pipeline.
    
    Pipeline:
    1. DOM Sanitization - Remove nav/footer/modals
    2. Main Content Selection - Score containers, pick best
    3. Structured Extraction - Emit typed blocks
    4. Boilerplate Filtering - Cross-page + within-page
    5. Quality Scoring - Compute metrics and flags
    
    Args:
        raw_html: Raw HTML bytes
        url: Page URL
        boilerplate_filter: Optional cross-page boilerplate filter
        final_url: Final URL after redirects
    
    Returns:
        StructuredContent with all fields populated
    """
    result = StructuredContent(url=url, final_url=final_url or url)
    
    if not raw_html:
        result.quality = QualityScore(score=0.0, flags=["empty_content"])
        return result
    
    # Decode HTML
    try:
        html = raw_html.decode("utf-8", errors="ignore")
    except Exception:
        result.quality = QualityScore(score=0.0, flags=["decode_error"])
        return result
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract metadata first (before pruning)
    metadata = extract_metadata(soup)
    result.title = metadata["title"]
    result.meta_description = metadata["meta_description"]
    result.lang = metadata["lang"]
    result.published_date = metadata["published_date"]
    result.byline = metadata["byline"]
    
    # Pass A: DOM Sanitization
    soup = prune_dom(soup)
    
    # Pass B: Main Content Selection
    main = find_main_content(soup)
    
    # Pass C: Structured Block Extraction
    result.blocks = extract_blocks(main)
    
    # Compute raw text (before boilerplate removal)
    result.raw_text = main.get_text(separator="\n", strip=True)
    result.raw_text = normalize_text(result.raw_text)
    
    # Pass D: Boilerplate Filtering
    boilerplate_ratio = 0.0
    if boilerplate_filter:
        result.text, boilerplate_ratio = boilerplate_filter.remove_boilerplate(result.raw_text)
    else:
        result.text = result.raw_text
    
    # Remove duplicate lines
    result.text, dup_ratio = remove_duplicate_lines(result.text)
    result.text = normalize_text(result.text)
    
    # Pass E: Compute Metrics
    result.metrics = ExtractionMetrics(
        char_count=len(result.text),
        word_count=len(result.text.split()),
        link_density=compute_link_density(main),
        boilerplate_ratio=boilerplate_ratio,
        dup_line_ratio=dup_ratio,
        heading_count=sum(1 for b in result.blocks if b.type.startswith("h")),
        paragraph_count=sum(1 for b in result.blocks if b.type == "p"),
        list_item_count=sum(1 for b in result.blocks if b.type == "li"),
        quote_count=sum(1 for b in result.blocks if b.type == "quote"),
    )
    
    # Compute Quality Score
    result.quality = compute_quality_score(result.metrics, result.blocks)
    
    return result


# =============================================================================
# BATCH PROCESSING WITH BOILERPLATE LEARNING
# =============================================================================

def extract_with_boilerplate_learning(
    pages: list[tuple[str, bytes]],
    boilerplate_threshold: float = 0.3,
) -> list[StructuredContent]:
    """
    Extract structured content from multiple pages with boilerplate learning.
    
    Two-phase approach:
    1. Extract all pages and learn boilerplate patterns
    2. Re-apply boilerplate filter to get clean text
    
    Args:
        pages: List of (url, raw_html_bytes) tuples
        boilerplate_threshold: Fraction of pages for boilerplate detection
    
    Returns:
        List of StructuredContent objects with boilerplate removed
    """
    if not pages:
        return []
    
    # Phase 1: Extract and learn boilerplate
    bp_filter = BoilerplateFilter()
    initial_results = []
    
    for url, raw_html in pages:
        content = extract_structured_content(raw_html, url)
        initial_results.append((url, raw_html, content))
        bp_filter.add_page(content.raw_text)
    
    # Compute boilerplate patterns
    bp_filter.compute_boilerplate(threshold=boilerplate_threshold)
    
    # Phase 2: Re-extract with boilerplate filter
    final_results = []
    for url, raw_html, _ in initial_results:
        content = extract_structured_content(raw_html, url, bp_filter)
        final_results.append(content)
    
    return final_results


def get_clean_text_for_summarization(
    structured: StructuredContent,
    include_cta: bool = False,
    min_quality_score: float = 0.3,
) -> Optional[str]:
    """
    Get clean text suitable for LLM summarization.
    
    Returns None if quality is too low.
    """
    if structured.quality.score < min_quality_score:
        return None
    
    return structured.to_plain_text(include_cta=include_cta)


# =============================================================================
# QUALITY-BASED TIER ESCALATION HELPER
# =============================================================================

def should_escalate_tier(content: StructuredContent) -> tuple[bool, str]:
    """
    Determine if extraction quality is poor enough to warrant tier escalation.
    
    Returns:
        (should_escalate, reason)
    """
    # Very low quality score
    if content.quality.score < 0.4:
        return True, f"low_quality_score:{content.quality.score:.2f}"
    
    # Too short
    if content.metrics.char_count < 300:
        return True, f"too_short:{content.metrics.char_count}"
    
    # No headings and very high link density (likely nav page)
    if content.metrics.heading_count == 0 and content.metrics.link_density > 0.4:
        return True, "nav_like_page"
    
    # Check for app shell / JS placeholder signals
    low_text_flags = ["low_text", "no_headings"]
    if all(f in content.quality.flags for f in low_text_flags):
        return True, "possible_app_shell"
    
    return False, ""
