"""
Google Gemini provider.

Wraps ``google.genai`` and implements the same ``Provider`` interface as
the OpenAI-compatible providers. Translates the OpenAI-style message list
(``[{"role": "system" | "user" | "assistant", "content": ...}]``) into
Gemini's ``system_instruction`` + ``contents`` shape, then dispatches
through ``client.models.generate_content`` (or the streaming variant when
``streaming=True`` is passed in ``provider_kwargs``).

Provider-specific knobs accepted via ``provider_kwargs``:

- ``thinking_level``: ``"low"`` or ``"high"`` (default ``"high"``). Maps
  to Gemini 3 ``ThinkingConfig.thinking_level``.
- ``streaming``: ``True`` enables ``generate_content_stream`` so the
  caller eats the stream into the returned text. Defaults to ``False``.

Quota handling is split into two cases. Daily quota exhaustion (the user
has run out of free-tier requests for the day) raises ``QuotaExhaustedError``
so the consuming function can add a UI message and stop. Transient
rate-limit errors (HTTP 429) and generic exceptions retry with exponential
backoff up to ``retries`` attempts before giving up.
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

logger = get_logger("ai.providers.gemini")


# ---------------------------------------------------------------------------
# Lazy SDK import — keep the provider importable even when google.genai is
# missing (e.g. minimal install). Construction succeeds; first call raises
# ProviderUnavailableError.
# ---------------------------------------------------------------------------

try:
    from google import genai as _google_genai
    from google.genai import types as _google_types

    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as import_error:
    _google_genai = None  # type: ignore[assignment]
    _google_types = None  # type: ignore[assignment]
    _GENAI_IMPORT_ERROR = import_error


# ---------------------------------------------------------------------------
# Quota / rate-limit classification
# ---------------------------------------------------------------------------


def _is_daily_quota_exhausted(error: Exception) -> bool:
    """True for daily-quota hits that won't recover via retry."""
    error_text = str(error).lower()
    if "resource_exhausted" not in error_text:
        return False
    return "per_day" in error_text or ("quota" in error_text and "exceeded" in error_text)


def _is_rate_limited(error: Exception) -> bool:
    """True for transient 429 / resource_exhausted-but-not-daily hits."""
    error_text = str(error).lower()
    if _is_daily_quota_exhausted(error):
        return False
    return "429" in error_text or "resource_exhausted" in error_text


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------


