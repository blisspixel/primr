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
    ModelCircuitBreaker,
    ModelHealthEvent,
)


class TestFallbackChainOrder:
    """Test that fallback chains are defined in the correct order."""

    def test_analysis_fallback_chain_order(self) -> None:
        """Analysis chain: Grok 4.3 -> Grok 4.20 -> Grok 4.1 -> Gemini Flash."""
        assert ANALYSIS_FALLBACK_CHAIN.models == (
            PrimrModels.GROK_MODEL_43,
            PrimrModels.GROK_MODEL_420,
            PrimrModels.GROK_MODEL,
            PrimrModels.FLASH_MODEL,
        )

    def test_analysis_fallback_chain_name(self) -> None:
        """Analysis chain has the correct name."""
        assert ANALYSIS_FALLBACK_CHAIN.name == "analysis"

    def test_premium_fallback_chain_order(self) -> None:
        """Premium chain: Gemini Pro -> Grok 4.1."""
        assert PREMIUM_FALLBACK_CHAIN.models == (
            PrimrModels.PRO_MODEL,
            PrimrModels.GROK_MODEL,
        )

    def test_premium_fallback_chain_name(self) -> None:
        """Premium chain has the correct name."""
        assert PREMIUM_FALLBACK_CHAIN.name == "premium"


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
