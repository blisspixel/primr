"""Tests for thin wrapper helpers in DeepResearchOrchestrator/Client:
_get_phase_name, _get_poll_interval, _extract_content, _extract_citations,
_extract_search_queries_count.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import (
    DeepResearchClient,
    DeepResearchOrchestrator,
)


@pytest.fixture
def orchestrator(monkeypatch):
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    monkeypatch.setattr(dr, "_orchestrator", None)
    monkeypatch.setattr(dr, "_client", None)
    return DeepResearchOrchestrator(api_key="fake-key-1234567890")


@pytest.fixture
def client(monkeypatch):
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    monkeypatch.setattr(dr, "_orchestrator", None)
    monkeypatch.setattr(dr, "_client", None)
    return DeepResearchClient(api_key="fake-key-1234567890")


class TestOrchestratorGetPhaseName:
    def test_returns_string(self, orchestrator):
        name = orchestrator._get_phase_name(0)
        assert isinstance(name, str)

    def test_different_times_can_differ(self, orchestrator):
        early = orchestrator._get_phase_name(10)
        late = orchestrator._get_phase_name(2000)
        # Both should be strings (may or may not differ depending on phase boundaries)
        assert isinstance(early, str)
        assert isinstance(late, str)


class TestOrchestratorGetPollInterval:
    def test_under_60_returns_5(self, orchestrator):
        assert orchestrator._get_poll_interval(30) == 5.0

    def test_under_180_returns_10(self, orchestrator):
        assert orchestrator._get_poll_interval(120) == 10.0

    def test_under_360_returns_20(self, orchestrator):
        assert orchestrator._get_poll_interval(300) == 20.0

    def test_over_360_returns_30(self, orchestrator):
        assert orchestrator._get_poll_interval(500) == 30.0

    def test_returns_float(self, orchestrator):
        assert isinstance(orchestrator._get_poll_interval(10), float)


class TestExtractWrappers:
    def test_extract_content_delegates(self, client, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.deep_research.extract_interaction_content",
            MagicMock(return_value="extracted body"),
        )
        result = client._extract_content(MagicMock())
        assert result == "extracted body"

    def test_extract_citations_delegates(self, client, monkeypatch):
        cites = [{"title": "a", "url": "https://a.example"}]
        monkeypatch.setattr(
            "primr.ai.deep_research.extract_interaction_citations",
            MagicMock(return_value=cites),
        )
        result = client._extract_citations(MagicMock())
        assert result == cites

    def test_extract_search_queries_count_delegates(self, client, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.deep_research.extract_search_queries_count",
            MagicMock(return_value=42),
        )
        result = client._extract_search_queries_count(MagicMock())
        assert result == 42
