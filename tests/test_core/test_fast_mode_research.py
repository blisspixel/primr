"""
Tests for fast mode research deepening (Phase 2) and cross-validation (Phase 5).

Validates the gap analysis, cross-validation, and section regeneration helpers
that enhance fast mode report quality.
"""

import json

from primr.core.fast_run_gaps import _fast_gap_analysis
from primr.core.research_agent import (
    _build_fast_section_prompt,
    _clean_fast_report_output,
    _compute_fast_report_qa_metrics,
    _determine_section_reasoning_mode,
    _fast_cross_validate,
    _fast_regenerate_section,
    _normalize_fast_citations,
    _normalize_generated_section_payload,
    _parse_batch_sections,
    _parse_single_section,
    _parse_structured_section_envelopes,
)
from primr.prompts.loader import SectionConfig


class TestFastGapAnalysis:
    """Tests for _fast_gap_analysis() — Phase 2 Research Deepening."""

    def test_returns_queries_from_grok_response(self, monkeypatch):
        """Gap analysis should parse QUERY: lines from Grok response."""
        response = (
            "GAP: No financial data found\n"
            "QUERY: ExampleCo revenue funding 2025\n"
            "PRIORITY: CRITICAL\n\n"
            "GAP: Missing competitor analysis\n"
            "QUERY: ExampleCo competitors market share\n"
            "PRIORITY: IMPORTANT\n\n"
            "GAP: No leadership info\n"
            "QUERY: ExampleCo CEO leadership team\n"
            "PRIORITY: IMPORTANT\n"
        )

        def mock_grok(prompt, **kwargs):
            return response

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock_grok)

        queries, text = _fast_gap_analysis(
            "ExampleCo",
            "https://example.com",
            "raw corpus text",
            "external sources text",
            ["https://existing-source.com"],
        )

        assert len(queries) == 3
        assert "ExampleCo revenue funding 2025" in queries
        assert "ExampleCo competitors market share" in queries
        assert "ExampleCo CEO leadership team" in queries
        assert text == response

    def test_handles_empty_response(self, monkeypatch):
        """Gap analysis should return empty list on empty Grok response."""
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: "")

        queries, text = _fast_gap_analysis(
            "ExampleCo",
            "https://example.com",
            "corpus",
            "external",
            [],
        )

        assert queries == []
        assert "empty" in text.lower()

    def test_handles_grok_exception(self, monkeypatch):
        """Gap analysis should return empty list when Grok fails."""

        def boom(*args, **kwargs):
            raise RuntimeError("API down")

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", boom)

        queries, text = _fast_gap_analysis(
            "ExampleCo",
            "https://example.com",
            "corpus",
            "external",
            [],
        )

        assert queries == []
        assert "failed" in text.lower()

    def test_limits_to_8_queries(self, monkeypatch):
        """Gap analysis should return at most 8 queries even if Grok returns more."""
        lines = []
        for i in range(12):
            lines.append(f"GAP: Gap {i}")
            lines.append(f"QUERY: query number {i}")
            lines.append("PRIORITY: IMPORTANT")
            lines.append("")

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: "\n".join(lines))

        queries, _ = _fast_gap_analysis(
            "ExampleCo",
            "https://example.com",
            "corpus",
            "external",
            [],
        )

        assert len(queries) <= 8

    def test_prompt_includes_company_name(self, monkeypatch):
        """Gap analysis prompt should include the company name."""
        captured = {}

        def mock_grok(prompt, **kwargs):
            captured["prompt"] = prompt
            return "GAP: nothing\nQUERY: test query\nPRIORITY: IMPORTANT"

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock_grok)

        _fast_gap_analysis("AcmeCorp", None, "corpus", "external", [])

        assert "AcmeCorp" in captured["prompt"]


