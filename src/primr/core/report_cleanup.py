"""Pure report-content cleanup helpers.

Extracted from `primr.core.research_agent` for isolated unit testing. All
functions here are pure string transforms — no I/O, no globals modified.
They are imported back into `research_agent` so existing call sites and
tests that import from the original module continue to work.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_INFORMAL_CITE_BRACKET_RE = re.compile(r"\[\s*((?:cites?)\s*:[^\]]+)\]", re.IGNORECASE)
_FENCED_CODE_BLOCK_RE = re.compile(
    r"(^[ \t]{0,3}(```|~~~)[^\n]*\n.*?^[ \t]{0,3}\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)


def _apply_outside_fenced_code(content: str, transform: Callable[[str], str]) -> str:
    """Apply a text transform outside Markdown fenced code blocks."""
    if not content or ("```" not in content and "~~~" not in content):
        return transform(content)

    parts: list[str] = []
    cursor = 0
    for match in _FENCED_CODE_BLOCK_RE.finditer(content):
        parts.append(transform(content[cursor : match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(transform(content[cursor:]))
    return "".join(parts)


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


def _normalize_informal_cite_brackets(content: str) -> str:
    """Normalize writer-emitted citation placeholders without touching prose."""
    return _apply_outside_fenced_code(
        content,
        lambda text: _INFORMAL_CITE_BRACKET_RE.sub(
            lambda match: _sanitize_numeric_cite_bracket(match.group(1)),
            text,
        ),
    )


def _strip_fast_report_scaffolding(content: str) -> str:
    """Strip leaked writer scaffolding from prose while preserving code fences."""
    content = _normalize_informal_cite_brackets(content)

    # Inner scan length-bounded to prevent ReDoS on adversarial input.
    content = re.sub(
        r"\s*\[cross-ref(?:[\s:][^\]]{0,200})?\]",
        "",
        content,
        flags=re.IGNORECASE,
    )

    content = re.sub(
        r"\n?\[citation inventory[^\]]*\]\n?",
        "\n",
        content,
        flags=re.IGNORECASE,
    )

    content = re.sub(
        r"\s*\[workbook(?:[\s:§][^\]]{0,200})?\]",
        "",
        content,
        flags=re.IGNORECASE,
    )
    content = re.sub(r"\[Analysis Workbook[^\]]*\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\[Analysis:[^\]]*\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\[External Sources\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"vendor-research-[\w.-]+\.txt", "", content, flags=re.IGNORECASE)
    # Leaked Title-Case workbook labels: matched CASE-SENSITIVELY so legitimate
    # lowercase prose ("based on our internal analysis", "the analysis workbook
    # process") is preserved rather than silently deleted. Stripping real content
    # is the brittle trap in its worst form - silent corruption (agentic-balance:
    # do not mangle content; only the exact leaked Title-Case label is removed).
    content = re.sub(r"\bInternal ROI Model\b", "", content)
    content = re.sub(r"\bInternal Analysis\b", "", content)
    content = re.sub(r"\bAnalysis Workbook\b", "", content)

    content = re.sub(r"\[Word count:\s*[\d,]+\]", "", content, flags=re.IGNORECASE)
    return content


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

    report_content = _apply_outside_fenced_code(report_content, _strip_fast_report_scaffolding)

    # Collapse interior multi-space runs only. The old ``re.sub(r"  +", " ")``
    # also collapsed LEADING indentation, which flattened nested lists and broke
    # fenced/indented code blocks in the shipped report - silent structural
    # corruption (agentic-balance: never mangle real content). The lookbehind
    # preserves leading indentation; fenced code is skipped entirely.
    report_content = _apply_outside_fenced_code(
        report_content,
        lambda text: re.sub(r"(?<=\S) {2,}", " ", text),
    )
    # Collapse 3+ blank lines, tolerating CRLF: a plain ``\n{3,}`` misses runs of
    # ``\r\n`` and leaves excess whitespace in a CRLF-sourced report.
    report_content = re.sub(r"(?:\r?\n){3,}", "\n\n", report_content)

    return report_content.strip() + "\n"


_INTERNAL_REFERENCE_TERMS = (
    "analysis context",
    "analysis workbook",
    "internal analysis",
    "internal roi model",
    "vendor-research",
    "workbook",
    # Only primr's own internal artifact names belong here. Generic external
    # descriptors ("market analysis", "company report", "industry baseline")
    # were removed: matched as lowercase substrings they silently deleted
    # legitimate confidence-labeled external sources such as
    # "[Reported: per Gartner market analysis]" (agentic-balance: never silently
    # delete real content; cf. the case-sensitive Title-Case strip above).
    "insights.txt",
    "workbook.md",
)


def _strip_internal_source_placeholders(content: str) -> str:
    """Remove non-auditable internal source placeholders from final outputs."""
    if not content.strip():
        return content

    def _strip_chunk(text: str) -> str:
        confidence_bracket = re.compile(
            r"\[(Confirmed|Reported|Estimated|Hypothesis):\s*([^\]]+)\]",
            re.IGNORECASE,
        )

        def _drop_if_internal(match: re.Match[str]) -> str:
            source_text = match.group(2).lower()
            if any(term in source_text for term in _INTERNAL_REFERENCE_TERMS):
                return ""
            return match.group(0)

        cleaned = confidence_bracket.sub(_drop_if_internal, text)
        cleaned = re.sub(
            r"\[(?:Reported|Confirmed|Estimated|Hypothesis):\s*\]",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\[citation inventory[^\]]*\]", "", cleaned, flags=re.IGNORECASE)
        return cleaned

    cleaned = _apply_outside_fenced_code(content, _strip_chunk)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _strip_unresolved_section_cross_references(content: str) -> str:
    """Remove unresolved internal section references that should not ship."""
    if not content.strip():
        return content

    def _strip_chunk(text: str) -> str:
        cleaned = re.sub(
            r"\[\s*(?:see|cross-?ref|xref)\s+##\s+[^\]]+\]",
            "",
            text,
            flags=re.IGNORECASE,
        )
        # Collapse only repeated horizontal whitespace left behind by the removed
        # token. `\s{2,}` would also eat newlines (including the blank line after
        # a heading), flattening "## Heading\n\n..." into "## Heading ..." and
        # breaking downstream heading/section parsing. Restrict to spaces/tabs
        # and let the following rule normalize any excess blank lines.
        return re.sub(r"[ \t]{2,}", " ", cleaned)

    cleaned = _apply_outside_fenced_code(content, _strip_chunk)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def compute_repair_report(before: str, after: str) -> dict:
    """Measure how much the final-stage deterministic cleanup actually changed.

    The cleanup (`_clean_fast_report_output` + citation normalization + section
    guards) silently strips internal-scaffolding markers, malformed citations,
    disclaimers, and word-count tags from raw writer output. This makes that
    work *visible*: it counts the scaffolding markers present before vs after,
    so a run's reliance on arbitrary repair is tracked instead of silent.

    The goal (ROADMAP "Artifact Pipeline Hardening") is to push consistency
    upstream into the writing/regeneration prompts so this trends toward zero —
    a writer that emits clean markdown needs no repair. ``writer_output_clean``
    is the headline signal: when it is consistently true, the cleanup is a
    safety net rather than load-bearing.

    Reuses the ship-time scanner (`scan_scaffolding_leakage`) so the categories
    match the gates exactly — no duplicated marker definitions.
    """
    from primr.qa.report_analyzer import scan_scaffolding_leakage

    before_leak = scan_scaffolding_leakage(before)
    after_leak = scan_scaffolding_leakage(after)
    before_total = int(before_leak["total_leaked"])
    after_total = int(after_leak["total_leaked"])
    return {
        "scaffolding_before": before_total,
        "scaffolding_after": after_total,
        "scaffolding_removed": max(0, before_total - after_total),
        "chars_removed": max(0, len(before) - len(after)),
        "writer_output_clean": before_total == 0,
        "changed": before.strip() != after.strip(),
    }


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
