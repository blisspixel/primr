"""Unit tests for primr.core.fast_mode_helpers.

Pure-function tests for the quality guards, batch parser, QA metrics, and
assembly helpers extracted from research_agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from primr.core.fast_mode_helpers import (
    _assemble_fast_report,
    _compute_fast_report_qa_metrics,
    _enforce_fast_section_quality_guards,
    _parse_batch_sections,
)


@dataclass
class _FakeSection:
    """Stand-in for SectionConfig with just the attributes used by the parser."""

    id: str
    name: str
    purpose: str = ""
    covers: list[str] = field(default_factory=list)
    depth: str | None = ""
    position: str | None = "middle"
    part: int = 1


# ---------------------------------------------------------------------------
# _enforce_fast_section_quality_guards
# ---------------------------------------------------------------------------


class TestEnforceFastSectionQualityGuards:
    def test_returns_unchanged_when_no_sections(self):
        content = "Just a preamble, no headings."
        assert _enforce_fast_section_quality_guards(content) == content

    def test_adds_default_confidence_label_when_missing(self):
        content = "## Overview\n\nBody text.\nWhat to validate: x"
        result = _enforce_fast_section_quality_guards(content)
        assert "(Reported)" in result

    def test_preserves_existing_confidence_label(self):
        content = "## Overview\n\n(Confirmed) Body text.\nWhat to validate: x"
        result = _enforce_fast_section_quality_guards(content)
        # Should not add another (Reported) since (Confirmed) already counts.
        assert result.count("(Reported)") == 0

    def test_adds_validate_line_when_missing(self):
        content = "## Overview\n\n(Reported) Body text without validate prompt."
        result = _enforce_fast_section_quality_guards(content)
        assert "What to validate:" in result

    def test_reference_sections_skip_guards(self):
        # Sources / Citations / References headings should not get the guards.
        content = "## Sources\n\n[cite: 1] https://example.com/a"
        result = _enforce_fast_section_quality_guards(content)
        assert "(Reported)" not in result
        assert "What to validate:" not in result

    @pytest.mark.parametrize("heading", ["Sources", "Citations", "References"])
    def test_reference_heading_variants(self, heading):
        content = f"## {heading}\n\n[cite: 1] https://example.com"
        result = _enforce_fast_section_quality_guards(content)
        assert "(Reported)" not in result

    def test_preamble_preserved(self):
        content = "Top intro line.\n\n## Section\n\nBody.\nWhat to validate: x"
        result = _enforce_fast_section_quality_guards(content)
        assert "Top intro line" in result


# ---------------------------------------------------------------------------
# _compute_fast_report_qa_metrics
# ---------------------------------------------------------------------------


class TestComputeFastReportQaMetrics:
    def _clean_report(self):
        """Build a synthetic report that passes the QA gate."""
        sections = []
        for i in range(8):
            body = (
                f"## Section {i}\n\n"
                + ("filler word " * 110)  # > 100 words to avoid thin
                + f"(Reported) data from [cite: {i + 1}].\n"
                "What to validate: confirm the claim above."
            )
            sections.append(body)
        sources = "## Sources\n\n" + "\n".join(
            f"[cite: {i + 1}] https://example.com/{i}" for i in range(8)
        )
        return "\n\n".join(sections) + "\n\n" + sources

    def test_gate_passes_for_clean_report(self):
        report = self._clean_report()
        m = _compute_fast_report_qa_metrics(report)
        assert m["qa_gate_passed"] is True
        assert m["confidence_labels"] >= 8
        assert m["missing_citations"] == 0
        assert m["duplicate_sections"] == 0
        assert m["thin_sections"] == 0

    def test_unresolved_contradictions_fails_gate(self):
        report = self._clean_report()
        m = _compute_fast_report_qa_metrics(report, unresolved_contradictions=1)
        assert m["qa_gate_passed"] is False
        assert m["unresolved_contradictions"] == 1

    def test_missing_citation_detected(self):
        # Body cites [cite: 99] but no Sources appendix defines it.
        content = (
            "## Section\n\n"
            + ("word " * 110)
            + "(Reported) claim [cite: 99].\nWhat to validate: x\n"
        )
        m = _compute_fast_report_qa_metrics(content)
        assert m["missing_citations"] == 1
        assert m["qa_gate_passed"] is False

    def test_thin_section_detected(self):
        content = "## Section\n\n(Reported) tiny.\nWhat to validate: x\n"
        m = _compute_fast_report_qa_metrics(content)
        assert m["thin_sections"] == 1

    def test_duplicate_sections_detected(self):
        body = ("word " * 110) + "(Reported)\nWhat to validate: x"
        content = f"## Same\n\n{body}\n\n## Same\n\n{body}"
        m = _compute_fast_report_qa_metrics(content)
        assert m["duplicate_sections"] >= 1

    def test_word_count_calculated(self):
        m = _compute_fast_report_qa_metrics("a b c d e")
        assert m["word_count"] == 5

    def test_empty_content(self):
        m = _compute_fast_report_qa_metrics("")
        assert m["word_count"] == 0
        assert m["section_count"] == 0
        assert m["qa_gate_passed"] is False


# ---------------------------------------------------------------------------
# _parse_batch_sections
# ---------------------------------------------------------------------------


class TestParseBatchSections:
    def test_parses_markdown_headings(self):
        content = "## A\n\nbody-a\n\n## B\n\nbody-b"
        expected = [_FakeSection(id="a", name="A"), _FakeSection(id="b", name="B")]
        result = _parse_batch_sections(content, expected)
        assert [s.title for s in result] == ["A", "B"]

    def test_parses_xml_envelopes(self):
        content = (
            "<section><title>A</title><body>body-a</body></section>"
            "<section><title>B</title><body>body-b</body></section>"
        )
        expected = [_FakeSection(id="a", name="A"), _FakeSection(id="b", name="B")]
        result = _parse_batch_sections(content, expected)
        assert [s.title for s in result] == ["A", "B"]

    def test_falls_back_to_full_content_when_no_blocks(self):
        content = "no headings here, just text body"
        expected = [_FakeSection(id="x", name="Fallback")]
        result = _parse_batch_sections(content, expected)
        assert len(result) == 1
        assert result[0].title == "Fallback"
        assert "no headings here" in result[0].content

    def test_preamble_prepended_to_first_section(self):
        content = "intro preamble\n\n## A\n\nbody-a"
        result = _parse_batch_sections(content, [_FakeSection(id="a", name="A")])
        assert "intro preamble" in result[0].content
        assert "body-a" in result[0].content

    def test_empty_content_returns_empty(self):
        assert _parse_batch_sections("", []) == []

    def test_more_blocks_than_expected_uses_block_title(self):
        content = "## A\n\nbody-a\n\n## Extra\n\nbody-e"
        expected = [_FakeSection(id="a", name="A")]  # only one expected
        result = _parse_batch_sections(content, expected)
        assert len(result) == 2
        # First uses expected_title 'A'
        assert result[0].title == "A"
        # Second falls back to the block's own title
        assert result[1].title == "Extra"


# ---------------------------------------------------------------------------
# _assemble_fast_report
# ---------------------------------------------------------------------------


@dataclass
class _FakeGenerated:
    title: str
    body: str = "body content"

    def to_markdown(self) -> str:
        return f"## {self.title}\n\n{self.body}"


class TestAssembleFastReport:
    def test_header_contains_company_name(self):
        report = _assemble_fast_report("Acme", "https://acme.example", [])
        assert "Strategic Company Overview: Acme" in report

    def test_website_link_included(self):
        report = _assemble_fast_report("Acme", "https://acme.example", [])
        assert "[https://acme.example](https://acme.example)" in report

    def test_no_website_omits_link(self):
        report = _assemble_fast_report("Acme", None, [])
        assert "](https" not in report  # no markdown link

    def test_sections_assembled_in_order(self):
        sections = [_FakeGenerated(title=f"S{i}") for i in range(3)]
        report = _assemble_fast_report("Acme", None, sections)
        # Order preserved
        s0 = report.index("S0")
        s1 = report.index("S1")
        s2 = report.index("S2")
        assert s0 < s1 < s2

    def test_horizontal_rule_every_five_sections(self):
        sections = [_FakeGenerated(title=f"S{i}") for i in range(11)]
        report = _assemble_fast_report("Acme", None, sections)
        # Header has one ---, then a separator after section 5 and 10 = 3 total
        assert report.count("---") >= 3

    def test_no_trailing_rule_after_last_section(self):
        sections = [_FakeGenerated(title=f"S{i}") for i in range(5)]
        report = _assemble_fast_report("Acme", None, sections)
        # Header has the ---, then exactly 5 sections, no trailing separator after S4
        # Count of --- = 1 (header) since (i+1)%5==0 and (i+1) < len is False at i=4
        assert report.count("---") == 1
