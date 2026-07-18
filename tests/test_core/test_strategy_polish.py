"""Tests for the _strategy_polish coherence and evidence-discipline pass."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.research_agent import _strategy_polish


class TestStrategyPolish:
    def test_prompt_preserves_business_first_vendor_neutral_contract(self, monkeypatch):
        original = "## Section\n\n" + ("word " * 100)
        mock = MagicMock(return_value=original)
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)

        _strategy_polish("Acme", "agnostic", original)

        prompt = mock.call_args.args[0]
        assert "business-first AI strategy" in prompt
        assert "not a predetermined vendor answer" in prompt
        assert "Specific AGNOSTIC services/products" not in prompt
        assert "Lacks specific implementation details, timelines, or cost estimates" not in prompt

    def test_generic_strategy_keeps_its_own_document_contract(self, monkeypatch):
        original = "## Section\n\n" + ("word " * 100)
        mock = MagicMock(return_value=original)
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)

        _strategy_polish(
            "Acme",
            "Customer Experience",
            original,
            label="Customer Experience",
        )

        prompt = mock.call_args.args[0]
        assert "Customer Experience document" in prompt
        assert "business-first AI strategy" not in prompt
        assert "PLATFORM EVALUATION EMPHASIS" not in prompt

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
        # The polished result keeps only 50% of the original, below the 90% threshold.
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
        polished = "## Section\n\n" + ("word " * 95)  # 95% is within tolerance.
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
