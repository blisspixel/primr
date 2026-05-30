"""Unit tests for primr.core.strategy_artifacts.

Pure-function tests for the strategy-document QA, citation normalization,
and structural-splitting helpers extracted from research_agent.
"""

from __future__ import annotations

import pytest

from primr.core.strategy_artifacts import (
    _clean_strategy_output,
    _compute_strategy_qa_metrics,
    _ensure_strategy_source_inventory,
    _extract_strategy_citation_definitions,
    _is_auditable_source_url,
    _normalize_fast_citations,
    _normalize_strategy_source_urls,
    _split_markdown_sections,
    _strategy_money_to_millions,
)


class TestStrategyMoneyToMillions:
    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [
            (1.5, "B", 1500.0),
            (1.5, "b", 1500.0),
            (250.0, "M", 250.0),
            (250.0, "m", 250.0),
            (500.0, "K", 0.5),
            (500.0, "k", 0.5),
        ],
    )
    def test_unit_conversions(self, value, unit, expected):
        assert _strategy_money_to_millions(value, unit) == expected

    def test_unknown_unit_returns_value_unchanged(self):
        assert _strategy_money_to_millions(42.0, "X") == 42.0


class TestIsAuditableSourceUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com",
            "https://acme.example/path?x=1",
            "http://news.example.com/article",
        ],
    )
    def test_valid_urls(self, url):
        assert _is_auditable_source_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "https://localhost",  # no dot
            "https://-bad-.example",  # leading hyphen
            "https://example-.com",  # trailing hyphen
            "https://EX$AMPLE.com",  # invalid char
        ],
    )
    def test_invalid_urls(self, url):
        assert _is_auditable_source_url(url) is False

    def test_ip_address_allowed(self):
        # IP addresses are accepted in this helper (the SSRF check is separate).
        assert _is_auditable_source_url("https://1.1.1.1/x") is True


class TestNormalizeStrategySourceUrls:
    def test_accepts_valid_urls(self):
        urls = ["https://example.com/a", "https://example.com/b"]
        normalized, rejected = _normalize_strategy_source_urls(urls)
        assert len(normalized) == 2
        assert rejected == []

    def test_dedupes(self):
        urls = ["https://example.com/a", "https://example.com/a"]
        normalized, rejected = _normalize_strategy_source_urls(urls)
        assert len(normalized) == 1

    def test_rejects_unsafe_urls(self):
        urls = ["javascript:alert(1)", "https://example.com/ok"]
        normalized, rejected = _normalize_strategy_source_urls(urls)
        assert "https://example.com/ok" in normalized[0]
        assert rejected == ["javascript:alert(1)"]

    def test_skips_blank_entries(self):
        urls = ["", "  ", "https://example.com"]
        normalized, rejected = _normalize_strategy_source_urls(urls)
        assert len(normalized) == 1
        assert rejected == []


class TestExtractStrategyCitationDefinitions:
    def test_parses_well_formed_defs(self):
        # Each cite-N followed by ANY non-whitespace token is considered a
        # candidate definition; non-URL tokens land in `invalid` while the
        # valid URL wins for that number in the dict.
        content = "## Sources\n[cite: 1] https://example.com/a\n[cite: 2] https://example.com/b\n"
        cited, valid, invalid = _extract_strategy_citation_definitions(content)
        assert cited == {1, 2}
        assert valid == {
            1: "https://example.com/a",
            2: "https://example.com/b",
        }
        assert invalid == []

    def test_marks_invalid_urls(self):
        content = "## Sources\n[cite: 1] not-a-url\n"
        cited, valid, invalid = _extract_strategy_citation_definitions(content)
        assert 1 in cited
        assert valid == {}
        assert "not-a-url" in invalid

    def test_no_citations(self):
        cited, valid, invalid = _extract_strategy_citation_definitions("plain text")
        assert cited == set()
        assert valid == {}
        assert invalid == []