class TestFastCrossValidate:
    """Tests for _fast_cross_validate() — Phase 5 Cross-Validation."""

    def test_returns_structured_output(self, monkeypatch):
        """Cross-validation should return parsed JSON with weak_sections and contradictions."""
        response_obj = {
            "weak_sections": [
                {
                    "title": "Competitive Landscape",
                    "reason": "No citations",
                    "queries": ["q1", "q2"],
                },
            ],
            "contradictions": ["Revenue claim in Exec Summary contradicts Financial Profile"],
        }
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: json.dumps(response_obj),
        )

        result = _fast_cross_validate(
            "ExampleCo",
            "https://example.com",
            "## Executive Summary\n\nContent\n\n## Competitive Landscape\n\nWeak content",
            ["https://src1.com"],
        )

        assert len(result["weak_sections"]) == 1
        assert result["weak_sections"][0]["title"] == "Competitive Landscape"
        assert len(result["contradictions"]) == 1

    def test_limits_to_3_sections(self, monkeypatch):
        """Cross-validation should cap weak sections at 3 even if Grok returns 5."""
        response_obj = {
            "weak_sections": [
                {"title": f"Section {i}", "reason": "weak", "queries": [f"q{i}"]} for i in range(5)
            ],
            "contradictions": [],
        }
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: json.dumps(response_obj),
        )

        result = _fast_cross_validate(
            "ExampleCo",
            "https://example.com",
            "report content",
            [],
        )

        assert len(result["weak_sections"]) == 3

    def test_handles_no_weak_sections(self, monkeypatch):
        """Cross-validation should return empty arrays when report is solid."""
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: json.dumps({"weak_sections": [], "contradictions": []}),
        )

        result = _fast_cross_validate(
            "ExampleCo",
            "https://example.com",
            "## Good Section\n\nStrong content with [Source: url].",
            [],
        )

        assert result["weak_sections"] == []
        assert result["contradictions"] == []

    def test_handles_malformed_json(self, monkeypatch):
        """Cross-validation should return empty result on malformed JSON."""
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: "This is not JSON at all",
        )

        result = _fast_cross_validate(
            "ExampleCo",
            "https://example.com",
            "report",
            [],
        )

        assert result["weak_sections"] == []
        assert result["contradictions"] == []

    def test_handles_grok_exception(self, monkeypatch):
        """Cross-validation should return empty result when Grok fails."""

        def boom(*args, **kwargs):
            raise RuntimeError("API error")

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", boom)

        result = _fast_cross_validate(
            "ExampleCo",
            "https://example.com",
            "report",
            [],
        )

        assert result["weak_sections"] == []
        assert result["contradictions"] == []

    def test_strips_markdown_code_fencing(self, monkeypatch):
        """Cross-validation should handle JSON wrapped in markdown code blocks."""
        fenced = '```json\n{"weak_sections": [], "contradictions": ["test"]}\n```'
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: fenced)

        result = _fast_cross_validate(
            "ExampleCo",
            "https://example.com",
            "report",
            [],
        )

        assert len(result["contradictions"]) == 1
        assert result["contradictions"][0] == "test"


