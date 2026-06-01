"""Unit tests for primr.core.report_cleanup.

These cover the pure string-transform helpers extracted from research_agent
so the cleanup logic can be exercised directly without spinning up the rest
of the pipeline.
"""

from __future__ import annotations

import pytest

from primr.core.report_cleanup import (
    _INTERNAL_REFERENCE_TERMS,
    _clean_fast_report_output,
    _extract_markdown_headings,
    _preserves_report_structure,
    _rewrite_cite_from_url_tags,
    _rewrite_inline_confidence_citations,
    _sanitize_numeric_cite_bracket,
    _strip_internal_source_placeholders,
    _strip_unresolved_section_cross_references,
    compute_repair_report,
)


class TestSanitizeNumericCiteBracket:
    def test_extracts_single_id(self):
        assert _sanitize_numeric_cite_bracket("cite: 3") == "[cite: 3]"

    def test_extracts_multiple_ids(self):
        assert _sanitize_numeric_cite_bracket("cite: 1, 2, 3") == "[cite: 1, 2, 3]"

    def test_dedupes_repeated_ids(self):
        assert _sanitize_numeric_cite_bracket("cite: 1; cite: 1, 2") == "[cite: 1, 2]"

    def test_returns_empty_when_no_ids(self):
        assert _sanitize_numeric_cite_bracket("cite: workbook") == ""

    def test_returns_empty_on_garbage(self):
        assert _sanitize_numeric_cite_bracket("nothing here") == ""

    def test_handles_plural_cites(self):
        assert _sanitize_numeric_cite_bracket("cites: 4") == "[cite: 4]"


class TestRewriteInlineConfidenceCitations:
    def test_rewrites_with_detail(self):
        content = "[Confirmed: 12% growth [cite: 1 from https://example.com/q3]]"
        result = _rewrite_inline_confidence_citations(content)
        assert "(Confirmed: 12% growth)" in result
        assert "[Source: https://example.com/q3]" in result

    def test_rewrites_without_detail(self):
        content = "[Reported:  [cite: 2 from https://example.com/r]]"
        result = _rewrite_inline_confidence_citations(content)
        assert "(Reported)" in result
        assert "[Source: https://example.com/r]" in result

    def test_unmatched_passthrough(self):
        content = "regular text without nested citation"
        assert _rewrite_inline_confidence_citations(content) == content


class TestRewriteCiteFromUrlTags:
    def test_rewrites_url_tag(self):
        content = "see [cite: 1 from https://example.com/a]"
        assert "[Source: https://example.com/a]" in _rewrite_cite_from_url_tags(content)

    def test_no_change_when_no_url_tag(self):
        content = "plain [cite: 1]"
        assert _rewrite_cite_from_url_tags(content) == content


