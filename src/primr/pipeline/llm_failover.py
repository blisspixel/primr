"""Circuit-breaker-aware LLM call dispatch.

Wraps :func:`primr.ai.grok_client.grok_llm` (and the cross-provider variants
it dispatches to) in a :class:`~primr.pipeline.model_breaker.ModelCircuitBreaker`
so that a single provider's quota exhaustion (typed as
:class:`~primr.ai.providers.base.QuotaExhaustedError`) triggers automatic
fallover to the next model in the appropriate fallback chain instead of
failing the entire research run.

Before this seam existed, ``grok_llm`` calls in ``research_agent.py``
caught the quota error inside the per-call retry loop, decided it was
non-retryable, and re-raised it up to the pipeline executor — which then
killed the stage and bubbled to the user. The circuit breaker existed and
was tested in isolation (roadmap item #6) but no production call site ever
invoked it.

Usage::

    from primr.pipeline.llm_failover import call_with_failover, LLMRole

    text = call_with_failover(
        LLMRole.REASONING,
        prompt,
        temperature=0.3,
        max_tokens=8000,
    )

The chain selected per role is the same one used by the existing eval and
provider-availability tests, so behavior on success is identical to a
direct ``grok_llm`` call — the wrapping only kicks in on
``QuotaExhaustedError``.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from primr.pipeline.model_breaker import (
    ANALYSIS_FALLBACK_CHAIN,
    PREMIUM_FALLBACK_CHAIN,
    UTILITY_FALLBACK_CHAIN,
    FallbackChain,
    ModelCircuitBreaker,
)

logger = logging.getLogger(__name__)


class LLMRole(str, Enum):
    """Pipeline role hint used to select the fallback chain.

    REASONING — workbook generation, cross-validation, gap analysis. The
    primary slot is Grok 4.3 (or whatever the active recipe overrides
    reasoning to); fallback runs Claude Sonnet / GPT-5.x / Gemini Flash.
    WRITING — bulk section writing, strategy prose. Cheaper writer-class
    models, falls back to gpt-5.4-mini / Gemini Flash.
    PREMIUM — Deep Research style work; falls back through the largest
    models because the user explicitly accepted premium-tier cost.
    """

    REASONING = "reasoning"
    WRITING = "writing"
    PREMIUM = "premium"


# Module-level singleton so the breaker's quota/health state survives across
# call sites in a single process. A fresh breaker per call would forget
# every quota event the moment a call returns, defeating the purpose.
_BREAKER: ModelCircuitBreaker | None = None
_BREAKER_OVERRIDE: ModelCircuitBreaker | None = None


def _get_breaker() -> ModelCircuitBreaker:
    """Return the process-wide circuit breaker, lazy-constructed."""
    global _BREAKER
    if _BREAKER_OVERRIDE is not None:
        return _BREAKER_OVERRIDE
    if _BREAKER is None:
        _BREAKER = ModelCircuitBreaker()
    return _BREAKER


def set_breaker_for_test(breaker: ModelCircuitBreaker | None) -> None:
    """Test hook: install (or clear) an override breaker.

    Tests pass a fresh ``ModelCircuitBreaker`` so they don't inherit
    quota-exhausted state from earlier tests in the same process.
    """
    global _BREAKER_OVERRIDE
    _BREAKER_OVERRIDE = breaker


def _chain_for_role(role: LLMRole) -> FallbackChain:
    if role is LLMRole.REASONING:
        return ANALYSIS_FALLBACK_CHAIN
    if role is LLMRole.WRITING:
        return UTILITY_FALLBACK_CHAIN
    if role is LLMRole.PREMIUM:
        return PREMIUM_FALLBACK_CHAIN
    raise ValueError(f"Unknown LLM role: {role!r}")


def call_with_failover(
    role: LLMRole,
    prompt: str,
    *,
    preferred_model: str | None = None,
    grok_llm_fn: Callable[..., str] | None = None,
    **kwargs: Any,
) -> str:
    """Call an LLM, falling over to the next chain member on quota errors.

    Args:
        role: Pipeline role used to select the fallback chain.
        prompt: The user prompt forwarded to ``grok_llm``.
        preferred_model: If provided AND present in the role's chain, the
            chain is rotated so this model is tried first. Used by stages
            that have a strong opinion about which model they want (e.g.
            a recipe override picking gemini-3.1-flash-lite for writing).
        grok_llm_fn: Test/DI hook. Defaults to the real ``grok_llm``.
        **kwargs: Forwarded to ``grok_llm`` (temperature, max_tokens, etc.).

    Returns:
        The text response from the first successful model.

    Raises:
        RuntimeError: If every model in the chain is unavailable.
        Any non-quota exception from ``grok_llm`` is re-raised as-is —
        only QuotaExhaustedError triggers fallover.
    """
    if grok_llm_fn is None:
        from primr.ai.grok_client import grok_llm as _grok_llm

        grok_llm_fn = _grok_llm

    chain = _chain_for_role(role)
    if preferred_model and preferred_model in chain.models:
        # Rotate preferred to the front, preserving the rest as fallback order.
        ordered = (
            preferred_model,
            *(m for m in chain.models if m != preferred_model),
        )
        chain = FallbackChain(name=f"{chain.name}+pref", models=ordered)

    breaker = _get_breaker()

    def _call(model_name: str) -> str:
        logger.debug("LLM failover dispatch: role=%s model=%s", role.value, model_name)
        return grok_llm_fn(prompt, model=model_name, **kwargs)

    return breaker.execute_with_fallback(chain, _call)
