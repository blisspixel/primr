"""Normalized final-document model for shipping report artifacts.

This module keeps the final artifact pipeline stricter than the upstream
research pipeline. It canonicalizes long-form markdown into a stable shape
before Markdown/TXT/DOCX rendering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_REFERENCE_HEADINGS = {"sources", "citations", "references"}
_SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


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


def canonicalize_final_markdown(markdown_content: str) -> str:
    return parse_final_markdown(markdown_content).to_markdown()
