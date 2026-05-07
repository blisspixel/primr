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
import re
from typing import Any

from primr.ai.providers import OpenAICompatibleProvider
from primr.utils.logging_config import get_logger

logger = get_logger("grok_client")

# ---------------------------------------------------------------------------
# Session-level token tracking (per-model for accurate cost reporting)
# ---------------------------------------------------------------------------
_session_input_tokens: int = 0
_session_output_tokens: int = 0
_session_tokens_by_model: dict[str, dict[str, int]] = {}


def get_grok_session_usage() -> dict[str, int]:
    """Return cumulative token usage for the current session."""
    return {
        "input_tokens": _session_input_tokens,
        "output_tokens": _session_output_tokens,
    }


def get_grok_session_usage_by_model() -> dict[str, dict[str, int]]:
    """Return per-model token usage for accurate cost calculation.

    Returns:
        {"model-name": {"input_tokens": N, "output_tokens": N}, ...}
    """
    return dict(_session_tokens_by_model)


def reset_grok_session() -> None:
    """Reset session token counters (useful for testing)."""
    global _session_input_tokens, _session_output_tokens, _session_tokens_by_model
    _session_input_tokens = 0
    _session_output_tokens = 0
    _session_tokens_by_model = {}


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

    _client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
    )
    return _client


# ---------------------------------------------------------------------------
# xAI provider singleton (used by grok_llm; ContinuousReasoningSession also
# delegates to it after Step 3 of the routing-layer migration)
# ---------------------------------------------------------------------------
_xai_provider: OpenAICompatibleProvider | None = None


def _get_provider() -> OpenAICompatibleProvider:
    """Lazy singleton for the xAI provider."""
    global _xai_provider
    if _xai_provider is None:
        _xai_provider = OpenAICompatibleProvider(
            name="xai",
            base_url="https://api.x.ai/v1",
            api_key_env="XAI_API_KEY",
            billing_help_url="https://console.x.ai/",
        )
    return _xai_provider


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "grok-4.3"


def _is_billing_exhausted(error: Exception) -> bool:
    """Return True when the error indicates credits/spending limit exhaustion.

    These errors will never resolve on retry — the user must add credits.
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
    # Billing exhaustion is never retryable — bail immediately
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


def _extract_retry_after_seconds(error: Exception) -> float | None:
    """Best-effort extraction of server-directed retry delay (Retry-After header)."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                value = float(retry_after)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass

    # Fallback parse for message fragments like "retry after 10 seconds"
    match = re.search(r"retry after\s+(\d+(?:\.\d+)?)", str(error).lower())
    if match:
        try:
            value = float(match.group(1))
            if value > 0:
                return value
        except ValueError:
            pass
    return None


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
    global _session_input_tokens, _session_output_tokens, _session_tokens_by_model

    if model is None:
        model = _DEFAULT_MODEL

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

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
    # returning consistent numbers. ContinuousReasoningSession still writes
    # to these directly; Step 3 of the routing-layer migration collapses the
    # duplication.
    _session_input_tokens += response.input_tokens
    _session_output_tokens += response.output_tokens
    if model not in _session_tokens_by_model:
        _session_tokens_by_model[model] = {"input_tokens": 0, "output_tokens": 0}
    _session_tokens_by_model[model]["input_tokens"] += response.input_tokens
    _session_tokens_by_model[model]["output_tokens"] += response.output_tokens

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
        global _session_input_tokens, _session_output_tokens, _session_tokens_by_model

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
        _session_input_tokens += response.input_tokens
        _session_output_tokens += response.output_tokens
        if self.model not in _session_tokens_by_model:
            _session_tokens_by_model[self.model] = {
                "input_tokens": 0,
                "output_tokens": 0,
            }
        _session_tokens_by_model[self.model]["input_tokens"] += response.input_tokens
        _session_tokens_by_model[self.model]["output_tokens"] += response.output_tokens

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
    citations**, not direct page scrape content — downstream pipelines should
    tag it as "grok-surrogate" so it isn't confused with first-party text.
    """
    import os

    import httpx

    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        logger.debug("grok_browse_and_summarize skipped: XAI_API_KEY not set")
        return None

    context_block = f"\n\nAdditional context: {context}" if context else ""
    prompt = (
        f"Use your web search and browse tools to gather content from this URL: {url}\n\n"
        "Summarize what the page says in 200-400 words. Focus on concrete facts — "
        "dates, products, services, leadership, customers, financials, strategy. "
        "If you cannot browse the page directly (e.g., it is behind bot protection), "
        "synthesize an equivalent summary from public sources about the same company "
        "or topic, and clearly cite where each fact came from. Do not invent details."
        f"{context_block}"
    )

    try:
        resp = httpx.post(
            "https://api.x.ai/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": prompt,
                "tools": [{"type": "web_search"}],
                "max_output_tokens": max_tokens,
            },
            timeout=timeout,
        )
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.warning("grok_browse_and_summarize: network error for %s: %s", url, e)
        return None

    if resp.status_code != 200:
        logger.warning(
            "grok_browse_and_summarize: status %s for %s — %s",
            resp.status_code,
            url,
            (resp.text or "")[:200],
        )
        return None

    try:
        data = resp.json()
    except ValueError:
        logger.warning("grok_browse_and_summarize: non-JSON response for %s", url)
        return None

    # Walk the output list for the assistant message text
    text = ""
    citations: list[str] = []
    tool_calls_made = 0
    for item in data.get("output", []) or []:
        item_type = item.get("type")
        if item_type == "web_search_call":
            tool_calls_made += 1
            continue
        if item_type == "message":
            for block in item.get("content", []) or []:
                if block.get("type") in ("output_text", "text"):
                    text += block.get("text", "")
                    for ann in block.get("annotations", []) or []:
                        if ann.get("type") == "url_citation" and ann.get("url"):
                            citations.append(ann["url"])

    # Track token usage for cost accounting when available
    usage = data.get("usage") or {}
    inp = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    if inp or out:
        global _session_input_tokens, _session_output_tokens, _session_tokens_by_model
        _session_input_tokens += inp
        _session_output_tokens += out
        if model not in _session_tokens_by_model:
            _session_tokens_by_model[model] = {"input_tokens": 0, "output_tokens": 0}
        _session_tokens_by_model[model]["input_tokens"] += inp
        _session_tokens_by_model[model]["output_tokens"] += out

    text = text.strip()
    if not text:
        logger.info("grok_browse_and_summarize: empty body for %s", url)
        return None

    # Deduplicate citations preserving order.
    seen: set[str] = set()
    unique_citations: list[str] = []
    for c in citations:
        if c not in seen:
            seen.add(c)
            unique_citations.append(c)

    logger.info(
        "grok_browse_and_summarize: %s — %d chars, %d tool calls, %d citations",
        url,
        len(text),
        tool_calls_made,
        len(unique_citations),
    )
    return {
        "text": text,
        "citations": unique_citations,
        "source_url": url,
        "tool_calls": tool_calls_made,
    }
