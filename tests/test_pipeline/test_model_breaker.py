"""
Unit tests for model circuit breaker, fallback chains, and health logging.

**Feature: pipeline-resilience**
**Validates: Requirements 11.3, 12.1, 12.2, 12.3**
"""

from __future__ import annotations

from primr.config.models import PrimrModels
from primr.pipeline.model_breaker import (
    ANALYSIS_FALLBACK_CHAIN,
    PREMIUM_FALLBACK_CHAIN,
    UTILITY_FALLBACK_CHAIN,
    ModelCircuitBreaker,
    ModelHealthEvent,
)


class TestFallbackChainOrder:
    """Test that fallback chains are defined in the correct order."""

    def test_analysis_fallback_chain_order(self) -> None:
        """Analysis chain: Grok 4.3 -> Grok 4.20 -> Claude Sonnet -> GPT-5.4 -> Gemini Flash."""
        assert ANALYSIS_FALLBACK_CHAIN.models == (
            PrimrModels.GROK_MODEL_43,
            PrimrModels.GROK_MODEL_420,
            "claude-sonnet-4-6",
            "gpt-5.4",
            PrimrModels.FLASH_MODEL,
        )

    def test_analysis_fallback_chain_name(self) -> None:
        """Analysis chain has the correct name."""
        assert ANALYSIS_FALLBACK_CHAIN.name == "analysis"

    def test_premium_fallback_chain_order(self) -> None:
        """Premium chain: Gemini Pro -> Claude Opus -> GPT-5.5 -> Grok 4.3."""
        assert PREMIUM_FALLBACK_CHAIN.models == (
            PrimrModels.PRO_MODEL,
            "claude-opus-4-7",
            "gpt-5.5",
            PrimrModels.GROK_MODEL_43,
        )

    def test_premium_fallback_chain_name(self) -> None:
        """Premium chain has the correct name."""
        assert PREMIUM_FALLBACK_CHAIN.name == "premium"

    def test_utility_fallback_chain_order(self) -> None:
        """Utility chain: grok-4.20-non-reasoning -> gpt-5.4-mini -> Gemini Flash."""
        assert UTILITY_FALLBACK_CHAIN.models == (
            "grok-4.20-non-reasoning",
            "gpt-5.4-mini",
            PrimrModels.FLASH_MODEL,
        )

    def test_utility_fallback_chain_name(self) -> None:
        """Utility chain has the correct name."""
        assert UTILITY_FALLBACK_CHAIN.name == "utility"


class TestModelHealthEvent:
    """Test ModelHealthEvent dataclass and serialization."""

    def test_to_dict_structure(self) -> None:
        """to_dict() produces the correct structure."""
        event = ModelHealthEvent(
            timestamp="2026-02-15T10:30:00",
            model="grok-4.20-0309-reasoning",
            from_state="closed",
            to_state="open",
            failure_count=3,
        )
        result = event.to_dict()
        assert result == {
            "timestamp": "2026-02-15T10:30:00",
            "model": "grok-4.20-0309-reasoning",
            "from_state": "closed",
            "to_state": "open",
            "failure_count": 3,
        }

    def test_to_dict_keys(self) -> None:
        """to_dict() contains exactly the expected keys."""
        event = ModelHealthEvent(
            timestamp="2026-02-15T10:30:00",
            model="test-model",
            from_state="closed",
            to_state="open",
            failure_count=3,
        )
        assert set(event.to_dict().keys()) == {
            "timestamp",
            "model",
            "from_state",
            "to_state",
            "failure_count",
        }


class TestModelHealthLogging:
    """Test that health events are emitted and can be stored in run state."""

    def test_health_events_collected_for_model_health_key(self) -> None:
        """Health events can be collected into a model_health array."""
        model_health: list[dict[str, object]] = []

        def listener(event: ModelHealthEvent) -> None:
            model_health.append(event.to_dict())

        breaker = ModelCircuitBreaker(
            failure_threshold=3,
            health_listener=listener,
        )

        model = PrimrModels.GROK_MODEL_420
        for _ in range(3):
            breaker.record_failure(model)

        # Should have one event: CLOSED -> OPEN
        assert len(model_health) == 1
        event = model_health[0]
        assert event["model"] == model
        assert event["from_state"] == "closed"
        assert event["to_state"] == "open"
        assert isinstance(event["timestamp"], str)
        assert len(str(event["timestamp"])) > 0

    def test_no_events_without_listener(self) -> None:
        """No crash when health_listener is None."""
        breaker = ModelCircuitBreaker(failure_threshold=3)
        model = PrimrModels.GROK_MODEL
        for _ in range(3):
            breaker.record_failure(model)
        # Should not raise — just verifying no crash

    def test_multiple_transitions_logged(self) -> None:
        """Multiple state transitions produce multiple health events."""
        import time

        events: list[ModelHealthEvent] = []
        breaker = ModelCircuitBreaker(
            failure_threshold=3,
            recovery_timeout=0.01,
            health_listener=events.append,
        )

        model = PrimrModels.GROK_MODEL
        # CLOSED -> OPEN
        for _ in range(3):
            breaker.record_failure(model)
        assert len(events) == 1

        # Wait for timeout, trigger HALF_OPEN
        time.sleep(0.02)
        breaker.is_healthy(model)
        # OPEN -> HALF_OPEN
        assert len(events) == 2

        # HALF_OPEN -> CLOSED
        breaker.record_success(model)
        assert len(events) == 3

        states = [(e.from_state, e.to_state) for e in events]
        assert states == [
            ("closed", "open"),
            ("open", "half_open"),
            ("half_open", "closed"),
        ]


