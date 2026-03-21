"""
WAF, soft block, and challenge detection.

Operates on raw HTML, headers, and response metadata.
"""

import hashlib
import re

from .config import MIN_CONTENT_LENGTH_BYTES, MIN_UNIQUE_LINE_RATIO, WAF_SIGNATURES
from .models import BlockType

# Per-host template hashes for known blocked pages
# Populated during scraping when we detect a block
_host_block_templates: dict[str, set[str]] = {}


def _compute_template_hash(raw_content: bytes) -> str:
    """
    Compute structural hash of page for template matching.

    Uses title + h1 + main text patterns to identify templates.
    """
    try:
        text = raw_content.decode("utf-8", errors="ignore").lower()
    except (UnicodeDecodeError, AttributeError):
        return ""

    # Extract structural elements
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.DOTALL)
    h1 = h1_match.group(1).strip() if h1_match else ""

    # Remove HTML tags for text content
    text_only = re.sub(r"<[^>]+>", " ", text)
    text_only = re.sub(r"\s+", " ", text_only).strip()

    # Take first 500 chars of text for template matching
    text_sample = text_only[:500]

    # Combine and hash (MD5 used for fingerprinting, not security)
    template_str = f"{title}|{h1}|{text_sample}"
    return hashlib.md5(template_str.encode(), usedforsecurity=False).hexdigest()


def register_block_template(host: str, raw_content: bytes) -> None:
    """
    Register a page as a known block template for this host.

    Called when we confirm a page is blocked, so future pages
    matching the same template are detected faster.
    """
    template_hash = _compute_template_hash(raw_content)
    if not template_hash:
        return

    if host not in _host_block_templates:
        _host_block_templates[host] = set()
    _host_block_templates[host].add(template_hash)


def clear_block_templates(host: str | None = None) -> None:
    """Clear registered block templates (for testing)."""
    global _host_block_templates
    if host:
        _host_block_templates.pop(host, None)
    else:
        _host_block_templates = {}


