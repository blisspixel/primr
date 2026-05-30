"""Tests for the circuit-breaker-aware LLM dispatch helper.

Validates that ``call_with_failover`` actually invokes the configured
fallback chain on ``QuotaExhaustedError`` instead of propagating it like
a fatal error — this is the seam the v1.26.0 "wire circuit breaker into
production LLM call sites" roadmap item ships.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from primr.ai.providers.base import QuotaExhaustedError
from primr.pipeline.llm_failover import (
    LLMRole,
    _chain_for_role,
    call_with_failover,
    set_breaker_for_test,
)
from primr.pipeline.model_breaker import (
    ANALYSIS_FALLBACK_CHAIN,
    PREMIUM_FALLBACK_CHAIN,
    UTILITY_FALLBACK_CHAIN,
    ModelCircuitBreaker,
)


@pytest.fixture
def fresh_breaker():
    """Install a clean breaker so prior tests' quota events don't leak."""
    breaker = ModelCircuitBreaker(failure_threshold=3, recovery_timeout=0.01)
    set_breaker_for_test(breaker)
    yield breaker
    set_breaker_for_test(None)


@pytest.fixture
def all_keys_set(monkeypatch):
    """Pretend every provider has an API key so chain selection is unrestricted."""
    monkeypatch.setenv("XAI_API_KEY", "fake")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")


class TestChainSelection:
    def test_reasoning_role_uses_analysis_chain(self):
        assert _chain_for_role(LLMRole.REASONING) is ANALYSIS_FALLBACK_CHAIN

    def test_writing_role_uses_utility_chain(self):
        assert _chain_for_role(LLMRole.WRITING) is UTILITY_FALLBACK_CHAIN

    def test_premium_role_uses_premium_chain(self):
        assert _chain_for_role(LLMRole.PREMIUM) is PREMIUM_FALLBACK_CHAIN


class TestHappyPath:
    def test_first_model_succeeds_no_failover(self, fresh_breaker, all_keys_set):
        """When the primary model works, no fallback is attempted."""
        calls: list[str] = []

        def fake_llm(prompt: str, *, model: str, **kw) -> str:
            calls.append(model)
            return f"ok from {model}"

        result = call_with_failover(
            LLMRole.REASONING,
            "test prompt",
            grok_llm_fn=fake_llm,
        )
        assert result.startswith("ok from ")
        assert len(calls) == 1, f"Expected single call, got {calls}"
        # Should be the first model in the analysis chain
        assert calls[0] == ANALYSIS_FALLBACK_CHAIN.models[0]

    def test_kwargs_forwarded_to_grok_llm(self, fresh_breaker, all_keys_set):
        captured: dict = {}

        def fake_llm(prompt: str, *, model: str, **kw) -> str:
            captured["prompt"] = prompt
            captured["model"] = model
            captured["kwargs"] = kw
            return "ok"

        call_with_failover(
            LLMRole.WRITING,
            "the prompt",
            grok_llm_fn=fake_llm,
            temperature=0.42,
            max_tokens=1234,
        )
        assert captured["prompt"] == "the prompt"
        assert captured["kwargs"] == {"temperature": 0.42, "max_tokens": 1234}


class TestQuotaFailover:
    def test_quota_on_first_model_falls_back(self, fresh_breaker, all_keys_set):
        """QuotaExhaustedError from model #1 triggers retry on model #2."""
        chain = _chain_for_role(LLMRole.REASONING)
        first_model = chain.models[0]
        calls: list[str] = []

        def fake_llm(prompt: str, *, model: str, **kw) -> str:
            calls.append(model)
            if model == first_model:
                raise QuotaExhaustedError(f"quota exhausted for {model}")
            return f"ok from {model}"

        result = call_with_failover(
            LLMRole.REASONING,
            "test",
            grok_llm_fn=fake_llm,
        )
        assert result.startswith("ok from ")
        assert calls[0] == first_model
        assert len(calls) >= 2, f"Expected fallback, got only {calls}"
        # The successful model must not be the exhausted first model.
        assert calls[-1] != first_model

    def test_all_models_exhausted_raises_runtime_error(self, fresh_breaker, all_keys_set):
        """When every model in the chain quotas out, we surface RuntimeError."""

        def fake_llm(prompt: str, *, model: str, **kw) -> str:
            raise QuotaExhaustedError(f"quota exhausted for {model}")

        with pytest.raises(RuntimeError, match=r"unavailable|exhausted"):
            call_with_failover(
                LLMRole.UTILITY if hasattr(LLMRole, "UTILITY") else LLMRole.WRITING,
                "test",
                grok_llm_fn=fake_llm,
            )

    def test_non_quota_error_propagates_immediately(self, fresh_breaker, all_keys_set):
        """A regular exception (not QuotaExhaustedError) bubbles up without retry."""
        calls: list[str] = []

        def fake_llm(prompt: str, *, model: str, **kw) -> str:
            calls.append(model)
            raise ValueError("not a quota issue — programmer error")

        with pytest.raises(ValueError, match="programmer error"):
            call_with_failover(
                LLMRole.REASONING,
                "test",
                grok_llm_fn=fake_llm,
            )
        # Should not have tried multiple models for a non-quota error.
        assert len(calls) == 1


