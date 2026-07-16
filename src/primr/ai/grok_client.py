"""
Grok client for primr.

Uses xAI's OpenAI-compatible API at https://api.x.ai/v1. Requires the
``XAI_API_KEY`` environment variable and the ``openai`` package.

As of v1.22.0 the chat path delegates to ``OpenAICompatibleProvider`` from
``primr.ai.providers`` so adding new OpenAI-compatible providers (OpenAI
itself, Ollama, vLLM) is a one-line registry entry rather than a parallel
client file. This module remains the public entry point for xAI-specific
features: ``grok_llm`` (chat completions), ``ContinuousReasoningSession``
(multi-turn shared-history sessions used by the standard pipeline), and
``grok_browse_and_summarize`` (xAI Responses API with the ``web_search``
agent tool, which is xAI-specific and not OpenAI-shape-compatible).

Usage::

    from primr.ai.grok_client import grok_llm, get_grok_session_usage

    text = grok_llm("Write a report about ...", max_tokens=16_000)
    usage = get_grok_session_usage()  # {'input_tokens': ..., 'output_tokens': ...}
"""

import random
import threading
from typing import Any

from primr.ai.error_policy import extract_retry_after_seconds
from primr.ai.providers import XAIProvider
from primr.ai.providers.openai_compatible import create_openai_sdk_client
from primr.utils.logging_config import get_logger
from primr.utils.model_policy import require_model_calls_allowed

logger = get_logger("grok_client")
_extract_retry_after_seconds = extract_retry_after_seconds

# ---------------------------------------------------------------------------
# Session-level token tracking (per-model for accurate cost reporting)
# ---------------------------------------------------------------------------
# The counters are mutated concurrently by the parallel section writers and
# strategy vendor threads; the lock keeps each read-modify-write whole so a
# lost update cannot silently drop a call's tokens from budget checkpoints.
_session_lock = threading.Lock()
_session_input_tokens: int = 0
_session_output_tokens: int = 0
_session_cached_input_tokens: int = 0
_session_tokens_by_model: dict[str, dict[str, int]] = {}


def get_grok_session_usage() -> dict[str, int]:
    """Return cumulative token usage for the current session.

    ``cached_input_tokens`` is the subset of ``input_tokens`` served from the
    provider's prompt cache. This is load-bearing on the sub-$1 default (Grok 4.3
    cached input at $0.20/M), so it is threaded through to usage records.
    """
    with _session_lock:
        return {
            "input_tokens": _session_input_tokens,
            "output_tokens": _session_output_tokens,
            "cached_input_tokens": _session_cached_input_tokens,
        }


def get_grok_session_usage_by_model() -> dict[str, dict[str, int]]:
    """Return per-model token usage for accurate cost calculation.

    Returns:
        {"model-name": {"input_tokens": N, "output_tokens": N,
        "cached_input_tokens": N}, ...}
    """
    with _session_lock:
        return {model: dict(bucket) for model, bucket in _session_tokens_by_model.items()}


def reset_grok_session() -> None:
    """Reset session token counters (useful for testing)."""
    global _session_input_tokens, _session_output_tokens
    global _session_cached_input_tokens, _session_tokens_by_model
    with _session_lock:
        _session_input_tokens = 0
        _session_output_tokens = 0
        _session_cached_input_tokens = 0
        _session_tokens_by_model = {}


def _mirror_session_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> None:
    """Mirror per-call usage into the module-level session counters.

    Single accounting seam for all four call paths (grok_llm xAI,
    grok_llm cross-provider, ContinuousReasoningSession,
    grok_browse_and_summarize) so cost reporting stays uniform.
    """
    global _session_input_tokens, _session_output_tokens, _session_cached_input_tokens
    with _session_lock:
        _session_input_tokens += input_tokens
        _session_output_tokens += output_tokens
        _session_cached_input_tokens += cached_input_tokens
        bucket = _session_tokens_by_model.setdefault(
            model, {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
        )
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        # Older buckets predate the cached counter; setdefault keeps them safe.
        bucket["cached_input_tokens"] = bucket.get("cached_input_tokens", 0) + cached_input_tokens


# ---------------------------------------------------------------------------
# Lazy client init
# ---------------------------------------------------------------------------
_client = None


def _get_grok_client():
    """Lazy-init an OpenAI client pointed at xAI."""
    global _client
    if _client is not None:
        return _client

    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "The 'openai' package is required for --fast mode. "
            "Install it with: pip install 'primr[fast]' or pip install openai"
        ) from exc

    import os

    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        from primr.utils.errors import ConfigurationError

        raise ConfigurationError(
            "XAI_API_KEY not set. Add it to your .env file or environment. "
            "Get a key at https://console.x.ai/"
        )

    _client = create_openai_sdk_client(
        openai,
        api_key=api_key,
        base_url="https://api.x.ai/v1",
    )
    return _client


# ---------------------------------------------------------------------------
# xAI provider singleton (used by grok_llm; ContinuousReasoningSession also
# delegates to it after Step 3 of the routing-layer migration)
# ---------------------------------------------------------------------------
_xai_provider: XAIProvider | None = None