def detect_soft_block(
    raw_content: bytes,
    http_status: int | None = None,
    content_type: str | None = None,
    final_url: str | None = None,
    host: str | None = None,
) -> tuple[bool, str | None]:
    """
    Detect if response is a soft block (200 OK but fake content).

    Checks (in order):
    1. HTTP status (non-200 is obvious block)
    2. Final URL (redirected to /blocked, /captcha, etc.)
    3. Known WAF signatures in HTML
    4. Template-based detection (hash matches known block template for this host)
    5. JavaScript-only pages that haven't rendered
    6. Repetitive content (< 30% unique lines)
    7. Content length (only if no structural elements present)

    Returns: (is_blocked, reason)
    """
    if not raw_content:
        return True, "Empty response"

    # Decode content
    try:
        text = raw_content.decode("utf-8", errors="ignore")
        text_lower = text.lower()
    except (UnicodeDecodeError, AttributeError):
        return True, "Failed to decode content"

    # 1. HTTP status check
    if http_status and http_status != 200:
        if http_status == 403:
            return True, f"HTTP {http_status} Forbidden"
        elif http_status == 401:
            return True, f"HTTP {http_status} Unauthorized"
        elif http_status == 429:
            return True, f"HTTP {http_status} Too Many Requests"
        elif http_status >= 400:
            return True, f"HTTP {http_status} Error"

    # 2. Final URL check (redirected to block page) - check early
    if final_url:
        final_lower = final_url.lower()
        block_paths = ["/blocked", "/captcha", "/challenge", "/access-denied", "/forbidden"]
        for path in block_paths:
            if path in final_lower:
                return True, f"Redirected to block page: {path}"

    # 3. Check for known WAF signatures
    # Only flag as blocked if content is small (likely a block page)
    # Real pages often reference WAF names in scripts/cookies but have substantial content
    content_length = len(raw_content)

    for signature, description in WAF_SIGNATURES:
        if signature in text_lower:
            # Avoid false positives for legitimate content with substantial size
            # Block pages are typically small (<10KB), real pages are larger
            if content_length > 10000:
                continue  # Substantial content = probably not a block page

            # Additional checks for common false positives
            if signature == "cloudflare" and "cloudflare.com" in (final_url or "").lower():
                continue  # Cloudflare's own site

            return True, f"WAF signature: {description}"

    # 3b. Browser compatibility blocks (site requires modern browser)
    browser_block_indicators = [
        ("browser not supported", "Browser not supported"),
        ("not compatible with internet explorer", "Internet Explorer not supported"),
        ("please upgrade your browser", "Browser upgrade required"),
        ("unsupported browser", "Unsupported browser"),
        ("your browser is not supported", "Browser not supported"),
        ("this site requires", "Browser requirements not met"),
        ("please use a modern browser", "Modern browser required"),
        ("browser is out of date", "Browser out of date"),
    ]

    for indicator, description in browser_block_indicators:
        if indicator in text_lower:
            # Legitimate sites sometimes embed hidden IE/browser fallback markup
            # inside otherwise valid pages. Treat browser-support text like other
            # block signatures: only fail when the overall response is small.
            if content_length > 10000:
                continue
            return True, f"Browser block: {description}"

    # 4. Template-based detection
    if host:
        template_hash = _compute_template_hash(raw_content)
        if template_hash and template_hash in _host_block_templates.get(host, set()):
            return True, "Matches known block template for this host"

    # 5. JavaScript-only pages
    if "<noscript>" in text_lower:
        # Check if there's meaningful content outside noscript
        text_without_noscript = re.sub(
            r"<noscript[^>]*>.*?</noscript>", "", text, flags=re.DOTALL | re.IGNORECASE
        )
        # Remove script tags
        text_without_scripts = re.sub(
            r"<script[^>]*>.*?</script>", "", text_without_noscript, flags=re.DOTALL | re.IGNORECASE
        )
        # Remove HTML tags
        text_only = re.sub(r"<[^>]+>", " ", text_without_scripts)
        text_only = re.sub(r"\s+", " ", text_only).strip()

        if len(text_only) < 200:
            return True, "JavaScript-only page (content not rendered)"

    # 6. Repetitive content check
    # Only apply to small pages - large pages with repeated nav/footer are fine
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) > 10 and content_length < 50000:  # Only check pages < 50KB
        unique_lines = set(lines)
        unique_ratio = len(unique_lines) / len(lines)
        if unique_ratio < MIN_UNIQUE_LINE_RATIO:
            return True, f"Suspiciously repetitive content ({unique_ratio:.0%} unique)"

    # 7. Content length check - only if no structural elements present
    # This is the last check because legitimate small pages with good structure should pass
    if content_length < MIN_CONTENT_LENGTH_BYTES:
        # Check for structural elements that indicate legitimate content
        has_title = bool(re.search(r"<title[^>]*>.+</title>", text, re.DOTALL | re.IGNORECASE))
        has_h1 = bool(re.search(r"<h1[^>]*>.+</h1>", text, re.DOTALL | re.IGNORECASE))
        has_main = bool(
            re.search(r"<main[^>]*>", text_lower) or re.search(r"<article[^>]*>", text_lower)
        )
        has_nav = bool(re.search(r"<nav[^>]*>", text_lower))
        has_header = bool(re.search(r"<header[^>]*>", text_lower))

        # If page has good structure (title + h1 + semantic elements), allow it
        if has_title and has_h1 and (has_main or has_nav or has_header):
            return False, None

        # Check if it's HTML (not JSON/API response)
        if (
            (content_type and "html" in content_type.lower())
            or "<html" in text_lower
            or "<!doctype" in text_lower
        ):
            return True, f"Content too short ({content_length} bytes)"

    return False, None


