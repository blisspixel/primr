"""Pure section-parsing helpers.

Extracted from `primr.core.research_agent` for isolated unit testing.
These functions parse and normalize section content emitted by the writer
stage of fast-mode research.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from primr.output.final_artifact import GeneratedSection
    from primr.prompts.loader import SectionConfig


_SECTION_ENVELOPE_RE = re.compile(
    r"<section>\s*<title>(.*?)</title>\s*<body>(.*?)</body>\s*</section>",
    re.IGNORECASE | re.DOTALL,
)
_SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _parse_structured_section_envelopes(content: str) -> list[tuple[str, str]]:
    """Parse optional XML-style section envelopes emitted by the writer stage."""
    matches = re.findall(
        r"<section>\s*<title>(.*?)</title>\s*<body>(.*?)</body>\s*</section>",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    parsed: list[tuple[str, str]] = []
    for title, body in matches:
        clean_title = re.sub(r"\s+", " ", title).strip()
        clean_body = body.strip()
        if clean_title:
            parsed.append((clean_title, clean_body))
    return parsed


def _extract_generated_section_blocks(content: str) -> tuple[str, list[tuple[str, str]]]:
    """Extract generated sections in source order from envelopes and/or markdown headings."""
    envelope_matches = list(_SECTION_ENVELOPE_RE.finditer(content))
    envelope_spans = [(match.start(), match.end()) for match in envelope_matches]

    def inside_envelope(position: int) -> bool:
        return any(start <= position < end for start, end in envelope_spans)

    heading_matches = [
        match
        for match in _SECTION_HEADING_RE.finditer(content)
        if not inside_envelope(match.start())
    ]

    block_starts = sorted(
        [match.start() for match in envelope_matches] + [match.start() for match in heading_matches]
    )
    parsed_blocks: list[tuple[int, str, str]] = []

    for match in envelope_matches:
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        body = match.group(2).strip()
        if title:
            parsed_blocks.append((match.start(), title, body))

    for match in heading_matches:
        next_start = next((start for start in block_starts if start > match.start()), len(content))
        title = match.group(1).strip().rstrip("#").strip()
        body = content[match.end() : next_start].strip()
        if title:
            parsed_blocks.append((match.start(), title, body))

    parsed_blocks.sort(key=lambda item: item[0])
    preamble_end = parsed_blocks[0][0] if parsed_blocks else 0
    preamble = content[:preamble_end].strip()
    ordered_blocks = [(title, body) for _, title, body in parsed_blocks]
    return preamble, ordered_blocks


def _normalize_generated_section_payload(
    title: str,
    body: str,
    expected_title: str | None = None,
) -> GeneratedSection:
    """Normalize a generated section into a stricter payload contract."""
    canonical_title = (expected_title or title or "Section").strip().rstrip("#").strip()
    working_body = body.strip()

    heading_match = re.match(r"^##\s+.+?(?:\n+|$)", working_body)
    if heading_match:
        working_body = working_body[heading_match.end() :].lstrip()

    ref_match = re.search(
        r"^##\s+(Sources|References|Citations)\s*$",
        working_body,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if ref_match:
        working_body = working_body[: ref_match.start()].rstrip()

    validation_lines: list[str] = []
    cleaned_lines: list[str] = []
    validate_prefix_re = re.compile(
        r"^\s*\**\s*What to validate\s*:?\s*\**\s*",
        flags=re.IGNORECASE,
    )
    for raw_line in working_body.splitlines():
        stripped = raw_line.strip()
        if validate_prefix_re.match(stripped):
            remainder = validate_prefix_re.sub("", stripped).rstrip()
            remainder = re.sub(r"\*+\s*$", "", remainder).rstrip()
            if remainder:
                validation_lines.append(f"What to validate: {remainder}")
            continue
        cleaned_lines.append(raw_line)

    cleaned_body = "\n".join(cleaned_lines).strip()
    validation_line = (
        validation_lines[-1]
        if validation_lines
        else (
            "What to validate: Confirm this section's key claim with primary "
            "customer or operator evidence."
        )
    )
    content = (cleaned_body + "\n\n" + validation_line).strip() if cleaned_body else validation_line
    citation_numbers: list[int] = []
    for raw_group in re.findall(r"\[cite:\s*([0-9,\s]+)\]", content, re.IGNORECASE):
        for raw_num in raw_group.split(","):
            raw_num = raw_num.strip()
            if raw_num.isdigit():
                num = int(raw_num)
                if num not in citation_numbers:
                    citation_numbers.append(num)

    from primr.output.final_artifact import GeneratedSection

    return GeneratedSection(
        title=canonical_title,
        content=content,
        words=len(content.split()),
        validate_line=validation_line,
        citation_numbers=citation_numbers,
    )


def _parse_single_section(
    content: str,
    expected_section: SectionConfig,
) -> GeneratedSection:
    """Parse Grok's single-section response.

    Expects one ``## `` heading or an optional ``<section>`` envelope.
    Falls back to using the expected section name if no heading found.
    """
    preamble, blocks = _extract_generated_section_blocks(content)
    if blocks:
        title, body = blocks[0]
        if preamble:
            body = f"{preamble}\n\n{body}".strip()
        return _normalize_generated_section_payload(title, body, expected_section.name)

    return _normalize_generated_section_payload(
        expected_section.name,
        content.strip(),
        expected_section.name,
    )