class TestFastRegenerateSection:
    """Tests for _fast_regenerate_section() — Phase 5 section re-writing."""

    def test_preserves_heading(self, monkeypatch):
        """Regenerated section should start with ## heading."""
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: "## Financial Profile\n\nUpdated content with evidence.",
        )

        result = _fast_regenerate_section(
            "ExampleCo",
            "https://example.com",
            "Financial Profile",
            "## Financial Profile\n\nOld thin content.",
            "workbook context",
            "[Source: https://new.com]\nNew financial data.",
            ["https://new.com"],
        )

        assert result.startswith("## Financial Profile")

    def test_adds_heading_if_missing(self, monkeypatch):
        """Regenerated section should have heading added if Grok omits it."""
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: "Updated content without heading.",
        )

        result = _fast_regenerate_section(
            "ExampleCo",
            None,
            "Market Position",
            "## Market Position\n\nOriginal.",
            "workbook",
            "evidence",
            [],
        )

        assert result.startswith("## Market Position")

    def test_returns_original_on_exception(self, monkeypatch):
        """Regeneration should return original section content on Grok failure."""

        def boom(*args, **kwargs):
            raise RuntimeError("API down")

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", boom)

        original = "## Test Section\n\nOriginal content."
        result = _fast_regenerate_section(
            "ExampleCo",
            None,
            "Test Section",
            original,
            "workbook",
            "evidence",
            [],
        )

        assert result == original

    def test_returns_original_on_empty_response(self, monkeypatch):
        """Regeneration should return original on empty Grok response."""
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: "")

        original = "## Test\n\nContent."
        result = _fast_regenerate_section(
            "ExampleCo",
            None,
            "Test",
            original,
            "workbook",
            "evidence",
            [],
        )

        assert result == original

    def test_prompt_includes_new_evidence(self, monkeypatch):
        """Regeneration prompt should include the new evidence."""
        captured = {}

        def mock_grok(prompt, **kwargs):
            captured["prompt"] = prompt
            return "## Section\n\nRewritten."

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock_grok)

        evidence = "[Source: https://new.com]\nRevenue grew 40% YoY."
        _fast_regenerate_section(
            "ExampleCo",
            None,
            "Section",
            "## Section\n\nOld.",
            "workbook",
            evidence,
            ["https://new.com"],
        )

        assert "Revenue grew 40% YoY" in captured["prompt"]
        assert "https://new.com" in captured["prompt"]

    def test_strips_wrong_heading_from_grok(self, monkeypatch):
        """If Grok uses a different heading, strip it and use the correct one."""
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: "## Wrong Heading Name\n\nActual good content here.",
        )

        result = _fast_regenerate_section(
            "ExampleCo",
            None,
            "Financial Profile",
            "## Financial Profile\n\nOriginal.",
            "workbook",
            "evidence",
            [],
        )

        assert result.startswith("## Financial Profile")
        assert "## Wrong Heading Name" not in result
        assert "Actual good content here." in result


class TestGapAnalysisQueryParsing:
    """Test that gap analysis strips wrapper characters from queries."""

    def test_strips_quotes_from_queries(self, monkeypatch):
        """Queries wrapped in quotes should have quotes stripped."""
        response = 'GAP: Missing\nQUERY: "ExampleCo revenue 2025"\nPRIORITY: CRITICAL'
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: response)

        queries, _ = _fast_gap_analysis("Co", None, "corpus", "ext", [])

        assert queries == ["ExampleCo revenue 2025"]

    def test_strips_brackets_from_queries(self, monkeypatch):
        """Queries wrapped in brackets should have brackets stripped."""
        response = "GAP: Missing\nQUERY: [ExampleCo competitors]\nPRIORITY: IMPORTANT"
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: response)

        queries, _ = _fast_gap_analysis("Co", None, "corpus", "ext", [])

        assert queries == ["ExampleCo competitors"]

    def test_handles_mixed_case_query_prefix(self, monkeypatch):
        """Should parse QUERY:, Query:, query: etc."""
        response = "GAP: A\nquery: lowercase query\nPRIORITY: IMPORTANT"
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: response)

        queries, _ = _fast_gap_analysis("Co", None, "corpus", "ext", [])

        assert queries == ["lowercase query"]


class TestCrossValidateTypeSafety:
    """Tests that _fast_cross_validate handles malformed Grok output gracefully."""

    def test_handles_non_dict_json(self, monkeypatch):
        """Should return empty result when JSON is a list instead of dict."""
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: '[{"title": "X"}]',
        )
        result = _fast_cross_validate("Co", None, "report", [])
        assert result["weak_sections"] == []

    def test_handles_weak_sections_as_string(self, monkeypatch):
        """Should return empty list when weak_sections is a string, not a list."""
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: json.dumps({"weak_sections": "none", "contradictions": []}),
        )
        result = _fast_cross_validate("Co", None, "report", [])
        assert result["weak_sections"] == []

    def test_filters_non_dict_entries_from_weak_sections(self, monkeypatch):
        """Should skip non-dict entries in weak_sections array."""
        response_obj = {
            "weak_sections": [
                "just a string",
                {"title": "Good", "reason": "r", "queries": ["q"]},
                42,
            ],
            "contradictions": [],
        }
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: json.dumps(response_obj),
        )
        result = _fast_cross_validate("Co", None, "report", [])
        assert len(result["weak_sections"]) == 1
        assert result["weak_sections"][0]["title"] == "Good"

    def test_filters_non_string_contradictions(self, monkeypatch):
        """Should skip non-string entries in contradictions array."""
        response_obj = {
            "weak_sections": [],
            "contradictions": ["valid", 123, {"not": "a string"}, "also valid"],
        }
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: json.dumps(response_obj),
        )
        result = _fast_cross_validate("Co", None, "report", [])
        assert result["contradictions"] == ["valid", "also valid"]


