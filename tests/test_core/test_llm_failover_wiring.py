"""Production-wiring tests for the circuit-breaker failover (Active Queue #6).

The failover seam itself is covered in tests/test_pipeline/test_llm_failover.py.
These tests pin the WIRING: the research_agent helpers and the llm() utility
dispatch must route through call_with_failover, so a QuotaExhaustedError on the
primary model advances to the next provider in the chain instead of degrading
(or failing) the stage.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from primr.ai.providers.base import QuotaExhaustedError
from primr.pipeline.llm_failover import set_breaker_for_test
from primr.pipeline.model_breaker import ModelCircuitBreaker


@pytest.fixture(autouse=True)
def fresh_breaker():
    """Each test gets a clean breaker so quota state never leaks between tests."""
    breaker = ModelCircuitBreaker(failure_threshold=3, recovery_timeout=0.01)
    set_breaker_for_test(breaker)
    yield breaker
    set_breaker_for_test(None)


@pytest.fixture(autouse=True)
def all_keys_set(monkeypatch):
    """Pretend every provider has an API key so chain selection is unrestricted."""
    monkeypatch.setenv("XAI_API_KEY", "fake")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")


def _quota_on_first(first_model: str, response: str = "ok"):
    """Fake grok_llm that quota-fails the given model and succeeds on others."""
    calls: list[str] = []

    def fake(prompt: str, *, model: str | None = None, **kw) -> str:
        calls.append(model or "")
        if model == first_model:
            raise QuotaExhaustedError(f"quota exhausted for {model}")
        return response

    return fake, calls


class TestStrategyCrossValidateFailover:
    def test_quota_on_preferred_model_falls_over_instead_of_degrading(self):
        from primr.core.research_agent import _strategy_cross_validate

        fake, calls = _quota_on_first("grok-4.3", response='{"weak_sections": [], "issues": []}')
        with patch("primr.ai.grok_client.grok_llm", side_effect=fake):
            result = _strategy_cross_validate(
                "Acme Corp",
                "## Strategy\nSome content.",
                "azure",
                ["https://example.com"],
                model="grok-4.3",
            )

        # Without failover this returned {"_failed": True} and the stage was
        # silently skipped. With it, the next chain model serviced the call.
        assert "_failed" not in result
        assert result == {"weak_sections": [], "issues": []}
        assert calls[0] == "grok-4.3"
        assert len(calls) >= 2


class TestWritingHelperFailover:
    def test_citation_repair_falls_over_on_quota(self):
        from primr.core.research_agent import _repair_fast_report_citation_integrity

        report = "## Overview\nA claim that needs a citation.\n"
        fake, calls = _quota_on_first(
            "grok-4.20-non-reasoning",
            response="## Overview\nA claim that needs a citation. [cite: 1]\n\n## Sources\n1. https://example.com\n",
        )
        with patch("primr.ai.grok_client.grok_llm", side_effect=fake):
            repaired = _repair_fast_report_citation_integrity(
                "Acme Corp",
                "https://acme.example",
                report,
                ["https://example.com"],
                model="grok-4.20-non-reasoning",
            )

        assert "[cite: 1]" in repaired
        assert calls[0] == "grok-4.20-non-reasoning"
        assert len(calls) >= 2

    def test_non_quota_error_still_degrades_gracefully(self):
        """Regular exceptions keep the existing keep-original behavior."""
        from primr.core.research_agent import _repair_fast_report_citation_integrity

        report = "## Overview\nOriginal content.\n"

        def explode(prompt: str, **kw) -> str:
            raise ValueError("malformed request")

        with patch("primr.ai.grok_client.grok_llm", side_effect=explode):
            repaired = _repair_fast_report_citation_integrity(
                "Acme Corp", None, report, ["https://example.com"]
            )

        assert repaired == report


class TestLLMUtilityDispatchFailover:
    def test_xai_utility_dispatch_falls_over_on_quota(self, monkeypatch):
        from primr.ai import llm as llm_module

        monkeypatch.setattr(llm_module, "_get_model_for_type", lambda t: "grok-4.20-non-reasoning")

        fake, calls = _quota_on_first("grok-4.20-non-reasoning", response="utility ok")
        with patch("primr.ai.grok_client.grok_llm", side_effect=fake):
            result = llm_module.llm("summarize this", model_type="fast")

        assert result == "utility ok"
        assert calls[0] == "grok-4.20-non-reasoning"
        assert len(calls) >= 2

    def test_xai_utility_dispatch_happy_path_single_call(self, monkeypatch):
        from primr.ai import llm as llm_module

        monkeypatch.setattr(llm_module, "_get_model_for_type", lambda t: "grok-4.20-non-reasoning")

        calls: list[str] = []

        def fake(prompt: str, *, model: str | None = None, **kw) -> str:
            calls.append(model or "")
            return "ok"

        with patch("primr.ai.grok_client.grok_llm", side_effect=fake):
            result = llm_module.llm("summarize this", model_type="fast")

        assert result == "ok"
        assert calls == ["grok-4.20-non-reasoning"]
