"""Tests for _assess_source_relevance — LLM-based source filtering."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.research_agent import _assess_source_relevance


def _ten_sources():
    return {f"https://s{i}.example": f"content about Acme {i}" * 50 for i in range(10)}


class TestAssessSourceRelevance:
    def test_skips_filter_when_too_few_sources(self):
        small = {f"https://s{i}.example": "body" for i in range(5)}
        result = _assess_source_relevance("Acme", small)
        # 5 sources or fewer -> short circuit, return unchanged
        assert result == small

    def test_empty_input_returns_empty(self):
        assert _assess_source_relevance("Acme", {}) == {}

    def test_llm_filters_to_subset(self, monkeypatch):
        sources = _ten_sources()
        # LLM keeps 1, 3, 5, 7, 9 (1-indexed)
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value="[1, 3, 5, 7, 9]"),
        )
        result = _assess_source_relevance("Acme", sources)
        # 5 kept (>= 3 threshold)
        assert len(result) == 5

    def test_llm_too_aggressive_falls_back_to_all(self, monkeypatch):
        sources = _ten_sources()
        # LLM keeps only 2 — too aggressive, fallback returns originals
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value="[1, 2]"),
        )
        result = _assess_source_relevance("Acme", sources)
        assert result == sources  # fallback

    def test_llm_response_with_markdown_fence_parsed(self, monkeypatch):
        sources = _ten_sources()
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value="```json\n[1, 2, 3, 4, 5]\n```"),
        )
        result = _assess_source_relevance("Acme", sources)
        assert len(result) == 5

    def test_llm_no_brackets_falls_back(self, monkeypatch):
        sources = _ten_sources()
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value="not a list at all"),
        )
        result = _assess_source_relevance("Acme", sources)
        assert result == sources

    def test_llm_exception_falls_back(self, monkeypatch):
        sources = _ten_sources()
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(side_effect=RuntimeError("llm down")),
        )
        result = _assess_source_relevance("Acme", sources)
        assert result == sources

    def test_out_of_range_indices_filtered(self, monkeypatch):
        sources = _ten_sources()  # 10 sources, indices 1-10
        # Mix valid and out-of-range
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value="[1, 2, 3, 50, 100]"),
        )
        result = _assess_source_relevance("Acme", sources)
        # Only indices 1-3 are valid -> 3 sources; >= 3 threshold met
        assert len(result) == 3
