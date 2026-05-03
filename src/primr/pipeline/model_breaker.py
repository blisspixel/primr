"""
Model-level circuit breaker with provider-aware fallback chains.

This module provides:
- FallbackChain frozen dataclass for ordered model fallback lists
- ANALYSIS_FALLBACK_CHAIN and PREMIUM_FALLBACK_CHAIN constants
- PROVIDER_API_KEY_ENV mapping for cross-provider API key checks
- ModelHealthEvent dataclass for health transition logging
- ModelCircuitBreaker class wrapping the existing CircuitBreaker

The ModelCircuitBreaker wraps ``CircuitBreaker`` from
``src/primr/utils/circuit_breaker.py`` with model-specific config
(failure_threshold=3, timeout_seconds=600). It does NOT reimplement
circuit breaker logic.

**Feature: pipeline-resilience**
**Validates: Requirements 11.1-11.6, 12.1, 13.1-13.3**
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from primr.config.models import PrimrModels
from primr.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    StateChangeEvent,
)

if TYPE_CHECKING:
    from collections.abc import Callable


# =============================================================================
# FALLBACK CHAIN
# =============================================================================


@dataclass(frozen=True)
class FallbackChain:
    """Ordered list of model names to try when primary is unhealthy."""

    name: str
    models: tuple[str, ...]


# Declarative fallback chains per Requirement 11.3
ANALYSIS_FALLBACK_CHAIN = FallbackChain(
    name="analysis",
    models=(
        PrimrModels.GROK_MODEL_43,  # grok-4.3 (always-on reasoning, current flagship)
        PrimrModels.GROK_MODEL_420,  # grok-4.20 reasoning (legacy fallback)
        PrimrModels.GROK_MODEL,  # grok-4.1 fast reasoning
        PrimrModels.FLASH_MODEL,  # gemini-3-flash
    ),
)

PREMIUM_FALLBACK_CHAIN = FallbackChain(
    name="premium",
    models=(
        PrimrModels.PRO_MODEL,  # gemini-3.1-pro
        PrimrModels.GROK_MODEL,  # grok-4.1 fast reasoning
    ),
)


# =============================================================================
# PROVIDER API KEY MAPPING
# =============================================================================

PROVIDER_API_KEY_ENV: dict[str, str] = {
    "xai": "XAI_API_KEY",
    "google": "GEMINI_API_KEY",
}


def _has_api_key(provider: str) -> bool:
    """Check if the API key for a provider is configured."""
    env_var = PROVIDER_API_KEY_ENV.get(provider)
    if env_var is None:
        return False
    return bool(os.getenv(env_var))


# =============================================================================
# MODEL HEALTH EVENT
# =============================================================================


@dataclass
class ModelHealthEvent:
    """A timestamped model health transition for run state logging."""

    timestamp: str
    model: str
    from_state: str
    to_state: str
    failure_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON storage."""
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "failure_count": self.failure_count,
        }


# =============================================================================
# MODEL CIRCUIT BREAKER
# =============================================================================


class ModelCircuitBreaker:
    """
    Circuit breaker that tracks consecutive failures per model
    and routes to fallback models.

    Wraps the existing CircuitBreaker with model-specific config:
    - failure_threshold=3 (open after 3 consecutive failures)
    - timeout_seconds=600 (10 minute recovery window)
    - success_threshold=1 (single successful probe closes circuit)
    - half_open_max_calls=1

    **Validates: Requirements 11.1-11.6, 12.1, 13.1-13.3**
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 600.0,
        health_listener: Callable[[ModelHealthEvent], None] | None = None,
    ) -> None:
        self._breaker = CircuitBreaker(
            config=CircuitBreakerConfig(
                failure_threshold=failure_threshold,
                success_threshold=1,
                timeout_seconds=recovery_timeout,
                half_open_max_calls=1,
            )
        )
        self._health_listener = health_listener
        # Wire up state change listener to emit ModelHealthEvents
        self._breaker.add_state_change_listener(self._on_state_change)

    def _on_state_change(self, event: StateChangeEvent) -> None:
        """Convert CircuitBreaker state changes to ModelHealthEvents."""
        if self._health_listener is None:
            return
        health_event = ModelHealthEvent(
            timestamp=datetime.now().isoformat(),
            model=event.key,
            from_state=event.from_state.value,
            to_state=event.to_state.value,
            failure_count=self._breaker.get_stats(event.key).failure_count,
        )
        self._health_listener(health_event)

    def record_success(self, model: str) -> None:
        """Record a successful API call for a model."""
        self._breaker.record_success(model)

    def record_failure(self, model: str) -> None:
        """Record a failed API call for a model."""
        self._breaker.record_failure(model)

    def is_healthy(self, model: str) -> bool:
        """Return True if the model is accepting requests."""
        return self._breaker.can_execute(model)

    def get_state(self, model: str) -> CircuitState:
        """Return the circuit state for a model."""
        return self._breaker.get_state(model)

    def select_model(self, chain: FallbackChain) -> str:
        """
        Select the first healthy model in the chain that has a valid API key.

        Raises RuntimeError if no model is available.

        **Validates: Requirements 13.1, 13.2, 13.3**
        """
        for model_name in chain.models:
            config = PrimrModels.get_model_config(model_name)
            if config is None:
                continue
            # Check API key for cross-provider fallback (Req 13)
            if not _has_api_key(config.provider):
                continue
            if self.is_healthy(model_name):
                return model_name
        raise RuntimeError(
            f"All models in fallback chain '{chain.name}' are unavailable: {list(chain.models)}"
        )

    def reset(self) -> None:
        """Reset all model circuit breakers."""
        self._breaker.reset_all()