class TestCrossValidateJsonExtraction:
    """Test that _fast_cross_validate extracts JSON from prose-wrapped responses."""

    def test_extracts_json_from_surrounding_prose(self, monkeypatch):
        """Should find JSON object embedded in prose text."""
        response = (
            "Here is my analysis:\n\n"
            '{"weak_sections": [{"title": "X", "reason": "r", "queries": ["q"]}], "contradictions": []}\n\n'
            "Let me know if you need more."
        )
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: response)

        result = _fast_cross_validate("Co", None, "report", [])
        assert len(result["weak_sections"]) == 1

    def test_pure_json_still_works(self, monkeypatch):
        """Plain JSON without wrapper should still parse."""
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: '{"weak_sections": [], "contradictions": []}',
        )
        result = _fast_cross_validate("Co", None, "report", [])
        assert result["weak_sections"] == []


class TestCrossValidateCodeFencing:
    """Edge cases for JSON parsing in _fast_cross_validate."""

    def test_handles_bare_backticks_fence(self, monkeypatch):
        """Should strip ``` without language tag."""
        fenced = '```\n{"weak_sections": [{"title": "X", "reason": "r", "queries": ["q"]}], "contradictions": []}\n```'
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: fenced)

        result = _fast_cross_validate("Co", None, "report", [])
        assert len(result["weak_sections"]) == 1

    def test_handles_uppercase_json_fence(self, monkeypatch):
        """Should strip ```JSON (uppercase)."""
        fenced = '```JSON\n{"weak_sections": [], "contradictions": ["c1"]}\n```'
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", lambda *a, **k: fenced)

        result = _fast_cross_validate("Co", None, "report", [])
        assert result["contradictions"] == ["c1"]

    def test_limits_contradictions_to_3(self, monkeypatch):
        """Should cap contradictions at 3."""
        response_obj = {
            "weak_sections": [],
            "contradictions": [f"contradiction {i}" for i in range(6)],
        }
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            lambda *a, **k: json.dumps(response_obj),
        )

        result = _fast_cross_validate("Co", None, "report", [])
        assert len(result["contradictions"]) == 3


class TestGapAnalysisCorpusParsing:
    """Test that gap analysis correctly summarizes different corpus formats."""

    def test_parses_page_blocks(self, monkeypatch):
        """Gap analysis should extract [Page:] blocks from corpus."""
        corpus = (
            "[Page: https://example.com]\nLong content here "
            + "x" * 1000
            + "\n\n[Page: https://example.com/about]\nAbout page content "
            + "y" * 1000
        )
        captured = {}

        def mock_grok(prompt, **kwargs):
            captured["prompt"] = prompt
            return "GAP: nothing\nQUERY: test\nPRIORITY: IMPORTANT"

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock_grok)

        _fast_gap_analysis("Co", None, corpus, "(no external sources)", [])

        # Prompt should contain truncated page summaries, not the full 1000+ char content
        assert "[Page: https://example.com]" in captured["prompt"]
        assert len(captured["prompt"]) < len(corpus)

    def test_falls_back_on_no_page_blocks(self, monkeypatch):
        """Gap analysis should use raw corpus truncation when no [Page:] blocks found."""
        corpus = "Just raw text without page markers. " * 100
        captured = {}

        def mock_grok(prompt, **kwargs):
            captured["prompt"] = prompt
            return "GAP: nothing\nQUERY: test\nPRIORITY: IMPORTANT"

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock_grok)

        _fast_gap_analysis("Co", None, corpus, "(no external sources)", [])

        # Should still have corpus content in prompt (truncated fallback)
        assert "Just raw text" in captured["prompt"]

    def test_includes_known_urls_in_prompt(self, monkeypatch):
        """Gap analysis should list known URLs so Grok avoids duplicates."""
        captured = {}

        def mock_grok(prompt, **kwargs):
            captured["prompt"] = prompt
            return "GAP: nothing\nQUERY: test\nPRIORITY: IMPORTANT"

        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock_grok)

        urls = ["https://already-found.com/article1", "https://already-found.com/article2"]
        _fast_gap_analysis("Co", None, "corpus", "external", urls)

        assert "https://already-found.com/article1" in captured["prompt"]
        assert "https://already-found.com/article2" in captured["prompt"]