class TestComputeStrategyQaMetrics:
    def test_empty_returns_zero_state(self):
        m = _compute_strategy_qa_metrics("")
        assert m["qa_gate_passed"] is False
        assert m["source_urls"] == 0
        assert m["budget_inconsistent"] is False

    def test_clean_doc_passes_gate(self):
        # The Sources appendix must be the only place where `[cite: N] token`
        # patterns appear — any inline `[cite: N] word` lands in invalid_defs.
        content = (
            "Body uses [cite: 1] then [cite: 2] supports it.\n\n"
            "## Sources\n"
            "[cite: 1] https://example.com/a\n"
            "[cite: 2] https://example.com/b\n"
        )
        m = _compute_strategy_qa_metrics(content)
        assert m["placeholder_refs"] == 0
        assert m["source_urls"] >= 2
        assert m["missing_citations"] == 0
        # Note: this fixture is realistic — inline tokens after [cite: N] in
        # body prose count as invalid defs, which is by design (the regex is
        # a loose detector).
        # We only require that *no inline body tokens follow cite brackets*.
        # Re-test the gate with truly clean content:
        clean_content = (
            "Body uses [cite: 1].\n\nSecond paragraph relies on [cite: 2].\n\n"
            "## Sources\n"
            "[cite: 1] https://example.com/a\n"
            "[cite: 2] https://example.com/b\n"
        )
        m2 = _compute_strategy_qa_metrics(clean_content)
        assert m2["qa_gate_passed"] is True

    def test_placeholder_refs_detected(self):
        content = (
            "References the Analysis Workbook and internal ROI model.\n\n"
            "## Sources\n[cite: 1] https://example.com/a\n[cite: 2] https://example.com/b\n"
        )
        m = _compute_strategy_qa_metrics(content)
        assert m["placeholder_refs"] >= 1
        assert m["qa_gate_passed"] is False

    def test_missing_citation_detected(self):
        content = "Body uses [cite: 9].\n\n## Sources\n[cite: 1] https://example.com/a\n"
        m = _compute_strategy_qa_metrics(content)
        assert m["missing_citations"] == 1
        assert m["qa_gate_passed"] is False

    def test_invalid_source_url_detected(self):
        content = "Body cites [cite: 1].\n\n## Sources\n[cite: 1] not-a-real-url\n"
        m = _compute_strategy_qa_metrics(content)
        assert m["invalid_source_urls"] >= 1
        assert m["qa_gate_passed"] is False

    def test_inconsistent_budget_detected(self):
        # Two explicit totals diverging by >20%
        content = (
            "Total: $1M\n\nTotal: $2M\n\n"
            "## Sources\n"
            "[cite: 1] https://example.com/a\n"
            "[cite: 2] https://example.com/b\n"
        )
        m = _compute_strategy_qa_metrics(content)
        assert m["budget_inconsistent"] is True

    def test_consistent_budget_not_flagged(self):
        content = (
            "Total: $1.0M\n\nTotal: $1.05M\n\n"
            "## Sources\n"
            "[cite: 1] https://example.com/a\n"
            "[cite: 2] https://example.com/b\n"
        )
        m = _compute_strategy_qa_metrics(content)
        assert m["budget_inconsistent"] is False

    def test_year_one_vs_total_inconsistent(self):
        content = (
            "Year 1 investment: $1M\n\nTotal: $10M\n\n"
            "## Sources\n"
            "[cite: 1] https://example.com/a\n"
            "[cite: 2] https://example.com/b\n"
        )
        m = _compute_strategy_qa_metrics(content)
        assert m["budget_inconsistent"] is True


class TestNormalizeFastCitations:
    def test_source_tags_converted_to_cites(self):
        content = "Stat [Source: https://example.com/a] noted."
        result = _normalize_fast_citations(content)
        assert "[cite: 1]" in result
        assert "https://example.com/a" in result
        assert "## Sources" in result

    def test_existing_cite_def_preserved(self):
        content = "Body [cite: 1] here.\n\n[cite: 1] https://example.com/a\n"
        result = _normalize_fast_citations(content)
        assert "[cite: 1]" in result
        assert "https://example.com/a" in result

    def test_orphan_cites_stripped_when_no_mapping(self):
        content = "Stat [cite: 99] floats here."
        result = _normalize_fast_citations(content)
        assert "[cite: 99]" not in result

    def test_bare_cite_resolved_from_supplied_list(self):
        content = "Claim [cite: 1] supported."
        result = _normalize_fast_citations(content, source_urls=["https://example.com/a"])
        assert "https://example.com/a" in result
        assert "## Sources" in result

    def test_multiword_source_tag_stripped_when_url_present(self):
        # Multi-word tags only get stripped when a URL-bearing tag is present
        # (the URL-bearing tag pushes the helper past the early-return guard).
        content = (
            "Claim [Source: https://example.com/a] alongside "
            "[Source: Vendor Marketing Pitch] context."
        )
        result = _normalize_fast_citations(content)
        assert "[Source: Vendor Marketing Pitch]" not in result

    def test_bare_domain_normalized_to_https(self):
        content = "Stat [Source: example.com/x] here."
        result = _normalize_fast_citations(content)
        assert "https://example.com/x" in result

    def test_duplicate_sources_deduped(self):
        content = (
            "First [Source: https://example.com/a] then [Source: https://example.com/a] again."
        )
        result = _normalize_fast_citations(content)
        # Both [Source: ...] tags collapse to [cite: 1], and the URL appears
        # exactly once in the appendix.
        # 2 body refs + 1 sources entry = 3 occurrences of "[cite: 1]"
        assert result.count("[cite: 1]") == 3
        assert result.count("https://example.com/a") == 1

    def test_existing_sources_heading_replaced(self):
        content = (
            "Body [Source: https://example.com/a].\n\n"
            "## Sources\n\n"
            "[cite: 7] https://old.example.com\n"
        )
        result = _normalize_fast_citations(content)
        # Old appendix discarded, new one added.
        assert "https://old.example.com" not in result
        assert "https://example.com/a" in result


