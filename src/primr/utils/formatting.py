"""
Formatting utilities for consulting-tier reports.

Provides functions to clean content by removing em-dashes, emojis,
numbered headings, and formatting numbers for readability.
"""

import re

# Emoji regex pattern covering common emoji ranges
EMOJI_PATTERN = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map symbols
    "\U0001f700-\U0001f77f"  # alchemical symbols
    "\U0001f780-\U0001f7ff"  # geometric shapes extended
    "\U0001f800-\U0001f8ff"  # supplemental arrows-c
    "\U0001f900-\U0001f9ff"  # supplemental symbols and pictographs
    "\U0001fa00-\U0001fa6f"  # chess symbols
    "\U0001fa70-\U0001faff"  # symbols and pictographs extended-a
    "\U00002702-\U000027b0"  # dingbats
    "\U000024c2-\U0001f251"  # enclosed characters
    "\U0001f1e0-\U0001f1ff"  # flags
    "\U00002600-\U000026ff"  # misc symbols
    "\U00002700-\U000027bf"  # dingbats
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "\U0001f000-\U0001f02f"  # mahjong tiles
    "\U0001f0a0-\U0001f0ff"  # playing cards
    "]+",
    flags=re.UNICODE,
)

# Em-dash and similar dashes
EM_DASH_PATTERN = re.compile(r"[\u2014\u2013\u2012]")  # em-dash, en-dash, figure dash

# Numbered heading pattern (e.g., "1. Executive Summary", "2.1 Overview")
NUMBERED_HEADING_PATTERN = re.compile(r"^(\s*)(#+\s*)?\d+(?:\.\d+)*\.?\s+", re.MULTILINE)

# Nested numbering in lists (e.g., "1.1.1", "a.i.ii")
NESTED_NUMBERING_PATTERN = re.compile(
    r"^\s*(?:"
    r"(?:\d+\.){2,}"  # 1.1.1, 2.3.4
    r"|[a-z]+\.[ivx]+\."  # a.i., b.ii.
    r"|[ivx]+\.[a-z]+\."  # i.a., ii.b.
    r")\s*",
    re.MULTILINE | re.IGNORECASE,
)


def remove_emojis(text: str) -> str:
    """Remove all emoji characters from text."""
    return EMOJI_PATTERN.sub("", text)


def remove_em_dashes(text: str) -> str:
    """
    Replace em-dashes with appropriate punctuation.

    Uses commas for mid-sentence dashes, periods for sentence breaks.
    """
    # Handle em-dash used as parenthetical (word — word — word)
    # Replace with commas
    result = EM_DASH_PATTERN.sub(", ", text)

    # Clean up double commas or comma-period combinations
    result = re.sub(r",\s*,", ",", result)
    result = re.sub(r",\s*\.", ".", result)
    result = re.sub(r"\.\s*,", ".", result)

    # Clean up spaces around commas
    result = re.sub(r"\s+,", ",", result)
    result = re.sub(r",\s+", ", ", result)

    return result


def fix_numbered_headings(text: str) -> str:
    """
    Remove numbered prefixes from headings.

    Converts "1. Executive Summary" to "Executive Summary"
    Converts "## 2.1 Overview" to "## Overview"
    """

    def replace_heading(match: re.Match[str]) -> str:
        indent = match.group(1) or ""
        hash_prefix = match.group(2) or ""
        return indent + hash_prefix

    result = NUMBERED_HEADING_PATTERN.sub(replace_heading, text)
    return result


def fix_nested_numbering(text: str) -> str:
    """
    Remove nested numbering schemes from lists.

    Converts "1.1.1 Item" to "Item"
    Converts "a.i. Item" to "Item"
    """
    return NESTED_NUMBERING_PATTERN.sub("", text)


def format_number(value: float, precision: int = 1) -> str:
    """
    Format large numbers in readable abbreviated form.

    Examples:
        1500000 -> "1.5M"
        50000000 -> "50M"
        2500 -> "2.5K"
        500 -> "500"
    """
    if value < 0:
        return "-" + format_number(abs(value), precision)

    if value >= 1_000_000_000_000:
        formatted = value / 1_000_000_000_000
        return (
            f"{formatted:.{precision}f}T".rstrip("0").rstrip(".") + "T"
            if formatted != int(formatted)
            else f"{int(formatted)}T"
        )
    elif value >= 1_000_000_000:
        formatted = value / 1_000_000_000
        if formatted == int(formatted):
            return f"{int(formatted)}B"
        return f"{formatted:.{precision}f}B".rstrip("0").rstrip(".")
    elif value >= 1_000_000:
        formatted = value / 1_000_000
        if formatted == int(formatted):
            return f"{int(formatted)}M"
        return f"{formatted:.{precision}f}M".rstrip("0").rstrip(".")
    elif value >= 1_000:
        formatted = value / 1_000
        if formatted == int(formatted):
            return f"{int(formatted)}K"
        return f"{formatted:.{precision}f}K".rstrip("0").rstrip(".")
    else:
        if value == int(value):
            return str(int(value))
        return f"{value:.{precision}f}".rstrip("0").rstrip(".")


def format_currency(value: float, currency: str = "$", precision: int = 1) -> str:
    """
    Format currency values in readable abbreviated form.

    Examples:
        50000000 -> "$50M"
        2500000 -> "$2.5M"
        1500 -> "$1.5K"
    """
    return currency + format_number(value, precision)