class TestPreferredModel:
    def test_preferred_model_rotates_to_front(self, fresh_breaker, all_keys_set):
        """preferred_model=X causes X to be tried first if it's in the chain."""
        chain = _chain_for_role(LLMRole.REASONING)
        preferred = chain.models[-1]  # something deep in the chain
        calls: list[str] = []

        def fake_llm(prompt: str, *, model: str, **kw) -> str:
            calls.append(model)
            return f"ok from {model}"

        call_with_failover(
            LLMRole.REASONING,
            "test",
            preferred_model=preferred,
            grok_llm_fn=fake_llm,
        )
        assert calls[0] == preferred

    def test_unknown_preferred_model_falls_through(self, fresh_breaker, all_keys_set):
        """preferred_model with no known config is prepended but skipped by
        select_model (no config / no API key), so dispatch safely falls through
        to the chain head without erroring."""
        calls: list[str] = []

        def fake_llm(prompt: str, *, model: str, **kw) -> str:
            calls.append(model)
            return "ok"

        call_with_failover(
            LLMRole.REASONING,
            "test",
            preferred_model="not-a-real-model-xyz",
            grok_llm_fn=fake_llm,
        )
        # First call uses the default chain head, not the unusable preferred.
        assert calls[0] == _chain_for_role(LLMRole.REASONING).models[0]

    def test_usable_preferred_model_outside_chain_is_honored(self, fresh_breaker, all_keys_set):
        """A real model that is NOT a standing chain member must still be tried
        first. This is the cost-cap fix: fast-mode writing routes to
        gemini-3.1-flash-lite, which is absent from UTILITY_FALLBACK_CHAIN and
        is what the MCP estimate is priced against. Before the fix, an absent
        preferred model was silently dropped and the pricier Grok chain head ran
        instead — diverging from the approved max_estimated_cost_usd.
        """
        preferred = "gemini-3.1-flash-lite"
        # Guard the premise: the bug only bites for models outside the chain.
        assert preferred not in UTILITY_FALLBACK_CHAIN.models
        calls: list[str] = []

        def fake_llm(prompt: str, *, model: str, **kw) -> str:
            calls.append(model)
            return f"ok from {model}"

        call_with_failover(
            LLMRole.WRITING,
            "test",
            preferred_model=preferred,
            grok_llm_fn=fake_llm,
        )
        assert calls[0] == preferred


class TestProductionDispatchDefault:
    """When no grok_llm_fn is provided, the real grok_llm is used."""

    def test_default_dispatcher_is_grok_llm(self, fresh_breaker, all_keys_set):
        # Patch the real grok_llm to return a sentinel — confirms the helper
        # routes through it when grok_llm_fn is not explicitly provided.
        with patch("primr.ai.grok_client.grok_llm", return_value="sentinel") as mock:
            result = call_with_failover(LLMRole.REASONING, "test")
        assert result == "sentinel"
        mock.assert_called_once()
