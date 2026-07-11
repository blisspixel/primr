"""
Text extraction from HTML and PDF.

Operates on raw bytes from tiers (not pre-parsed content).
Uses BeautifulSoup for robust HTML parsing and reader-mode extraction.
"""

import contextlib
import logging
import os
import re
import warnings

from bs4 import BeautifulSoup, FeatureNotFound, NavigableString, XMLParsedAsHTMLWarning

from primr.ai.genai_factory import default_genai_http_options

logger = logging.getLogger(__name__)

XML_DOCUMENT_TOKENS = (
    "<urlset",
    "<sitemapindex",
    "<rss",
    "<feed",
    "<rdf:rdf",
    "<atom:feed",
)

# Tags to remove in both modes
NOISE_TAGS_ALWAYS = ["script", "style", "noscript", "meta", "link", "svg", "canvas", "iframe"]

# Additional tags to remove in aggressive mode
NOISE_TAGS_AGGRESSIVE = ["header", "footer", "form", "aside", "nav"]

# Tags that typically contain boilerplate, not main content
BOILERPLATE_CLASSES = [
    "nav",
    "navbar",
    "navigation",
    "menu",
    "sidebar",
    "footer",
    "header",
    "advertisement",
    "ad",
    "ads",
    "social",
    "share",
    "comment",
    "comments",
    "related",
    "recommended",
    "cookie",
    "consent",
    "popup",
    "modal",
    "breadcrumb",
    "pagination",
    "search",
    "login",
    "signup",
    "subscribe",
]

# Pre-compiled regex for word-boundary matching of boilerplate classes
# This prevents false positives like "ddpa" matching "ad"
BOILERPLATE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(bp) for bp in BOILERPLATE_CLASSES) + r")\b", re.IGNORECASE
)

# Tags that typically contain main content
CONTENT_TAGS = ["article", "main", "section", "div"]
CONTENT_CLASSES = ["content", "article", "post", "entry", "main", "body", "text"]

# Minimum thresholds for quality content
MIN_CONTENT_LENGTH = 200  # chars
MIN_WORD_COUNT = 30
MIN_SENTENCE_COUNT = 2

# Garbage content patterns (block pages, errors, etc.)
GARBAGE_PATTERNS = [
    "browser not supported",
    "internet explorer",
    "please upgrade your browser",
    "enable javascript",
    "javascript is required",
    "cookies must be enabled",
    "access denied",
    "403 forbidden",
    "404 not found",
    "page not found",
    "something went wrong",
    "an error occurred",
    "please try again",
    "loading...",
    "still loading",
]

NAV_HINT_TERMS = {
    "skip",
    "content",
    "login",
    "products",
    "solutions",
    "integrations",
    "resources",
    "careers",
    "contact",
    "demo",
    "assessment",
    "hiring",
}


def _is_nav_like_line(line: str) -> bool:
    """Heuristic detector for mega-menu/navigation text lines."""
    text = (line or "").strip()
    if len(text) < 40:
        return False

    lower = text.lower()
    if "skip to content" in lower:
        return True

    # Navigation bundles are often long token lists without sentence punctuation.
    if any(p in text for p in ".?!;:"):
        return False

    words = [w.strip(".,()[]{}|/-") for w in text.split() if w.strip()]
    if len(words) < 8:
        return False

    short_ratio = sum(1 for w in words if len(w) <= 14) / len(words)
    alpha_words = [w for w in words if w.isalpha()]
    title_ratio = sum(1 for w in alpha_words if w[:1].isupper()) / max(len(alpha_words), 1)
    nav_hits = sum(1 for w in words if w.lower() in NAV_HINT_TERMS)

    return short_ratio >= 0.85 and title_ratio >= 0.55 and nav_hits >= 4