def _get_provider() -> XAIProvider:
    """Lazy singleton for the xAI provider."""
    global _xai_provider
    if _xai_provider is None:
        _xai_provider = XAIProvider()
    return _xai_provider


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "grok-4.3"


def _is_billing_exhausted(error: Exception) -> bool:
    """Return True when the error indicates credits/spending limit exhaustion.

    These errors will never resolve on retry; the user must add credits.
    Checked before the retryable test so we don't waste time on backoff.
    """
    from primr.ai.error_policy import is_billing_exhausted

    return is_billing_exhausted(error)


def _is_retryable_grok_error(error: Exception) -> bool:
    """Return True when a Grok API error is likely transient and safe to retry.

    NOTE (pipeline-resilience): This client-level retry logic is intentionally
    retained alongside the stage-level RecoveryExecutor.  The executor handles
    *stage* recovery (model fallback, tier escalation, skip/abort), while this
    function drives *API-call* retries inside a single stage attempt.  Both
    layers are needed: the client absorbs brief transient blips so the executor
    only sees persistent failures.  Candidate for future consolidation if the
    executor gains per-call retry support.
    """
    # Billing exhaustion is never retryable; bail immediately.
    if _is_billing_exhausted(error):
        return False

    error_text = str(error).lower()
    retryable_markers = [
        "429",
        "rate limit",
        "rate_limit",
        "quota",
        "500",
        "502",
        "503",
        "504",
        "internal server error",
        "service unavailable",
        "temporarily unavailable",
        "try again later",
        "timeout",
        "timed out",
        "connection reset",
        "connection aborted",
        "connection refused",
    ]
    return any(marker in error_text for marker in retryable_markers)


def _compute_backoff_delay(attempt: int, *, base: float = 5.0, cap: float = 90.0) -> float:
    """Exponential backoff with jitter for transient API failures."""
    raw = min(cap, base * (2**attempt))
    jitter = random.uniform(0, raw * 0.2)
    return raw + jitter


def grok_llm(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 16_000,
    retries: int = 4,
    system_prompt: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    """
    Call Grok and return the text response.

    Args:
        prompt: The user prompt to send.
        model: Model ID. ``None`` selects the default
               (``grok-4.3``). Use
               ``grok-4.20-non-reasoning`` for writing tasks.
        temperature: Sampling temperature.
        max_tokens: Maximum output tokens.
        retries: Number of retries on transient errors (429/5xx/network timeouts).
        system_prompt: Optional system message prepended before the user message.
        reasoning_effort: Optional reasoning effort level ("low", "medium", "high").
            Used to differentiate FAST tier (low) from HYBRID tier (default).
            Only effective on models that support reasoning effort (e.g. grok-4.3).

    Returns:
        The assistant's text response.

    Raises:
        ImportError: If the openai package is not installed.
        ConfigurationError: If XAI_API_KEY is not set.
        RuntimeError: If the API call fails after retries.
    """
    require_model_calls_allowed("chat generation")
    if model is None:
        model = _DEFAULT_MODEL

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Cross-provider dispatch (v1.24.0). When the resolved model is not an xAI
    # model, e.g. an eval recipe override has set writing="gemini-3.1-flash-lite",
    # route the call to that model's native provider instead of trying to
    # call xAI with a non-Grok model ID. The function name stays grok_llm for
    # back-compat but it now acts as a generic chat dispatcher when needed.
    # Production reasoning-tier calls without an override still hit the xAI
    # path below since they resolve to grok-4.3 / grok-4.20-NR.
    from primr.config.models import PrimrModels as _PrimrModels

    _model_config = _PrimrModels.get_model_config(model)
    if _model_config is not None and _model_config.provider != "xai":
        from primr.ai.routing import get_provider_for_model as _get_provider_for_model

        cross_provider = _get_provider_for_model(model)
        cross_kwargs: dict[str, Any] = {}
        if reasoning_effort is not None:
            cross_kwargs["reasoning_effort"] = reasoning_effort
        cross_response = cross_provider.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            retries=retries,
            **cross_kwargs,
        )
        # Mirror tokens into the same session counters so cost reporting works
        # uniformly regardless of which provider serviced the call.
        _mirror_session_usage(
            model,
            cross_response.input_tokens,
            cross_response.output_tokens,
            cached_input_tokens=cross_response.cached_input_tokens,
        )
        return cross_response.text

    # Delegate the chat call (with retry/error handling) to the shared
    # OpenAICompatibleProvider. We sync the lazy SDK client through
    # _get_grok_client so callers/tests that patch _get_grok_client to inject
    # a fake client still flow through.
    provider = _get_provider()
    provider._client = _get_grok_client()

    # Build provider kwargs for optional parameters
    provider_kwargs: dict[str, Any] = {}
    if reasoning_effort is not None:
        provider_kwargs["reasoning_effort"] = reasoning_effort

    response = provider.chat(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        **provider_kwargs,
    )

    # Mirror per-call usage into the legacy module-level counters so existing
    # readers (get_grok_session_usage / get_grok_session_usage_by_model) keep
    # returning consistent numbers.
    _mirror_session_usage(
        model,
        response.input_tokens,
        response.output_tokens,
        cached_input_tokens=response.cached_input_tokens,
    )

    return response.text


