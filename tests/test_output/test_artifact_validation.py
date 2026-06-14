"""Unit tests for primr.output.artifact_validation.

Direct tests on the forbidden-pattern scanner / auto-strip / validation
fail-closed behavior that ships every final artifact through.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from primr.output.artifact_validation import (
    _DANGLING_CITATION_THRESHOLD_ENV,
    _FORBIDDEN_INTERNAL_TERMS,
    _FORBIDDEN_OUTPUT_CLEANERS,
    _FORBIDDEN_OUTPUT_PATTERNS,
    _SCAFFOLDING_LEAK_THRESHOLD_ENV,
    _STRUCTURE_DEFECT_THRESHOLD_ENV,
    _auto_strip_forbidden_patterns,
    _dangling_citation_threshold,
    _extract_docx_text,
    _scaffolding_leak_threshold,
    _scan_citation_integrity_issues,
    _scan_forbidden_output_patterns,
    _scan_scaffolding_leakage_issues,
    _scan_section_structure_issues,
    _structure_defect_threshold,
    _validate_output_docx,
    _validate_output_markdown,
    _write_output_validation_report,
)


class TestForbiddenPatternConstants:
    def test_patterns_and_cleaners_share_labels(self):
        pattern_labels = {label for label, _ in _FORBIDDEN_OUTPUT_PATTERNS}
        cleaner_labels = {label for label, _ in _FORBIDDEN_OUTPUT_CLEANERS}
        assert pattern_labels == cleaner_labels, (
            "Every detector pattern must have a matching cleaner — see the "
            "_FORBIDDEN_OUTPUT_PATTERNS/_FORBIDDEN_OUTPUT_CLEANERS comment."
        )

    def test_patterns_have_string_regex(self):
        for label, pattern in _FORBIDDEN_OUTPUT_PATTERNS:
            assert isinstance(label, str)
            assert label
            assert isinstance(pattern, str)
            assert pattern

    def test_internal_terms_lowercase(self):
        for term in _FORBIDDEN_INTERNAL_TERMS:
            assert term == term.lower(), "scanner uses lower() — terms must be pre-lowered"


class TestScanForbiddenOutputPatterns:
    def test_clean_text_returns_empty(self):
        assert _scan_forbidden_output_patterns("Just a clean report.") == []

    def test_raw_source_tag_detected(self):
        issues = _scan_forbidden_output_patterns("body [Source: https://example.com] more")
        assert any(i.startswith("raw_source_tag:") for i in issues)

    def test_workbook_ref_detected(self):
        issues = _scan_forbidden_output_patterns("Per [Workbook: section 3]")
        assert any(i.startswith("workbook_ref:") for i in issues)

    def test_analysis_workbook_detected(self):
        issues = _scan_forbidden_output_patterns("Per [Analysis Workbook entry]")
        assert any(i.startswith("analysis_workbook_ref:") for i in issues)

    def test_internal_roi_label_detected(self):
        # The leaked Title-Case workbook label is caught.
        issues = _scan_forbidden_output_patterns("From Internal ROI Model assumption")
        assert any(i.startswith("internal_roi_model:") for i in issues)

    def test_analysis_context_label_detected(self):
        issues = _scan_forbidden_output_patterns("See Analysis Context for details")
        assert any(i.startswith("analysis_context:") for i in issues)

    def test_lowercase_prose_is_not_false_blocked(self):
        # Legitimate lowercase prose must NOT trip the leaked-label scan
        # (agentic-balance: don't gate real content). Case-sensitive by design.
        issues = _scan_forbidden_output_patterns(
            "Based on our internal analysis and the analysis context, the internal "
            "ROI model suggests upside."
        )
        assert issues == []

    def test_vendor_research_file_detected(self):
        issues = _scan_forbidden_output_patterns("from vendor-research-acme.txt note")
        assert any(i.startswith("vendor_research_file:") for i in issues)

    def test_cross_ref_detected(self):
        issues = _scan_forbidden_output_patterns("[see ## Strategy] mid-text")
        assert any(i.startswith("section_cross_ref:") for i in issues)

    def test_first_match_only_per_pattern(self):
        # Multiple occurrences of one pattern should only emit one issue (the scanner
        # uses re.search, not findall).
        text = "[Source: https://example.com/a] and [Source: https://example.com/b]"
        issues = _scan_forbidden_output_patterns(text)
        source_issues = [i for i in issues if i.startswith("raw_source_tag:")]
        assert len(source_issues) == 1

    def test_external_sources_marker_detected(self):
        issues = _scan_forbidden_output_patterns("background [External Sources] note")
        assert any(i.startswith("external_sources_ref:") for i in issues)

    def test_match_text_truncated_to_120_chars(self):
        long_url = "https://example.com/" + ("x" * 500)
        issues = _scan_forbidden_output_patterns(f"[Source: {long_url}]")
        for i in issues:
            if i.startswith("raw_source_tag:"):
                # ~ "raw_source_tag: <up to 120 of the match>"
                _, _, match_text = i.partition(": ")
                assert len(match_text) <= 120


class TestAutoStripForbiddenPatterns:
    def test_empty_unchanged(self):
        assert _auto_strip_forbidden_patterns("") == ""

    def test_whitespace_only_passes(self):
        assert _auto_strip_forbidden_patterns("   ") == "   "

    def test_strips_source_tag(self):
        result = _auto_strip_forbidden_patterns("body [Source: https://example.com] more")
        assert "[Source:" not in result
        assert "body" in result
        assert "more" in result

    def test_strips_workbook_ref(self):
        result = _auto_strip_forbidden_patterns("From [Workbook: section 3] context")
        assert "Workbook" not in result

    def test_strips_leaked_titlecase_label(self):
        # The Title-Case leaked label is stripped...
        result = _auto_strip_forbidden_patterns("See Analysis Context for detail")
        assert "Analysis Context" not in result

    def test_preserves_lowercase_prose(self):
        # ...but legitimate lowercase prose is left intact (no mangling).
        text = "Based on our internal analysis in the analysis context here."
        result = _auto_strip_forbidden_patterns(text)
        assert "internal analysis" in result
        assert "analysis context" in result

    def test_collapses_double_spaces(self):
        result = _auto_strip_forbidden_patterns("a  b   c")
        assert "  " not in result

    def test_collapses_excess_blank_lines(self):
        result = _auto_strip_forbidden_patterns("a\n\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_strips_multiple_pattern_types(self):
        text = (
            "From [Workbook: x] using Internal ROI Model — see "
            "[Source: https://example.com] and [Analysis: y]"
        )
        result = _auto_strip_forbidden_patterns(text)
        # All four pattern types removed
        for marker in ("Workbook", "Internal ROI", "[Source:", "[Analysis:"):
            assert marker not in result

    def test_idempotent_on_clean_content(self):
        clean = "Just regular report prose with no markers."
        assert _auto_strip_forbidden_patterns(clean) == clean


class TestValidateOutputMarkdown:
    def test_clean_passes(self):
        result = _validate_output_markdown("Clean report content.")
        assert result["passed"] is True
        assert result["issues"] == []
        assert result["errors"] == []

    def test_dirty_fails_with_issues(self):
        result = _validate_output_markdown("With [Source: https://example.com] leak")
        assert result["passed"] is False
        assert len(result["issues"]) >= 1
        assert result["errors"] == []

    def test_exception_inside_scanner_fails_closed(self):
        with patch(
            "primr.output.artifact_validation._scan_forbidden_output_patterns",
            side_effect=RuntimeError("scanner boom"),
        ):
            result = _validate_output_markdown("anything")
        assert result["passed"] is False
        # Fail-closed: empty issues, exception recorded in errors
        assert result["issues"] == []
        assert result["errors"] == ["scanner boom"]


class TestScaffoldingLeakThreshold:
    def test_default_is_zero(self, monkeypatch):
        monkeypatch.delenv(_SCAFFOLDING_LEAK_THRESHOLD_ENV, raising=False)
        assert _scaffolding_leak_threshold() == 0

    def test_reads_valid_int(self, monkeypatch):
        monkeypatch.setenv(_SCAFFOLDING_LEAK_THRESHOLD_ENV, "3")
        assert _scaffolding_leak_threshold() == 3

    def test_negative_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv(_SCAFFOLDING_LEAK_THRESHOLD_ENV, "-5")
        assert _scaffolding_leak_threshold() == 0

    def test_garbage_falls_back_to_zero(self, monkeypatch):
        # Must never silently disable the gate via a bad env value.
        monkeypatch.setenv(_SCAFFOLDING_LEAK_THRESHOLD_ENV, "lots")
        assert _scaffolding_leak_threshold() == 0


class TestScanScaffoldingLeakageIssues:
    def test_clean_returns_empty(self):
        assert _scan_scaffolding_leakage_issues("Clean report prose.", 0) == []

    def test_bold_validate_over_threshold_flags(self):
        issues = _scan_scaffolding_leakage_issues("**What to validate:** the TAM", 0)
        assert any(i.startswith("scaffolding_leak:total=") for i in issues)
        assert any("bold_validate_lines=1" in i for i in issues)

    def test_bare_workbook_marker_flags(self):
        issues = _scan_scaffolding_leakage_issues("Per [workbook] the margin is thin.", 0)
        assert any("workbook_markers=1" in i for i in issues)

    def test_informal_cite_flags(self):
        issues = _scan_scaffolding_leakage_issues("Revenue grew [cite: workbook] sharply.", 0)
        assert any("informal_cite_markers=1" in i for i in issues)

    def test_within_threshold_passes(self):
        # One leak, threshold 1 -> not over threshold -> no issues.
        assert _scan_scaffolding_leakage_issues("Per [workbook] note.", 1) == []

    def test_numeric_cite_not_flagged(self):
        # Real numeric citations are legitimate, not scaffolding.
        assert _scan_scaffolding_leakage_issues("Revenue grew [cite: 12] sharply.", 0) == []


class TestValidateOutputMarkdownScaffolding:
    def test_leak_is_nonblocking_warning(self, monkeypatch):
        # A scaffolding leak is a content signal, not a ship blocker
        # (agentic-balance: gate structure/acts, not content). It surfaces as a
        # warning and the artifact still passes.
        monkeypatch.delenv(_SCAFFOLDING_LEAK_THRESHOLD_ENV, raising=False)
        result = _validate_output_markdown("intro\n**What to validate:** the ARR claim")
        assert result["passed"] is True
        assert result["issues"] == []
        assert any(w.startswith("scaffolding_leak:") for w in result["warnings"])

    def test_env_threshold_suppresses_warning(self, monkeypatch):
        monkeypatch.setenv(_SCAFFOLDING_LEAK_THRESHOLD_ENV, "1")
        # Exactly one leak, threshold 1 -> not even a warning.
        result = _validate_output_markdown("intro\n**What to validate:** the ARR claim")
        assert result["passed"] is True
        assert result["issues"] == []
        assert result["warnings"] == []

    def test_explicit_threshold_arg_overrides_env(self, monkeypatch):
        monkeypatch.setenv(_SCAFFOLDING_LEAK_THRESHOLD_ENV, "9")
        result = _validate_output_markdown(
            "intro\n**What to validate:** x", scaffolding_threshold=0
        )
        # threshold=0 surfaces the leak as a warning; it is non-blocking, so the
        # artifact still passes (content findings never withhold the deliverable).
        assert result["passed"] is True
        assert any(w.startswith("scaffolding_leak:") for w in result["warnings"])

    def test_clean_still_passes(self, monkeypatch):
        monkeypatch.delenv(_SCAFFOLDING_LEAK_THRESHOLD_ENV, raising=False)
        result = _validate_output_markdown("A clean strategic report.")
        assert result["passed"] is True
        assert result["issues"] == []


class TestDanglingCitationThreshold:
    def test_default_is_zero(self, monkeypatch):
        monkeypatch.delenv(_DANGLING_CITATION_THRESHOLD_ENV, raising=False)
        assert _dangling_citation_threshold() == 0

    def test_reads_valid_int(self, monkeypatch):
        monkeypatch.setenv(_DANGLING_CITATION_THRESHOLD_ENV, "2")
        assert _dangling_citation_threshold() == 2

    def test_negative_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv(_DANGLING_CITATION_THRESHOLD_ENV, "-1")
        assert _dangling_citation_threshold() == 0

    def test_garbage_falls_back_to_zero(self, monkeypatch):
        monkeypatch.setenv(_DANGLING_CITATION_THRESHOLD_ENV, "all")
        assert _dangling_citation_threshold() == 0


class TestScanCitationIntegrityIssues:
    RESOLVED = "Revenue grew [cite: 1].\n\n## Sources\n[cite: 1] https://example.com/a\n"

    def test_resolved_citations_pass(self):
        assert _scan_citation_integrity_issues(self.RESOLVED, 0) == []

    def test_no_citations_pass(self):
        assert _scan_citation_integrity_issues("A clean report with no citations.", 0) == []

    def test_dangling_citation_flagged(self):
        text = "Revenue grew [cite: 2].\n\n## Sources\n[cite: 1] https://example.com/a\n"
        issues = _scan_citation_integrity_issues(text, 0)
        assert any(i.startswith("citation_integrity:dangling=1") for i in issues)
        assert any("unresolved: 2" in i for i in issues)

    def test_inline_cites_without_appendix_flagged(self):
        issues = _scan_citation_integrity_issues("Revenue grew [cite: 1] sharply.", 0)
        assert any("no Sources appendix" in i for i in issues)

    def test_grouped_inline_citation_resolved(self):
        text = (
            "Margins compressed [cite: 1, 2].\n\n"
            "## Sources\n[cite: 1] https://a.example\n[cite: 2] https://b.example\n"
        )
        assert _scan_citation_integrity_issues(text, 0) == []

    def test_lenient_appendix_heading(self):
        # "## Sources Consulted" should still count as the appendix (no false block).
        text = "Claim [cite: 1].\n\n## Sources Consulted\n[cite: 1] https://a.example\n"
        assert _scan_citation_integrity_issues(text, 0) == []

    def test_within_threshold_passes(self):
        text = "A [cite: 9] claim.\n\n## Sources\n[cite: 1] https://a.example\n"
        assert _scan_citation_integrity_issues(text, 1) == []


class TestValidateOutputMarkdownCitations:
    def test_dangling_blocks_by_default(self, monkeypatch):
        monkeypatch.delenv(_DANGLING_CITATION_THRESHOLD_ENV, raising=False)
        result = _validate_output_markdown(
            "Claim [cite: 5].\n\n## Sources\n[cite: 1] https://a.example\n"
        )
        assert result["passed"] is False
        assert any(i.startswith("citation_integrity:") for i in result["issues"])

    def test_env_threshold_relaxes_gate(self, monkeypatch):
        monkeypatch.setenv(_DANGLING_CITATION_THRESHOLD_ENV, "1")
        result = _validate_output_markdown(
            "Claim [cite: 5].\n\n## Sources\n[cite: 1] https://a.example\n"
        )
        assert result["passed"] is True
        assert result["issues"] == []

    def test_resolved_citations_pass(self, monkeypatch):
        monkeypatch.delenv(_DANGLING_CITATION_THRESHOLD_ENV, raising=False)
        result = _validate_output_markdown(
            "Claim [cite: 1].\n\n## Sources\n[cite: 1] https://a.example\n"
        )
        assert result["passed"] is True
        assert result["issues"] == []


class TestStructureDefectThreshold:
    def test_default_is_zero(self, monkeypatch):
        monkeypatch.delenv(_STRUCTURE_DEFECT_THRESHOLD_ENV, raising=False)
        assert _structure_defect_threshold() == 0

    def test_reads_valid_int(self, monkeypatch):
        monkeypatch.setenv(_STRUCTURE_DEFECT_THRESHOLD_ENV, "2")
        assert _structure_defect_threshold() == 2

    def test_negative_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv(_STRUCTURE_DEFECT_THRESHOLD_ENV, "-3")
        assert _structure_defect_threshold() == 0

    def test_garbage_falls_back_to_zero(self, monkeypatch):
        monkeypatch.setenv(_STRUCTURE_DEFECT_THRESHOLD_ENV, "none")
        assert _structure_defect_threshold() == 0


class TestScanSectionStructureIssues:
    CLEAN = "## Executive Summary\n\nSolid prose here.\n\n## Outlook\n\nMore prose.\n"

    def test_clean_structure_passes(self):
        assert _scan_section_structure_issues(self.CLEAN, 0) == []

    def test_no_headings_passes(self):
        assert _scan_section_structure_issues("Just prose, no sections.", 0) == []

    def test_duplicate_heading_flagged(self):
        text = "## Summary\n\nA.\n\n## Summary\n\nB.\n"
        issues = _scan_section_structure_issues(text, 0)
        assert any(i.startswith("section_structure:defects=1") for i in issues)
        assert any("duplicate=Summary" in i for i in issues)

    def test_empty_section_flagged(self):
        text = "## Summary\n\nA.\n\n## Outlook\n\n## Sources\n\n[cite: 1] https://a.example\n"
        issues = _scan_section_structure_issues(text, 0)
        assert any("empty=Outlook" in i for i in issues)

    def test_within_threshold_passes(self):
        # One duplicate, threshold 1 -> not over threshold.
        text = "## Summary\n\nA.\n\n## Summary\n\nB.\n"
        assert _scan_section_structure_issues(text, 1) == []


class TestValidateOutputMarkdownStructure:
    def test_duplicate_blocks_by_default(self, monkeypatch):
        monkeypatch.delenv(_STRUCTURE_DEFECT_THRESHOLD_ENV, raising=False)
        result = _validate_output_markdown("## A\n\nx.\n\n## A\n\ny.\n")
        assert result["passed"] is False
        assert any(i.startswith("section_structure:") for i in result["issues"])

    def test_env_threshold_relaxes_gate(self, monkeypatch):
        monkeypatch.setenv(_STRUCTURE_DEFECT_THRESHOLD_ENV, "1")
        result = _validate_output_markdown("## A\n\nx.\n\n## A\n\ny.\n")
        assert result["passed"] is True
        assert result["issues"] == []


class TestExtractDocxText:
    def _doc(self, paragraphs=None, tables=None):
        document = MagicMock()
        paragraphs = paragraphs or []
        para_mocks = [MagicMock(text=text) for text in paragraphs]
        document.paragraphs = para_mocks

        table_mocks = []
        for table_text_grid in tables or []:
            table = MagicMock()
            row_mocks = []
            for row_text in table_text_grid:
                row = MagicMock()
                cell_mocks = [MagicMock(text=cell_text) for cell_text in row_text]
                row.cells = cell_mocks
                row_mocks.append(row)
            table.rows = row_mocks
            table_mocks.append(table)
        document.tables = table_mocks
        return document

    def test_extracts_paragraphs(self):
        doc = self._doc(paragraphs=["First line.", "Second line."])
        assert _extract_docx_text(doc) == "First line.\nSecond line."

    def test_skips_empty_paragraphs(self):
        doc = self._doc(paragraphs=["First.", "", "Second."])
        assert "First." in _extract_docx_text(doc)
        assert "Second." in _extract_docx_text(doc)

    def test_extracts_table_cells(self):
        doc = self._doc(
            paragraphs=[],
            tables=[[["A", "B"], ["C", "D"]]],
        )
        result = _extract_docx_text(doc)
        for cell in ("A", "B", "C", "D"):
            assert cell in result

    def test_combines_paragraphs_and_tables(self):
        doc = self._doc(
            paragraphs=["Intro."],
            tables=[[["X"]]],
        )
        result = _extract_docx_text(doc)
        assert "Intro." in result
        assert "X" in result

    def test_empty_document(self):
        doc = self._doc()
        assert _extract_docx_text(doc) == ""


class TestValidateOutputDocx:
    def test_missing_file_fails_closed(self, tmp_path):
        # python-docx raises when given a non-existent path; we should fail closed.
        bogus = tmp_path / "does_not_exist.docx"
        result = _validate_output_docx(bogus)
        assert result["passed"] is False
        assert result["errors"], "fail-closed must record the exception text"

    def test_clean_document_passes(self, tmp_path):
        path = tmp_path / "clean.docx"
        with patch("docx.Document") as DocumentMock:
            doc = MagicMock()
            doc.paragraphs = [MagicMock(text="Clean content.")]
            doc.tables = []
            DocumentMock.return_value = doc

            with patch("primr.output.markdown_parser.ArtifactDetector") as DetectorMock:
                DetectorMock.return_value.scan_document.return_value = []
                result = _validate_output_docx(path)
        assert result["passed"] is True
        assert result["issues"] == []

    def test_artifact_detector_issues_included(self, tmp_path):
        path = tmp_path / "dirty.docx"
        with patch("docx.Document") as DocumentMock:
            doc = MagicMock()
            doc.paragraphs = [MagicMock(text="content")]
            doc.tables = []
            DocumentMock.return_value = doc

            with patch("primr.output.markdown_parser.ArtifactDetector") as DetectorMock:
                DetectorMock.return_value.scan_document.return_value = [
                    {"type": "bold_marker", "match": "**bold**"}
                ]
                result = _validate_output_docx(path)
        assert result["passed"] is False
        assert any("markdown_artifact:bold_marker" in i for i in result["issues"])

    def test_forbidden_text_in_paragraphs_detected(self, tmp_path):
        path = tmp_path / "leak.docx"
        with patch("docx.Document") as DocumentMock:
            doc = MagicMock()
            doc.paragraphs = [MagicMock(text="From [Workbook: x] body content")]
            doc.tables = []
            DocumentMock.return_value = doc

            with patch("primr.output.markdown_parser.ArtifactDetector") as DetectorMock:
                DetectorMock.return_value.scan_document.return_value = []
                result = _validate_output_docx(path)
        assert result["passed"] is False
        assert any(i.startswith("workbook_ref:") for i in result["issues"])

    def test_caps_artifacts_at_ten(self, tmp_path):
        path = tmp_path / "many.docx"
        many_artifacts = [{"type": "noise", "match": f"m{i}"} for i in range(50)]
        with patch("docx.Document") as DocumentMock:
            doc = MagicMock()
            doc.paragraphs = []
            doc.tables = []
            DocumentMock.return_value = doc

            with patch("primr.output.markdown_parser.ArtifactDetector") as DetectorMock:
                DetectorMock.return_value.scan_document.return_value = many_artifacts
                result = _validate_output_docx(path)
        # Only first 10 artifact issues should be carried forward.
        markdown_issues = [i for i in result["issues"] if i.startswith("markdown_artifact:")]
        assert len(markdown_issues) == 10


class TestWriteOutputValidationReport:
    def test_no_issues_returns_none(self, tmp_path):
        result = _write_output_validation_report(tmp_path / "report.md", "markdown", [], [])
        assert result is None

    def test_writes_to_default_sibling(self, tmp_path):
        base = tmp_path / "company_report.md"
        out = _write_output_validation_report(base, "markdown", ["issue 1", "issue 2"], [])
        assert out is not None
        assert out.exists()
        assert out.name == "company_report_markdown_validation.txt"
        text = out.read_text(encoding="utf-8")
        assert "Artifact validation report (markdown)" in text
        assert "- issue 1" in text
        assert "- issue 2" in text

    def test_writes_to_diagnostics_dir(self, tmp_path):
        diagnostics = tmp_path / "diag"
        base = tmp_path / "company_report.md"
        out = _write_output_validation_report(
            base, "docx", [], ["validator boom"], diagnostics_dir=diagnostics
        )
        assert out is not None
        assert out.parent == diagnostics
        assert "Validator errors:" in out.read_text(encoding="utf-8")

    def test_creates_diagnostics_dir(self, tmp_path):
        diagnostics = tmp_path / "new_subdir"
        assert not diagnostics.exists()
        base = tmp_path / "company.md"
        _write_output_validation_report(
            base, "markdown", ["issue"], [], diagnostics_dir=diagnostics
        )
        assert diagnostics.exists()

    def test_both_issues_and_errors_recorded(self, tmp_path):
        out = _write_output_validation_report(tmp_path / "x.md", "markdown", ["i1"], ["e1"])
        text = out.read_text(encoding="utf-8")
        assert "Issues:" in text
        assert "Validator errors:" in text
        assert "- i1" in text
        assert "- e1" in text

    def test_path_string_accepted_for_diagnostics(self, tmp_path):
        diag_str = str(tmp_path / "diag_str")
        out = _write_output_validation_report(
            tmp_path / "x.md", "markdown", ["i"], [], diagnostics_dir=diag_str
        )
        assert out.parent == Path(diag_str)


@pytest.mark.parametrize(
    "pattern_text",
    [
        "[Source: https://example.com]",
        "[Workbook: section x]",
        "[workbook section 2]",
        "[Workbook §7]",
        "[Analysis Workbook entry]",
        "[Analysis: something]",
        "[External Sources]",
        "[citation inventory id-3]",
        "vendor-research-acme.txt",
        "Internal ROI Model",
        "Internal Analysis",
        "[see ## Strategy]",
    ],
)
def test_every_pattern_round_trips_scan_then_strip(pattern_text):
    body = f"before {pattern_text} after"
    # Scanner sees it
    assert _scan_forbidden_output_patterns(body), f"scanner missed: {pattern_text}"
    # Stripper removes it
    cleaned = _auto_strip_forbidden_patterns(body)
    assert _scan_forbidden_output_patterns(cleaned) == [], (
        f"strip residue still flagged for: {pattern_text} -> {cleaned!r}"
    )