def _is_body_like_line(line: str) -> bool:
    """Heuristic for a likely article/body paragraph line."""
    text = (line or "").strip()
    if len(text) < 60:
        return False
    if "cookie" in text.lower() or "consent" in text.lower():
        return False
    words = text.split()
    if len(words) < 10:
        return False
    lower_words = sum(1 for w in words if any(ch.islower() for ch in w))
    return lower_words >= max(4, len(words) // 3)


def _trim_leading_noise(lines: list[str]) -> list[str]:
    """Drop leading nav/cookie blocks before the first body-like content."""
    start = 0
    for i, line in enumerate(lines):
        if _is_body_like_line(line):
            start = i
            break
    # Preserve a nearby heading if present just before the first body paragraph.
    if start > 0:
        prev = lines[start - 1].strip()
        if 4 <= len(prev) <= 80 and prev.lower() not in {"login", "request a demo"}:
            return lines[start - 1 :]
    return lines[start:] if start > 0 else lines


def is_quality_content(text: str, min_length: int = MIN_CONTENT_LENGTH) -> tuple[bool, str]:
    """
    Check if extracted text is quality content vs garbage.

    Returns:
        (is_quality, reason) - True if content is good, False with reason if garbage
    """
    if not text:
        return False, "Empty content"

    text_lower = text.lower()

    # Check for garbage patterns
    for pattern in GARBAGE_PATTERNS:
        if pattern in text_lower:
            return False, f"Garbage pattern: {pattern}"

    # Check minimum length
    if len(text) < min_length:
        return False, f"Too short ({len(text)} chars < {min_length})"

    # Check word count
    words = text.split()
    if len(words) < MIN_WORD_COUNT:
        return False, f"Too few words ({len(words)} < {MIN_WORD_COUNT})"

    # Check for sentences (rough heuristic)
    sentences = len([s for s in text.split(".") if len(s.strip()) > 10])
    if sentences < MIN_SENTENCE_COUNT:
        return False, f"Too few sentences ({sentences} < {MIN_SENTENCE_COUNT})"

    # Check for repetitive content (same line repeated)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines:
        unique_lines = set(lines)
        if len(unique_lines) < len(lines) * 0.5:  # Less than 50% unique
            return False, f"Repetitive content ({len(unique_lines)}/{len(lines)} unique)"

    return True, "OK"


def detect_content_type(
    raw_content: bytes,
    content_type_header: str | None = None,
) -> str:
    """
    Detect content type from bytes and/or header.

    Args:
        raw_content: Raw bytes to analyze
        content_type_header: Content-Type header if available

    Returns:
        Content type string: "html", "pdf", "json", "xml", "text", "unknown"
    """
    # Check header first
    if content_type_header:
        header_lower = content_type_header.lower()
        if "html" in header_lower:
            return "html"
        elif "pdf" in header_lower:
            return "pdf"
        elif "json" in header_lower:
            return "json"
        elif "xml" in header_lower:
            return "xml"
        elif "text" in header_lower:
            return "text"

    # Check magic bytes
    if raw_content:
        # PDF magic bytes
        if raw_content[:4] == b"%PDF":
            return "pdf"

        # Try to decode and check content
        try:
            text = raw_content[:1000].decode("utf-8", errors="ignore").lower()

            if "<!doctype html" in text or "<html" in text:
                return "html"
            elif text.strip().startswith("{") or text.strip().startswith("["):
                return "json"
            elif "<?xml" in text:
                return "xml"
        except (UnicodeDecodeError, AttributeError):
            pass

    return "unknown"


def _looks_like_xml_document(text: str) -> bool:
    """Heuristically detect XML-like documents before handing them to BeautifulSoup."""
    sample = (text or "").lstrip()[:2000].lower()
    if not sample:
        return False
    if "<!doctype html" in sample or "<html" in sample:
        return False
    return sample.startswith("<?xml") or any(token in sample for token in XML_DOCUMENT_TOKENS)


def _parse_markup_document(text: str) -> BeautifulSoup:
    """Parse HTML normally, but route XML-like documents to an XML parser when available."""
    parser = "xml" if _looks_like_xml_document(text) else "html.parser"
    try:
        return BeautifulSoup(text, parser)
    except FeatureNotFound:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            return BeautifulSoup(text, "html.parser")


def extract_clean_text(
    raw_html: bytes,
    mode: str = "conservative",
) -> str:
    """
    Extract clean text from raw HTML bytes using BeautifulSoup.

    Args:
        raw_html: Raw HTML bytes from tier
        mode: "conservative" (keep more) or "aggressive" (strip more)

    Conservative mode:
    - Removes only obvious noise tags (script, style, noscript, meta)
    - Keeps content in unconventional divs
    - Better for sites with non-standard layouts

    Aggressive mode:
    - Removes header/footer/nav/aside
    - Focuses on main content area
    - Better for standard layouts

    Both modes:
    - Deduplicate consecutive identical lines
    - Preserve paragraph structure with newlines

    Returns:
        Clean text string
    """
    if not raw_html:
        return ""

    # Decode bytes
    try:
        html = raw_html.decode("utf-8", errors="ignore")
    except (UnicodeDecodeError, AttributeError) as e:
        logger.warning("HTML decode failed in extract_clean_text: %s", e)
        return ""

    # Reject binary/non-HTML content that would crash the parser
    sample = html[:2000]
    control_chars = sum(1 for c in sample if ord(c) < 32 and c not in "\n\r\t")
    if len(sample) > 0 and control_chars / len(sample) > 0.05:
        return ""

    try:
        soup = _parse_markup_document(html)
    except (ValueError, TypeError):
        return ""

    # Determine which tags to remove
    if mode == "aggressive":
        noise_tags = NOISE_TAGS_ALWAYS + NOISE_TAGS_AGGRESSIVE
    else:
        noise_tags = NOISE_TAGS_ALWAYS

    # Remove noise tags (collect first to avoid mutating tree during iteration)
    for tag in noise_tags:
        for element in list(soup.find_all(tag)):
            element.decompose()

    # In aggressive mode, also remove boilerplate by class/id
    if mode == "aggressive":
        to_remove = []
        for element in soup.find_all(True):
            if element is None or not hasattr(element, "attrs") or element.attrs is None:
                continue
            classes = element.get("class", [])
            element_id = element.get("id", "")
            all_attrs = " ".join(classes) + " " + element_id

            # Use word-boundary matching to avoid false positives (e.g., "ddpa" matching "ad")
            if BOILERPLATE_PATTERN.search(all_attrs):
                to_remove.append(element)
        for element in to_remove:
            with contextlib.suppress(Exception):
                element.decompose()

    # Get text with newlines for block elements
    text = soup.get_text(separator="\n", strip=True)

    # Clean up whitespace and deduplicate
    lines = []
    prev_line = None

    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()

        if _is_nav_like_line(line):
            continue

        if line and line != prev_line:  # Deduplicate consecutive identical lines
            lines.append(line)
            prev_line = line

    lines = _trim_leading_noise(lines)
    return "\n".join(lines)


def _decode_html_entities(text: str) -> str:
    """Decode common HTML entities."""
    entities = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&apos;": "'",
        "&#39;": "'",
        "&mdash;": "—",
        "&ndash;": "–",
        "&copy;": "©",
        "&reg;": "®",
        "&trade;": "™",
        "&hellip;": "…",
        "&bull;": "•",
    }

    for entity, char in entities.items():
        text = text.replace(entity, char)

    # Handle numeric entities (guard against out-of-range values)
    def _safe_chr_decimal(m: re.Match[str]) -> str:
        try:
            code = int(m.group(1))
            return chr(code) if 0 < code <= 0x10FFFF else m.group(0)
        except (ValueError, OverflowError):
            return m.group(0)

    def _safe_chr_hex(m: re.Match[str]) -> str:
        try:
            code = int(m.group(1), 16)
            return chr(code) if 0 < code <= 0x10FFFF else m.group(0)
        except (ValueError, OverflowError):
            return m.group(0)

    text = re.sub(r"&#(\d+);", _safe_chr_decimal, text)
    text = re.sub(r"&#x([0-9a-fA-F]+);", _safe_chr_hex, text)

    return text


