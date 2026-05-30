"""Unit tests for _fast_gap_analysis branches in primr.core.research_agent."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.research_agent import _fast_gap_analysis


class TestFastGapAnalysis:
    def test_empty_response_returns_empty(self, monkeypatch):
        # When LLM returns empty string, function reports gap analysis failed.
        monkeypatch.setattr(
            "primr.pipeline.llm_failover.call_with_failover",
            MagicMock(return_value=""),
        )
        queries, text = _fast_gap_analysis(
            "Acme",
            "https://acme.example",
            "[Page: home]\nbody",
            "[Source: news]\nbody",
            ["https://known.example"],
        )
        assert queries == []
        assert "empty" in text.lower()

    def test_llm_exception_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "primr.pipeline.llm_failover.call_with_failover",
            MagicMock(side_effect=RuntimeError("LLM down")),
        )
        queries, text = _fast_gap_analysis(
            "Acme",
            "https://acme.example",
            "raw corpus",
            "external sources",
            [],
        )
        assert queries == []
        assert "failed" in text.lower()

    def test_parses_query_lines(self, monkeypatch):
        response = """GAP: missing financial data
QUERY: Acme Corp revenue 2025
PRIORITY: CRITICAL

GAP: leadership changes
QUERY: Acme Corp CEO departure
PRIORITY: IMPORTANT

GAP: customer evidence
QUERY: Acme Corp case studies
PRIORITY: CRITICAL"""
        monkeypatch.setattr(
            "primr.pipeline.llm_failover.call_with_failover",
            MagicMock(return_value=response),
        )
        queries, _ = _fast_gap_analysis(
            "Acme",
            "https://acme.example",
            "raw",
            "ext",
            [],
        )
        assert "Acme Corp revenue 2025" in queries
        assert "Acme Corp CEO departure" in queries
        assert len(queries) == 3

    def test_caps_at_8_queries(self, monkeypatch):
        # 10 queries -> only first 8 returned
        response_lines = []
        for i in range(10):
            response_lines.append(f"GAP: gap {i}")
            response_lines.append(f"QUERY: query {i}")
            response_lines.append("PRIORITY: CRITICAL")
            response_lines.append("")
        monkeypatch.setattr(
            "primr.pipeline.llm_failover.call_with_failover",
            MagicMock(return_value="\n".join(response_lines)),
        )
        queries, _ = _fast_gap_analysis("Acme", None, "raw", "ext", [])
        assert len(queries) == 8

    def test_strips_quotes_and_brackets_from_queries(self, monkeypatch):
        response = """QUERY: "quoted query"
QUERY: [bracketed query]
QUERY: 'single quoted'"""
        monkeypatch.setattr(
            "primr.pipeline.llm_failover.call_with_failover",
            MagicMock(return_value=response),
        )
        queries, _ = _fast_gap_analysis("Acme", None, "raw", "ext", [])
        assert "quoted query" in queries
        assert "bracketed query" in queries
        assert "single quoted" in queries

    def test_uses_page_markers_for_corpus_summary(self, monkeypatch):
        # When corpus has [Page: ...] markers, only the marker-prefixed blocks are used.
        # Just verify the function doesn't crash with structured corpus.
        corpus = "[Page: about]\nabout body\n\n[Page: products]\nproducts body"
        monkeypatch.setattr(
            "primr.pipeline.llm_failover.call_with_failover",
            MagicMock(return_value=""),
        )
        queries, _ = _fast_gap_analysis("Acme", "https://acme.example", corpus, "", [])
        assert queries == []
