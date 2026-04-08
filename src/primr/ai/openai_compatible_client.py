"""OpenAI-compatible chat client helpers.

Supports local backends such as Ollama or self-hosted inference servers that
expose an OpenAI-compatible chat completions API.
"""

from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass

from primr.utils.logging_config import get_logger

logger = get_logger("openai_compatible_client")


@dataclass(frozen=True)
class ChatCompletionResult:
    """Normalized response from an OpenAI-compatible chat completion."""

    text: str
    prompt_tokens: int
    completion_tokens: int


_default_base_url = "http://localhost:11434/v1"


def normalize_openai_base_url(base_url: str | None) -> str:
    """Normalize a local OpenAI-compatible base URL."""
    value = (
        base_url
        or os.getenv("LOCAL_LLM_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or _default_base_url
    ).strip()
    if not value:
        return _default_base_url
    if not re.search(r"/v\d+/?$", value):
        return value.rstrip("/") + "/v1"
    return value.rstrip("/")


def _is_retryable_error(error: Exception) -> bool:
    text = str(error).lower()
    markers = [
        "429",
        "rate limit",
        "rate_limit",
        "500",
        "502",
        "503",
        "504",
        "timeout",
        "timed out",
        "connection reset",
        "connection aborted",
        "connection refused",
        "temporarily unavailable",
        "try again later",
    ]
    return any(marker in text for marker in markers)


def _compute_backoff_delay(attempt: int, *, base: float = 2.0, cap: float = 20.0) -> float:
    raw = min(cap, base * (2**attempt))
    jitter = random.uniform(0, raw * 0.2)
    return raw + jitter


def chat_completion(
    prompt: str,
    *,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str = "LOCAL_LLM_API_KEY",
    temperature: float = 0.1,
    max_tokens: int = 900,
    retries: int = 2,
    system_prompt: str | None = None,
) -> ChatCompletionResult:
    """Call an OpenAI-compatible chat completions endpoint and normalize the result."""
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "The 'openai' package is required for OpenAI-compatible local evals. "
            "Install it with: pip install 'primr[fast]' or pip install openai"
        ) from exc

    resolved_base_url = normalize_openai_base_url(base_url)
    resolved_api_key = api_key if api_key is not None else os.getenv(api_key_env, "ollama")

    client = openai.OpenAI(api_key=resolved_api_key or "ollama", base_url=resolved_base_url)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if not response.choices:
                raise RuntimeError("OpenAI-compatible backend returned no choices")
            text = response.choices[0].message.content or ""
            usage = response.usage
            return ChatCompletionResult(
                text=text,
                prompt_tokens=(usage.prompt_tokens if usage else 0) or 0,
                completion_tokens=(usage.completion_tokens if usage else 0) or 0,
            )
        except Exception as exc:
            last_error = exc
            if attempt < retries and _is_retryable_error(exc):
                wait = _compute_backoff_delay(attempt)
                logger.warning(
                    "Transient OpenAI-compatible error, retrying in %.1fs (attempt %d/%d): %s",
                    wait,
                    attempt + 1,
                    retries + 1,
                    exc,
                )
                time.sleep(wait)
                continue
            break

    raise RuntimeError(
        f"OpenAI-compatible chat completion failed after {retries + 1} attempts: {last_error}"
    ) from last_error
