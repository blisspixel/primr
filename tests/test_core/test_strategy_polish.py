"""Tests for _strategy_polish — coherence + evidence discipline pass."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.research_agent import _a_or_an, _strategy_polish


class TestAOrAn:
    def test_vowel_returns_an(self):
        assert _a_or_an("Apple") == "an"
        assert _a_or_an("Orange") == "an"

    def test_consonant_returns_a(self):
        assert _a_or_an("Banana") == "a"
        assert _a_or_an("Strawberry") == "a"

    def test_empty_returns_a(self):
        assert _a_or_an("") == "a"

    def test_case_insensitive(self):
        assert _a_or_an("apple") == "an"
        assert _a_or_an("AZURE") == "an"


class TestStrategyPolish:
    def test_empty_content_returns_unchanged(self):
        assert _strategy_polish("Acme", "azure", "") == ""

    def test_whitespace_content_returns_unchanged(self):
        result = _strategy_polish("Acme", "azure", "   \n   ")
        assert result == "   \n   "

    def test_llm_returns_empty_returns_original(self, monkeypatch):
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", MagicMock(return_value=""))
        original = "## Section\n\nbody " * 100
        result = _strategy_polish("Acme", "azure", original)
        assert result == original

    def test_destructive_compression_returns_original(self, monkeypatch):
        # 100 words original; polished only 50 words (50% — below 90% threshold)
        original = "## Section\n\n" + ("word " * 100)
        polished = "## Section\n\n" + ("word " * 50)
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", MagicMock(return_value=polished))
        result = _strategy_polish("Acme", "azure", original)
        assert result == original

    def test_lost_sections_returns_original(self, monkeypatch):
        # 3 sections original; polished only 1 section
        original = (
            "## A\n\n"
            + "word " * 100
            + "\n\n## B\n\n"
            + "word " * 100
            + "\n\n## C\n\n"
            + "word " * 100
        )
        # Same word count but only 1 section
        polished = "## A\n\n" + "word " * 300
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", MagicMock(return_value=polished))
        result = _strategy_polish("Acme", "azure", original)
        assert result == original

    def test_acceptable_polish_returned(self, monkeypatch):
        original = "## Section\n\n" + ("word " * 100)
        polished = "## Section\n\n" + ("word " * 95)  # 95% — within tolerance
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", MagicMock(return_value=polished))
        result = _strategy_polish("Acme", "azure", original)
        assert result == polished

    def test_llm_exception_returns_original(self, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(side_effect=RuntimeError("grok down")),
        )
        original = "## Section\n\n" + ("word " * 100)
        result = _strategy_polish("Acme", "azure", original)
        assert result == original

    def test_explicit_model_used(self, monkeypatch):
        # Routed through the failover seam: a real registered model passed
        # explicitly is honored as the preferred (first-tried) model. Unknown
        # model strings fall through to the chain default by design.
        from primr.pipeline.llm_failover import set_breaker_for_test
        from primr.pipeline.model_breaker import ModelCircuitBreaker

        set_breaker_for_test(ModelCircuitBreaker())
        monkeypatch.setenv("XAI_API_KEY", "fake")
        mock = MagicMock(return_value="## Section\n\n" + ("word " * 100))
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)
        _strategy_polish(
            "Acme",
            "azure",
            "## Section\n\n" + ("word " * 100),
            model="grok-4.3",
        )
        set_breaker_for_test(None)
        assert mock.call_args.kwargs["model"] == "grok-4.3"
