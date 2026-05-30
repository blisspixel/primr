"""
Anthropic Claude provider.

Implements the Provider ABC for Anthropic's Messages API via the ``anthropic``
SDK. Handles:
- Message translation (system messages → top-level ``system`` param)
- Retry with exponential backoff on transient errors (429, 5xx)
- Quota/billing exhaustion detection → raises ``QuotaExhaustedError``
- Cache-aware token tracking (``cache_read_input_tokens``, ``cache_creation_input_tokens``)
- Passthrough of Anthropic-specific kwargs (``thinking``)

Prompt caching note: Anthropic's prompt caching is configured via ``cache_control``
directives embedded *inside* message content blocks (not as a top-level API
parameter). Callers wanting cache hits should construct messages with structured
content arrays that include ``{"type": "text", "text": ..., "cache_control":
{"type": "ephemeral"}}`` blocks and pass the whole structure as the message
content. This provider records ``cache_read_input_tokens`` and
``cache_creation_input_tokens`` from the response for usage tracking.
"""

from __future__ import annotations

import os
import time
from typing import Any

from primr.ai.providers.base import (
    ChatResponse,
    Provider,
    ProviderUnavailableError,
    QuotaExhaustedError,
)
from primr.utils.logging_config import get_logger

logger = get_logger("ai.providers.anthropic")


# ---------------------------------------------------------------------------
# Error classification helpers
# ---------------------------------------------------------------------------


def _is_quota_exhausted(error: Exception) -> bool:
    """Return True when the error indicates billing/quota exhaustion.

    Anthropic signals this via:
    - HTTP 403 with billing-related error codes
    - HTTP 429 with daily limit indicators (not transient rate-limit)
    """
    error_text = str(error).lower()

    # Billing / credit exhaustion markers
    billing_markers = (
        "billing",
        "insufficient_quota",
        "credits",
        "spending limit",
        "account_suspended",
        "payment",
    )
    if any(marker in error_text for marker in billing_markers):
        return True

    # Daily limit (distinct from transient rate-limit)
    return "daily" in error_text and ("limit" in error_text or "quota" in error_text)


def _is_retryable_status(status_code: int) -> bool:
    """Return True for HTTP status codes that are transient."""
    return status_code in (429, 500, 502, 503, 504)


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------