def detect_challenge_page(raw_content: bytes) -> tuple[bool, BlockType | None]:
    """
    Detect challenge pages vs hard blocks.

    Challenge pages (solvable): Cloudflare "Just a moment", CAPTCHA
    Hard blocks (not solvable): 403 Forbidden, geo-block

    Returns: (is_challenge_or_block, block_type)
    """
    if not raw_content:
        return False, None

    try:
        text_lower = raw_content.decode("utf-8", errors="ignore").lower()
    except (UnicodeDecodeError, AttributeError):
        return False, None

    # Challenge indicators (solvable)
    challenge_indicators = [
        "just a moment",
        "checking your browser",
        "please wait",
        "verifying",
        "one more step",
        "cf-browser-verification",
    ]

    for indicator in challenge_indicators:
        if indicator in text_lower:
            return True, BlockType.CHALLENGE

    # Hard block indicators (not solvable)
    hard_block_indicators = [
        "access denied",
        "403 forbidden",
        "forbidden",
        "blocked",
        "not authorized",
        "geo-restricted",
    ]

    for indicator in hard_block_indicators:
        if indicator in text_lower:
            # Make sure it's not just mentioning the word
            if len(text_lower) < 5000:  # Short page = likely actual block
                return True, BlockType.HARD_BLOCK

    return False, None


def detect_consent_wall(raw_content: bytes) -> bool:
    """Detect cookie consent walls blocking content."""
    if not raw_content:
        return False

    try:
        text_lower = raw_content.decode("utf-8", errors="ignore").lower()
    except (UnicodeDecodeError, AttributeError):
        return False

    consent_indicators = [
        "cookie consent",
        "we use cookies",
        "accept cookies",
        "cookie policy",
        "privacy preferences",
        "consent-wall",
        "cookie-wall",
        "gdpr",
        "accept all cookies",
    ]

    # Check for consent indicators
    has_consent = any(indicator in text_lower for indicator in consent_indicators)

    if has_consent:
        # Check if content is hidden (common pattern, handle minified CSS too)
        if re.search(r"display\s*:\s*none", text_lower) or re.search(
            r"visibility\s*:\s*hidden", text_lower
        ):
            return True
        # Check if modal/overlay is blocking
        if re.search(r"position\s*:\s*fixed", text_lower) and re.search(
            r"z-index\s*:\s*9999", text_lower
        ):
            return True

    return False


def check_success_signal(
    raw_content: bytes,
    http_status: int | None = None,
) -> bool:
    """
    Check if response passes success signal criteria.

    This runs BEFORE declaring success and BEFORE caching.
    Applied uniformly to ALL tiers (HTTP and browser).

    Success requires at least ONE of:
    - Content length > 5KB for HTML
    - Key selectors exist (title, h1, main content area)
    - Extracted text density > 30%

    Returns: True if success signal passes, False otherwise
    """
    if not raw_content:
        return False

    # HTTP status must be 200 (or None if not available)
    if http_status and http_status != 200:
        return False

    try:
        text = raw_content.decode("utf-8", errors="ignore")
        text_lower = text.lower()
    except (UnicodeDecodeError, AttributeError):
        return False

    # Check 1: Content length
    if len(raw_content) >= MIN_CONTENT_LENGTH_BYTES:
        return True

    # Check 2: Key selectors exist
    has_title = bool(re.search(r"<title[^>]*>.+</title>", text, re.DOTALL | re.IGNORECASE))
    has_h1 = bool(re.search(r"<h1[^>]*>.+</h1>", text, re.DOTALL | re.IGNORECASE))
    has_main = bool(
        re.search(r"<main[^>]*>", text_lower) or re.search(r"<article[^>]*>", text_lower)
    )

    if has_title and (has_h1 or has_main):
        return True

    # Check 3: Text density
    # Remove HTML tags
    text_only = re.sub(r"<[^>]+>", " ", text)
    text_only = re.sub(r"\s+", " ", text_only).strip()

    if len(text_only) > 0:
        # Calculate density (text length vs total length)
        density = len(text_only) / len(text) if len(text) > 0 else 0
        if density > 0.3 and len(text_only) > 500:
            return True

    return False
