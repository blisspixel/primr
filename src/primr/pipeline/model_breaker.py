"""
Model-level circuit breaker with provider-aware fallback chains.

This module provides:
- FallbackChain frozen dataclass for ordered model fallback lists
- ANALYSIS_FALLBACK_CHAIN, PREMIUM_FALLBACK_CHAIN, UTILITY_FALLBACK_CHAIN constants
- PROVIDER_API_KEY_ENV mapping for cross-provider API key checks
- ModelHealthEvent dataclass for health transition logging
- QuotaStatus dataclass for per-provider quota diagnostics
- ModelCircuitBreaker class wrapping the existing CircuitBreaker

The ModelCircuitBreaker wraps ``CircuitBreaker`` from
``src/primr/utils/circuit_breaker.py`` with model-specific config
(failure_threshold=3, timeout_seconds=600). It does NOT reimplement
circuit breaker logic.

**Feature: pipeline-resilience**
**Validates: Requirements 11.1-11.6, 12.1, 13.1-13.3**
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
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

logger = logging.getLogger(__name__)


# =============================================================================
# FALLBACK CHAIN
# =============================================================================


@dataclass(frozen=True)
class FallbackChain:
    """Ordered list of model names to try when primary is unhealthy."""

    name: str
    models: tuple[str, ...]


# =============================================================================
# QUOTA STATUS
# =============================================================================


@dataclass
class QuotaStatus:
    """Per-provider quota state for diagnostics."""

    provider: str
    is_exhausted: bool
    exhausted_at: datetime | None = None
    resets_at: datetime | None = None  # Next midnight UTC


# Declarative fallback chains per Requirement 11.3
ANALYSIS_FALLBACK_CHAIN = FallbackChain(
    name="analysis",
    models=(
        PrimrModels.GROK_MODEL_43,  # grok-4.3 (primary)
        PrimrModels.GROK_MODEL_420,  # grok-4.20 reasoning (legacy)
        "claude-sonnet-4-6",  # Anthropic cross-provider fallback
        "gpt-5.4",  # OpenAI cross-provider fallback
        PrimrModels.FLASH_MODEL,  # gemini-3-flash (last resort)
    ),
)

UTILITY_FALLBACK_CHAIN = FallbackChain(
    name="utility",
    models=(
        PrimrModels.GROK_MODEL_WRITING,  # Primary utility (xAI 4.20 non-reasoning)
        "gpt-5.4-mini",  # OpenAI fallback
        PrimrModels.FLASH_MODEL,  # Gemini fallback
    ),
)

PREMIUM_FALLBACK_CHAIN = FallbackChain(
    name="premium",
    models=(
        PrimrModels.PRO_MODEL,  # gemini-3.1-pro (primary)
        "claude-opus-4-8",  # Anthropic fallback
        "gpt-5.5",  # OpenAI fallback
        PrimrModels.GROK_MODEL_43,  # xAI fallback
    ),
)


# =============================================================================
# PROVIDER API KEY MAPPING
# =============================================================================

PROVIDER_API_KEY_ENV: dict[str, str] = {
    "xai": "XAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}


def _has_api_key(provider: str) -> bool:
    """Check if the API key for a provider is configured.

    Also returns True for providers with a configured default key
    (e.g. Ollama, which doesn't need a real API key).
    """
    from primr.ai.providers.registry import KNOWN_PROVIDERS

    env_var = PROVIDER_API_KEY_ENV.get(provider)
    if env_var is None:
        return False
    if os.getenv(env_var):
        return True
    # Check if the provider has a default key configured (e.g. Ollama)
    for entry in KNOWN_PROVIDERS:
        if entry.name == provider and entry.api_key_default is not None:
            return True
    return False


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

    Also tracks per-provider quota exhaustion state. When a provider's
    quota is exhausted, all its models are considered unhealthy until
    midnight UTC (daily reset).

    **Validates: Requirements 5.1, 5.6, 11.1-11.6, 12.1, 13.1-13.3**
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
        self._quota_exhausted: dict[str, QuotaStatus] = {}
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
        """Return True if the model is accepting requests.

        Checks both the circuit breaker state and provider quota status.
        """
        # Check if the model's provider is quota-exhausted
        config = PrimrModels.get_model_config(model)
        if config is not None and self.is_provider_quota_exhausted(config.provider):
            return False
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

    # =========================================================================
    # QUOTA-AWARE EXTENSIONS
    # =========================================================================

    def mark_quota_exhausted(self, provider: str) -> None:
        """Mark a provider as quota-exhausted until midnight UTC.

        Unlike transient failures (which recover after timeout_seconds),
        quota exhaustion persists until the daily reset at midnight UTC.

        **Validates: Requirements 5.1, 5.6**
        """
        now = datetime.now(timezone.utc)
        # Compute next midnight UTC
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # If we're already past midnight today, go to next day
        from datetime import timedelta

        resets_at = tomorrow + timedelta(days=1)

        self._quota_exhausted[provider] = QuotaStatus(
            provider=provider,
            is_exhausted=True,
            exhausted_at=now,
            resets_at=resets_at,
        )
        logger.warning(
            "Provider '%s' marked as quota-exhausted until %s UTC",
            provider,
            resets_at.isoformat(),
        )

    def get_quota_status(self) -> dict[str, QuotaStatus]:
        """Return per-provider quota status for diagnostics."""
        self._reset_daily_quotas()
        return dict(self._quota_exhausted)

    def _reset_daily_quotas(self) -> None:
        """Check if midnight UTC has passed and clear expired quota entries."""
        now = datetime.now(timezone.utc)
        expired = [
            provider
            for provider, status in self._quota_exhausted.items()
            if status.resets_at is not None and now >= status.resets_at
        ]
        for provider in expired:
            del self._quota_exhausted[provider]
            logger.info(
                "Provider '%s' quota reset (midnight UTC passed)", provider
            )

    def is_provider_quota_exhausted(self, provider: str) -> bool:
        """Return True if the provider's quota is currently exhausted.

        Calls _reset_daily_quotas() first to clear any expired entries.
        """
        self._reset_daily_quotas()
        status = self._quota_exhausted.get(provider)
        if status is None:
            return False
        return status.is_exhausted

    def execute_with_fallback(
        self,
        chain: FallbackChain,
        call_fn: Callable[[str], Any],
    ) -> Any:
        """Execute a provider call with quota-aware fallback.

        Selects the first healthy model in *chain*, calls *call_fn(model_name)*,
        and handles QuotaExhaustedError by marking the provider exhausted and
        retrying with the next model in the chain.

        Args:
            chain: The fallback chain to use for model selection.
            call_fn: A callable that accepts a model name and performs the
                provider chat() call. Should raise QuotaExhaustedError when
                the provider's quota is exhausted.

        Returns:
            The result of call_fn on success.

        Raises:
            RuntimeError: When all models in the chain are unavailable.

        **Validates: Requirements 5.4, 5.7**
        """
        from primr.ai.providers.base import QuotaExhaustedError

        tried_models: list[str] = []
        # Defense-in-depth: cap iterations at chain length + 1 to prevent
        # infinite loops from unexpected state (e.g. race conditions in
        # quota marking). In normal operation, the tried_models check
        # terminates the loop well before this limit.
        max_iterations = len(chain.models) + 1

        for _iteration in range(max_iterations):
            model = self.select_model(chain)
            if model in tried_models:
                # We've cycled back — all remaining options exhausted
                raise RuntimeError(
                    f"All models in fallback chain '{chain.name}' are unavailable "
                    f"(tried: {tried_models})"
                )
            tried_models.append(model)

            try:
                result = call_fn(model)
                self.record_success(model)
                return result
            except QuotaExhaustedError as exc:
                # Determine the provider for this model
                config = PrimrModels.get_model_config(model)
                provider_name = config.provider if config else "unknown"
                self.mark_quota_exhausted(provider_name)
                logger.warning(
                    "QuotaExhaustedError on model '%s' (provider: %s): %s. "
                    "Retrying with next model in '%s' chain.",
                    model,
                    provider_name,
                    exc,
                    chain.name,
                )

        # Should never reach here, but guard against it
        raise RuntimeError(
            f"Fallback chain '{chain.name}' exhausted after {max_iterations} iterations "
            f"(tried: {tried_models})"
        )
