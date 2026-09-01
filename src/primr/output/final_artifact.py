"""Normalized final-document model for shipping report artifacts.

This module keeps the final artifact pipeline stricter than the upstream
research pipeline. It canonicalizes long-form markdown into a stable shape
before Markdown/TXT/DOCX rendering.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from html import unescape as html_unescape

from primr.utils.formatting import remove_em_dashes

_REFERENCE_HEADINGS = {"sources", "citations", "references"}
_SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_URL_RE = re.compile(r"https?://[^\s)\]]+")
_URL_DASH_REPLACEMENTS = {
    "\u2014": "%E2%80%94",
    "\u2013": "%E2%80%93",
    "\u2012": "%E2%80%92",
}
_HTML_ENTITY_RE = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_PRESENTATION_SPACE_RE = re.compile("[\u00a0\u2007\u202f]")
_MAX_HTML_ENTITY_PASSES = 4


@dataclass(slots=True)
class FinalSection:
    heading: str
    body: str

    @property
    def is_reference(self) -> bool:
        return self.heading.strip().lower() in _REFERENCE_HEADINGS


@dataclass(slots=True)
class GeneratedSection:
    title: str
    content: str
    words: int
    validate_line: str
    citation_numbers: list[int] = field(default_factory=list)

    def to_markdown(self) -> str:
        return f"## {self.title}\n\n{self.content}".strip()


@dataclass(slots=True)
class FinalDocument:
    preamble: str = ""
    sections: list[FinalSection] = field(default_factory=list)
    sources_heading: str = "Sources"
    sources_body: str = ""

    def to_markdown(self) -> str:
        parts: list[str] = []
        if self.preamble.strip():
            parts.append(self.preamble.strip())

        for section in self.sections:
            body = section.body.strip()
            parts.append(
                f"## {section.heading.strip()}\n\n{body}"
                if body
                else f"## {section.heading.strip()}"
            )

        if self.sources_body.strip():
            parts.append(f"## {self.sources_heading}\n\n{self.sources_body.strip()}")

        return "\n\n".join(part for part in parts if part).strip() + "\n"


def parse_final_markdown(markdown_content: str) -> FinalDocument:
    if not markdown_content.strip():
        return FinalDocument()

    lines = markdown_content.splitlines()
    preamble_lines: list[str] = []
    sections: list[FinalSection] = []
    sources_chunks: list[str] = []
    current_heading: str | None = None
    current_body: list[str] = []

    def flush_current() -> None:
        nonlocal current_heading, current_body
        if current_heading is None:
            return
        section = FinalSection(current_heading.strip(), "\n".join(current_body).strip())
        if section.is_reference:
            if section.body:
                sources_chunks.append(section.body)
        else:
            sections.append(section)
        current_heading = None
        current_body = []

    for line in lines:
        match = _SECTION_HEADING_RE.match(line)
        if match:
            flush_current()
            current_heading = match.group(1)
            continue
        if current_heading is None:
            preamble_lines.append(line)
        else:
            current_body.append(line)

    flush_current()

    preamble = "\n".join(preamble_lines).strip()
    sources_body = "\n\n".join(chunk.strip() for chunk in sources_chunks if chunk.strip())
    return FinalDocument(preamble=preamble, sections=sections, sources_body=sources_body)


# Detection threshold: any line longer than this that also contains inline
# structural markers (## heading, | table row, list-style "- **bold**") is
# almost certainly collapsed — Grok occasionally emits the first big chunk
# of a long response with newlines stripped.
_COLLAPSED_LINE_CHAR_THRESHOLD = 500


def _looks_collapsed(content: str) -> bool:
    """True if at least one line looks like a run-together multi-section blob."""
    for line in content.splitlines():
        if len(line) <= _COLLAPSED_LINE_CHAR_THRESHOLD:
            continue
        # Signals that the long line contains structure that should have been
        # broken out: multiple ## headings, multiple pipe-table rows, or a
        # "- **Label**" bullet pattern embedded mid-line.
        heading_hits = len(re.findall(r"(?<!^)(?<!\n)##\s+[A-Z]", line))
        pipe_hits = line.count("| ")
        bullet_hits = len(re.findall(r"(?<!^)(?<!\n)\s-\s\*\*[A-Z]", line))
        if heading_hits >= 1 or pipe_hits >= 4 or bullet_hits >= 2:
            return True
    return False


def _normalize_url_punctuation(url: str) -> str:
    for dash, replacement in _URL_DASH_REPLACEMENTS.items():
        url = url.replace(dash, replacement)
    return url


def _remove_em_dashes_around_urls(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _URL_RE.finditer(text):
        parts.append(remove_em_dashes(text[cursor : match.start()]))
        parts.append(_normalize_url_punctuation(match.group(0)))
        cursor = match.end()
    parts.append(remove_em_dashes(text[cursor:]))
    return "".join(parts)


def normalize_final_punctuation(markdown_content: str) -> str:
    """Normalize style-prohibited punctuation in final artifacts."""
    return _remove_em_dashes_around_urls(markdown_content)


def normalize_final_html_entities(markdown_content: str) -> str:
    """Decode presentation-safe HTML entities in final report prose.

    Provider and search-result text can retain encoded punctuation after all
    research stages. Decode those entities before shipping, but keep encoded
    angle brackets inert so cleanup cannot activate raw HTML in Markdown.
    Nested encodings are bounded to avoid attacker-controlled expansion.
    """

    def _decode(match: re.Match[str]) -> str:
        raw = match.group(0)
        decoded = html_unescape(raw)
        if decoded == raw or "<" in decoded or ">" in decoded:
            return raw
        if decoded.isspace():
            return " "
        if any(unicodedata.category(char).startswith("C") for char in decoded):
            return ""
        return decoded

    normalized = _PRESENTATION_SPACE_RE.sub(" ", markdown_content)
    for _ in range(_MAX_HTML_ENTITY_PASSES):
        decoded = _HTML_ENTITY_RE.sub(_decode, normalized)
        if decoded == normalized:
            break
        normalized = decoded
    return normalized


def _restore_collapsed_markdown(content: str) -> str:
    """Reinsert missing line breaks around structural markers in a collapsed
    markdown blob. Only applied when ``_looks_collapsed`` returns True — in
    the common case of well-formed markdown this function is a no-op.

    Heuristics are intentionally conservative: we only split when the marker
    is adjacent to whitespace and followed by a capitalized token (so
    legitimate cross-references like ``(see ## quick wins)`` stay put when
    lowercase).
    """
    if not _looks_collapsed(content):
        return content

    repaired = content

    # Break before "## " headings that appear mid-line followed by a
    # capitalized word. Require a space before the ## so we don't split on
    # "###" or inline bold markers.
    repaired = re.sub(
        r"(?<=\S) (##+\s+[A-Z][^\n]*?)(?=\s+[A-Z]|\s+\*|\n|$)",
        r"\n\n\1",
        repaired,
    )

    # Break before the single "# " top-level title when inline (rare but
    # happens if the LLM emits a subtitle on the same line).
    repaired = re.sub(r"(?<=\S) (#\s+[A-Z][^\n#]{2,})", r"\n\n\1", repaired)

    # Break before "- **Label**:" bullets that appear mid-line. Require the
    # bold opener and a capital letter to avoid matching em-dashes or
    # negative numbers.
    repaired = re.sub(r"(?<=\S) (-\s+\*\*[A-Z][^*\n]+\*\*)", r"\n\1", repaired)

    # Break pipe-table row boundaries. When an inline sequence contains
    # "| cell | cell | | ---- | ---- |" the transition between rows is a
    # closing "|" followed by whitespace and an opening "|". Insert a
    # newline between them. Also break the FIRST row of a table out of the
    # preceding prose ("...summary sentence. | Phase | Focus |").
    repaired = re.sub(r"\| +\|", "|\n|", repaired)
    repaired = re.sub(r"(?<=[.!?)\"'*\s])(\|\s+[A-Z][^\n|]*?\|)", r"\n\1", repaired)

    # Collapse any 3+ consecutive blank lines introduced by the splits.
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)

    return repaired


def canonicalize_final_markdown(markdown_content: str) -> str:
    repaired = _restore_collapsed_markdown(markdown_content)
    repaired = normalize_final_html_entities(repaired)
    repaired = normalize_final_punctuation(repaired)
    return parse_final_markdown(repaired).to_markdown()