class TestCleanFastReportOutput:
    """Tests for _clean_fast_report_output() — artifact cleanup."""

    def test_strips_grok_disclaimer(self):
        content = "## Summary\n\nGood content.\n\n_Disclaimer: Grok is not a financial adviser; please consult one. Don't share information that can identify you._\n"
        result = _clean_fast_report_output(content)
        assert "Disclaimer" not in result
        assert "Grok is not" not in result
        assert "Good content." in result

    def test_strips_standalone_reported_at_section_boundary(self):
        content = "## Executive Summary\n\nContent here.\n\nWhat to validate: check this.\n\n(Reported)\n\n## Products\n\nMore content.\n"
        result = _clean_fast_report_output(content)
        assert "\n(Reported)\n" not in result
        assert "## Executive Summary" in result
        assert "## Products" in result
        assert "Content here." in result

    def test_preserves_inline_reported_labels(self):
        content = "## Summary\n\nThis is (Reported) inline data and (Confirmed) facts.\n"
        result = _clean_fast_report_output(content)
        assert "(Reported)" in result
        assert "(Confirmed)" in result

    def test_strips_informal_cite_tags(self):
        content = "## Section\n\nClaim [cite: workbook] and also [cite: bbb; cite: enrollment].\n"
        result = _clean_fast_report_output(content)
        assert "[cite: workbook]" not in result
        assert "[cite: bbb" not in result
        assert "Claim" in result

    def test_preserves_numeric_cite_tags(self):
        content = "## Section\n\nClaim [cite: 1] and [cite: 2, 3].\n"
        result = _clean_fast_report_output(content)
        assert "[cite: 1]" in result
        assert "[cite: 2, 3]" in result

    def test_strips_cross_ref_tags(self):
        content = (
            "## Section\n\nSee details [cross-ref: Financial Profile] and also [cross-ref: SWOT].\n"
        )
        result = _clean_fast_report_output(content)
        assert "[cross-ref:" not in result
        assert "See details" in result

    def test_collapses_excess_blank_lines(self):
        content = "## Section\n\nParagraph.\n\n\n\n\n## Next\n\nContent.\n"
        result = _clean_fast_report_output(content)
        assert "\n\n\n" not in result

    def test_strips_workbook_and_external_source_artifacts(self):
        content = (
            "## Section\n\n"
            "Claim [Workbook: Financial Profile] and [workbook section 3] and [Workbook §7].\n"
            "Noise [External Sources].\n"
        )
        result = _clean_fast_report_output(content)
        assert "[Workbook:" not in result
        assert "[workbook section" not in result
        assert "[Workbook §" not in result
        assert "[External Sources]" not in result

    def test_strips_bare_workbook_marker(self):
        content = (
            "## Section\n\nClaim about growth (2026 [workbook]) and trend [workbook] continues.\n"
        )
        result = _clean_fast_report_output(content)
        assert "[workbook]" not in result
        # Surrounding prose stays intact (whitespace collapsed to single space).
        assert "(2026)" in result
        assert "trend continues." in result

    def test_strips_space_separated_workbook_with_content(self):
        content = "## Section\n\nNote [workbook ARDA/prior sections] from research.\n"
        result = _clean_fast_report_output(content)
        assert "[workbook" not in result
        assert "Note from research." in result

    def test_strips_space_separated_cross_ref(self):
        content = (
            "## Section\n\nSee [cross-ref Financial Profile] and [cross-ref SWOT] for detail.\n"
        )
        result = _clean_fast_report_output(content)
        assert "[cross-ref" not in result
        assert "See and for detail." in result

    def test_strips_bare_cross_ref(self):
        content = "## Section\n\nDetail here [cross-ref] and more text.\n"
        result = _clean_fast_report_output(content)
        assert "[cross-ref" not in result
        assert "Detail here and more text." in result

    def test_empty_input_returns_unchanged(self):
        assert _clean_fast_report_output("") == ""
        assert _clean_fast_report_output("   ") == "   "


