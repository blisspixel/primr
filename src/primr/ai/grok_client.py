"""
Grok 4.1 client for fast research mode.

Uses xAI's OpenAI-compatible API at https://api.x.ai/v1.
Requires XAI_API_KEY environment variable and the `openai` package.

Usage:
    from primr.ai.grok_client import grok_llm, get_grok_session_usage

    text = grok_llm("Write a report about ...", max_tokens=16_000)
    usage = get_grok_session_usage()  # {'input_tokens': ..., 'output_tokens': ...}
"""

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


def grok_llm(
    prompt: str,
    *,
    model: str = _DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 16_000,
    retries: int = 2,
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
        retries: Number of retries on 429 rate-limit errors.
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
                raise RuntimeError("Grok returned empty response (no choices — possible content filter)")

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
            # Retry on rate limit (429)
            error_str = str(e)
            if "429" in error_str or "rate limit" in error_str.lower() or "rate_limit" in error_str.lower():
                if attempt < retries:
                    wait = 2 ** attempt * 5  # 5s, 10s
                    logger.warning("Grok rate limited, retrying in %ds (attempt %d/%d)", wait, attempt + 1, retries + 1)
                    time.sleep(wait)
                    continue
                # Final attempt — don't sleep, fall through to raise
                logger.warning("Grok rate limited on final attempt (%d/%d)", attempt + 1, retries + 1)
                break
            # Non-retryable error
            raise RuntimeError(f"Grok API call failed: {e}") from e

    raise RuntimeError(f"Grok API call failed after {retries + 1} attempts: {last_error}") from last_error
