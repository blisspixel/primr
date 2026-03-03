"""
Tests for deterministic analysis methods in ReportAnalyzer.

Covers: analyze_hypothesis_coverage, analyze_confidence_labels,
analyze_section_lengths, analyze_citation_density, and
report-type-aware analyze_structure.
"""

import tempfile

from src.primr.qa.report_analyzer import ReportAnalyzer


def _make_analyzer(content: str, filename: str = "test_report.md") -> ReportAnalyzer:
    """Create a ReportAnalyzer from in-memory content."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=f"_{filename}", delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.close()
    return ReportAnalyzer(tmp.name)


# =============================================================================
# Hypothesis Coverage
# =============================================================================

class TestAnalyzeHypothesisCoverage:
    def test_counts_hypothesis_labels(self):
        content = (
            "## Section\n"
            "This is a (Hypothesis) and another (hypothesis) here.\n"
            "A third (Hypothesis) label.\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_hypothesis_coverage()
        assert result["hypothesis_labels"] == 3

    def test_counts_validation_phrases(self):
        content = (
            "## Section\n"
            "We hypothesize that X is true.\n"
            "This requires validation before proceeding.\n"
            "It is worth validating the claim.\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_hypothesis_coverage()
        assert result["validation_phrases"] == 3

    def test_total_signals_combines_labels_and_phrases(self):
        content = (
            "## Section\n"
            "(Hypothesis) We hypothesize this is true.\n"
            "To validate, we need more data.\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_hypothesis_coverage()
        assert result["total_signals"] == 3  # 1 label + 2 phrases

    def test_strategic_overview_threshold(self):
        content = "Company Overview\n" + "(Hypothesis) " * 5
        analyzer = _make_analyzer(content, "strategic_overview_report.md")
        result = analyzer.analyze_hypothesis_coverage()
        assert result["threshold"] == 5
        assert result["meets_threshold"] is True

    def test_ai_strategy_threshold(self):
        content = "AI Strategy\n" + "(Hypothesis) " * 3
        analyzer = _make_analyzer(content, "ai_strategy_report.md")
        result = analyzer.analyze_hypothesis_coverage()
        assert result["threshold"] == 3
        assert result["meets_threshold"] is True

    def test_unknown_type_threshold(self):
        content = "(Hypothesis) (Hypothesis)"
        analyzer = _make_analyzer(content, "misc.md")
        result = analyzer.analyze_hypothesis_coverage()
        assert result["threshold"] == 2
        assert result["meets_threshold"] is True

    def test_empty_report(self):
        analyzer = _make_analyzer("")
        result = analyzer.analyze_hypothesis_coverage()
        assert result["total_signals"] == 0
        assert result["meets_threshold"] is False


# =============================================================================
# Confidence Labels
# =============================================================================

class TestAnalyzeConfidenceLabels:
    def test_counts_all_four_label_types(self):
        content = (
            "(Confirmed) fact one\n"
            "(Reported) fact two\n"
            "(Estimated) number three\n"
            "(Hypothesis) guess four\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_confidence_labels()
        assert result["label_counts"]["confirmed"] == 1
        assert result["label_counts"]["reported"] == 1
        assert result["label_counts"]["estimated"] == 1
        assert result["label_counts"]["hypothesis"] == 1
        assert result["total_labels"] == 4

    def test_counts_hedging_phrases(self):
        content = (
            "This appears to be correct.\n"
            "It is worth exploring further.\n"
            "Signals suggest growth.\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_confidence_labels()
        assert result["hedging_phrases"] == 3

    def test_strategic_overview_threshold(self):
        content = "Company Overview\n" + "(Confirmed) " * 8
        analyzer = _make_analyzer(content, "strategic_overview_report.md")
        result = analyzer.analyze_confidence_labels()
        assert result["threshold"] == 8
        assert result["meets_threshold"] is True

    def test_below_threshold(self):
        content = "Company Overview\n(Confirmed) only one"
        analyzer = _make_analyzer(content, "strategic_overview_report.md")
        result = analyzer.analyze_confidence_labels()
        assert result["meets_threshold"] is False

    def test_empty_report(self):
        analyzer = _make_analyzer("")
        result = analyzer.analyze_confidence_labels()
        assert result["total_labels"] == 0


# =============================================================================
# Section Lengths
# =============================================================================

class TestAnalyzeSectionLengths:
    def test_detects_truncated_sections(self):
        content = (
            "# Title\n"
            "## Full Section\n"
            + "word " * 100
            + "\n## Short Section\n"
            "Just a few words.\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_section_lengths()
        assert "Short Section" in result["truncated_sections"]
        assert "Full Section" not in result["truncated_sections"]

    def test_no_false_positives_on_full_report(self):
        content = (
            "# Title\n"
            "## Section A\n" + "word " * 100 + "\n"
            "## Section B\n" + "word " * 80 + "\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_section_lengths()
        assert result["truncated_count"] == 0
        assert result["truncated_sections"] == []

    def test_counts_words_per_section(self):
        content = (
            "# Title\n"
            "## First\n" + "word " * 60 + "\n"
            "## Second\n" + "word " * 30 + "\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_section_lengths()
        assert len(result["sections"]) == 2
        assert result["sections"][0]["word_count"] >= 60
        assert result["sections"][1]["word_count"] >= 30

    def test_empty_report(self):
        analyzer = _make_analyzer("")
        result = analyzer.analyze_section_lengths()
        assert result["truncated_count"] == 0


# =============================================================================
# Citation Density
# =============================================================================

class TestAnalyzeCitationDensity:
    def test_counts_cite_patterns(self):
        content = "[cite: 1] text [cite: 2] more text " + "word " * 100
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_citation_density()
        assert result["total_citations"] == 2

    def test_counts_source_patterns(self):
        content = "[Source: Company] text [source: Report] " + "word " * 100
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_citation_density()
        assert result["total_citations"] == 2

    def test_density_calculation(self):
        # 10 citations in ~1000 words = density of ~10
        content = "[cite: 1] " * 10 + "word " * 990
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_citation_density()
        assert result["density_per_1000_words"] > 5.0

    def test_zero_word_edge_case(self):
        analyzer = _make_analyzer("")
        result = analyzer.analyze_citation_density()
        assert result["density_per_1000_words"] == 0.0

    def test_strategic_overview_threshold(self):
        content = "Company Overview\n" + "[cite: 1] " * 5 + "word " * 500
        analyzer = _make_analyzer(content, "strategic_overview_report.md")
        result = analyzer.analyze_citation_density()
        assert result["threshold"] == 3.0

    def test_ai_strategy_threshold(self):
        content = "AI Strategy\n" + "[cite: 1] " * 3 + "word " * 500
        analyzer = _make_analyzer(content, "ai_strategy_report.md")
        result = analyzer.analyze_citation_density()
        assert result["threshold"] == 2.0


# =============================================================================
# Structure (report-type-aware)
# =============================================================================

class TestAnalyzeStructureReportTypeAware:
    def test_strategic_overview_required_sections(self):
        content = (
            "Company Overview\n"
            "## Executive Summary\nText\n"
            "## Products and Services\nText\n"
            "## Target Customers\nText\n"
            "## Competitive Landscape\nText\n"
            "## Financial Performance\nText\n"
            "## SWOT Analysis\nText\n"
            "## Strategic Outlook\nText\n"
        )
        analyzer = _make_analyzer(content, "strategic_overview_report.md")
        result = analyzer.analyze_structure()
        assert result["report_type"] == "strategic_overview"
        assert len(result["key_sections_missing"]) == 0

    def test_ai_strategy_required_sections(self):
        content = (
            "AI Strategy\n"
            "## Executive Summary\nText\n"
            "## Current State Assessment\nText\n"
            "## Recommendations\nText\n"
            "## Implementation Roadmap\nText\n"
            "## Risk Analysis\nText\n"
        )
        analyzer = _make_analyzer(content, "ai_strategy_report.md")
        result = analyzer.analyze_structure()
        assert result["report_type"] == "ai_strategy"
        assert len(result["key_sections_missing"]) == 0

    def test_unknown_type_uses_minimal_sections(self):
        content = (
            "## Executive Summary\nText\n"
            "## Key Insights\nText\n"
            "## Sources\nText\n"
        )
        analyzer = _make_analyzer(content, "misc.md")
        result = analyzer.analyze_structure()
        assert result["report_type"] == "unknown"
        assert len(result["key_sections_missing"]) == 0

    def test_missing_sections_reported(self):
        content = "AI Strategy\n## Executive Summary\nText\n"
        analyzer = _make_analyzer(content, "ai_strategy_report.md")
        result = analyzer.analyze_structure()
        assert len(result["key_sections_missing"]) > 0
        assert "Current State" in result["key_sections_missing"]