# ---------------------------------------------------------------------------
# Continuous reasoning session (pilot)
# ---------------------------------------------------------------------------
#
# A ContinuousReasoningSession holds a single message history across multiple
# Grok calls so that the model retains its prior reasoning context instead of
# re-reading a serialized summary at each handoff. Used by the workbook +
# cross-validation stages of the standard pipeline when the
# `--continuous-reasoning` flag (or PRIMR_CONTINUOUS_REASONING=1) is set.
#
# Continuous-chat topology: keeping the model's prior reasoning in working
# memory across stages, instead of re-reading a serialized summary at each
# handoff. Default-on for the standard pipeline after an n=3 paired-comparison
# pilot showed measurably sharper analysis at acceptable cost.


class ContinuousReasoningSession:
    """Multi-turn Grok session that preserves message history across stages.

    Use one session per primr run. Each `.send()` call appends a user turn
    and an assistant turn to the history, so the next stage's call sees all
    prior reasoning natively (no JSON re-serialization, no rolling summary).

    Tracks tokens through the same module-level counters as `grok_llm`, so
    cost reporting and the existing eval harness keep working unchanged.
    """

    def __init__(
        self,
        *,
        model: str = _DEFAULT_MODEL,
        system_prompt: str | None = None,
        reasoning_effort: str | None = None,
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.history: list[dict[str, str]] = []
        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})
        self._turn_count = 0

    @property
    def turns(self) -> int:
        return self._turn_count

    @property
    def approx_context_tokens(self) -> int:
        """Rough estimate of accumulated context size (4 chars/token heuristic)."""
        total_chars = sum(len(m.get("content", "")) for m in self.history)
        return total_chars // 4

    def send(
        self,
        prompt: str,
        *,
        temperature: float = 0.5,
        max_tokens: int = 16_000,
        retries: int = 4,
    ) -> str:
        """Append a user turn, call Grok, append the assistant reply, return it."""
        require_model_calls_allowed("continuous reasoning generation")
        self.history.append({"role": "user", "content": prompt})

        # Delegate the chat call (with retry/error handling) to the shared
        # OpenAICompatibleProvider. Errors propagate after rolling back the
        # user turn so the session stays consistent with what the model
        # actually saw.
        provider = _get_provider()
        provider._client = _get_grok_client()
        try:
            provider_kwargs: dict[str, Any] = {}
            if self.reasoning_effort is not None:
                provider_kwargs["reasoning_effort"] = self.reasoning_effort

            response = provider.chat(
                list(self.history),
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=retries,
                **provider_kwargs,
            )
        except Exception:
            self.history.pop()
            raise

        # Mirror per-call usage into legacy module-level counters for callers
        # that still read get_grok_session_usage().
        _mirror_session_usage(
            self.model,
            response.input_tokens,
            response.output_tokens,
            cached_input_tokens=response.cached_input_tokens,
        )

        self.history.append({"role": "assistant", "content": response.text})
        self._turn_count += 1
        logger.info(
            "Continuous session turn %d complete: %d input, %d output tokens "
            "(history now %d turns, ~%dk context tokens)",
            self._turn_count,
            response.input_tokens,
            response.output_tokens,
            self._turn_count,
            self.approx_context_tokens // 1000,
        )
        return response.text

    def send_stateless(
        self,
        prompt: str,
        *,
        system_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 16_000,
        retries: int = 4,
    ) -> str:
        """Call the configured model without reading or mutating session history."""
        return grok_llm(
            prompt,
            system_prompt=system_prompt,
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            retries=retries,
            reasoning_effort=self.reasoning_effort,
        )


# ---------------------------------------------------------------------------
# Grok Agent Tools (browse + web search)
# ---------------------------------------------------------------------------


def grok_browse_and_summarize(
    url: str,
    context: str | None = None,
    *,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 2000,
    timeout: float = 90.0,
) -> dict | None:
    """Ask Grok to fetch a URL (or synthesize equivalent content) and summarize.

    Uses xAI's Responses API with the ``web_search`` agent tool. Grok attempts
    to open the page directly, and when that fails (Kasada / Akamai / etc) it
    falls back to searching the web and synthesizing from public sources,
    citing them.

    Returns a dict with ``text`` (summary), ``citations`` (list of urls), and
    ``source_url`` (the URL we asked about). Returns None on transport or auth
    failures.

    The caller should treat the returned text as **LLM synthesis with
    citations**, not direct page scrape content; downstream pipelines should
    tag it as "grok-surrogate" so it isn't confused with first-party text.
    """
    require_model_calls_allowed("Grok browse generation")
    summary = _get_provider().browse_and_summarize(
        url,
        context=context,
        model=model,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    if summary is None:
        return None
    if summary.input_tokens or summary.output_tokens:
        _mirror_session_usage(
            model,
            summary.input_tokens,
            summary.output_tokens,
            cached_input_tokens=summary.cached_input_tokens,
        )
    return summary.to_public_dict()