class TestNormalizeCitationsBareDomains:
    """Tests for _normalize_fast_citations handling bare domain URLs."""

    def test_normalizes_bare_domain_source(self):
        content = "## Section\n\nClaim [Source: gripsintelligence.com/insights/senegence].\n"
        result = _normalize_fast_citations(content)
        assert "[cite: 1]" in result
        assert "https://gripsintelligence.com/insights/senegence" in result

    def test_normalizes_https_and_bare_together(self):
        content = (
            "## Section\n\n"
            "Claim A [Source: https://example.com/a].\n"
            "Claim B [Source: other.com/b].\n"
        )
        result = _normalize_fast_citations(content)
        assert "[cite: 1]" in result
        assert "[cite: 2]" in result
        assert "https://example.com/a" in result
        assert "https://other.com/b" in result

    def test_deduplicates_same_bare_domain(self):
        content = (
            "## Section\n\nFirst [Source: example.com/page].\nSecond [Source: example.com/page].\n"
        )
        result = _normalize_fast_citations(content)
        # Both inline + 1 in Sources section = 3 total occurrences of [cite: 1]
        citations = result.count("[cite: 1]")
        assert citations == 3
        # Only one URL entry in Sources section
        sources_section = result.split("## Sources")[1]
        assert sources_section.count("https://example.com/page") == 1


class TestFastReportQaMetrics:
    """Tests for contradiction-aware fast report QA."""

    def test_unresolved_contradictions_force_warn_gate(self):
        content = (
            "## Executive Summary\n\n"
            "Claim (Reported) [cite: 1].\n\n"
            "What to validate: Confirm revenue.\n\n"
            "## Sources\n\n"
            "[cite: 1] https://example.com/source\n"
        )
        metrics = _compute_fast_report_qa_metrics(content, unresolved_contradictions=2)
        assert metrics["unresolved_contradictions"] == 2
        assert metrics["qa_gate_passed"] is False


def test_clean_fast_report_output_strips_analysis_and_internal_model_artifacts():
    content = (
        "## Section\n\n"
        "Claim [Analysis Workbook: 4] and [Analysis: 2].\n"
        "Uses vendor-research-aws-2026-03.txt and Internal ROI Model with Internal Analysis.\n"
    )
    result = _clean_fast_report_output(content)
    assert "[Analysis Workbook" not in result
    assert "[Analysis:" not in result
    assert "vendor-research-aws-2026-03.txt" not in result
    assert "Internal ROI Model" not in result
    assert "Internal Analysis" not in result


def test_compute_fast_report_qa_metrics_fails_with_zero_citations():
    content = "## Executive Summary\n\nClaim (Reported).\n\nWhat to validate: Confirm revenue.\n"
    metrics = _compute_fast_report_qa_metrics(content)
    assert metrics["citations_used"] == 0
    assert metrics["citations_defined"] == 0
    assert metrics["qa_gate_passed"] is False


