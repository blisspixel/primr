"""Unit tests for _polish_fast_report_for_trust and similar polish helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.research_agent import _polish_fast_report_for_trust


class TestPolishFastReportForTrust:
    def test_empty_content_returns_unchanged(self):
        assert _polish_fast_report_for_trust("Acme", "https://acme.example", "", []) == ""

    def test_whitespace_content_returns_unchanged(self):
        result = _polish_fast_report_for_trust("Acme", "https://acme.example", "   \n\n", [])
        assert result == "   \n\n"

    def test_empty_polish_returns_original(self, monkeypatch):
        original = "## Section\n\nbody " * 50
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=""),
        )
        result = _polish_fast_report_for_trust(
            "Acme", "https://acme.example", original, ["https://s1.example"]
        )
        assert result == original

    def test_truncated_polish_returns_original(self, monkeypatch):
        # Original 1500 words; polished only 100 words -> rejected (too compressed)
        original = "## Section\n\n" + ("word " * 1500)
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value="## Section\n\n" + ("word " * 100)),
        )
        result = _polish_fast_report_for_trust(
            "Acme", "https://acme.example", original, ["https://s1.example"]
        )
        # Should fall back to original
        assert result == original

    def test_acceptable_polish_returned(self, monkeypatch):
        original = "## Section\n\n" + ("word " * 1500)
        # 80% of 1500 = 1200, so 1300 words passes
        polished = "## Section\n\n" + ("word " * 1300)
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=polished),
        )
        result = _polish_fast_report_for_trust(
            "Acme", "https://acme.example", original, ["https://s1.example"]
        )
        assert result == polished

    def test_short_report_uses_lower_threshold(self, monkeypatch):
        # Original < 100 words -> min_words = 1 -> any non-empty polish accepted
        original = "## S\n\nshort body"
        polished = "## S\n\nshort polished body"
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=polished),
        )
        result = _polish_fast_report_for_trust("Acme", "https://acme.example", original, [])
        assert result == polished

    def test_section_count_too_low_returns_original(self, monkeypatch):
        # Original 3 sections; polished only 1 section (1 < 3*0.70 = 2.1 → 2)
        original = (
            "## A\n\n"
            + "word " * 100
            + "\n\n## B\n\n"
            + "word " * 100
            + "\n\n## C\n\n"
            + "word " * 100
        )
        polished = "## A\n\n" + "word " * 300  # enough words but only 1 section
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=polished),
        )
        result = _polish_fast_report_for_trust("Acme", "https://acme.example", original, [])
        assert result == original

    def test_exception_returns_original(self, monkeypatch):
        original = "## Section\n\n" + "word " * 200
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(side_effect=RuntimeError("grok down")),
        )
        result = _polish_fast_report_for_trust("Acme", "https://acme.example", original, [])
        assert result == original

    def test_explicit_model_param_used(self, monkeypatch):
        # The polish pass now routes through the failover seam: an explicit
        # model param is honored as the preferred (first-tried) model when it
        # is a real registered model with an available key. Unknown model
        # strings intentionally fall through to the chain default instead of
        # being dispatched verbatim (see llm_failover preferred_model docs).
        from primr.pipeline.llm_failover import set_breaker_for_test
        from primr.pipeline.model_breaker import ModelCircuitBreaker

        set_breaker_for_test(ModelCircuitBreaker())
        monkeypatch.setenv("XAI_API_KEY", "fake")
        mock = MagicMock(return_value="## S\n\nbody " * 100)
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)
        _polish_fast_report_for_trust(
            "Acme",
            "https://acme.example",
            "## S\n\nbody " * 50,
            [],
            model="grok-4.3",
        )
        set_breaker_for_test(None)
        kwargs = mock.call_args.kwargs
        assert kwargs["model"] == "grok-4.3"
