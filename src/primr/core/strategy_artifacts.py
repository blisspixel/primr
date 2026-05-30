"""Pure strategy-artifact helpers.

Extracted from `primr.core.research_agent` for isolated unit testing.

These functions deal with strategy document QA, citation normalization,
source-URL validation, and structural splitting. They are imported back
into `research_agent` so existing import paths continue to work.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from urllib.parse import urlparse

from primr.core.report_cleanup import (
    _INTERNAL_REFERENCE_TERMS,
    _clean_fast_report_output,
    _rewrite_cite_from_url_tags,
    _sanitize_numeric_cite_bracket,
    _strip_internal_source_placeholders,
    _strip_unresolved_section_cross_references,
)
from primr.utils.validators import validate_url_for_request

logger = logging.getLogger(__name__)

_HOST_LABEL_RE = re.compile(r"^[a-z0-9-]{1,63}$")


def _strategy_money_to_millions(value: float, unit: str) -> float:
    unit = unit.upper()
    if unit == "B":
        return value * 1000.0
    if unit == "K":
        return value / 1000.0
    return value


def _is_auditable_source_url(url: str) -> bool:
    """Require a public HTTP(S) URL with a plausible hostname for source appendices."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass

    if "." not in host:
        return False

    labels = host.split(".")
    if any(not label or label.startswith("-") or label.endswith("-") for label in labels):
        return False

    return all(_HOST_LABEL_RE.fullmatch(label) for label in labels)


def _normalize_strategy_source_urls(source_urls: list[str]) -> tuple[list[str], list[str]]:
    """Return normalized auditable source URLs plus rejected raw entries."""
    normalized_urls: list[str] = []
    rejected_urls: list[str] = []
    seen: set[str] = set()

    for raw_url in source_urls:
        candidate = raw_url.strip()
        if not candidate:
            continue
        is_valid, normalized, _error = validate_url_for_request(candidate)
        if not is_valid or not _is_auditable_source_url(normalized):
            rejected_urls.append(candidate)
            continue
        if normalized not in seen:
            seen.add(normalized)
            normalized_urls.append(normalized)

    return normalized_urls, rejected_urls


def _extract_strategy_citation_definitions(
    strategy_content: str,
) -> tuple[set[int], dict[int, str], list[str]]:
    """Parse strategy citation definitions and keep only valid auditable URLs."""
    cited_numbers = {
        int(n) for n in re.findall(r"\[cite:\s*(\d+)\]", strategy_content, re.IGNORECASE)
    }
    valid_defs: dict[int, str] = {}
    invalid_defs: list[str] = []

    for num_str, raw_url in re.findall(
        r"\[cite:\s*(\d+)\]\s+([^\s]+)", strategy_content, re.IGNORECASE
    ):
        cite_num = int(num_str)
        is_valid, normalized, _error = validate_url_for_request(raw_url.strip())
        if not is_valid or not _is_auditable_source_url(normalized):
            invalid_defs.append(raw_url.strip())
            continue
        valid_defs[cite_num] = normalized

    return cited_numbers, valid_defs, invalid_defs


def _compute_strategy_qa_metrics(strategy_content: str) -> dict[str, int | float | bool]:
    """Deterministic QA checks for strategy outputs."""
    if not strategy_content.strip():
        return {
            "placeholder_refs": 0,
            "source_urls": 0,
            "citation_defs": 0,
            "missing_citations": 0,
            "invalid_source_urls": 0,
            "budget_totals_found": 0,
            "budget_inconsistent": False,
            "qa_gate_passed": False,
        }

    lower = strategy_content.lower()
    placeholder_refs = sum(1 for term in _INTERNAL_REFERENCE_TERMS if term in lower)
    placeholder_refs += len(
        re.findall(
            r"\[\s*(?:see|cross-?ref|xref)\s+##\s+[^\]]+\]",
            strategy_content,
            re.IGNORECASE,
        )
    )
    raw_source_urls = len(
        re.findall(r"\[Source:\s*https?://[^\]\s]+", strategy_content, re.IGNORECASE)
    )
    cited_numbers, valid_defs, invalid_defs = _extract_strategy_citation_definitions(
        strategy_content
    )
    missing_citations = sorted(cited_numbers - set(valid_defs))
    source_urls = max(raw_source_urls, len(valid_defs))

    totals: list[float] = []
    explicit_totals: list[float] = []
    year_one_totals: list[float] = []
    for m in re.finditer(
        r"Total\s*:?\s*\$([0-9]+(?:\.[0-9]+)?)\s*([KMB])",
        strategy_content,
        re.IGNORECASE,
    ):
        total_value = _strategy_money_to_millions(float(m.group(1)), m.group(2))
        totals.append(total_value)
        explicit_totals.append(total_value)

    for m in re.finditer(
        r"Year 1 investment\s*\(?[^\n)]*\)?\s*:?\s*\$([0-9]+(?:\.[0-9]+)?)"
        r"(?:\s*-\s*([0-9]+(?:\.[0-9]+)?))?\s*([KMB])",
        strategy_content,
        re.IGNORECASE,
    ):
        low = _strategy_money_to_millions(float(m.group(1)), m.group(3))
        high = _strategy_money_to_millions(float(m.group(2)), m.group(3)) if m.group(2) else low
        midpoint = (low + high) / 2.0
        totals.append(midpoint)
        year_one_totals.append(midpoint)

    budget_inconsistent = False
    comparison_pool = explicit_totals + year_one_totals
    if len(explicit_totals) >= 2 or (explicit_totals and year_one_totals):
        min_total = min(comparison_pool)
        max_total = max(comparison_pool)
        if min_total > 0 and ((max_total - min_total) / min_total) > 0.20:
            budget_inconsistent = True

    qa_passed = bool(
        placeholder_refs == 0
        and source_urls >= 2
        and len(missing_citations) == 0
        and len(invalid_defs) == 0
        and not budget_inconsistent
    )
    return {
        "placeholder_refs": placeholder_refs,
        "source_urls": source_urls,
        "citation_defs": len(valid_defs),
        "missing_citations": len(missing_citations),
        "invalid_source_urls": len(invalid_defs),
        "budget_totals_found": len(totals),
        "budget_inconsistent": budget_inconsistent,
        "qa_gate_passed": qa_passed,
    }