class TestFastSectionReasoning:
    """Tests for constrained-evidence section writing behavior."""

    def test_reasoning_mode_downgrades_to_constrained_evidence_when_signal_is_thin(self):
        section = SectionConfig(
            id="industry_outlook",
            name="Industry Outlook",
            part=2,
            purpose="Outlook",
            covers=["Near-term", "Medium-term"],
            depth="Deep analysis",
        )

        mode = _determine_section_reasoning_mode(
            section, "Workbook mentions none of the tracked keywords"
        )

        assert mode == "constrained_evidence"

    def test_build_fast_section_prompt_includes_constrained_evidence_guidance(self):
        section = SectionConfig(
            id="industry_outlook",
            name="Industry Outlook",
            part=2,
            purpose="Outlook",
            covers=["Near-term", "Medium-term"],
            depth="Deep analysis",
        )

        prompt = _build_fast_section_prompt(
            company_name="ExampleCo",
            website="https://example.com",
            analysis_workbook="thin workbook",
            raw_corpus_subset="website facts",
            external_sources="industry news",
            source_urls=["https://example.com/news"],
            section=section,
            written_sections=[],
            section_index=0,
            all_section_names=["Industry Outlook"],
            reasoning_mode="constrained_evidence",
        )

        assert "CONSTRAINED-EVIDENCE MODE" in prompt
        assert "Do NOT collapse into a thin fact check" in prompt
        assert "strategic implication" in prompt
        assert "Keep citations compact" in prompt
        assert "final Sources appendix" in prompt


