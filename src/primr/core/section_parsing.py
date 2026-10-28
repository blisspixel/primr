"""Pure section-parsing helpers.

Extracted from `primr.core.research_agent` for isolated unit testing.
These functions parse and normalize section content emitted by the writer
stage of fast-mode research.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from primr.output.final_artifact import GeneratedSection
    from primr.prompts.loader import SectionConfig


_SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_ENVELOPE_OPEN_RE = re.compile(r"<section\s*>", re.IGNORECASE)
_ENVELOPE_HEAD_RE = re.compile(
    r"<section\s*>\s*(?:<title\s*>(?P<title>[^<]*)</title\s*>)?\s*(?P<body_open><body\s*>)?",
    re.IGNORECASE,
)
_ENVELOPE_CLOSE_RE = re.compile(r"(?P<body_close></body\s*>\s*)?</section\s*>", re.IGNORECASE)
_REFERENCE_TITLE_RE = re.compile(r"^(?:Sources|References|Citations)$", re.IGNORECASE)
_CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
_TRAILING_BODY_CLOSE_RE = re.compile(r"</body\s*>\s*$", re.IGNORECASE)
# A tag cut off by truncation (``... text </bo``) is markup, not prose.
_TRAILING_TAG_FRAGMENT_RE = re.compile(r"</?[a-z]{0,7}$", re.IGNORECASE)

# Envelope recovery outcomes. ``missing_body_tags`` is repaired safely because
# the section is still closed. ``truncated`` keeps the recovered text but may be
# incomplete. ``ambiguous`` keeps the raw envelope verbatim so the ship gate
# withholds the DOCX instead of presenting a guess. ``outside_envelope`` marks
# text the writer placed after a closed envelope; it is kept, never dropped.
ENVELOPE_RECOVERED = "missing_body_tags"
ENVELOPE_TRUNCATED = "truncated"
ENVELOPE_AMBIGUOUS = "ambiguous"
ENVELOPE_OUTSIDE_TEXT = "outside_envelope"
ENVELOPE_NEEDS_REVIEW = frozenset({ENVELOPE_TRUNCATED, ENVELOPE_AMBIGUOUS})


_ENVELOPE_SEVERITY = (
    ENVELOPE_AMBIGUOUS,
    ENVELOPE_TRUNCATED,
    ENVELOPE_RECOVERED,
    ENVELOPE_OUTSIDE_TEXT,
)


def most_severe_envelope_issue(*issues: str | None) -> str | None:
    """Return the most severe recovery outcome among ``issues``."""
    present = set(issues)
    return next((issue for issue in _ENVELOPE_SEVERITY if issue in present), None)


class SectionBlock(NamedTuple):
    """One writer section in source order, with its envelope recovery outcome."""

    title: str
    body: str
    issue: str | None = None


def _mask_code(text: str) -> str:
    """Blank code spans and fences, keeping offsets and line breaks.

    Structural searches run on this view so a code sample that mentions
    ``<section>`` or ``## Heading`` never splits a section; bodies are always
    sliced from the original text.
    """
    return _CODE_RE.sub(lambda match: re.sub(r"[^\n]", " ", match.group()), text)


def _parse_envelope(content: str, masked: str, start: int) -> tuple[SectionBlock, int]:
    """Parse the envelope opening at ``start``; return the block and its end."""
    from primr.qa.report_analyzer import has_section_envelope_markers

    head = _ENVELOPE_HEAD_RE.match(masked, start)
    if head is None:  # pragma: no cover - callers pass an opening-tag position
        raise ValueError("no section envelope at position")
    title = re.sub(r"\s+", " ", head.group("title") or "").strip()
    next_open = _ENVELOPE_OPEN_RE.search(masked, head.end())
    limit = next_open.start() if next_open else len(content)
    close = _ENVELOPE_CLOSE_RE.search(masked, head.end(), limit)
    issue: str | None
    if close is not None:
        body = content[head.end() : close.start()]
        end = close.end()
        complete = head.group("body_open") and close.group("body_close")
        issue = None if complete else ENVELOPE_RECOVERED
    else:
        raw = content[head.end() : limit].rstrip()
        body = _TRAILING_BODY_CLOSE_RE.sub("", raw)
        end = limit
        # A closed body is complete even when ``</section>`` is missing.
        issue = ENVELOPE_RECOVERED if body != raw else ENVELOPE_TRUNCATED
        if issue == ENVELOPE_TRUNCATED:
            body = _TRAILING_TAG_FRAGMENT_RE.sub("", body)
    body = body.strip()
    if not title or has_section_envelope_markers(body):
        return SectionBlock(title, content[start:end].strip(), ENVELOPE_AMBIGUOUS), end
    return SectionBlock(title, body, issue), end


def _heading_blocks(
    region: str, masked: str, offset: int
) -> tuple[str, list[tuple[int, SectionBlock]]]:
    """Split text outside envelopes on ``##`` headings; return lead text and blocks."""
    from primr.qa.report_analyzer import has_section_envelope_markers

    matches = list(_SECTION_HEADING_RE.finditer(masked))
    lead = region[: matches[0].start()] if matches else region
    blocks: list[tuple[int, SectionBlock]] = []
    for index, match in enumerate(matches):
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(region)
        title = match.group(1).strip().rstrip("#").strip()
        body = region[match.end() : body_end].strip()
        if title:
            issue = ENVELOPE_AMBIGUOUS if has_section_envelope_markers(body) else None
            blocks.append((offset + match.start(), SectionBlock(title, body, issue)))
    return lead, blocks


