"""Pure report-content cleanup helpers.

Extracted from `primr.core.research_agent` for isolated unit testing. All
functions here are pure string transforms — no I/O, no globals modified.
They are imported back into `research_agent` so existing call sites and
tests that import from the original module continue to work.
"""

from __future__ import annotations

import re


def _sanitize_numeric_cite_bracket(inner: str) -> str:
    """Keep only numeric cite ids from a mixed citation bracket."""
    nums: list[str] = []
    for cite_match in re.finditer(r"cites?:\s*([^;\]]+)", inner, re.IGNORECASE):
        for raw_num in re.findall(r"\d+", cite_match.group(1)):
            if raw_num not in nums:
                nums.append(raw_num)
    if not nums:
        return ""
    return "[cite: " + ", ".join(nums) + "]"


def _rewrite_inline_confidence_citations(content: str) -> str:
    """Convert nested confidence/source annotations into cleaner prose."""
    pattern = re.compile(
        r"\[(Confirmed|Reported|Estimated|Hypothesis):\s*([^\[\]]*?)\s*"
        r"\[cite:\s*\d+\s+from\s+(https?://[^\]\s]+)\]\s*\]",
        re.IGNORECASE,
    )

    def _replace(match: re.Match[str]) -> str:
        label = match.group(1).capitalize()
        detail = re.sub(r"\s+", " ", match.group(2)).strip(" ;,")
        url = match.group(3).strip()
        if detail:
            return f"({label}: {detail}) [Source: {url}]"
        return f"({label}) [Source: {url}]"

    return pattern.sub(_replace, content)


def _rewrite_cite_from_url_tags(content: str) -> str:
    """Convert malformed `[cite: N from URL]` tags into source tags for normalization."""
    return re.sub(
        r"\[cite:\s*\d+\s+from\s+(https?://[^\]\s]+)\]",
        lambda m: f"[Source: {m.group(1).strip()}]",
        content,
        flags=re.IGNORECASE,
    )


def _clean_fast_report_output(report_content: str) -> str:
    """Final cleanup of fast-mode report artifacts before citation normalization."""
    if not report_content.strip():
        return report_content

    report_content = _rewrite_inline_confidence_citations(report_content)
    report_content = _rewrite_cite_from_url_tags(report_content)

    report_content = re.sub(
        r"\n*_?Disclaimer:\s*Grok is not a financial advi[sc]er[^\n]*\n?",
        "\n",
        report_content,
        flags=re.IGNORECASE,
    )

    report_content = re.sub(
        r"\n\s*\((?:Reported|Estimated|Confirmed|Hypothesis)\)\s*\n(?=\s*\n|$)",
        "\n",
        report_content,
    )

    def _strip_informal_cites(match: re.Match[str]) -> str:
        return _sanitize_numeric_cite_bracket(match.group(1))

    report_content = re.sub(
        r"\[([^\]]*cites?:\s*[^\]]+)\]",
        _strip_informal_cites,
        report_content,
        flags=re.IGNORECASE,
    )

    # Inner scan length-bounded to prevent ReDoS on adversarial input.
    report_content = re.sub(
        r"\s*\[cross-ref(?:[\s:][^\]]{0,200})?\]",
        "",
        report_content,
        flags=re.IGNORECASE,
    )

    report_content = re.sub(
        r"\n?\[citation inventory[^\]]*\]\n?",
        "\n",
        report_content,
        flags=re.IGNORECASE,
    )

    report_content = re.sub(
        r"\s*\[workbook(?:[\s:§][^\]]{0,200})?\]",
        "",
        report_content,
        flags=re.IGNORECASE,
    )
    report_content = re.sub(r"\[Analysis Workbook[^\]]*\]", "", report_content, flags=re.IGNORECASE)
    report_content = re.sub(r"\[Analysis:[^\]]*\]", "", report_content, flags=re.IGNORECASE)
    report_content = re.sub(r"\[External Sources\]", "", report_content, flags=re.IGNORECASE)
    report_content = re.sub(
        r"vendor-research-[\w.-]+\.txt", "", report_content, flags=re.IGNORECASE
    )
    report_content = re.sub(r"\bInternal ROI Model\b", "", report_content, flags=re.IGNORECASE)
    report_content = re.sub(r"\bInternal Analysis\b", "", report_content, flags=re.IGNORECASE)
    report_content = re.sub(r"\bAnalysis Workbook\b", "", report_content, flags=re.IGNORECASE)

    report_content = re.sub(r"\[Word count:\s*[\d,]+\]", "", report_content, flags=re.IGNORECASE)

    report_content = re.sub(r"  +", " ", report_content)
    report_content = re.sub(r"\n{3,}", "\n\n", report_content)

    return report_content.strip() + "\n"


_INTERNAL_REFERENCE_TERMS = (
    "analysis context",
    "analysis workbook",
    "internal analysis",
    "internal roi model",
    "vendor-research",
    "workbook",
    "company report",
    "industry baseline",
    "market analysis",
    "itr on website",
    "itron website",
    "insights.txt",
    "workbook.md",
)


def _strip_internal_source_placeholders(content: str) -> str:
    """Remove non-auditable internal source placeholders from final outputs."""
    if not content.strip():
        return content

    confidence_bracket = re.compile(
        r"\[(Confirmed|Reported|Estimated|Hypothesis):\s*([^\]]+)\]", re.IGNORECASE
    )

    def _drop_if_internal(match: re.Match[str]) -> str:
        source_text = match.group(2).lower()
        if any(term in source_text for term in _INTERNAL_REFERENCE_TERMS):
            return ""
        return match.group(0)

    cleaned = confidence_bracket.sub(_drop_if_internal, content)
    cleaned = re.sub(
        r"\[(?:Reported|Confirmed|Estimated|Hypothesis):\s*\]", "", cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"\[citation inventory[^\]]*\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _strip_unresolved_section_cross_references(content: str) -> str:
    """Remove unresolved internal section references that should not ship."""
    if not content.strip():
        return content

    cleaned = re.sub(
        r"\[\s*(?:see|cross-?ref|xref)\s+##\s+[^\]]+\]",
        "",
        content,
        flags=re.IGNORECASE,
    )
    # Collapse only repeated horizontal whitespace left behind by the removed
    # token. `\s{2,}` would also eat newlines (including the blank line after a
    # heading), flattening "## Heading\n\n..." into "## Heading ..." and
    # breaking downstream heading/section parsing. Restrict to spaces/tabs and
    # let the following rule normalize any excess blank lines.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _extract_markdown_headings(content: str) -> list[str]:
    """Return normalized markdown headings in document order."""
    return [heading.strip() for heading in re.findall(r"^##\s+(.+?)\s*$", content, re.MULTILINE)]


def _preserves_report_structure(original: str, candidate: str) -> bool:
    """Require same ordered headings, allowing only an appended sources section."""
    original_headings = _extract_markdown_headings(original)
    candidate_headings = _extract_markdown_headings(candidate)
    if candidate_headings[: len(original_headings)] != original_headings:
        return False
    extra_headings = [h.strip().lower() for h in candidate_headings[len(original_headings) :]]
    if any(h not in {"sources", "citations", "references"} for h in extra_headings):
        return False

    original_words = len(original.split())
    candidate_words = len(candidate.split())
    if original_words == 0:
        return False
    return candidate_words >= int(original_words * 0.98)
