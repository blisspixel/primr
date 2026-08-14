"""
OpenAI-compatible provider.

A single class that talks to anything exposing a chat-completions endpoint
shaped like ``POST /v1/chat/completions`` with the OpenAI message schema.
This covers xAI/Grok, OpenAI itself, Ollama (with ``OLLAMA_API_KEY=ollama``
or the built-in placeholder), vLLM, llama.cpp's server, and similar
runtimes.

Each instance is a *parameterized* provider — registering xAI vs OpenAI vs
Ollama is just constructing this class with different ``base_url`` and
``api_key_env`` values. No per-vendor subclass needed for these.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any

from primr.ai.error_policy import extract_retry_after_seconds as _extract_retry_after_seconds
from primr.ai.provider_availability import LocalCapacityBusyError
from primr.ai.providers.base import (
    ChatResponse,
    CredentialCheck,
    Provider,
    ProviderUnavailableError,
)
from primr.utils.logging_config import get_logger
from primr.utils.model_policy import require_model_calls_allowed

logger = get_logger("ai.providers.openai_compatible")
_LOCAL_INTERNAL_RETRY_CAP_SECONDS = 20.0


def create_openai_sdk_client(
    openai_module: Any,
    *,
    api_key: str,
    base_url: str,
) -> Any:
    """Create a transport whose retries and redirects are bounded by Primr."""
    http_client = openai_module.DefaultHttpxClient(follow_redirects=False)
    return openai_module.OpenAI(
        api_key=api_key,
        base_url=base_url,
        max_retries=0,
        http_client=http_client,
    )


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

    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    if status_code == 429 or (isinstance(status_code, int) and 500 <= status_code <= 599):
        return True

    error_type = type(error)
    if error_type.__module__.startswith("openai") and error_type.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
    }:
        return True

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
        "connection error",
    )
    return any(marker in error_text for marker in retryable_markers)


def _is_temperature_unsupported(error: Exception) -> bool:
    """Return True for the OpenAI 400 raised when a model rejects a custom
    temperature (reasoning tiers like gpt-5.5 / o-series only allow the default)."""
    text = str(error).lower()
    if "temperature" not in text:
        return False
    return (
        "unsupported value" in text
        or "does not support" in text
        or "only the default" in text
        or "only supports" in text
    )


def _compute_backoff_delay(attempt: int, *, base: float = 5.0, cap: float = 90.0) -> float:
    """Exponential backoff with jitter for transient API failures."""
    raw = min(cap, base * (2**attempt))
    jitter = random.uniform(0, raw * 0.2)
    return raw + jitter


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider(Provider):
    """Provider for OpenAI-shaped Responses or Chat Completions endpoints.

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
        local_capacity: bool | None = None,
        api_style: str = "chat_completions",
    ) -> None:
        super().__init__(name)
        self._base_url = base_url
        self._api_key_env = api_key_env
        self._api_key_default = api_key_default
        self._billing_help_url = billing_help_url
        self._local_capacity = name == "ollama" if local_capacity is None else local_capacity
        if api_style not in {"chat_completions", "responses"}:
            raise ValueError(f"Unsupported OpenAI-compatible API style: {api_style}")
        self._api_style = api_style
        self._client: Any = None

    # -----------------------------------------------------------------
    # Availability + lazy client init
    # -----------------------------------------------------------------

    def is_available(self) -> bool:
        # A usable provider needs both a credential and the transport SDK.
        # The credential may come from the env var or a baked-in default (local
        # runtimes like Ollama). The transport is always the ``openai`` SDK, so
        # an unimportable ``openai`` means this provider can't actually run -
        # mirror Anthropic/Gemini, which also gate on their SDK here so that
        # `primr doctor` reports usability honestly rather than at call time.
        has_credential = self._api_key_default is not None or bool(os.getenv(self._api_key_env))
        if not has_credential:
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

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

        self._client = create_openai_sdk_client(
            openai,
            api_key=api_key,
            base_url=self._base_url,
        )
        return self._client

    def validate_credentials(self) -> CredentialCheck:
        """Auth-only check via the free ``GET /models`` endpoint (no generation)."""
        import time

        if not self.is_available():
            return CredentialCheck(
                provider=self.name, ok=False, detail=f"{self._api_key_env} not set"
            )
        start = time.monotonic()
        try:
            client = self._get_client()
            models = client.models.list()
            count = len(list(getattr(models, "data", []) or []))
            latency = int((time.monotonic() - start) * 1000)
            return CredentialCheck(
                provider=self.name,
                ok=True,
                detail=f"authenticated; {count} models visible",
                latency_ms=latency,
            )
        except Exception as exc:
            return CredentialCheck(
                provider=self.name,
                ok=False,
                detail=f"{type(exc).__name__}: {str(exc)[:120]}",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

    # -----------------------------------------------------------------
    # Chat
    # -----------------------------------------------------------------

    def _build_sdk_kwargs(
        self, provider_kwargs: dict[str, Any], *, max_tokens: int
    ) -> dict[str, Any]:
        """Translate the normalized chat knobs into the selected API shape."""
        if self._api_style == "responses":
            sdk_kwargs: dict[str, Any] = {
                "max_output_tokens": max_tokens,
                "store": bool(provider_kwargs.get("store", False)),
            }
            if "top_p" in provider_kwargs:
                sdk_kwargs["top_p"] = provider_kwargs["top_p"]
            if "reasoning_effort" in provider_kwargs:
                sdk_kwargs["reasoning"] = {"effort": provider_kwargs["reasoning_effort"]}
            response_format = provider_kwargs.get("response_format")
            if isinstance(response_format, dict):
                normalized_format = response_format
                if response_format.get("type") == "json_schema" and isinstance(
                    response_format.get("json_schema"), dict
                ):
                    normalized_format = {
                        "type": "json_schema",
                        **response_format["json_schema"],
                    }
                sdk_kwargs["text"] = {"format": normalized_format}
            for key in ("tools", "tool_choice", "parallel_tool_calls"):
                if key in provider_kwargs:
                    sdk_kwargs[key] = provider_kwargs[key]
            prompt_cache_key = provider_kwargs.get("prompt_cache_key")
            if prompt_cache_key:
                sdk_kwargs["extra_body"] = {"prompt_cache_key": str(prompt_cache_key)}
            return sdk_kwargs

        sdk_kwargs = {}
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
        output_key = "max_completion_tokens" if self.name == "openai" else "max_tokens"
        sdk_kwargs[output_key] = max_tokens
        return sdk_kwargs

    def _create_sdk_response(
        self,
        client: Any,
        *,
        model: str,
        messages: list[dict[str, str]],
        call_kwargs: dict[str, Any],
    ) -> Any:
        """Issue one request using Responses or Chat Completions."""
        if self._api_style == "responses":
            return client.responses.create(model=model, input=messages, **call_kwargs)
        return client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            **call_kwargs,
        )

    def _normalize_sdk_response(self, response: Any) -> ChatResponse:
        """Normalize text, token usage, cache usage, and exact billed cost."""
        if self._api_style == "responses":
            text = getattr(response, "output_text", "") or ""
            response_status = getattr(response, "status", None)
            incomplete_details = getattr(response, "incomplete_details", None)
            if isinstance(incomplete_details, dict):
                incomplete_reason = incomplete_details.get("reason")
            else:
                incomplete_reason = getattr(incomplete_details, "reason", None)
        else:
            if not response.choices:
                raise RuntimeError(
                    f"{self.name} returned empty response (no choices, possible content filter)"
                )
            text = response.choices[0].message.content or ""
            response_status = None
            incomplete_reason = None

        usage = getattr(response, "usage", None)
        if usage is None:
            return ChatResponse(text=text)

        if self._api_style == "responses":
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            details = getattr(usage, "input_tokens_details", None)
        else:
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
            details = getattr(usage, "prompt_tokens_details", None)
        cached_input_tokens = getattr(usage, "cached_tokens", 0) or 0
        if cached_input_tokens == 0 and details is not None:
            cached_input_tokens = getattr(details, "cached_tokens", 0) or 0
        billed_ticks = getattr(usage, "cost_in_usd_ticks", None)
        actual_cost_usd = int(billed_ticks) / 10_000_000_000 if billed_ticks is not None else None
        return ChatResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            actual_cost_usd=actual_cost_usd,
            response_status=str(response_status) if response_status is not None else None,
            incomplete_reason=(str(incomplete_reason) if incomplete_reason is not None else None),
        )

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

        Recognized ``provider_kwargs`` are translated to the selected API
        shape. Responses supports structured text, tools, tool choice,
        parallel-tool policy, reasoning effort, top-p, storage policy, and the
        xAI prompt-cache extension. Unknown provider-specific knobs are ignored.
        """
        require_model_calls_allowed(f"{self.name} chat")
        client = self._get_client()
        capacity_retry_attempt = provider_kwargs.pop("capacity_retry_attempt", 0)

        sdk_kwargs = self._build_sdk_kwargs(provider_kwargs, max_tokens=max_tokens)

        last_error: Exception | None = None
        # OpenAI reasoning tiers (gpt-5.5, o-series, ...) reject a non-default
        # temperature with a 400. We can't reliably enumerate which models do, so
        # we send temperature optimistically and drop it on that specific error.
        omit_temperature = False
        attempt = 0
        while attempt <= retries:
            try:
                call_kwargs: dict[str, Any] = dict(sdk_kwargs)
                if not omit_temperature:
                    call_kwargs["temperature"] = temperature
                response = self._create_sdk_response(
                    client,
                    model=model,
                    messages=messages,
                    call_kwargs=call_kwargs,
                )
                normalized = self._normalize_sdk_response(response)
                if getattr(response, "usage", None):
                    self._record_usage(
                        model,
                        normalized.input_tokens,
                        normalized.output_tokens,
                        cached_input_tokens=normalized.cached_input_tokens,
                    )

                logger.info(
                    "%s call complete (model=%s): %d input, %d output tokens",
                    self.name,
                    model,
                    normalized.input_tokens,
                    normalized.output_tokens,
                )
                return normalized

            except Exception as e:
                last_error = e
                local_busy_error = (
                    LocalCapacityBusyError.from_exception(
                        e,
                        attempt=capacity_retry_attempt,
                    )
                    if self._local_capacity
                    else None
                )

                # Reasoning models reject a custom temperature - drop it once and
                # retry the same call rather than failing outright.
                if not omit_temperature and _is_temperature_unsupported(e):
                    omit_temperature = True
                    logger.info(
                        "%s rejected temperature for model %s; retrying without it",
                        self.name,
                        model,
                    )
                    continue

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

                if _is_retryable_error(e) or local_busy_error is not None:
                    if attempt < retries:
                        retry_after = _extract_retry_after_seconds(e)
                        wait = (
                            retry_after
                            if retry_after is not None
                            else _compute_backoff_delay(attempt)
                        )
                        if self._local_capacity:
                            wait = min(wait, _LOCAL_INTERNAL_RETRY_CAP_SECONDS)
                        logger.warning(
                            "Transient %s API error, retrying in %.1fs (attempt %d/%d): %s",
                            self.name,
                            wait,
                            attempt + 1,
                            retries + 1,
                            e,
                        )
                        time.sleep(wait)
                        attempt += 1
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

        if self._local_capacity and last_error is not None:
            busy_error = LocalCapacityBusyError.from_exception(
                last_error,
                attempt=capacity_retry_attempt,
            )
            if busy_error is not None:
                raise busy_error from last_error

        raise RuntimeError(
            f"{self.name} API call failed after {retries + 1} attempts: {last_error}"
        ) from last_error
