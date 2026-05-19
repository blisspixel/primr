"""Pure helpers for fast-mode report assembly and QA.

Extracted from `primr.core.research_agent` for isolated unit testing.

These helpers run after the LLM has produced section bodies. They enforce
deterministic quality guards, parse XML/markdown section blocks into
typed :class:`GeneratedSection` payloads, assemble the per-batch outputs
into a final markdown report, and compute deterministic QA metrics on
the assembled report.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from primr.core.section_parsing import (
    _extract_generated_section_blocks,
    _normalize_generated_section_payload,
)
from primr.core.strategy_artifacts import _split_markdown_sections

if TYPE_CHECKING:
    from primr.output.final_artifact import GeneratedSection
    from primr.prompts.loader import SectionConfig


def _enforce_fast_section_quality_guards(report_content: str) -> str:
    """Apply deterministic quality guards to fast reports.

    - Ensure each section has at least one confidence label token.
    - Ensure each non-reference section includes a "What to validate:" line.
    """
    preamble, sections = _split_markdown_sections(report_content)
    if not sections:
        return report_content

    label_pattern = re.compile(
        r"\((Confirmed|Reported|Estimated|Hypothesis)[^)]*\)", re.IGNORECASE
    )
    reference_headings = {"sources", "citations", "references"}
    rebuilt: list[str] = [preamble] if preamble else []

    for heading, body in sections:
        lower_heading = heading.strip().lower()
        guarded_body = body.strip()

        if lower_heading not in reference_headings:
            if not label_pattern.search(guarded_body):
                guarded_body = (guarded_body + "\n\n(Reported)").strip()
            if "what to validate" not in guarded_body.lower():
                guarded_body = (
                    guarded_body
                    + "\n\nWhat to validate: Confirm this section's key claim "
                    "with primary customer or operator evidence."
                ).strip()

        rebuilt.append(f"## {heading}\n\n{guarded_body}")

    return "\n\n".join(part for part in rebuilt if part).strip() + "\n"


def _compute_fast_report_qa_metrics(
    report_content: str,
    unresolved_contradictions: int = 0,
) -> dict[str, int | float | bool]:
    """Compute lightweight local QA metrics for fast reports."""
    confidence_labels = len(
        re.findall(
            r"\((Confirmed|Reported|Estimated|Hypothesis)[^)]*\)",
            report_content,
            re.IGNORECASE,
        )
    )
    cited_numbers: set[int] = set()
    for raw_group in re.findall(r"\[cite:\s*([0-9,\s]+)\]", report_content, re.IGNORECASE):
        for raw_num in raw_group.split(","):
            raw_num = raw_num.strip()
            if raw_num.isdigit():
                cited_numbers.add(int(raw_num))

    sources_block = ""
    match = re.search(
        r"^##\s+Sources\s*$", report_content, flags=re.IGNORECASE | re.MULTILINE
    )
    if match:
        sources_block = report_content[match.start() :]
    defined: set[int] = set()
    for raw_group in re.findall(r"\[cite:\s*([0-9,\s]+)\]", sources_block, re.IGNORECASE):
        for raw_num in raw_group.split(","):
            raw_num = raw_num.strip()
            if raw_num.isdigit():
                defined.add(int(raw_num))
    missing = sorted(cited_numbers - defined)

    _, sections = _split_markdown_sections(report_content)
    reference_headings = {"sources", "citations", "references"}
    content_sections = [h for h, _ in sections if h.strip().lower() not in reference_headings]
    with_validate = sum(
        1
        for h, body in sections
        if h.strip().lower() not in reference_headings
        and "what to validate:" in body.lower()
    )

    heading_counts: dict[str, int] = {}
    for h, _ in sections:
        key = h.strip().lower()
        heading_counts[key] = heading_counts.get(key, 0) + 1
    duplicate_sections = sum(1 for c in heading_counts.values() if c > 1)

    thin_sections = sum(
        1
        for h, body in sections
        if h.strip().lower() not in reference_headings and len(body.split()) < 100
    )

    qa_passed = bool(
        confidence_labels >= 8
        and len(cited_numbers) > 0
        and len(defined) > 0
        and len(missing) == 0
        and with_validate >= max(1, len(content_sections))
        and duplicate_sections == 0
        and thin_sections == 0
        and unresolved_contradictions == 0
    )

    return {
        "word_count": len(report_content.split()),
        "confidence_labels": confidence_labels,
        "citations_used": len(cited_numbers),
        "citations_defined": len(defined),
        "missing_citations": len(missing),
        "section_count": len(content_sections),
        "sections_with_validate": with_validate,
        "duplicate_sections": duplicate_sections,
        "thin_sections": thin_sections,
        "unresolved_contradictions": unresolved_contradictions,
        "qa_gate_passed": qa_passed,
    }


def _parse_batch_sections(
    content: str,
    expected_sections: list[SectionConfig],
) -> list[GeneratedSection]:
    """Parse Grok's batch response from XML envelopes and/or markdown headings."""

    parsed: list[GeneratedSection] = []
    preamble, blocks = _extract_generated_section_blocks(content)

    for idx, (title, body) in enumerate(blocks):
        expected_title = (
            expected_sections[idx].name if idx < len(expected_sections) else title
        )
        parsed.append(_normalize_generated_section_payload(title, body, expected_title))

    if not parsed and content.strip():
        expected_title = expected_sections[0].name if expected_sections else "Section"
        parsed.append(
            _normalize_generated_section_payload(
                expected_title,
                content.strip(),
                expected_title,
            )
        )

    if preamble and parsed:
        first_body = parsed[0].content
        parsed[0] = _normalize_generated_section_payload(
            parsed[0].title,
            preamble + "\n\n" + first_body,
            parsed[0].title,
        )

    return parsed


def _assemble_fast_report(
    company_name: str,
    website: str | None,
    written_sections: list[GeneratedSection],
) -> str:
    """Assemble individual batch sections into a final markdown report."""
    current_date = datetime.now().strftime("%B %d, %Y")

    header = f"# Strategic Company Overview: {company_name}\n\n"
    header += f"*{current_date}*"
    if website:
        header += f" | [{website}]({website})"
    header += "\n\n---\n"

    body_parts: list[str] = []
    for i, section in enumerate(written_sections):
        body_parts.append(section.to_markdown())
        if (i + 1) % 5 == 0 and i + 1 < len(written_sections):
            body_parts.append("---")

    return header + "\n\n".join(body_parts)