class TestGeneratedSectionNormalization:
    """Tests for stricter section payload normalization before report assembly."""

    def test_normalize_generated_section_payload_removes_embedded_reference_appendix(self):
        payload = _normalize_generated_section_payload(
            "Executive Summary",
            "Core analysis (Reported).\n\n## Sources\n\n[cite: 1] https://example.com/a\n",
            "Executive Summary",
        )

        assert payload.title == "Executive Summary"
        assert "## Sources" not in payload.content
        assert payload.content.endswith(payload.validate_line)

    def test_normalize_generated_section_payload_keeps_single_trailing_validate_line(self):
        payload = _normalize_generated_section_payload(
            "SWOT Analysis",
            "Point A.\n\nWhat to validate: Old question.\n\nMore detail.\n\nWhat to validate: Final question.",
            "SWOT Analysis",
        )

        assert payload.content.count("What to validate:") == 1
        assert payload.validate_line == "What to validate: Final question."
        assert payload.content.endswith("What to validate: Final question.")

    def test_normalize_generated_section_payload_strips_nested_heading_from_body(self):
        payload = _normalize_generated_section_payload(
            "Competitive Landscape",
            "## Wrong Heading\n\nComparison body.\n\nWhat to validate: Confirm competitor win-loss reasons.",
            "Competitive Landscape",
        )

        assert not payload.content.startswith("## ")
        assert payload.content.startswith("Comparison body.")
        assert payload.content.endswith("What to validate: Confirm competitor win-loss reasons.")

    def test_normalize_generated_section_payload_dedups_bold_validate_line(self):
        # The writer sometimes wraps the validate line in bold markdown
        # (e.g. "**What to validate:** Confirm X?"). Normalization must
        # extract the question and emit a single canonical trailing line,
        # not leave the bold variant in the body alongside a default line.
        payload = _normalize_generated_section_payload(
            "Financial Profile",
            "Revenue analysis here.\n\n**What to validate:** Confirm 2026 ARR growth rate.",
            "Financial Profile",
        )

        assert payload.content.count("What to validate:") == 1
        assert payload.validate_line == "What to validate: Confirm 2026 ARR growth rate."
        # The bold markers must not survive into the body.
        assert "**What to validate" not in payload.content
        assert payload.content.endswith("What to validate: Confirm 2026 ARR growth rate.")

    def test_normalize_generated_section_payload_drops_bare_bold_validate_scaffold(self):
        # A bare "**What to validate:**" with no question is prompt-template
        # scaffolding that leaked through. It should be removed entirely and
        # the default trailing line used instead.
        payload = _normalize_generated_section_payload(
            "SWOT Analysis",
            "Strengths and weaknesses summary.\n\n**What to validate:**",
            "SWOT Analysis",
        )

        assert "**What to validate" not in payload.content
        assert payload.content.count("What to validate:") == 1
        # Falls back to the default question since no real question was supplied.
        assert payload.validate_line.startswith("What to validate:")
        assert payload.content.endswith(payload.validate_line)

    def test_normalize_generated_section_payload_fully_bolded_validate_line(self):
        # "**What to validate: question?**" — bold wrapper spans the whole
        # line including the question. Trailing bold markers should be stripped
        # so the canonical line is plain text.
        payload = _normalize_generated_section_payload(
            "Customer Profile",
            "Customer base description.\n\n**What to validate: What is the net revenue retention?**",
            "Customer Profile",
        )

        assert "**" not in payload.validate_line
        assert payload.validate_line == "What to validate: What is the net revenue retention?"
        assert payload.content.endswith(payload.validate_line)

    def test_parse_single_section_normalizes_title_and_validate_line(self):
        class ExpectedSection:
            name = "Competitive Landscape"

        parsed = _parse_single_section(
            "## Wrong Heading\n\nComparison body.\n\nWhat to validate: Confirm competitor win-loss reasons.\n\n## References\n\n[cite: 1] https://example.com/a\n",
            ExpectedSection(),
        )

        assert parsed.title == "Competitive Landscape"
        assert "## References" not in parsed.content
        assert parsed.content.endswith("What to validate: Confirm competitor win-loss reasons.")

    def test_parse_structured_section_envelopes_reads_xml_blocks(self):
        content = (
            "<section><title>Executive Summary</title><body>Summary body.\n\nWhat to validate: Confirm summary.</body></section>"
            "<section><title>SWOT Analysis</title><body>SWOT body.\n\nWhat to validate: Confirm SWOT.</body></section>"
        )

        parsed = _parse_structured_section_envelopes(content)

        assert parsed[0][0] == "Executive Summary"
        assert parsed[1][0] == "SWOT Analysis"

    def test_parse_single_section_prefers_structured_envelope(self):
        class ExpectedSection:
            name = "Competitive Landscape"

        parsed = _parse_single_section(
            "<section><title>Wrong Heading</title><body>Comparison body.\n\nWhat to validate: Confirm competitor win-loss reasons.</body></section>",
            ExpectedSection(),
        )

        assert parsed.title == "Competitive Landscape"
        assert parsed.content.endswith("What to validate: Confirm competitor win-loss reasons.")

    def test_parse_batch_sections_prefers_structured_envelopes(self):
        class ExpectedSection:
            def __init__(self, name: str):
                self.name = name

        expected = [ExpectedSection("Executive Summary"), ExpectedSection("SWOT Analysis")]
        content = (
            "<section><title>Executive Summary</title><body>Summary body.\n\nWhat to validate: Confirm summary.</body></section>"
            "<section><title>SWOT Analysis</title><body>SWOT body.\n\nWhat to validate: Confirm SWOT.</body></section>"
        )

        parsed = _parse_batch_sections(content, expected)

        assert [section.title for section in parsed] == ["Executive Summary", "SWOT Analysis"]

    def test_parse_batch_sections_handles_mixed_envelope_and_markdown_output(self):
        class ExpectedSection:
            def __init__(self, name: str):
                self.name = name

        expected = [ExpectedSection("Executive Summary"), ExpectedSection("SWOT Analysis")]
        content = (
            "<section><title>Wrong Summary</title><body>Summary body.\n\nWhat to validate: Confirm summary.</body></section>\n\n"
            "## Wrong SWOT\n\nSWOT body.\n\nWhat to validate: Confirm SWOT."
        )

        parsed = _parse_batch_sections(content, expected)

        assert [section.title for section in parsed] == ["Executive Summary", "SWOT Analysis"]
        assert parsed[0].content.endswith("What to validate: Confirm summary.")
        assert parsed[1].content.endswith("What to validate: Confirm SWOT.")

    def test_parse_batch_sections_keeps_preamble_on_first_section_with_mixed_output(self):
        class ExpectedSection:
            def __init__(self, name: str):
                self.name = name

        expected = [ExpectedSection("Executive Summary"), ExpectedSection("SWOT Analysis")]
        content = (
            "Internal note before sections.\n\n"
            "<section><title>Executive Summary</title><body>Summary body.\n\nWhat to validate: Confirm summary.</body></section>\n\n"
            "## SWOT Analysis\n\nSWOT body.\n\nWhat to validate: Confirm SWOT."
        )

        parsed = _parse_batch_sections(content, expected)

        assert parsed[0].content.startswith("Internal note before sections.")
        assert parsed[0].content.endswith("What to validate: Confirm summary.")
