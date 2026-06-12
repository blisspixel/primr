"""Tests for the extracted insights/external-sources assembly (roadmap #23, Batch B)."""

from __future__ import annotations

from primr.core.insights_assembly import (
    NO_EXTERNAL_SOURCES,
    NO_RESEARCH_FALLBACK,
    build_combined_insights,
    build_external_sources_raw,
)


class TestBuildCombinedInsights:
    def test_all_parts_present_in_order(self):
        result = build_combined_insights(
            "site summary",
            ["[Source: https://a.example]\nfact"],
            "=== HIRING SIGNALS ===\npostings",
        )
        web = result.index("=== WEBSITE INSIGHTS ===")
        ext = result.index("=== EXTERNAL SOURCES ===")
        hiring = result.index("=== HIRING SIGNALS ===")
        assert web < ext < hiring
        assert "site summary" in result
        assert "fact" in result

    def test_empty_parts_are_omitted(self):
        result = build_combined_insights("site summary", [], "")
        assert "=== EXTERNAL SOURCES ===" not in result
        assert "=== HIRING SIGNALS ===" not in result

    def test_default_fallback_when_everything_empty(self):
        assert build_combined_insights("", [], "") == NO_RESEARCH_FALLBACK

    def test_rebuild_fallback_preserves_previous_insights(self):
        # The post-gap rebuild passes the previous combined insights so a
        # degenerate refresh never erases data.
        previous = "=== WEBSITE INSIGHTS ===\nfrom the first build"
        assert build_combined_insights("", [], "", fallback=previous) == previous

    def test_multiple_external_parts_joined(self):
        result = build_combined_insights("", ["[Source: a]\none", "[Source: b]\ntwo"], "")
        assert "one" in result
        assert "two" in result
        assert result.count("=== EXTERNAL SOURCES ===") == 1


class TestBuildExternalSourcesRaw:
    def test_hiring_block_rides_along(self):
        result = build_external_sources_raw(
            ["[Source: a]\ncontent"], "=== HIRING SIGNALS ===\npostings"
        )
        assert "content" in result
        assert "=== HIRING SIGNALS ===" in result
        assert result.index("content") < result.index("=== HIRING SIGNALS ===")

    def test_no_hiring_block(self):
        assert build_external_sources_raw(["only"], "") == "only"

    def test_empty_returns_sentinel(self):
        assert build_external_sources_raw([], "") == NO_EXTERNAL_SOURCES

    def test_hiring_only_is_still_evidence(self):
        # Hiring signals alone (no other external sources) must still reach
        # the prompts rather than collapsing to the no-sources sentinel.
        result = build_external_sources_raw([], "=== HIRING SIGNALS ===\npostings")
        assert result != NO_EXTERNAL_SOURCES
        assert "postings" in result

    def test_input_list_not_mutated(self):
        parts = ["a"]
        build_external_sources_raw(parts, "hiring")
        assert parts == ["a"]