def extract_text_from_pdf(pdf_bytes: bytes) -> str | None:
    """
    Extract text from PDF bytes using PyMuPDF.

    Args:
        pdf_bytes: Raw PDF bytes

    Returns:
        Extracted text or None if extraction fails
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None

    if not pdf_bytes:
        return None

    try:
        # Open PDF from bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        text_parts = []
        for page in doc:
            text_parts.append(page.get_text("text"))

        doc.close()

        text = "\n".join(text_parts).strip()
        return text if text else None

    except Exception as e:
        logger.warning("PDF text extraction failed: %s", e)
        return None


# Per-process budget for Gemini PDF extraction. The default is zero because PDF
# LLM extraction is not part of the static scrape/full estimates; operators can
# opt in with PRIMR_PDF_LLM_MAX_CALLS when chart/table extraction is worth the
# extra spend.
_PDF_LLM_CALL_BUDGET = int(os.environ.get("PRIMR_PDF_LLM_MAX_CALLS", "0"))
_PDF_LLM_BYTE_BUDGET = int(os.environ.get("PRIMR_PDF_LLM_MAX_TOTAL_MB", "40")) * 1024 * 1024
_PDF_LLM_TIMEOUT_S = float(os.environ.get("PRIMR_PDF_LLM_TIMEOUT_S", "60"))
_pdf_llm_calls_made = 0
_pdf_llm_bytes_sent = 0


def reset_pdf_llm_budget() -> None:
    """Reset the in-process PDF LLM-call counters (test/operator helper)."""
    global _pdf_llm_calls_made, _pdf_llm_bytes_sent
    _pdf_llm_calls_made = 0
    _pdf_llm_bytes_sent = 0


def extract_text_from_pdf_via_llm(pdf_bytes: bytes) -> str | None:
    """
    Extract text from PDF bytes using Gemini (handles charts, tables, images).

    Falls back to PyMuPDF text extraction if Gemini is unavailable, disabled, or if
    the per-process budget (PRIMR_PDF_LLM_MAX_CALLS /
    PRIMR_PDF_LLM_MAX_TOTAL_MB) has been exhausted.
    """
    global _pdf_llm_calls_made, _pdf_llm_bytes_sent

    if not pdf_bytes:
        return None
    from primr.utils.model_policy import model_calls_disabled

    if model_calls_disabled():
        return extract_text_from_pdf(pdf_bytes)

    # Limit PDF size to 20MB to avoid excessive API costs
    if len(pdf_bytes) > 20 * 1024 * 1024:
        return extract_text_from_pdf(pdf_bytes)

    if _pdf_llm_calls_made >= _PDF_LLM_CALL_BUDGET:
        logger.info(
            "PDF LLM extraction budget reached (%d calls); falling back to PyMuPDF",
            _PDF_LLM_CALL_BUDGET,
        )
        return extract_text_from_pdf(pdf_bytes)
    if _pdf_llm_bytes_sent + len(pdf_bytes) > _PDF_LLM_BYTE_BUDGET:
        logger.info(
            "PDF LLM byte budget reached (%d bytes); falling back to PyMuPDF",
            _PDF_LLM_BYTE_BUDGET,
        )
        return extract_text_from_pdf(pdf_bytes)

    try:
        from google import genai

        from primr.config.settings import get_settings

        settings = get_settings()
        if not settings.api.gemini_key:
            return extract_text_from_pdf(pdf_bytes)

        import base64

        # Charge the budget before the API call so error retries can't loop.
        _pdf_llm_calls_made += 1
        _pdf_llm_bytes_sent += len(pdf_bytes)

        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        prompt = """Extract all text content from this PDF document.
