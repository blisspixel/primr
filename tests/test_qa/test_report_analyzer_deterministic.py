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
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
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
            "This appears to be correct.\nIt is worth exploring further.\nSignals suggest growth.\n"
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
            "# Title\n## Full Section\n" + "word " * 100 + "\n## Short Section\nJust a few words.\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_section_lengths()
        assert "Short Section" in result["truncated_sections"]
        assert "Full Section" not in result["truncated_sections"]

    def test_no_false_positives_on_full_report(self):
        content = (
            "# Title\n## Section A\n" + "word " * 100 + "\n## Section B\n" + "word " * 80 + "\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_section_lengths()
        assert result["truncated_count"] == 0
        assert result["truncated_sections"] == []

    def test_counts_words_per_section(self):
        content = "# Title\n## First\n" + "word " * 60 + "\n## Second\n" + "word " * 30 + "\n"
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
        content = "## Executive Summary\nText\n## Key Insights\nText\n## Sources\nText\n"
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


# =============================================================================
# Scaffolding Leakage Detection
# =============================================================================


class TestAnalyzeScaffoldingLeakage:
    """Tests for analyze_scaffolding_leakage() — shipping-artifact validation."""

    def test_clean_report_reports_zero_leakage(self):
        content = (
            "## Executive Summary\n\n"
            "Strong revenue growth (Reported) [cite: 1].\n\n"
            "What to validate: Confirm 2026 ARR.\n\n"
            "## Sources\n\n[cite: 1] https://example.com/a\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_scaffolding_leakage()
        assert result["total_leaked"] == 0
        assert result["clean"] is True

    def test_detects_bare_and_separated_workbook_markers(self):
        content = (
            "## Section\n\n"
            "Trend (2026 [workbook]) and note [workbook ARDA/prior] and [Workbook: Profile].\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_scaffolding_leakage()
        assert result["workbook_markers"] == 3
        assert result["clean"] is False

    def test_detects_cross_ref_variants(self):
        content = (
            "## Section\n\n"
            "See [cross-ref Financial Profile] and [cross-ref: SWOT] and [cross-ref].\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_scaffolding_leakage()
        assert result["cross_ref_markers"] == 3

    def test_detects_bold_validate_line(self):
        content = (
            "## Section\n\nBody text.\n\n"
            "**What to validate:** Confirm revenue.\n\n"
            "## Other\n\nMore body.\n\n**What to validate:**\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_scaffolding_leakage()
        assert result["bare_bold_validate"] == 2

    def test_detects_informal_cite_labels(self):
        content = "## Section\n\nClaim [cite: workbook] and [cite: bbb] but [cite: 1] is fine.\n"
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_scaffolding_leakage()
        assert result["informal_cite_markers"] == 2

    def test_total_leaked_sums_all_categories(self):
        content = (
            "## Section\n\n"
            "Note [workbook] and [cross-ref X] and [cite: workbook].\n\n"
            "**What to validate:** Q?\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_scaffolding_leakage()
        assert result["total_leaked"] == 4
        assert result["clean"] is False


# =============================================================================
# URLs and Sources Categorization
# =============================================================================


class TestAnalyzeUrlsAndSources:
    """Tests for analyze_urls_and_sources() — derives primary host generically."""

    def test_empty_content_returns_zero_urls(self):
        analyzer = _make_analyzer("## Section\n\nNo URLs here.\n")
        result = analyzer.analyze_urls_and_sources()
        assert result["total_urls"] == 0
        assert result["primary_host"] == ""
        assert result["url_categories"]["primary_host"] == 0

    def test_primary_host_derived_from_most_cited_first_party_domain(self):
        # Three citations to acme.example, one to a news site, one to LinkedIn.
        # primary_host should reflect the dominant first-party domain.
        content = (
            "## Section\n\n"
            "First [Source: https://acme.example/about].\n"
            "Second [Source: https://acme.example/products].\n"
            "Third [Source: https://acme.example/team].\n"
            "Fourth [Source: https://reuters.com/article].\n"
            "Fifth [Source: https://linkedin.com/in/ceo].\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_urls_and_sources()
        assert result["primary_host"] == "acme.example"
        assert result["url_categories"]["primary_host"] == 3
        assert result["url_categories"]["news_sources"] == 1
        assert result["url_categories"]["linkedin"] == 1

    def test_www_prefix_stripped_from_host(self):
        # The www. prefix must be stripped via removeprefix, not lstrip
        # (lstrip would also strip leading w/. chars from other hostnames).
        content = (
            "## Section\n\n"
            "One https://www.acme.example/a and\n"
            "two https://www.acme.example/b\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_urls_and_sources()
        assert result["primary_host"] == "acme.example"
        assert result["url_categories"]["primary_host"] == 2

    def test_hostname_with_leading_w_not_stripped(self):
        # Regression check for the lstrip("www.") bug: a host starting with
        # 'w' but not 'www.' must keep its leading 'w'. lstrip would have
        # turned wood.example into ood.example.
        content = "## Section\n\nSee https://wood.example/page for detail.\n"
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_urls_and_sources()
        assert result["primary_host"] == "wood.example"

    def test_only_news_and_linkedin_means_no_primary_host(self):
        content = (
            "## Section\n\n"
            "https://reuters.com/a and https://bloomberg.com/b and\n"
            "https://linkedin.com/c\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_urls_and_sources()
        # Neither news nor linkedin counts toward the primary host derivation.
        assert result["primary_host"] == ""
        assert result["url_categories"]["primary_host"] == 0
        assert result["url_categories"]["news_sources"] == 2
        assert result["url_categories"]["linkedin"] == 1


# =============================================================================
# Citation Analysis
# =============================================================================


class TestAnalyzeCitations:
    """Tests for analyze_citations() — citation reference and bibliography parsing."""

    def test_no_citations_returns_zero(self):
        analyzer = _make_analyzer("## Section\n\nNo citations here.\n")
        result = analyzer.analyze_citations()
        assert result["total_references"] == 0
        assert result["unique_citations"] == 0
        assert result["has_bibliography"] is False
        assert result["citation_coverage"] == 0

    def test_counts_unique_citation_references(self):
        content = (
            "## Section\n\n"
            "Claim A [cite: 1].\nClaim B [cite: 2, 3].\nClaim C [cite: 1].\n"
            "## Sources\n\n[cite: 1] https://a.example\n[cite: 2] https://b.example\n[cite: 3] https://c.example\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_citations()
        # total_references counts every [cite: ...] match across the document
        # including the bibliography entries: 3 body + 3 sources = 6.
        assert result["total_references"] == 6
        assert result["unique_citations"] == 3  # numbers 1, 2, 3
        assert result["has_bibliography"] is True
        assert result["citation_coverage"] == 1.0
        assert result["missing_citations"] == []

    def test_missing_citation_reported(self):
        content = (
            "## Section\n\nClaim [cite: 1] and [cite: 99].\n"
            "## Sources\n\n[cite: 1] https://a.example\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_citations()
        assert 99 in result["missing_citations"]
        assert result["citation_coverage"] < 1.0


# =============================================================================
# Content Quality
# =============================================================================


class TestAnalyzeContentQuality:
    """Tests for analyze_content_quality() — word counts, frameworks, confidence."""

    def test_word_count_and_page_estimate(self):
        # 500 words = 1 page in the analyzer's heuristic.
        content = "## Section\n\n" + ("word " * 500)
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_content_quality()
        # Expect word_count near 500 plus the heading line tokens.
        assert result["word_count"] >= 500
        assert result["estimated_pages"] >= 1.0

    def test_detects_strategic_frameworks(self):
        content = (
            "## SWOT Analysis\n\nStrengths.\n"
            "## Porter's Five Forces\n\nForces.\n"
            "## Value Chain\n\nValue.\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_content_quality()
        assert result["strategic_frameworks"]["SWOT"] is True
        assert result["strategic_frameworks"]["Porter"] is True
        assert result["strategic_frameworks"]["Value Chain"] is True
        assert result["frameworks_used"] == 3

    def test_confidence_indicator_counts(self):
        content = (
            "## Section\n\n"
            "(Confirmed: by 10-K) and (Reported: by press release) and "
            "(Estimated: from comp set) and (Hypothesis).\n"
        )
        analyzer = _make_analyzer(content)
        result = analyzer.analyze_content_quality()
        assert result["confidence_indicators"]["confirmed"] >= 1
        assert result["confidence_indicators"]["reported"] >= 1
        assert result["confidence_indicators"]["estimated"] >= 1
        assert result["confidence_indicators"]["hypothesis"] >= 1


# =============================================================================
# Full Report Generation Smoke Test
# =============================================================================


class TestGenerateReport:
    """Smoke test: generate_report() executes end-to-end on a realistic doc."""

    def test_generate_report_runs_on_strategic_overview(self):
        content = (
            "# Acme Corp Strategic Overview\n\n"
            "## Executive Summary\n\nSummary text. (Hypothesis) We hypothesize growth. (Reported).\n\n"
            "What to validate: Confirm ARR.\n\n"
            "## Products and Services\n\nProduct lineup. " + ("word " * 80) + "\n\n"
            "## Target Customers\n\nCustomer base. " + ("word " * 80) + "\n\n"
            "## Competitive Landscape\n\nCompetitors. " + ("word " * 80) + "\n\n"
            "## Financial Profile\n\nFinancials. " + ("word " * 80) + "\n\n"
            "## SWOT Analysis\n\nSWOT. " + ("word " * 80) + "\n\n"
            "## Strategic Outlook\n\nOutlook. " + ("word " * 80) + "\n\n"
            "## Sources\n\n[cite: 1] https://acme.example/about\n"
        )
        analyzer = _make_analyzer(content, "strategic_overview_report.md")
        report = analyzer.generate_report()
        assert "# Report Quality Analysis" in report
        assert "Overall Quality Score" in report
        assert "Citation Analysis" in report

    def test_generate_report_surfaces_scaffolding_warnings(self):
        # A report with leaked markers must surface the new warning block.
        content = (
            "## Executive Summary\n\nText [workbook] and [cross-ref X].\n\n"
            "**What to validate:** Q?\n\n## Sources\n\n[cite: 1] https://a.example\n"
        )
        analyzer = _make_analyzer(content, "strategic_overview_report.md")
        report = analyzer.generate_report()
        assert "SCAFFOLDING LEAKS" in report
        assert "[workbook] markers" in report
        assert "[cross-ref ...] markers" in report