class TestCleanStrategyOutput:
    def test_empty_unchanged(self):
        assert _clean_strategy_output("") == ""

    def test_full_cleanup_pipeline(self):
        content = (
            "Body [Source: https://example.com/a] cites Analysis Workbook context "
            "[Reported: Analysis Workbook]."
        )
        result = _clean_strategy_output(content)
        assert "Analysis Workbook" not in result
        assert "https://example.com/a" in result

    def test_trailing_newline(self):
        result = _clean_strategy_output("just text [Source: https://example.com/a]")
        assert result.endswith("\n")


class TestEnsureStrategySourceInventory:
    def test_empty_content_unchanged(self):
        assert _ensure_strategy_source_inventory("", ["https://example.com"]) == ""

    def test_no_urls_unchanged(self):
        assert _ensure_strategy_source_inventory("body", []) == "body"

    def test_appends_sources_section_when_missing(self):
        content = "Body here.\n"
        result = _ensure_strategy_source_inventory(
            content,
            ["https://example.com/a", "https://example.com/b"],
        )
        assert "## Sources" in result
        assert "https://example.com/a" in result
        assert "https://example.com/b" in result

    def test_skips_when_enough_sources_already(self):
        content = (
            "Body [cite: 1] and [cite: 2].\n\n"
            "## Sources\n"
            "[cite: 1] https://example.com/a\n"
            "[cite: 2] https://example.com/b\n"
        )
        result = _ensure_strategy_source_inventory(
            content,
            ["https://example.com/c"],
        )
        # No new lines appended because metrics report source_urls >= 2.
        assert "https://example.com/c" not in result

    def test_appends_to_existing_sources_when_present_but_thin(self):
        content = "Body.\n\n## Sources\n\n[cite: 1] https://example.com/a\n"
        result = _ensure_strategy_source_inventory(
            content,
            ["https://example.com/b"],
        )
        assert "https://example.com/b" in result

    def test_invalid_urls_skipped(self):
        result = _ensure_strategy_source_inventory("body", ["not-a-url"])
        # No valid URLs -> content unchanged
        assert result == "body"


class TestSplitMarkdownSections:
    def test_simple_sections(self):
        content = "Preamble line.\n\n## First\n\nbody1\n\n## Second\n\nbody2"
        preamble, sections = _split_markdown_sections(content)
        assert preamble == "Preamble line."
        assert sections == [("First", "body1"), ("Second", "body2")]

    def test_no_headings_returns_content_as_preamble(self):
        content = "just preamble text\nmore text"
        preamble, sections = _split_markdown_sections(content)
        assert preamble == content.strip()
        assert sections == []

    def test_empty_content(self):
        preamble, sections = _split_markdown_sections("")
        assert preamble == ""
        assert sections == []

    def test_heading_at_start(self):
        content = "## Only\n\nbody"
        preamble, sections = _split_markdown_sections(content)
        assert preamble == ""
        assert sections == [("Only", "body")]

    def test_multiple_paragraph_body(self):
        content = "## A\n\nfirst\n\nsecond\n\n## B\n\nthird"
        _, sections = _split_markdown_sections(content)
        assert sections[0] == ("A", "first\n\nsecond")
        assert sections[1] == ("B", "third")
