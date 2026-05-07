"""
OpenAI-compatible provider.

A single class that talks to anything exposing a chat-completions endpoint
shaped like ``POST /v1/chat/completions`` with the OpenAI message schema.
This covers xAI/Grok, OpenAI itself, Ollama (with ``OPENAI_API_KEY=ollama``
or any non-empty placeholder), vLLM, llama.cpp's server, and similar
runtimes.

Each instance is a *parameterized* provider — registering xAI vs OpenAI vs
Ollama is just constructing this class with different ``base_url`` and
``api_key_env`` values. No per-vendor subclass needed for these.
"""

from __future__ import annotations

import os
import random
import re
import time
from typing import Any

from primr.ai.providers.base import ChatResponse, Provider, ProviderUnavailableError
from primr.utils.logging_config import get_logger

logger = get_logger("ai.providers.openai_compatible")


# ---------------------------------------------------------------------------
# Error classification (shared across all OpenAI-compatible providers)
# ---------------------------------------------------------------------------


def _is_billing_exhausted(error: Exception) -> bool:
    """Return True when the error indicates credits/spending limit exhaustion.

    These errors will never resolve on retry — the user must add credits.
    Checked before the retryable test so we don't waste time on backoff.
    """
    from primr.ai.error_policy import is_billing_exhausted

    return is_billing_exhausted(error)


def _is_retryable_error(error: Exception) -> bool:
    """Return True when an OpenAI-compatible API error is likely transient."""
    if _is_billing_exhausted(error):
        return False

    error_text = str(error).lower()
    retryable_markers = (
        "429",
        "rate limit",
        "rate_limit",
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
    )
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


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider(Provider):
    """Provider for any OpenAI-shaped chat-completions endpoint.

    Construct one instance per (base_url, key) pair. Examples::

        xai = OpenAICompatibleProvider(
            name="xai",
            base_url="https://api.x.ai/v1",
            api_key_env="XAI_API_KEY",
        )

        openai_p = OpenAICompatibleProvider(
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
        )

        ollama = OpenAICompatibleProvider(
            name="ollama",
            base_url="http://localhost:11434/v1",
            api_key_env="OLLAMA_API_KEY",  # Ollama ignores the key but the SDK requires one
            api_key_default="ollama-local",
        )
    """

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key_env: str,
        api_key_default: str | None = None,
        billing_help_url: str | None = None,
    ) -> None:
        super().__init__(name)
        self._base_url = base_url
        self._api_key_env = api_key_env
        self._api_key_default = api_key_default
        self._billing_help_url = billing_help_url
        self._client: Any = None

    # -----------------------------------------------------------------
    # Availability + lazy client init
    # -----------------------------------------------------------------

    def is_available(self) -> bool:
        if self._api_key_default is not None:
            return True
        return bool(os.getenv(self._api_key_env))

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            import openai
        except ImportError as exc:
            raise ProviderUnavailableError(
                f"The 'openai' package is required for the {self.name} provider. "
                "Install it with: pip install openai"
            ) from exc

        api_key = os.getenv(self._api_key_env) or self._api_key_default
        if not api_key:
            raise ProviderUnavailableError(
                f"{self._api_key_env} is not set. The {self.name} provider needs it."
            )

        self._client = openai.OpenAI(api_key=api_key, base_url=self._base_url)
        return self._client

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
        """Run a chat completion against this provider.

        Unknown ``provider_kwargs`` are forwarded to the underlying SDK call
        when they correspond to OpenAI-shaped knobs (``reasoning_effort``,
        ``top_p``, ``stop``, ``presence_penalty``, ``frequency_penalty``,
        ``seed``, ``response_format``). Anything else is ignored so the
        abstraction stays robust to provider-specific kwargs that this
        provider doesn't know about.
        """
        client = self._get_client()

        # Whitelist the SDK kwargs we accept; everything else is silently
        # dropped on the floor for this provider.
        sdk_kwargs: dict[str, Any] = {}
        for key in (
            "top_p",
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "response_format",
            "reasoning_effort",
        ):
            if key in provider_kwargs:
                sdk_kwargs[key] = provider_kwargs[key]

        last_error: Exception | None = None
        for attempt in range(1 + retries):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **sdk_kwargs,
                )

                if not response.choices:
                    raise RuntimeError(
                        f"{self.name} returned empty response "
                        "(no choices — possible content filter)"
                    )

                input_tokens = 0
                output_tokens = 0
                cached_input_tokens = 0
                if response.usage:
                    input_tokens = response.usage.prompt_tokens or 0
                    output_tokens = response.usage.completion_tokens or 0
                    # xAI: usage.cached_tokens (top-level)
                    cached_input_tokens = getattr(response.usage, "cached_tokens", 0) or 0
                    # OpenAI: usage.prompt_tokens_details.cached_tokens
                    if cached_input_tokens == 0:
                        prompt_details = getattr(response.usage, "prompt_tokens_details", None)
                        if prompt_details is not None:
                            cached_input_tokens = getattr(prompt_details, "cached_tokens", 0) or 0
                    self._record_usage(
                        model, input_tokens, output_tokens,
                        cached_input_tokens=cached_input_tokens,
                    )

                text = response.choices[0].message.content or ""
                logger.info(
                    "%s call complete (model=%s): %d input, %d output tokens",
                    self.name,
                    model,
                    input_tokens,
                    output_tokens,
                )
                return ChatResponse(
                    text=text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

            except Exception as e:
                last_error = e

                if _is_billing_exhausted(e):
                    from primr.ai.providers.base import QuotaExhaustedError

                    help_link = (
                        f" Add credits at {self._billing_help_url} and re-run."
                        if self._billing_help_url
                        else ""
                    )
                    raise QuotaExhaustedError(
                        f"{self.name} API credits exhausted or spending limit reached.{help_link} "
                        "Your progress has been saved — the same command will resume."
                    ) from e

                if _is_retryable_error(e):
                    if attempt < retries:
                        retry_after = _extract_retry_after_seconds(e)
                        wait = (
                            retry_after
                            if retry_after is not None
                            else _compute_backoff_delay(attempt)
                        )
                        logger.warning(
                            "Transient %s API error, retrying in %.1fs (attempt %d/%d): %s",
                            self.name,
                            wait,
                            attempt + 1,
                            retries + 1,
                            e,
                        )
                        time.sleep(wait)
                        continue
                    logger.warning(
                        "Transient %s API error on final attempt (%d/%d): %s",
                        self.name,
                        attempt + 1,
                        retries + 1,
                        e,
                    )
                    break

                raise RuntimeError(f"{self.name} API call failed (non-retryable): {e}") from e

        raise RuntimeError(
            f"{self.name} API call failed after {retries + 1} attempts: {last_error}"
        ) from last_error