def _normalize_fast_citations(report_content: str, source_urls: list[str] | None = None) -> str:
    """Normalize fast-mode citations to the deterministic analyzer format."""
    report_content = _rewrite_cite_from_url_tags(report_content)
    report_content = re.sub(
        r"\[([^\]]*cites?:\s*[^\]]+)\]",
        lambda m: _sanitize_numeric_cite_bracket(m.group(1)),
        report_content,
        flags=re.IGNORECASE,
    )

    existing_cite_def = re.compile(r"\[cite:\s*(\d+)\]\s*(https?://\S+)", re.IGNORECASE)
    num_to_url: dict[int, str] = {}
    for m in existing_cite_def.finditer(report_content):
        num_to_url[int(m.group(1))] = m.group(2).strip()

    source_pattern = re.compile(r"\[Source:\s*((?:https?://)?[^\]\s]+)\s*\]", re.IGNORECASE)
    multiword_source_pattern = re.compile(r"\[Source:\s*[^\]]+\]", re.IGNORECASE)
    urls_in_order: list[str] = []
    url_to_num: dict[str, int] = {}
    next_num = max(num_to_url.keys(), default=0) + 1

    for num, url in sorted(num_to_url.items()):
        url_to_num[url] = num
        urls_in_order.append(url)

    for match in source_pattern.finditer(report_content):
        raw_url = match.group(1).strip()
        url = raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"
        if url not in url_to_num:
            url_to_num[url] = next_num
            next_num += 1
            urls_in_order.append(url)

    if not url_to_num and not num_to_url:
        bare_cite_pattern = re.compile(r"\[cite:\s*(\d+(?:\s*,\s*\d+)*)\]", re.IGNORECASE)
        if source_urls:
            cited_nums: set[int] = set()
            for m in bare_cite_pattern.finditer(report_content):
                for n in re.findall(r"\d+", m.group(1)):
                    cited_nums.add(int(n))
            valid_nums = {n for n in cited_nums if 1 <= n <= len(source_urls)}
            if valid_nums:
                num_to_url = {n: source_urls[n - 1] for n in valid_nums}
                for n in sorted(num_to_url):
                    url_to_num[num_to_url[n]] = n
                    urls_in_order.append(num_to_url[n])
                next_num = max(num_to_url.keys()) + 1
        if not url_to_num and not num_to_url:
            bare_strip = re.compile(r"\s*\[cite:\s*\d+(?:\s*,\s*\d+)*\]", re.IGNORECASE)
            if bare_strip.search(report_content):
                logger.info("Stripping orphan [cite: N] refs with no backing URLs")
                return bare_strip.sub("", report_content)
            return report_content

    def _replace_source(match: re.Match[str]) -> str:
        raw_url = match.group(1).strip()
        url = raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"
        num = url_to_num.get(url)
        if num is None:
            nonlocal next_num
            num = next_num
            next_num += 1
            url_to_num[url] = num
            urls_in_order.append(url)
        return f"[cite: {num}]"

    normalized = source_pattern.sub(_replace_source, report_content)

    normalized = multiword_source_pattern.sub("", normalized)

    sources_heading = re.compile(
        r"^##\s+(Sources|Citations|References)\s*$", re.IGNORECASE | re.MULTILINE
    )
    if sources_heading.search(normalized):
        lines = normalized.splitlines()
        start_idx = None
        for i, line in enumerate(lines):
            if sources_heading.match(line.strip()):
                start_idx = i
                break
        if start_idx is not None:
            normalized = "\n".join(lines[:start_idx]).rstrip()

    known = dict(num_to_url)
    for url, num in url_to_num.items():
        known[num] = url

    cite_ref = re.compile(r"\[cite:\s*([0-9,\s]+)\]", re.IGNORECASE)
    used_old_nums: list[int] = []

    def _clean_refs(match: re.Match[str]) -> str:
        nums: list[int] = []
        for raw in match.group(1).split(","):
            raw = raw.strip()
            if not raw.isdigit():
                continue
            n = int(raw)
            if n in known and n not in nums:
                nums.append(n)
        if not nums:
            return ""
        for n in nums:
            if n not in used_old_nums:
                used_old_nums.append(n)
        return "[cite: " + ", ".join(str(n) for n in nums) + "]"

    normalized = cite_ref.sub(_clean_refs, normalized)

    remap = {old: idx + 1 for idx, old in enumerate(used_old_nums)}

    def _renumber_refs(match: re.Match[str]) -> str:
        nums: list[str] = []
        for raw in match.group(1).split(","):
            raw = raw.strip()
            if not raw.isdigit():
                continue
            old = int(raw)
            if old in remap:
                new_num = str(remap[old])
                if new_num not in nums:
                    nums.append(new_num)
        return f"[cite: {', '.join(nums)}]" if nums else ""

    normalized = cite_ref.sub(_renumber_refs, normalized)

    sources_lines = ["## Sources", ""]
    for old in used_old_nums:
        url = known[old]
        sources_lines.append(f"[cite: {remap[old]}] {url}")

    return normalized.rstrip() + "\n\n" + "\n".join(sources_lines) + "\n"


