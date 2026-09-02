"""
Provider abstraction base classes.

A ``Provider`` is the seam between primr's pipeline and a specific LLM API.
It owns lazy client construction, retry/backoff, billing-exhaustion detection,
and per-model token accounting. Routing decisions live one layer up.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


class ProviderUnavailableError(RuntimeError):
    """Raised when a provider's API key or transport is not configured."""


class QuotaExhaustedError(RuntimeError):
    """Raised when a provider's daily/billing quota is exhausted.

    This is distinct from transient rate-limiting (HTTP 429 with retry-after).
    Callers typically print a UI message and then exit / fail the run rather
    than retrying — the user has to wait for the quota window to reset, top
    up credits, or rotate keys before another run can succeed.
    """


@dataclass(frozen=True)
class CredentialCheck:
    """Result of a lightweight, auth-only credential validation.

    ``ok`` is True when the key authenticated against a free provider metadata
    endpoint with no model generation or token spend. ``detail`` is a short
    human-readable status or error class. ``latency_ms`` is the round trip when
    measured.
    """

    provider: str
    ok: bool
    detail: str
    latency_ms: int | None = None


@dataclass(frozen=True)
class ChatResponse:
    """Normalized return shape for a single chat call.

    ``input_tokens`` and ``output_tokens`` come from the provider's usage
    metadata when available; both default to 0 for transports (e.g. local
    Ollama) that don't report usage. ``cached_input_tokens`` is the subset of
    ``input_tokens`` served from the provider's prompt cache (xAI
    ``cached_tokens``, OpenAI ``prompt_tokens_details.cached_tokens``,
    Anthropic ``cache_read_input_tokens``, Gemini
    ``cached_content_token_count``) — cache hit rate is load-bearing on the
    sub-$1 default recipe, so callers can thread it into usage records.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    # Exact provider-billed amount when the response exposes it. None means
    # callers must retain conservative token-based accounting.
    actual_cost_usd: float | None = None
    # Responses APIs can return accepted but incomplete or tool-only results.
    # Preserve that state so usage remains accountable even when text is empty.
    response_status: str | None = None
    incomplete_reason: str | None = None


@dataclass
class _UsageAccumulator:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: Any = field(default_factory=Lock, repr=False)

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> None:
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.cached_input_tokens += cached_input_tokens
            bucket = self.by_model.setdefault(
                model, {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
            )
            bucket["input_tokens"] += input_tokens
            bucket["output_tokens"] += output_tokens
            bucket["cached_input_tokens"] += cached_input_tokens

    def reset(self) -> None:
        with self._lock:
            self.input_tokens = 0
            self.output_tokens = 0
            self.cached_input_tokens = 0
            self.by_model = {}


class Provider(ABC):
    """Abstract LLM provider.

    Subclasses implement ``chat()`` against their specific transport. The
    base class owns usage accounting so callers see consistent token-tracking
    semantics regardless of which provider serviced the call. Provider-
    specific knobs (Gemini ``thinking_level``, Anthropic ``cache_control``,
    OpenAI ``reasoning_effort``) flow through as ``**kwargs`` — providers that
    recognize them apply them, others ignore them. This keeps the abstraction
    thin without flattening real feature differences.
    """

    name: str

    def __init__(self, name: str) -> None:
        self.name = name
        self._usage = _UsageAccumulator()

    def validate_credentials(self) -> CredentialCheck:
        """Auth-only credential check. Override with a free list/ping call.

        The default reports "unsupported" so a provider without a cheap probe
        never blocks ``primr keys test``. Implementations must NOT generate
        model output or spend tokens. Use a free provider metadata endpoint.
        """
        return CredentialCheck(
            provider=self.name,
            ok=False,
            detail="credential validation not implemented for this provider",
        )

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 16_000,
        retries: int = 4,
        **provider_kwargs: Any,
    ) -> ChatResponse:
        """Send a chat-format request and return the response.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts. Roles
                follow OpenAI/Anthropic conventions: ``system`` / ``user`` /
                ``assistant``. Providers that put system prompts elsewhere
                (Gemini ``system_instruction``) are responsible for handling
                the conversion.
            model: Provider-specific model ID.
            temperature: Sampling temperature (provider clamps as needed).
            max_tokens: Maximum output tokens.
            retries: Number of retries for transient errors.
            **provider_kwargs: Provider-specific knobs passed through
                untouched. Providers should ignore unknown kwargs.

        Returns:
            ChatResponse with normalized text and token usage.

        Raises:
            ProviderUnavailable: API key missing or transport unreachable.
            RuntimeError: All retry attempts failed.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` when the provider's key/transport is configured."""

    def get_usage(self) -> dict[str, int]:
        """Return cumulative ``{input_tokens, output_tokens, cached_input_tokens}`` for this provider."""
        return {
            "input_tokens": self._usage.input_tokens,
            "output_tokens": self._usage.output_tokens,
            "cached_input_tokens": self._usage.cached_input_tokens,
        }

    def get_usage_by_model(self) -> dict[str, dict[str, int]]:
        """Return per-model token usage as ``{model: {input_tokens, output_tokens}}``."""
        return {k: dict(v) for k, v in self._usage.by_model.items()}

    def reset_usage(self) -> None:
        """Reset usage counters. Useful for tests and per-run accounting."""
        self._usage.reset()

    def _record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> None:
        """Subclass hook for recording usage into the accumulator."""
        self._usage.record(
            model, input_tokens, output_tokens, cached_input_tokens=cached_input_tokens
        )
