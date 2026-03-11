"""
Grok 4.1 client for fast research mode.

Uses xAI's OpenAI-compatible API at https://api.x.ai/v1.
Requires XAI_API_KEY environment variable and the `openai` package.

Usage:
    from primr.ai.grok_client import grok_llm, get_grok_session_usage

    text = grok_llm("Write a report about ...", max_tokens=16_000)
    usage = get_grok_session_usage()  # {'input_tokens': ..., 'output_tokens': ...}
"""

import random
import re
import time

from primr.utils.logging_config import get_logger

logger = get_logger("grok_client")

# ---------------------------------------------------------------------------
# Session-level token tracking
# ---------------------------------------------------------------------------
_session_input_tokens: int = 0
_session_output_tokens: int = 0


def get_grok_session_usage() -> dict[str, int]:
    """Return cumulative token usage for the current session."""
    return {
        "input_tokens": _session_input_tokens,
        "output_tokens": _session_output_tokens,
    }


def reset_grok_session() -> None:
    """Reset session token counters (useful for testing)."""
    global _session_input_tokens, _session_output_tokens
    _session_input_tokens = 0
    _session_output_tokens = 0


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
# Main entry point
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "grok-4-1-fast-reasoning"


def _is_retryable_grok_error(error: Exception) -> bool:
    """Return True when a Grok API error is likely transient and safe to retry."""
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
    model: str = _DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 16_000,
    retries: int = 4,
    system_prompt: str | None = None,
) -> str:
    """
    Call Grok and return the text response.

    Args:
        prompt: The user prompt to send.
        model: Model ID (default: grok-4-1-fast-reasoning).
               Use grok-4-1-fast-non-reasoning for writing tasks.
        temperature: Sampling temperature.
        max_tokens: Maximum output tokens.
        retries: Number of retries on transient errors (429/5xx/network timeouts).
        system_prompt: Optional system message prepended before the user message.

    Returns:
        The assistant's text response.

    Raises:
        ImportError: If the openai package is not installed.
        ConfigurationError: If XAI_API_KEY is not set.
        RuntimeError: If the API call fails after retries.
    """
    global _session_input_tokens, _session_output_tokens

    client = _get_grok_client()

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_error = None
    for attempt in range(1 + retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if not response.choices:
                raise RuntimeError(
                    "Grok returned empty response (no choices — possible content filter)"
                )

            # Track tokens only after confirming we got a valid response
            if response.usage:
                _session_input_tokens += response.usage.prompt_tokens or 0
                _session_output_tokens += response.usage.completion_tokens or 0

            text = response.choices[0].message.content or ""
            logger.info(
                "Grok call complete: %d input, %d output tokens",
                response.usage.prompt_tokens if response.usage else 0,
                response.usage.completion_tokens if response.usage else 0,
            )
            return text

        except Exception as e:
            last_error = e
            if _is_retryable_grok_error(e):
                if attempt < retries:
                    retry_after = _extract_retry_after_seconds(e)
                    wait = (
                        retry_after if retry_after is not None else _compute_backoff_delay(attempt)
                    )
                    logger.warning(
                        "Transient Grok API error, retrying in %.1fs (attempt %d/%d): %s",
                        wait,
                        attempt + 1,
                        retries + 1,
                        e,
                    )
                    time.sleep(wait)
                    continue
                logger.warning(
                    "Transient Grok API error on final attempt (%d/%d): %s",
                    attempt + 1,
                    retries + 1,
                    e,
                )
                break

            # Non-retryable error
            raise RuntimeError(f"Grok API call failed (non-retryable): {e}") from e

    raise RuntimeError(
        f"Grok API call failed after {retries + 1} attempts: {last_error}"
    ) from last_error