class AnthropicProvider(Provider):
    """Provider for Anthropic Claude via the anthropic SDK.

    Translates the standard messages list into Anthropic Messages API shape:
    - system messages → top-level ``system`` parameter
    - user/assistant messages → ``messages`` array

    Provider-specific kwargs:
    - thinking: dict — Extended thinking configuration (budget_tokens, etc.)

    Prompt caching is not exposed as a kwarg here; callers embed
    ``cache_control`` directives inside the structured message content they
    pass via ``messages``. Cache token counts are still recorded from the
    response.
    """

    def __init__(
        self,
        *,
        name: str = "anthropic",
        api_key_env: str = "ANTHROPIC_API_KEY",
    ) -> None:
        super().__init__(name)
        self._api_key_env = api_key_env
        self._client: Any = None
        # Cache-aware usage tracking
        self._cached_input_tokens: int = 0
        self._cache_creation_tokens: int = 0

    # -----------------------------------------------------------------
    # Availability
    # -----------------------------------------------------------------

    def is_available(self) -> bool:
        """True when ANTHROPIC_API_KEY is set and anthropic SDK is importable."""
        if not os.getenv(self._api_key_env):
            return False
        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            return False

    # -----------------------------------------------------------------
    # Lazy client init
    # -----------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ProviderUnavailableError(
                "The 'anthropic' package is required for the anthropic provider. "
                "Install it with: pip install anthropic"
            ) from exc

        api_key = os.getenv(self._api_key_env)
        if not api_key:
            raise ProviderUnavailableError(
                f"{self._api_key_env} is not set. The anthropic provider needs it."
            )

        self._client = Anthropic(api_key=api_key)
        return self._client

    # -----------------------------------------------------------------
    # Message translation
    # -----------------------------------------------------------------

    def _translate_messages(
        self, messages: list[dict[str, str]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Split system messages from conversation messages.

        Returns (system_text, anthropic_messages) where system_text is
        the concatenated system messages (or None) and anthropic_messages
        is the user/assistant sequence in Anthropic's format.
        """
        system_parts: list[str] = []
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_parts.append(content)
            else:
                anthropic_messages.append({"role": role, "content": content})

        system_text = "\n\n".join(system_parts) if system_parts else None

        # Anthropic requires the first message to be a user message.
        # If the conversation starts with an assistant message (e.g. from
        # a pre-filled response pattern), prepend an empty user turn.
        if anthropic_messages and anthropic_messages[0].get("role") != "user":
            anthropic_messages.insert(0, {"role": "user", "content": "Continue."})

        return system_text, anthropic_messages

    # -----------------------------------------------------------------
    # Chat
    # -----------------------------------------------------------------

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
        """Send a Messages API request with retry/backoff.

        Raises QuotaExhaustedError on billing exhaustion (HTTP 403 with
        specific error codes or 429 with daily limit indicators).
        """
        if not messages:
            raise ValueError(
                "AnthropicProvider.chat() requires at least one message. "
                "Got an empty messages list."
            )

        client = self._get_client()

        system_text, anthropic_messages = self._translate_messages(messages)

        # Anthropic requires at least one user message in the messages array
        if not anthropic_messages:
            raise ValueError(
                "AnthropicProvider.chat() requires at least one user or assistant "
                "message. Got only system messages."
            )

        # Build the SDK call kwargs
        sdk_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
            "temperature": temperature,
        }

        if system_text is not None:
            sdk_kwargs["system"] = system_text

        # Pass through Anthropic-specific kwargs.
        # NOTE: prompt caching is configured at the message-content level
        # (cache_control directives inside content blocks), not as a top-level
        # parameter — see module docstring.
        if "thinking" in provider_kwargs:
            sdk_kwargs["thinking"] = provider_kwargs["thinking"]

        last_error: Exception | None = None
        backoff_delays = [1.0, 2.0, 4.0, 8.0]  # Exponential backoff

        for attempt in range(1 + retries):
            try:
                response = client.messages.create(**sdk_kwargs)

                # Extract response text
                text = ""
                if response.content:
                    text = response.content[0].text

                # Extract usage
                input_tokens = 0
                output_tokens = 0
                cached_input_tokens = 0
                cache_creation_tokens = 0

                if response.usage:
                    input_tokens = response.usage.input_tokens or 0
                    output_tokens = response.usage.output_tokens or 0
                    cached_input_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
                    cache_creation_tokens = (
                        getattr(response.usage, "cache_creation_input_tokens", 0) or 0
                    )

                self._record_usage(
                    model,
                    input_tokens,
                    output_tokens,
                    cached_input_tokens=cached_input_tokens,
                    cache_creation_tokens=cache_creation_tokens,
                )

                logger.info(
                    "%s call complete (model=%s): %d input, %d output tokens"
                    " (cached: %d, cache_creation: %d)",
                    self.name,
                    model,
                    input_tokens,
                    output_tokens,
                    cached_input_tokens,
                    cache_creation_tokens,
                )

                return ChatResponse(
                    text=text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

            except Exception as e:
                last_error = e

                # Check for quota/billing exhaustion first — never retry these
                if _is_quota_exhausted(e):
                    raise QuotaExhaustedError(f"Anthropic API quota/billing exhausted: {e}") from e

                # Check HTTP status code for structured errors
                status_code = getattr(e, "status_code", None)

                if status_code == 403:
                    # 403 is always billing/auth — don't retry
                    raise QuotaExhaustedError(f"Anthropic API access denied (HTTP 403): {e}") from e

                # Determine if retryable
                is_retryable = False
                if status_code is not None and _is_retryable_status(status_code):
                    is_retryable = True
                elif status_code is None:
                    # Fall back to text-based detection for non-SDK errors
                    error_text = str(e).lower()
                    retryable_markers = (
                        "429",
                        "rate limit",
                        "rate_limit",
                        "500",
                        "502",
                        "503",
                        "504",
                        "overloaded",
                        "temporarily unavailable",
                        "timeout",
                        "timed out",
                        "connection",
                    )
                    is_retryable = any(marker in error_text for marker in retryable_markers)

                if is_retryable:
                    if attempt < retries:
                        delay = (
                            backoff_delays[attempt]
                            if attempt < len(backoff_delays)
                            else backoff_delays[-1]
                        )
                        logger.warning(
                            "Transient Anthropic API error, retrying in %.1fs (attempt %d/%d): %s",
                            delay,
                            attempt + 1,
                            retries + 1,
                            e,
                        )
                        time.sleep(delay)
                        continue
                    logger.warning(
                        "Transient Anthropic API error on final attempt (%d/%d): %s",
                        attempt + 1,
                        retries + 1,
                        e,
                    )
                    break

                # Non-retryable, non-quota error
                raise RuntimeError(f"Anthropic API call failed (non-retryable): {e}") from e

        raise RuntimeError(
            f"Anthropic API call failed after {retries + 1} attempts: {last_error}"
        ) from last_error

    # -----------------------------------------------------------------
    # Usage tracking (cache-aware)
    # -----------------------------------------------------------------

    def _record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        cache_creation_tokens: int = 0,
    ) -> None:
        """Record usage including cache-specific token counts.

        Calls the parent's usage accumulator for standard input/output tokens
        and separately tracks cached token counts for later reporting.
        """
        # Record standard usage via parent accumulator (including cached tokens)
        self._usage.record(
            model,
            input_tokens,
            output_tokens,
            cached_input_tokens=cached_input_tokens,
        )

        # Track cache-specific tokens separately for Anthropic-specific reporting
        self._cached_input_tokens += cached_input_tokens
        self._cache_creation_tokens += cache_creation_tokens

    def get_cache_usage(self) -> dict[str, int]:
        """Return cumulative cache token counts."""
        return {
            "cached_input_tokens": self._cached_input_tokens,
            "cache_creation_tokens": self._cache_creation_tokens,
        }

    def reset_usage(self) -> None:
        """Reset all usage counters including cache tracking."""
        super().reset_usage()
        self._cached_input_tokens = 0
        self._cache_creation_tokens = 0