def _clean_strategy_output(strategy_content: str) -> str:
    """Final deterministic cleanup for strategy artifacts."""
    if not strategy_content.strip():
        return strategy_content
    cleaned = _clean_fast_report_output(strategy_content)
    cleaned = _normalize_fast_citations(cleaned)
    cleaned = _strip_internal_source_placeholders(cleaned)
    cleaned = _strip_unresolved_section_cross_references(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def _ensure_strategy_source_inventory(
    strategy_content: str, source_urls: list[str], min_sources: int = 2
) -> str:
    """Append a minimal sources inventory when strategy output lacks explicit source URLs."""
    if not strategy_content.strip() or not source_urls:
        return strategy_content

    metrics = _compute_strategy_qa_metrics(strategy_content)
    if metrics["source_urls"] >= min_sources:
        return strategy_content

    normalized_source_urls, _rejected_urls = _normalize_strategy_source_urls(source_urls)
    if not normalized_source_urls:
        return strategy_content

    existing_defs = re.findall(
        r"\[cite:\s*(\d+)\]\s*(https?://\S+)", strategy_content, re.IGNORECASE
    )
    existing_urls = {url.strip() for _, url in existing_defs}
    next_num = max((int(num) for num, _ in existing_defs), default=0) + 1
    new_lines: list[str] = []

    for url in normalized_source_urls:
        normalized = url.strip()
        if not normalized or normalized in existing_urls:
            continue
        new_lines.append(f"[cite: {next_num}] {normalized}")
        existing_urls.add(normalized)
        next_num += 1
        if len(new_lines) >= max(min_sources, 4):
            break

    if not new_lines:
        return strategy_content

    if re.search(r"^##\s+Sources\s*$", strategy_content, re.IGNORECASE | re.MULTILINE):
        return strategy_content.rstrip() + "\n" + "\n".join(new_lines) + "\n"

    return strategy_content.rstrip() + "\n\n## Sources\n\n" + "\n".join(new_lines) + "\n"


def _split_markdown_sections(content: str) -> tuple[str, list[tuple[str, str]]]:
    """Split markdown into preamble and (heading, body) sections."""
    lines = content.splitlines()
    sections: list[tuple[str, str]] = []
    preamble_lines: list[str] = []
    current_heading: str | None = None
    current_body: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_heading is None:
                preamble = "\n".join(preamble_lines).strip()
            else:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = line[3:].strip()
            current_body = []
            continue
        if current_heading is None:
            preamble_lines.append(line)
        else:
            current_body.append(line)

    if current_heading is not None:
        sections.append((current_heading, "\n".join(current_body).strip()))
        preamble = "\n".join(preamble_lines).strip()
    else:
        preamble = content.strip()

    return preamble, sections
