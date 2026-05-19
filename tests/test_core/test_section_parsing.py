"""Unit tests for primr.core.section_parsing.

Pure-function tests for the section envelope / heading extractor and
the GeneratedSection normalizer extracted from research_agent.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from primr.core.section_parsing import (
    _extract_generated_section_blocks,
    _normalize_generated_section_payload,
    _parse_single_section,
    _parse_structured_section_envelopes,
)


@dataclass
class _FakeSection:
    """Minimal stand-in for SectionConfig with just the attributes we use."""

    name: str
    id: str = "fake"


class TestParseStructuredSectionEnvelopes:
    def test_parses_single_envelope(self):
        content = "<section><title>Overview</title><body>body text</body></section>"
        assert _parse_structured_section_envelopes(content) == [("Overview", "body text")]

    def test_parses_multiple_envelopes(self):
        content = (
            "<section><title>One</title><body>first</body></section>"
            "<section><title>Two</title><body>second</body></section>"
        )
        assert _parse_structured_section_envelopes(content) == [
            ("One", "first"),
            ("Two", "second"),
        ]

    def test_strips_whitespace_in_title(self):
        content = "<section><title>  Spaced   Out  </title><body>x</body></section>"
        assert _parse_structured_section_envelopes(content) == [("Spaced Out", "x")]

    def test_skips_empty_title(self):
        content = "<section><title></title><body>x</body></section>"
        assert _parse_structured_section_envelopes(content) == []

    def test_case_insensitive_tags(self):
        content = "<SECTION><TITLE>Upper</TITLE><BODY>UP</BODY></SECTION>"
        assert _parse_structured_section_envelopes(content) == [("Upper", "UP")]

    def test_returns_empty_for_no_envelopes(self):
        assert _parse_structured_section_envelopes("plain text") == []

    def test_multiline_body_preserved(self):
        content = (
            "<section><title>Multi</title><body>line 1\n\nline 2</body></section>"
        )
        assert _parse_structured_section_envelopes(content) == [
            ("Multi", "line 1\n\nline 2")
        ]


class TestExtractGeneratedSectionBlocks:
    def test_markdown_headings_only(self):
        content = "## First\n\nbody1\n\n## Second\n\nbody2"
        preamble, blocks = _extract_generated_section_blocks(content)
        assert preamble == ""
        assert blocks == [("First", "body1"), ("Second", "body2")]

    def test_envelopes_only(self):
        content = "<section><title>A</title><body>x</body></section>"
        preamble, blocks = _extract_generated_section_blocks(content)
        assert preamble == ""
        assert blocks == [("A", "x")]

    def test_mixed_envelope_and_heading(self):
        content = (
            "<section><title>One</title><body>first body</body></section>\n\n"
            "## Two\n\nsecond body"
        )
        preamble, blocks = _extract_generated_section_blocks(content)
        assert preamble == ""
        assert blocks == [("One", "first body"), ("Two", "second body")]

    def test_preserves_source_order(self):
        content = (
            "## Alpha\n\na-body\n\n"
            "<section><title>Beta</title><body>b-body</body></section>\n\n"
            "## Gamma\n\ng-body"
        )
        _, blocks = _extract_generated_section_blocks(content)
        assert [t for t, _ in blocks] == ["Alpha", "Beta", "Gamma"]

    def test_headings_inside_envelope_ignored(self):
        # A '##' inside an envelope's body should not register as its own section.
        content = (
            "<section><title>Wrap</title><body>## Inner heading\nbody</body></section>"
        )
        _, blocks = _extract_generated_section_blocks(content)
        assert len(blocks) == 1
        assert blocks[0][0] == "Wrap"
        assert "Inner heading" in blocks[0][1]

    def test_preamble_extracted(self):
        content = "Preamble line.\n\n## First\n\nbody"
        preamble, blocks = _extract_generated_section_blocks(content)
        assert "Preamble" in preamble
        assert blocks == [("First", "body")]

    def test_no_blocks_returns_no_preamble(self):
        preamble, blocks = _extract_generated_section_blocks("plain text")
        assert blocks == []
        # No blocks -> no preamble extracted either (preamble_end = 0).
        assert preamble == ""

    def test_strips_trailing_hashes_in_heading(self):
        content = "## Heading ##\nbody"
        _, blocks = _extract_generated_section_blocks(content)
        assert blocks[0][0] == "Heading"


class TestNormalizeGeneratedSectionPayload:
    def test_basic_payload(self):
        result = _normalize_generated_section_payload("Overview", "body content")
        assert result.title == "Overview"
        assert "body content" in result.content
        assert result.words > 0
        # No validate line in input -> default added.
        assert result.validate_line.startswith("What to validate:")

    def test_expected_title_overrides(self):
        result = _normalize_generated_section_payload("Wrong", "x", expected_title="Right")
        assert result.title == "Right"

    def test_drops_duplicated_heading_in_body(self):
        body = "## Overview\n\nactual body"
        result = _normalize_generated_section_payload("Overview", body)
        assert "## Overview" not in result.content
        assert "actual body" in result.content

    def test_drops_embedded_sources_appendix(self):
        body = "real body\n\n## Sources\n\n[cite: 1] https://example.com/a"
        result = _normalize_generated_section_payload("Overview", body)
        assert "## Sources" not in result.content
        assert "real body" in result.content

    def test_extracts_what_to_validate_line(self):
        body = "body content\n\nWhat to validate: ask about pricing"
        result = _normalize_generated_section_payload("Overview", body)
        assert result.validate_line == "What to validate: ask about pricing"
        # Validate-line is removed from cleaned body and re-appended.
        assert result.content.count("What to validate:") == 1

    def test_validate_line_bold_emphasized(self):
        body = "body\n\n**What to validate:** ask about churn"
        result = _normalize_generated_section_payload("Overview", body)
        assert result.validate_line == "What to validate: ask about churn"

    def test_validate_line_wrapped_in_bold(self):
        body = "body\n\n**What to validate: ask about scope**"
        result = _normalize_generated_section_payload("Overview", body)
        assert result.validate_line == "What to validate: ask about scope"

    def test_extracts_citation_numbers(self):
        body = "Stat [cite: 1] and follow-up [cite: 2, 3] confirm."
        result = _normalize_generated_section_payload("Overview", body)
        assert result.citation_numbers == [1, 2, 3]

    def test_citation_numbers_deduped(self):
        body = "Stat [cite: 1] then [cite: 1, 2] then [cite: 2]."
        result = _normalize_generated_section_payload("Overview", body)
        assert result.citation_numbers == [1, 2]

    def test_empty_body_uses_default_validate_line(self):
        result = _normalize_generated_section_payload("Overview", "")
        assert result.validate_line.startswith("What to validate:")
        assert result.content == result.validate_line

    def test_title_fallback_when_all_inputs_blank(self):
        result = _normalize_generated_section_payload("", "body", expected_title=None)
        assert result.title == "Section"


class TestParseSingleSection:
    def test_parses_heading_first(self):
        content = "## Custom Heading\n\nbody text"
        section = _FakeSection(name="Expected Title")
        result = _parse_single_section(content, section)
        # Expected title wins over the body's heading text.
        assert result.title == "Expected Title"

    def test_falls_back_to_expected_when_no_heading(self):
        content = "plain body without heading"
        section = _FakeSection(name="Fallback Title")
        result = _parse_single_section(content, section)
        assert result.title == "Fallback Title"
        assert "plain body" in result.content

    def test_uses_first_block_when_multiple_present(self):
        content = "## A\nfirst\n\n## B\nsecond"
        section = _FakeSection(name="A")
        result = _parse_single_section(content, section)
        assert "first" in result.content
        # Second block content should NOT leak into single-section result.
        assert "second" not in result.content

    def test_preamble_prepended_to_body(self):
        content = "intro preamble\n\n## A\n\nactual body"
        section = _FakeSection(name="A")
        result = _parse_single_section(content, section)
        assert "intro preamble" in result.content
        assert "actual body" in result.content

    def test_envelope_path(self):
        content = "<section><title>Wrap</title><body>envelope body</body></section>"
        section = _FakeSection(name="Wrap")
        result = _parse_single_section(content, section)
        assert "envelope body" in result.content


@pytest.mark.parametrize(
    "content",
    [
        "## Heading\n\nbody",
        "<section><title>X</title><body>body</body></section>",
        "no heading at all",
    ],
)
def test_parse_single_section_always_returns_generated_section(content):
    section = _FakeSection(name="X")
    result = _parse_single_section(content, section)
    # GeneratedSection should always carry these attributes.
    assert hasattr(result, "title")
    assert hasattr(result, "content")
    assert hasattr(result, "words")
    assert hasattr(result, "validate_line")
    assert hasattr(result, "citation_numbers")