Focus on:
- All body text, headings, and paragraphs
- Tables: reproduce as structured text with columns aligned
- Charts/graphs: describe the data shown (axes, values, trends)
- Key figures, statistics, and financial data
- Footnotes and captions

Return the extracted content in clean, readable format with proper structure."""

        client = genai.Client(
            api_key=settings.api.gemini_key, http_options=default_genai_http_options()
        )
        try:
            response = client.models.generate_content(
                model=settings.ai.flash_model,
                contents=[
                    {"text": prompt},
                    {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
                ],
                config={"http_options": {"timeout": int(_PDF_LLM_TIMEOUT_S * 1000)}},
            )
        except TypeError:
            # Older google-genai SDKs reject the config kwarg.
            response = client.models.generate_content(
                model=settings.ai.flash_model,
                contents=[
                    {"text": prompt},
                    {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
                ],
            )

        text = response.text.strip() if response.text else ""
        return text if len(text) >= 100 else extract_text_from_pdf(pdf_bytes)

    except Exception as e:
        logger.warning("LLM PDF extraction failed, falling back to PyMuPDF: %s", e)
        return extract_text_from_pdf(pdf_bytes)


def extract_main_content(raw_html: bytes) -> str:
    """
    Extract main content using reader-mode style extraction.

    Uses BeautifulSoup to:
    1. Remove noise elements (nav, footer, ads, etc.)
    2. Find main content container (article, main, content div)
    3. Extract clean text preserving structure

    Args:
        raw_html: Raw HTML bytes

    Returns:
        Extracted main content text
    """
    if not raw_html:
        return ""

    try:
        html = raw_html.decode("utf-8", errors="ignore")
    except (UnicodeDecodeError, AttributeError) as e:
        logger.warning("HTML decode failed in extract_main_content: %s", e)
        return ""

    # Reject binary/non-HTML content that would crash the parser
    sample = html[:2000]
    control_chars = sum(1 for c in sample if ord(c) < 32 and c not in "\n\r\t")
    if len(sample) > 0 and control_chars / len(sample) > 0.05:
        return ""

    try:
        soup = _parse_markup_document(html)
    except (ValueError, TypeError):
        return ""

    # Remove noise elements (collect first to avoid mutating tree during iteration)
    for tag in NOISE_TAGS_ALWAYS:
        for element in list(soup.find_all(tag)):
            element.decompose()

    # Collect elements to remove (don't modify during iteration)
    to_remove = []
    for element in soup.find_all(True):
        if element is None or not hasattr(element, "get"):
            continue
        classes = element.get("class", []) or []
        element_id = element.get("id", "") or ""

        all_attrs = " ".join(classes) + " " + element_id

        # Use word-boundary matching to avoid false positives (e.g., "ddpa" matching "ad")
        if BOILERPLATE_PATTERN.search(all_attrs):
            to_remove.append(element)

    # Now remove them
    for element in to_remove:
        with contextlib.suppress(Exception):
            element.decompose()

    # Try to find main content container
    main_content = None

    # Priority 1: <main> or <article> tags
    main_content = soup.find("main") or soup.find("article")

    # Priority 2: div with content-related class/id
    if not main_content:
        for tag in CONTENT_TAGS:
            for element in soup.find_all(tag):
                if element is None or not hasattr(element, "get"):
                    continue
                classes = " ".join(element.get("class", []) or [])
                element_id = element.get("id", "") or ""
                attrs = (classes + " " + element_id).lower()

                if any(cc in attrs for cc in CONTENT_CLASSES):
                    main_content = element
                    break
            if main_content:
                break

    # Priority 3: Find the div with the most text content
    if not main_content:
        main_content = _find_content_rich_element(soup)

    # Fall back to body
    if not main_content:
        main_content = soup.find("body") or soup

    # Extract text with structure
    return _extract_text_with_structure(main_content)


def _find_content_rich_element(soup: BeautifulSoup):
    """Find the element with the most meaningful text content."""
    best_element = None
    best_score = 0

    for element in soup.find_all(["div", "section", "article", "main"]):
        # Skip small elements
        text = element.get_text(strip=True)
        if len(text) < 200:
            continue

        # Score based on text length and paragraph count
        paragraphs = element.find_all("p")
        score = len(text) + (len(paragraphs) * 100)

        # Penalize elements with too many links (likely nav)
        links = element.find_all("a")
        if links:
            link_text = sum(len(a.get_text(strip=True)) for a in links)
            link_ratio = link_text / max(len(text), 1)
            if link_ratio > 0.5:  # More than 50% links = probably nav
                score *= 0.3

        if score > best_score:
            best_score = score
            best_element = element

    return best_element


def _extract_text_with_structure(element) -> str:
    """Extract text from element preserving paragraph structure."""
    if not element:
        return ""

    lines = []

    for child in element.descendants:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text and text not in ["\n", "\t"]:
                # Check if parent is a block element
                parent = child.parent
                if parent and parent.name in [
                    "p",
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "li",
                    "div",
                    "section",
                    "article",
                ]:
                    lines.append(text)
                elif lines and not lines[-1].endswith(" "):
                    # Inline text - append to last line
                    lines[-1] = lines[-1] + " " + text
                else:
                    lines.append(text)

    # Clean up and deduplicate
    cleaned = []
    prev_line = None

    for line in lines:
        line = re.sub(r"\s+", " ", line).strip()
        if _is_nav_like_line(line):
            continue
        if line and line != prev_line and len(line) > 2:
            cleaned.append(line)
            prev_line = line

    cleaned = _trim_leading_noise(cleaned)
    return "\n".join(cleaned)


def get_page_title(raw_html: bytes) -> str | None:
    """
    Extract page title from HTML.

    Args:
        raw_html: Raw HTML bytes

    Returns:
        Page title or None
    """
    if not raw_html:
        return None

    try:
        html = raw_html.decode("utf-8", errors="ignore")
    except (UnicodeDecodeError, AttributeError) as e:
        logger.warning("HTML decode failed in get_page_title: %s", e)
        return None

    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.DOTALL | re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        # Clean up whitespace
        title = re.sub(r"\s+", " ", title)
        return _decode_html_entities(title)

    return None


def get_meta_description(raw_html: bytes) -> str | None:
    """
    Extract meta description from HTML.

    Args:
        raw_html: Raw HTML bytes

    Returns:
        Meta description or None
    """
    if not raw_html:
        return None

    try:
        html = raw_html.decode("utf-8", errors="ignore")
    except (UnicodeDecodeError, AttributeError) as e:
        logger.warning("HTML decode failed in get_meta_description: %s", e)
        return None

    # Try different meta description patterns
    patterns = [
        r'<meta[^>]*name="description"[^>]*content="([^"]*)"',
        r"<meta[^>]*name='description'[^>]*content='([^']*)'",
        r'<meta[^>]*content="([^"]*)"[^>]*name="description"',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            desc = match.group(1).strip()
            return _decode_html_entities(desc)

    return None