class TestCleanFastReportOutput:
    def test_empty_input(self):
        assert _clean_fast_report_output("") == ""

    def test_whitespace_only_returned_as_is(self):
        assert _clean_fast_report_output("   ") == "   "

    def test_strips_grok_disclaimer(self):
        content = "Real report content.\n\n_Disclaimer: Grok is not a financial adviser._"
        result = _clean_fast_report_output(content)
        assert "Grok is not a financial" not in result
        assert "Real report content" in result

    def test_strips_standalone_confidence_label(self):
        content = "Some text.\n\n(Reported)\n\nMore text.\n"
        result = _clean_fast_report_output(content)
        assert "(Reported)" not in result

    def test_preserves_inline_confidence_label(self):
        # Inline labels within prose should be preserved (they're not on their own line).
        content = "ARR grew 12% (Reported) over the period.\n"
        result = _clean_fast_report_output(content)
        assert "(Reported)" in result

    def test_strips_informal_cites(self):
        content = "Some claim [cite: workbook] about growth."
        result = _clean_fast_report_output(content)
        assert "[cite: workbook]" not in result

    def test_preserves_numeric_cites(self):
        content = "Some claim [cite: 1] about growth."
        result = _clean_fast_report_output(content)
        assert "[cite: 1]" in result

    def test_strips_cross_ref_tags(self):
        for variant in ("[cross-ref: Strategy]", "[cross-ref Strategy]", "[cross-ref]"):
            content = f"See {variant} for details."
            result = _clean_fast_report_output(content)
            assert "cross-ref" not in result.lower()

    def test_strips_citation_inventory(self):
        content = "Report.\n[citation inventory: 1-12]\nMore."
        result = _clean_fast_report_output(content)
        assert "citation inventory" not in result.lower()

    def test_strips_workbook_markers(self):
        for variant in (
            "[workbook]",
            "[Workbook: section 2]",
            "[workbook §7]",
            "[workbook ARDA/prior]",
        ):
            content = f"Detail {variant} here."
            result = _clean_fast_report_output(content)
            assert "workbook" not in result.lower(), f"failed for variant {variant}"

    def test_strips_analysis_workbook_phrase(self):
        result = _clean_fast_report_output("See Analysis Workbook for context.")
        assert "Analysis Workbook" not in result

    def test_strips_external_sources_marker(self):
        result = _clean_fast_report_output("Background [External Sources] note.")
        assert "[External Sources]" not in result

    def test_strips_vendor_research_filename(self):
        result = _clean_fast_report_output("From vendor-research-acme.txt details.")
        assert "vendor-research" not in result

    def test_strips_internal_roi_and_analysis_phrases(self):
        result = _clean_fast_report_output(
            "Per Internal ROI Model and Internal Analysis, growth..."
        )
        assert "Internal ROI Model" not in result
        assert "Internal Analysis" not in result

    def test_strips_word_count_meta(self):
        result = _clean_fast_report_output("Text [Word count: 1,028] here.")
        assert "Word count" not in result

    def test_collapses_double_spaces(self):
        result = _clean_fast_report_output("multiple    spaces here")
        assert "    " not in result

    def test_collapses_excess_blank_lines(self):
        result = _clean_fast_report_output("a\n\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_trailing_newline_added(self):
        result = _clean_fast_report_output("just text")
        assert result.endswith("\n")

    def test_cross_ref_bounded_against_redos(self):
        # Pathological unclosed bracket should not hang.
        bad = "[cross-ref " + ("x" * 5000)
        # Just assert it returns in reasonable time (pytest default timeout suffices).
        result = _clean_fast_report_output(bad)
        assert isinstance(result, str)


class TestStripInternalSourcePlaceholders:
    def test_drops_workbook_reference(self):
        content = "Stat here [Reported: Analysis Workbook]"
        result = _strip_internal_source_placeholders(content)
        assert "Workbook" not in result

    def test_drops_internal_roi_reference(self):
        content = "Stat here [Confirmed: Internal ROI Model]"
        result = _strip_internal_source_placeholders(content)
        assert "Internal ROI" not in result

    def test_keeps_external_reference(self):
        content = "Stat here [Confirmed: Q3 earnings call]"
        result = _strip_internal_source_placeholders(content)
        assert "[Confirmed: Q3 earnings call]" in result

    def test_drops_empty_bracket(self):
        content = "Stat here [Reported: ]"
        result = _strip_internal_source_placeholders(content)
        assert "[Reported:" not in result

    def test_drops_citation_inventory(self):
        result = _strip_internal_source_placeholders("Text [citation inventory: 1-3] more.")
        assert "citation inventory" not in result.lower()

    def test_collapses_excess_newlines(self):
        result = _strip_internal_source_placeholders("a\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_empty_passes_through(self):
        assert _strip_internal_source_placeholders("") == ""
        assert _strip_internal_source_placeholders("   ") == "   "


class TestStripUnresolvedSectionCrossReferences:
    def test_strips_see_reference(self):
        result = _strip_unresolved_section_cross_references("Detail [see ## Strategy] here.")
        assert "## Strategy" not in result

    def test_strips_xref(self):
        result = _strip_unresolved_section_cross_references("Detail [xref ## Other] here.")
        assert "xref" not in result.lower()

    def test_strips_cross_ref_variant(self):
        result = _strip_unresolved_section_cross_references("[cross-ref ## Section] here")
        assert "cross-ref" not in result.lower()

    def test_empty_passes(self):
        assert _strip_unresolved_section_cross_references("") == ""

    def test_no_change_when_no_markers(self):
        original = "Plain text without any markers."
        assert _strip_unresolved_section_cross_references(original) == original


class TestExtractMarkdownHeadings:
    def test_extracts_ordered_headings(self):
        content = "## First\n\ntext\n\n## Second\n\nmore\n\n## Third"
        assert _extract_markdown_headings(content) == ["First", "Second", "Third"]

    def test_ignores_h1_and_h3(self):
        content = "# Title\n## Real\n### Sub"
        assert _extract_markdown_headings(content) == ["Real"]

    def test_returns_empty_for_no_headings(self):
        assert _extract_markdown_headings("no headings here") == []

    def test_strips_trailing_whitespace(self):
        assert _extract_markdown_headings("## Spaced   ") == ["Spaced"]


class TestPreservesReportStructure:
    def test_identical_passes(self):
        content = "## A\n\nbody " * 50
        assert _preserves_report_structure(content, content) is True

    def test_appended_sources_section_allowed(self):
        original = "## A\n\n" + "word " * 100
        candidate = original + "\n## Sources\n\nfoo bar"
        assert _preserves_report_structure(original, candidate) is True

    def test_appended_random_heading_rejected(self):
        original = "## A\n\n" + "word " * 100
        candidate = original + "\n## RandomNewSection\n\nfoo"
        assert _preserves_report_structure(original, candidate) is False

    def test_reordered_headings_rejected(self):
        original = "## A\n\nx " * 50 + "\n## B\n\ny " * 50
        candidate = "## B\n\ny " * 50 + "\n## A\n\nx " * 50
        assert _preserves_report_structure(original, candidate) is False

    def test_too_few_words_rejected(self):
        original = "## A\n\n" + ("word " * 100)
        candidate = "## A\n\nshort"
        assert _preserves_report_structure(original, candidate) is False

    def test_empty_original_rejected(self):
        assert _preserves_report_structure("", "## A\nbody") is False


def test_internal_reference_terms_is_tuple_of_strings():
    assert isinstance(_INTERNAL_REFERENCE_TERMS, tuple)
    assert all(isinstance(t, str) for t in _INTERNAL_REFERENCE_TERMS)
    assert "workbook" in _INTERNAL_REFERENCE_TERMS


@pytest.mark.parametrize(
    "marker",
    ["[workbook]", "[Workbook: x]", "[workbook §7]"],
)
def test_clean_fast_report_output_workbook_variants_param(marker):
    cleaned = _clean_fast_report_output(f"text {marker} more")
    assert "workbook" not in cleaned.lower()


class TestComputeRepairReport:
    """The repair-observability signal behind 'push consistency upstream'."""

    def test_clean_writer_output_needs_no_repair(self):
        text = "## Summary\n\nClean prose. [cite: 1]\n\n## Sources\n[cite: 1] https://a.example\n"
        report = compute_repair_report(text, text)
        assert report["writer_output_clean"] is True
        assert report["scaffolding_before"] == 0
        assert report["scaffolding_removed"] == 0
        assert report["chars_removed"] == 0
        assert report["changed"] is False

    def test_dirty_writer_output_is_measured(self):
        before = (
            "## Summary\n\nMargins are thin [workbook] and see [cross-ref ## Risks] for more.\n"
        )
        after = _clean_fast_report_output(before)
        report = compute_repair_report(before, after)
        assert report["writer_output_clean"] is False
        assert report["scaffolding_before"] >= 2  # [workbook] + [cross-ref ...]
        assert report["scaffolding_removed"] >= 2
        assert report["chars_removed"] > 0
        assert report["changed"] is True

    def test_counts_never_go_negative(self):
        # If 'after' is somehow longer/cleaner, removed counts clamp at 0.
        report = compute_repair_report("x", "x with much more appended content here")
        assert report["chars_removed"] == 0
        assert report["scaffolding_removed"] == 0
