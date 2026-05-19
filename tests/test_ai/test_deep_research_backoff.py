"""Tests for DeepResearchOrchestrator._calculate_backoff_delay and other simple
synchronous helpers in primr.ai.deep_research."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import (
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


class TestCalculateBackoffDelay:
    def test_attempt_zero_returns_base(self, orchestrator):
        # delay = BASE_RETRY_DELAY * 2^0 = BASE_RETRY_DELAY
        d = orchestrator._calculate_backoff_delay(0)
        assert d == orchestrator.BASE_RETRY_DELAY

    def test_attempt_one_doubles(self, orchestrator):
        d = orchestrator._calculate_backoff_delay(1)
        assert d == orchestrator.BASE_RETRY_DELAY * 2

    def test_attempt_two_quadruples(self, orchestrator):
        d = orchestrator._calculate_backoff_delay(2)
        assert d == orchestrator.BASE_RETRY_DELAY * 4

    def test_attempt_three_8x(self, orchestrator):
        d = orchestrator._calculate_backoff_delay(3)
        assert d == orchestrator.BASE_RETRY_DELAY * 8

    def test_monotonic_increase(self, orchestrator):
        prev = 0
        for n in range(5):
            cur = orchestrator._calculate_backoff_delay(n)
            assert cur > prev
            prev = cur