class GeminiProvider(Provider):
    """Provider for Google Gemini via the ``google.genai`` SDK."""

    DEFAULT_RETRIES: int = 5
    BACKOFF_CAP_SECONDS: float = 60.0

    def __init__(
        self,
        *,
        name: str = "gemini",
        api_key_env: str = "GEMINI_API_KEY",
    ) -> None:
        super().__init__(name)
        self._api_key_env = api_key_env
        self._client: Any = None

    # -----------------------------------------------------------------
    # Availability + lazy client init
    # -----------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(os.getenv(self._api_key_env)) and _GENAI_IMPORT_ERROR is None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if _GENAI_IMPORT_ERROR is not None:
            raise ProviderUnavailableError(
                "google.genai is not available. Install primr's dependencies."
            ) from _GENAI_IMPORT_ERROR
        api_key = os.getenv(self._api_key_env)
        if not api_key:
            raise ProviderUnavailableError(
                f"{self._api_key_env} is not set. The Gemini provider needs it."
            )
        self._client = _google_genai.Client(api_key=api_key)
        return self._client

    # -----------------------------------------------------------------
    # Message translation
    # -----------------------------------------------------------------

    @staticmethod
    def _split_messages(
        messages: list[dict[str, str]],
    ) -> tuple[str | None, str]:
        """Return ``(system_instruction, contents)`` for the Gemini SDK.

        primr's only multi-turn pattern (ContinuousReasoningSession) is
        xAI-specific, so for the Gemini path we collapse non-system messages
        into a single ``contents`` string. A future Gemini chat-history
        feature can override this if multi-turn Gemini is needed.
        """
        system_parts: list[str] = []
        body_parts: list[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                body_parts.append(content)
        system_instruction = "\n\n".join(p for p in system_parts if p) or None
        contents = "\n\n".join(p for p in body_parts if p)
        return system_instruction, contents

    # -----------------------------------------------------------------
    # Chat
    # -----------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 1.0,
        max_tokens: int = 16_000,
        retries: int = DEFAULT_RETRIES,
        **provider_kwargs: Any,
    ) -> ChatResponse:
        """Run a Gemini generate_content call.

        ``max_tokens`` is accepted for interface symmetry but Gemini sets
        the response cap server-side based on the model — passing it is
        usually a no-op. Use ``thinking_level`` (low/high) and ``streaming``
        (bool) via ``provider_kwargs`` to control Gemini-specific behaviour.
        """
        client = self._get_client()
        system_instruction, contents = self._split_messages(messages)
        if not contents:
            raise RuntimeError("Gemini call requires at least one non-system message in `messages`")

        thinking_level = provider_kwargs.get("thinking_level", "high")
        streaming = bool(provider_kwargs.get("streaming", False))

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "thinking_config": _google_types.ThinkingConfig(thinking_level=thinking_level),
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        config = _google_types.GenerateContentConfig(**config_kwargs)

        last_error: Exception | None = None
        for attempt in range(1 + retries):
            try:
                if streaming:
                    stream = client.models.generate_content_stream(
                        model=model, contents=contents, config=config
                    )
                    parts: list[str] = []
                    for chunk in stream:
                        if hasattr(chunk, "text") and chunk.text:
                            parts.append(str(chunk.text))
                    text = "".join(parts).strip()
                    response = None
                else:
                    response = client.models.generate_content(
                        model=model, contents=contents, config=config
                    )
                    text = (response.text or "").strip()

                if not text:
                    raise RuntimeError(
                        "Gemini returned empty response (possible content filter or safety block)"
                    )

                input_tokens, output_tokens = self._extract_usage(response)
                if input_tokens or output_tokens:
                    self._record_usage(model, input_tokens, output_tokens)

                logger.info(
                    "gemini call complete (model=%s): %d input, %d output tokens",
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

                if _is_daily_quota_exhausted(e):
                    raise QuotaExhaustedError(
                        "Gemini daily API quota exhausted. Wait for the quota "
                        "window to reset, upgrade your plan, or rotate keys."
                    ) from e

                if _is_rate_limited(e):
                    if attempt < retries:
                        wait = min(self.BACKOFF_CAP_SECONDS, 5.0 * (2**attempt))
                        logger.warning(
                            "Gemini rate limited, waiting %.0fs before retry %d/%d",
                            wait,
                            attempt + 1,
                            retries + 1,
                        )
                        time.sleep(wait)
                        continue
                    break

                # Generic transient error — short backoff
                if attempt < retries:
                    logger.warning(
                        "Gemini API call failed (attempt %d/%d): %s",
                        attempt + 1,
                        retries + 1,
                        e,
                    )
                    time.sleep(2)
                    continue
                break

        raise RuntimeError(
            f"Gemini API call failed after {retries + 1} attempts: {last_error}"
        ) from last_error

    # -----------------------------------------------------------------
    # Usage extraction
    # -----------------------------------------------------------------

    @staticmethod
    def _extract_usage(response: Any) -> tuple[int, int]:
        """Pull (input_tokens, output_tokens) from a Gemini response if present."""
        if response is None:
            return 0, 0
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return 0, 0
        input_tokens = getattr(meta, "prompt_token_count", 0) or 0
        # Gemini 3 includes thinking tokens in candidates_token_count
        output_tokens = getattr(meta, "candidates_token_count", 0) or 0
        return int(input_tokens), int(output_tokens)