def _extract_generated_section_blocks(content: str) -> tuple[str, list[SectionBlock]]:
    """Extract writer sections in source order from envelopes and ``##`` headings.

    Well-formed envelopes parse as before. A closed envelope missing its body
    tags is repaired. A truncated envelope keeps its text and is flagged. An
    envelope whose title is missing or whose body still holds envelope tags is
    kept verbatim and flagged ambiguous. Text outside envelopes is split on
    headings; text after a closed envelope stays with that section.
    """
    positioned: list[tuple[int, SectionBlock]] = []
    regions: list[tuple[int, int]] = []
    masked = _mask_code(content)
    position = 0
    while (opening := _ENVELOPE_OPEN_RE.search(masked, position)) is not None:
        regions.append((position, opening.start()))
        block, position = _parse_envelope(content, masked, opening.start())
        positioned.append((opening.start(), block))
    regions.append((position, len(content)))

    preamble = ""
    for region_index, (region_start, region_end) in enumerate(regions):
        lead, blocks = _heading_blocks(
            content[region_start:region_end], masked[region_start:region_end], region_start
        )
        positioned.extend(blocks)
        if not lead.strip():
            continue
        # Region i follows envelope i - 1, which precedes it in source order.
        if region_index == 0:
            preamble = lead.strip()
            continue
        index = region_index - 1
        pos, previous = positioned[index]
        positioned[index] = (
            pos,
            SectionBlock(
                previous.title,
                f"{previous.body}\n\n{lead.strip()}".strip(),
                previous.issue or ENVELOPE_OUTSIDE_TEXT,
            ),
        )

    positioned.sort(key=lambda item: item[0])
    ordered = [block for _, block in positioned]
    # A bare heading that only introduces an envelope of the same title is a
    # repeated title, not a section of its own.
    deduplicated: list[SectionBlock] = []
    for index, block in enumerate(ordered):
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        if (
            not block.body
            and following is not None
            and following.title.casefold() == block.title.casefold()
        ):
            continue
        previous = deduplicated[-1] if deduplicated else None
        if previous is not None and previous.title.casefold() == block.title.casefold():
            # A heading repeating the section just closed continues that section.
            deduplicated[-1] = SectionBlock(
                previous.title,
                f"{previous.body}\n\n{block.body}".strip(),
                most_severe_envelope_issue(previous.issue, block.issue),
            )
            continue
        deduplicated.append(block)
    # Callers treat block-free content as one body, so it has no preamble.
    return (preamble if deduplicated else ""), deduplicated