def format_large_numbers_in_text(text: str) -> str:
    """
    Find and format large numbers in text to readable form.

    Converts "$50,000,000" to "$50M"
    Converts "50000000" to "50M"
    """

    # Pattern for currency with commas: $50,000,000
    def replace_currency(match: re.Match[str]) -> str:
        currency = match.group(1)
        number_str = match.group(2).replace(",", "")
        try:
            value = float(number_str)
            if value >= 1000:
                return format_currency(value, currency)
        except ValueError:
            pass
        return str(match.group(0))

    # Pattern for plain numbers with commas: 50,000,000
    def replace_plain(match: re.Match[str]) -> str:
        number_str = str(match.group(0)).replace(",", "")
        try:
            value = float(number_str)
            if value >= 10000:  # Only format numbers >= 10K
                return format_number(value)
        except ValueError:
            pass
        return str(match.group(0))

    # Replace currency amounts first
    result = re.sub(r"([$€£¥])(\d{1,3}(?:,\d{3})+(?:\.\d+)?)", replace_currency, text)

    # Replace standalone large numbers (not already formatted)
    result = re.sub(r"\b\d{1,3}(?:,\d{3}){2,}(?:\.\d+)?\b", replace_plain, result)

    return result


def clean_content(text: str) -> str:
    """
    Apply all formatting cleanup to text.

    Removes emojis, em-dashes, numbered headings, nested numbering,
    and formats large numbers for readability.
    """
    if not text:
        return text

    result = remove_emojis(text)
    result = remove_em_dashes(result)
    result = fix_numbered_headings(result)
    result = fix_nested_numbering(result)
    result = format_large_numbers_in_text(result)

    # Clean up any double spaces created by removals
    result = re.sub(r"  +", " ", result)

    # Clean up empty lines (more than 2 consecutive)
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def has_emojis(text: str) -> bool:
    """Check if text contains any emoji characters."""
    return bool(EMOJI_PATTERN.search(text))


def has_em_dashes(text: str) -> bool:
    """Check if text contains em-dashes or similar."""
    return bool(EM_DASH_PATTERN.search(text))


def has_numbered_headings(text: str) -> bool:
    """Check if text contains numbered headings."""
    return bool(NUMBERED_HEADING_PATTERN.search(text))


def has_nested_numbering(text: str) -> bool:
    """Check if text contains nested numbering schemes."""
    return bool(NESTED_NUMBERING_PATTERN.search(text))


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison.

    Lowercases, collapses whitespace, removes punctuation variations.
    """
    # Lowercase and collapse whitespace
    normalized = " ".join(text.lower().split())
    # Remove common punctuation that might vary
    normalized = re.sub(r'[.,;:!?\'"()-]', "", normalized)
    return normalized


def deduplicate_content(
    content: str, min_line_length: int = 20, dedupe_paragraphs: bool = True
) -> str:
    """
    Remove duplicate lines/paragraphs to reduce token usage.

    Scraped content often has duplicates from headers, footers, and
    navigation elements. This function removes them while preserving
    short lines (headers, separators) that may legitimately repeat.

    Args:
        content: Text content to deduplicate
        min_line_length: Lines shorter than this are not deduplicated
            (to preserve headers and separators)
        dedupe_paragraphs: Also deduplicate at paragraph level

    Returns:
        Deduplicated content

    Example:
        >>> content = "Header\\nMain content\\nHeader\\nMore content"
        >>> deduplicate_content(content, min_line_length=10)
        'Header\\nMain content\\nMore content'
    """
    if not content:
        return content

    # First pass: line-level deduplication
    seen_lines = set()
    unique_lines = []

    for line in content.split("\n"):
        stripped = line.strip()

        # Keep short lines without deduplication (headers, separators)
        if len(stripped) < min_line_length:
            unique_lines.append(line)
            continue

        # Normalize for comparison
        normalized = normalize_text(stripped)

        if normalized not in seen_lines:
            seen_lines.add(normalized)
            unique_lines.append(line)

    result = "\n".join(unique_lines)

    # Second pass: paragraph-level deduplication
    if dedupe_paragraphs:
        paragraphs = re.split(r"\n\s*\n", result)
        seen_paragraphs = set()
        unique_paragraphs = []

        for para in paragraphs:
            stripped = para.strip()

            # Keep short paragraphs
            if len(stripped) < min_line_length * 2:
                unique_paragraphs.append(para)
                continue

            normalized = normalize_text(stripped)

            if normalized not in seen_paragraphs:
                seen_paragraphs.add(normalized)
                unique_paragraphs.append(para)

        result = "\n\n".join(unique_paragraphs)

    return result


def get_deduplication_stats(original: str, deduplicated: str) -> dict:
    """
    Get statistics about content deduplication.

    Args:
        original: Original content
        deduplicated: Deduplicated content

    Returns:
        Dict with line counts and reduction percentage
    """
    original_lines = len(original.split("\n"))
    deduped_lines = len(deduplicated.split("\n"))
    original_chars = len(original)
    deduped_chars = len(deduplicated)

    line_reduction = (
        ((original_lines - deduped_lines) / original_lines * 100) if original_lines > 0 else 0
    )
    char_reduction = (
        ((original_chars - deduped_chars) / original_chars * 100) if original_chars > 0 else 0
    )

    return {
        "original_lines": original_lines,
        "deduplicated_lines": deduped_lines,
        "lines_removed": original_lines - deduped_lines,
        "line_reduction_percent": round(line_reduction, 1),
        "original_chars": original_chars,
        "deduplicated_chars": deduped_chars,
        "char_reduction_percent": round(char_reduction, 1),
    }