class TestQuotaAwareFallback:
    """Test quota-aware extensions of ModelCircuitBreaker."""

    def test_mark_quota_exhausted_stores_status(self) -> None:
        """mark_quota_exhausted stores a QuotaStatus entry for the provider."""
        breaker = ModelCircuitBreaker(failure_threshold=3)
        breaker.mark_quota_exhausted("xai")

        status = breaker.get_quota_status()
        assert "xai" in status
        assert status["xai"].is_exhausted is True
        assert status["xai"].provider == "xai"
        assert status["xai"].exhausted_at is not None
        assert status["xai"].resets_at is not None

    def test_is_provider_quota_exhausted_true_after_marking(self) -> None:
        """is_provider_quota_exhausted returns True after marking."""
        breaker = ModelCircuitBreaker(failure_threshold=3)
        breaker.mark_quota_exhausted("openai")
        assert breaker.is_provider_quota_exhausted("openai") is True

    def test_is_provider_quota_exhausted_false_for_unknown(self) -> None:
        """is_provider_quota_exhausted returns False for unmarked providers."""
        breaker = ModelCircuitBreaker(failure_threshold=3)
        assert breaker.is_provider_quota_exhausted("xai") is False

    def test_is_healthy_returns_false_for_quota_exhausted_provider(self, monkeypatch) -> None:
        """is_healthy returns False for models whose provider is quota-exhausted."""
        monkeypatch.setenv("XAI_API_KEY", "test-key")
        breaker = ModelCircuitBreaker(failure_threshold=3)
        breaker.mark_quota_exhausted("xai")

        # grok-4.3 is an xAI model — should be unhealthy
        assert breaker.is_healthy(PrimrModels.GROK_MODEL_43) is False

    def test_select_model_skips_quota_exhausted_provider(self, monkeypatch) -> None:
        """select_model skips models from quota-exhausted providers."""
        from primr.pipeline.model_breaker import FallbackChain

        monkeypatch.setenv("XAI_API_KEY", "test-key")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        breaker = ModelCircuitBreaker(failure_threshold=3)
        breaker.mark_quota_exhausted("xai")

        # Chain with xAI first, then Gemini
        chain = FallbackChain(
            name="test",
            models=(PrimrModels.GROK_MODEL_43, PrimrModels.FLASH_MODEL),
        )
        selected = breaker.select_model(chain)
        assert selected == PrimrModels.FLASH_MODEL

    def test_quota_resets_after_midnight(self) -> None:
        """Quota entries are cleared when resets_at time has passed."""
        from datetime import datetime, timedelta, timezone

        breaker = ModelCircuitBreaker(failure_threshold=3)
        breaker.mark_quota_exhausted("xai")

        # Manually set resets_at to the past to simulate midnight passing
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        breaker._quota_exhausted["xai"].resets_at = past

        assert breaker.is_provider_quota_exhausted("xai") is False

    def test_get_quota_status_empty_initially(self) -> None:
        """get_quota_status returns empty dict when no providers are exhausted."""
        breaker = ModelCircuitBreaker(failure_threshold=3)
        assert breaker.get_quota_status() == {}

    def test_execute_with_fallback_success(self, monkeypatch) -> None:
        """execute_with_fallback returns result on success."""
        from primr.pipeline.model_breaker import FallbackChain

        monkeypatch.setenv("XAI_API_KEY", "test-key")

        breaker = ModelCircuitBreaker(failure_threshold=3)
        chain = FallbackChain(
            name="test",
            models=(PrimrModels.GROK_MODEL_43,),
        )

        result = breaker.execute_with_fallback(chain, lambda model: f"ok:{model}")
        assert result == f"ok:{PrimrModels.GROK_MODEL_43}"

    def test_execute_with_fallback_catches_quota_error(self, monkeypatch) -> None:
        """execute_with_fallback catches QuotaExhaustedError and retries."""
        from primr.ai.providers.base import QuotaExhaustedError
        from primr.pipeline.model_breaker import FallbackChain

        monkeypatch.setenv("XAI_API_KEY", "test-key")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        breaker = ModelCircuitBreaker(failure_threshold=3)
        chain = FallbackChain(
            name="test",
            models=(PrimrModels.GROK_MODEL_43, PrimrModels.FLASH_MODEL),
        )

        call_count = 0

        def call_fn(model: str) -> str:
            nonlocal call_count
            call_count += 1
            if model == PrimrModels.GROK_MODEL_43:
                raise QuotaExhaustedError("xAI quota exhausted")
            return f"ok:{model}"

        result = breaker.execute_with_fallback(chain, call_fn)
        assert result == f"ok:{PrimrModels.FLASH_MODEL}"
        assert call_count == 2
        assert breaker.is_provider_quota_exhausted("xai") is True

    def test_execute_with_fallback_raises_when_all_exhausted(self, monkeypatch) -> None:
        """execute_with_fallback raises RuntimeError when all models exhausted."""
        import pytest

        from primr.ai.providers.base import QuotaExhaustedError
        from primr.pipeline.model_breaker import FallbackChain

        monkeypatch.setenv("XAI_API_KEY", "test-key")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        breaker = ModelCircuitBreaker(failure_threshold=3)
        chain = FallbackChain(
            name="test",
            models=(PrimrModels.GROK_MODEL_43, PrimrModels.FLASH_MODEL),
        )

        def call_fn(model: str) -> str:
            raise QuotaExhaustedError(f"{model} quota exhausted")

        with pytest.raises(RuntimeError, match="All models in fallback chain"):
            breaker.execute_with_fallback(chain, call_fn)