def _normalize_generated_section_payload(
    title: str,
    body: str,
    expected_title: str | None = None,
    envelope_issue: str | None = None,
) -> GeneratedSection:
    """Normalize a generated section into a stricter payload contract."""
    canonical_title = (expected_title or title or "Section").strip().rstrip("#").strip()
    working_body = body.strip()

    heading_match = re.match(r"^##\s+.+?(?:\n+|$)", working_body)
    if heading_match:
        working_body = working_body[heading_match.end() :].lstrip()
    # A first line that only repeats the section title (``# Title``,
    # ``**Title**``) duplicates the heading the renderer adds.
    first_line, _, rest = working_body.partition("\n")
    bare = re.sub(r"^#+\s*|^\*\*|\*\*$", "", first_line.strip()).strip()
    if bare and bare.casefold() == canonical_title.casefold():
        working_body = rest.lstrip()

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
        envelope_issue=envelope_issue,
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
        title, body, issue = blocks[0]
        # One section was requested: later blocks are subsections, never dropped.
        # Reference blocks go last, so the references policy below cuts only them.
        extras = sorted(blocks[1:], key=lambda block: bool(_REFERENCE_TITLE_RE.match(block.title)))
        for extra in extras:
            # Reference blocks keep ``##`` so normalization's existing
            # references policy applies; other blocks become subsections.
            level = "##" if _REFERENCE_TITLE_RE.match(extra.title) else "###"
            heading = f"{level} {extra.title}\n\n" if extra.title else ""
            body = f"{body}\n\n{heading}{extra.body}".strip()
            issue = most_severe_envelope_issue(issue, extra.issue)
        if preamble:
            body = f"{preamble}\n\n{body}".strip()
        return _normalize_generated_section_payload(title, body, expected_section.name, issue)

    return _normalize_generated_section_payload(
        expected_section.name,
        content.strip(),
        expected_section.name,
    )


def section_retry_reason(section: GeneratedSection, word_target: int) -> str | None:
    """Return why a written section deserves one retry, or ``None``."""
    if section.envelope_issue in ENVELOPE_NEEDS_REVIEW:
        return f"returned a {section.envelope_issue} section envelope"
    if section.words < word_target * 0.5:
        return f"too thin ({section.words}/{word_target} words)"
    return None


def section_retry_instruction(section: GeneratedSection, word_target: int) -> str:
    """Return the retry instruction that matches ``section_retry_reason``."""
    thin = (
        f"The minimum target is {word_target} words."
        if section.words < word_target * 0.5
        else "Keep the full length and substance."
    )
    if section.envelope_issue in ENVELOPE_NEEDS_REVIEW:
        return (
            "IMPORTANT: Your previous attempt did not return a complete section envelope. "
            "Return the whole section exactly once as "
            f"<section><title>Exact Section Name</title><body>...</body></section>. {thin}"
        )
    return (
        f"IMPORTANT: Your previous attempt produced only {section.words} words. "
        f"The minimum target is {word_target} words. Write a substantive, strategist-grade, "
        f"decision-useful section. If direct evidence is limited, deepen the analysis with explicit "
        f"inference and strategic implications rather than staying thin."
    )


def prefer_section_retry(first: GeneratedSection, retry: GeneratedSection) -> bool:
    """Prefer the less severe envelope outcome, then the longer section."""
    rank = {ENVELOPE_AMBIGUOUS: 0, ENVELOPE_TRUNCATED: 1}
    first_rank = rank.get(first.envelope_issue or "", 2)
    retry_rank = rank.get(retry.envelope_issue or "", 2)
    if first_rank != retry_rank:
        return retry_rank > first_rank
    return retry.words > first.words
