"""
Unified AI client for all LLM operations.

This module provides:
- Single AI client with consistent interface
- Automatic retry with exponential backoff
- Model fallback support
- Proper error handling and logging
- Token usage tracking for cost monitoring
"""

import asyncio
import concurrent.futures
import time
from dataclasses import dataclass
from typing import Any

try:
    from google import genai as _google_genai
    from google.genai import types as _google_types
    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as import_error:
    _GENAI_IMPORT_ERROR = import_error

    class _GenAIUnavailable:
        class Client:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("google.genai is unavailable")

    @dataclass
    class _FallbackThinkingConfig:
        thinking_level: str

    @dataclass
    class _FallbackGenerateContentConfig:
        temperature: float
        thinking_config: _FallbackThinkingConfig

    class _FallbackTypes:
        GenerateContentConfig = _FallbackGenerateContentConfig
        ThinkingConfig = _FallbackThinkingConfig

    _google_genai = _GenAIUnavailable()  # type: ignore[assignment]
    _google_types = _FallbackTypes()  # type: ignore[assignment]
    _FALLBACK_CLIENT_CLASS = _GenAIUnavailable.Client
else:
    _FALLBACK_CLIENT_CLASS = None  # type: ignore[misc]

genai = _google_genai
types = _google_types

from primr.ai.error_policy import (
    is_daily_quota_exhausted,
    is_invalid_api_key_error,
    is_timeout_error,
)
from primr.config.settings import get_settings
from primr.utils.errors import AIError, calculate_retry_delay, is_rate_limit_error
from primr.utils.logging_config import get_logger
from primr.utils.type_guards import is_valid_type

logger = get_logger("ai.client")


def _require_genai_dependency() -> None:
    """Raise a clear error when google.genai is unavailable."""
    if _GENAI_IMPORT_ERROR is None:
        return
    # Allow tests or callers to inject/patch a working client implementation.
    if _FALLBACK_CLIENT_CLASS is not None and getattr(genai, "Client", None) is not _FALLBACK_CLIENT_CLASS:
        return
    raise AIError(
        "google.genai is not available. Install compatible dependencies "
        "(Python 3.11+ and project requirements).",
        cause=_GENAI_IMPORT_ERROR,
    ) from _GENAI_IMPORT_ERROR


@dataclass
class TokenUsage:
    """Token usage from a single API call."""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class AIClient:
    """
    Unified AI client with retry logic and error handling.

    Example:
        client = AIClient()
        response = client.generate("What is Python?")

        # Fast mode for simple tasks
        response = client.generate_fast("Summarize this text")

        # Check usage
        print(f"Total tokens: {client.total_input_tokens + client.total_output_tokens}")
    """

    def __init__(self, api_key: str | None = None, track_usage: bool = True):
        """
        Initialize the AI client.

        Args:
            api_key: Optional API key override. If not provided,
                    uses the key from settings.
            track_usage: If True, track token usage for cost monitoring.
        """
        _require_genai_dependency()
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client = genai.Client(api_key=self._api_key)
        self._settings = settings.ai
        self._track_usage = track_usage
        self._pending_close_tasks: list[asyncio.Task[Any]] = []

        # Token usage tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0
        self.usage_by_model: dict[str, dict[str, int | float]] = {}

        logger.debug("AI client initialized")

    def close(self) -> None:
        """Best-effort close of underlying client transport resources."""
        close_fn = getattr(self._client, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception as e:
                logger.warning("Failed to close AI client with close(): %s", e)
            return

        aclose_fn = getattr(self._client, "aclose", None)
        if callable(aclose_fn):
            try:
                coro = aclose_fn()
                if asyncio.iscoroutine(coro):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        asyncio.run(coro)
                    else:
                        self._pending_close_tasks.append(loop.create_task(coro))
            except Exception as e:
                logger.warning("Failed to close AI client with aclose(): %s", e)

    def __enter__(self) -> "AIClient":
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.close()

    def generate(
        self,
        prompt: str,
        model_type: str = "research",
        temperature: float = 1.0,
        thinking_level: str = "high",
        max_retries: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """
        Generate content with automatic retries.

        Args:
            prompt: The prompt to send to the model
            model_type: "research" or "report" - determines which model to use
            temperature: Sampling temperature (0.0-2.0)
            thinking_level: "low" or "high" - controls reasoning depth
            max_retries: Override default retry count
            timeout: Request timeout in seconds

        Returns:
            Generated text response

        Raises:
            AIError: If all retries fail
            ValueError: If temperature is out of bounds

        Example:
            response = client.generate(
                "Analyze this company",
                model_type="research",
                thinking_level="high"
            )
        """
        # Validate inputs
        if not prompt or not prompt.strip():
            raise ValueError("prompt cannot be empty")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError(f"temperature must be between 0.0 and 2.0, got {temperature}")
        if thinking_level not in ("low", "high"):
            raise ValueError(f"thinking_level must be 'low' or 'high', got {thinking_level}")

        model = self._get_model(model_type)
        retries = max(1, max_retries if max_retries is not None else self._settings.max_retries)

        config = types.GenerateContentConfig(
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level)  # type: ignore[arg-type]
        )

        deadline = time.monotonic() + timeout if timeout is not None else None
        last_error = None
        for attempt in range(retries):
            try:
                logger.debug(f"AI call attempt {attempt + 1}/{retries} to {model}")

                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"AI call timed out after {timeout:.2f}s")
                else:
                    remaining = None

                if remaining is None:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=config
                    )
                else:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(
                            self._client.models.generate_content,
                            model=model,
                            contents=prompt,
                            config=config,
                        )
                        try:
                            response = future.result(timeout=remaining)
                        except concurrent.futures.TimeoutError as e:
                            raise TimeoutError(
                                f"AI call timed out after {timeout:.2f}s"
                            ) from e

                # Validate and extract response text using type guards
                result = self._validate_response_text(response)

                # Track token usage if available
                usage = self._extract_usage(response)
                if usage and self._track_usage:
                    self.total_input_tokens += usage.input_tokens
                    self.total_output_tokens += usage.output_tokens
                    self.call_count += 1
                    # Per-model accumulation with per-call cost
                    if model not in self.usage_by_model:
                        self.usage_by_model[model] = {
                            "input_tokens": 0, "output_tokens": 0,
                            "calls": 0, "cost": 0.0,
                        }
                    self.usage_by_model[model]["input_tokens"] += usage.input_tokens
                    self.usage_by_model[model]["output_tokens"] += usage.output_tokens
                    self.usage_by_model[model]["calls"] += 1
                    # Per-call tier-aware cost: prompt_token_count = input_tokens
                    from primr.config.models import PrimrModels
                    try:
                        call_cost = PrimrModels.calculate_cost(
                            model, usage.input_tokens, usage.output_tokens,
                            prompt_tokens=usage.input_tokens,
                        )
                    except KeyError:
                        call_cost = PrimrModels.calculate_active_pro_cost(
                            usage.input_tokens, usage.output_tokens
                        )
                    self.usage_by_model[model]["cost"] += call_cost
                    logger.debug(
                        f"Token usage: {usage.input_tokens:,} in / {usage.output_tokens:,} out"
                        f" (${call_cost:.4f})"
                    )

                logger.debug(f"AI response received: {len(result)} chars")
                return result

            except Exception as e:
                last_error = e
                if is_daily_quota_exhausted(e):
                    logger.error("Daily API quota exhausted - stopping immediately")
                    raise AIError(
                        "Daily API quota exhausted. Wait until quota resets or upgrade your plan. "
                        "Check status with: primr --check-quota",
                        model=model,
                        cause=e
                    ) from e

                # Check for invalid API key
                if is_invalid_api_key_error(e):
                    logger.error("Invalid API key - stopping immediately")
                    raise AIError(
                        "Invalid API key. Check your GEMINI_API_KEY in .env file.",
                        model=model,
                        cause=e
                    ) from e

                if is_timeout_error(e):
                    raise AIError(
                        str(e),
                        model=model,
                        cause=e,
                    ) from e

                logger.warning(
                    f"AI call failed (attempt {attempt + 1}/{retries}): {e}"
                )

                # Try fallback model if available
                fallback = self._get_fallback_model(model)
                if fallback and attempt < retries - 1:
                    logger.info(f"Trying fallback model: {fallback}")
                    model = fallback

                if attempt < retries - 1:
                    delay = calculate_retry_delay(attempt, is_rate_limited=is_rate_limit_error(e))
                    logger.debug(f"Retrying in {delay}s...")
                    time.sleep(delay)

        error_msg = f"AI call failed after {retries} attempts: {last_error}"
        logger.error(error_msg)
        raise AIError(error_msg, model=model, cause=last_error)

    def generate_fast(
        self,
        prompt: str,
        model_type: str = "research"
    ) -> str:
        """
        Fast generation with minimal thinking.

        Use this for simple tasks like:
        - Link filtering
        - Simple classifications
        - Quick summaries

        Args:
            prompt: The prompt to send
            model_type: "research" or "report"

        Returns:
            Generated text response
        """
        return self.generate(
            prompt,
            model_type=model_type,
            thinking_level="low"
        )

    def generate_with_context(
        self,
        prompt: str,
        context: dict[str, Any],
        model_type: str = "research",
        **kwargs: Any
    ) -> str:
        """
        Generate with structured context.

        Args:
            prompt: The main prompt
            context: Dictionary of context variables to include
            model_type: "research" or "report"
            **kwargs: Additional arguments passed to generate()

        Returns:
            Generated text response
        """
        # Build context string
        context_parts = []
        for key, value in context.items():
            if value:
                context_parts.append(f"## {key}\n{value}")

        full_prompt = prompt
        if context_parts:
            full_prompt = f"{prompt}\n\n" + "\n\n".join(context_parts)

        return self.generate(full_prompt, model_type=model_type, **kwargs)

    def _get_model(self, model_type: str) -> str:
        """Get the model name for a given type.

        Model types (USE THESE):
            - "scraping": Flash - summarizing scraped content
            - "link_selection": Flash - intelligent link prioritization (which pages to scrape)
            - "fast": Flash - general quick tasks
            - "section_writing": Pro - writing report sections
            - "analysis": Pro - complex analysis
            - "reasoning": Pro - general reasoning tasks

        Legacy aliases (backward compatible):
            - "filtering" -> Flash (DEPRECATED - use link_selection)
            - "research" -> Flash (DEPRECATED - confusing name)
            - "report" -> Pro
            - "summarization" -> Flash
        """
        # Flash model tasks (cheap, fast)
        if model_type in ("scraping", "link_selection", "filtering", "fast", "research", "summarization"):
            return self._settings.flash_model
        # Pro model tasks (expensive, smart)
        elif model_type in ("section_writing", "analysis", "reasoning", "report"):
            return self._settings.pro_model
        else:
            logger.warning(f"Unknown model type '{model_type}', using flash model")
            return self._settings.flash_model

    def _get_fallback_model(self, current_model: str) -> str | None:
        """Get a fallback model if available."""
        fallbacks = self._settings.model_fallbacks.get(current_model, [])
        return fallbacks[0] if fallbacks else None

    def _extract_usage(self, response: Any) -> TokenUsage | None:
        """
        Extract token usage from API response with type validation.

        Uses type guards to validate the response structure before
        extracting token counts.

        Args:
            response: The Gemini API response object

        Returns:
            TokenUsage if available and valid, None otherwise
        """
        try:
            # Gemini API returns usage_metadata with token counts
            if not hasattr(response, 'usage_metadata') or response.usage_metadata is None:
                return None

            metadata = response.usage_metadata
            input_tokens = getattr(metadata, 'prompt_token_count', None)
            output_tokens = getattr(metadata, 'candidates_token_count', None)

            # Use type guards to validate token counts are integers
            if not is_valid_type(input_tokens, int) or not is_valid_type(output_tokens, int):
                logger.debug(
                    f"Invalid token count types: input={type(input_tokens)}, "
                    f"output={type(output_tokens)}"
                )
                return None

            # Validate non-negative values
            if input_tokens < 0 or output_tokens < 0:
                logger.debug(f"Negative token counts: {input_tokens}, {output_tokens}")
                return None

            return TokenUsage(input_tokens=int(input_tokens), output_tokens=int(output_tokens))

        except Exception as e:
            logger.debug(f"Could not extract usage metadata: {e}")
        return None

    def _validate_response_text(self, response: Any) -> str:
        """
        Validate and extract text from API response.

        Uses type guards to ensure the response has valid text content.

        Args:
            response: The Gemini API response object

        Returns:
            Validated response text

        Raises:
            AIError: If response text is invalid or empty
        """
        try:
            # Check response exists
            if response is None:
                raise AIError("API returned None response")

            # Check response has text attribute
            if not hasattr(response, 'text'):
                raise AIError("API response missing 'text' attribute")

            text = response.text

            # Handle None text
            if text is None:
                # Check if there are candidates with content
                if hasattr(response, 'candidates') and response.candidates:
                    for candidate in response.candidates:
                        if hasattr(candidate, 'content') and candidate.content:
                            if hasattr(candidate.content, 'parts') and candidate.content.parts:
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        text = part.text
                                        break
                        if text is not None:
                            break
                if text is None:
                    raise AIError("API response text is None and no candidates found")

            # Validate text is a string
            if not is_valid_type(text, str):
                raise AIError(
                    f"API response text is not a string: {type(text).__name__}"
                )

            result = str(text).strip()

            # Check for empty response
            if not result:
                raise AIError("API returned empty response text")

            return result

        except AIError:
            raise
        except Exception as e:
            raise AIError(f"Failed to extract response text: {e}", cause=e) from e

    def get_usage_summary(self) -> dict[str, Any]:
        """
        Get a summary of token usage for this client instance.

        Uses per-call accumulated costs when available (tier-aware),
        otherwise falls back to Pro pricing (conservative estimate).

        Returns:
            Dict with usage statistics and estimated cost
        """
        from primr.config.models import PrimrModels

        if self.usage_by_model:
            total_cost = 0.0
            input_cost = 0.0
            output_cost = 0.0
            for model_name, counts in self.usage_by_model.items():
                in_tok = int(counts["input_tokens"])
                out_tok = int(counts["output_tokens"])
                # Use pre-calculated per-call cost (tier-aware) if available
                if "cost" in counts and counts["cost"] > 0:
                    total_cost += counts["cost"]
                else:
                    # Backward compat: no per-call cost, recalculate
                    try:
                        model_cost = PrimrModels.calculate_cost(
                            model_name, in_tok, out_tok
                        )
                    except KeyError:
                        model_cost = PrimrModels.calculate_active_pro_cost(
                            in_tok, out_tok
                        )
                    total_cost += model_cost
                # Input/output cost breakdown (standard tier, for display)
                try:
                    inp_price, out_price = PrimrModels.get_price(model_name)
                except KeyError:
                    active_pro = PrimrModels.get_active_pro_model()
                    inp_price = active_pro.cost_per_1m_input_tokens
                    out_price = active_pro.cost_per_1m_output_tokens
                input_cost += (in_tok / 1_000_000) * inp_price
                output_cost += (out_tok / 1_000_000) * out_price
        else:
            # Fallback to active Pro model pricing (conservative)
            active_pro = PrimrModels.get_active_pro_model()
            inp_price = active_pro.cost_per_1m_input_tokens
            out_price = active_pro.cost_per_1m_output_tokens
            input_cost = (self.total_input_tokens / 1_000_000) * inp_price
            output_cost = (self.total_output_tokens / 1_000_000) * out_price
            total_cost = input_cost + output_cost

        return {
            "call_count": self.call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
        }

    def reset_usage(self) -> None:
        """Reset usage counters."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0
        self.usage_by_model = {}


# =============================================================================
# SINGLETON ACCESS (Thread-Safe)
# =============================================================================

import threading

_client: AIClient | None = None
_client_lock = threading.Lock()


def get_client() -> AIClient:
    """
    Get the global AI client instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety
    while minimizing lock contention.

    Returns:
        AIClient instance
    """
    global _client
    if _client is None:
        with _client_lock:
            # Double-check after acquiring lock
            if _client is None:
                _client = AIClient()
    return _client


def reset_client() -> None:
    """Reset the global AI client (useful for testing)."""
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
        _client = None


# =============================================================================
# BACKWARD COMPATIBLE FUNCTIONS
# =============================================================================

def llm(
    prompt: str,
    model_type: str = "research",
    temperature: float = 1.0,
    thinking_level: str = "high",
    streaming: bool = False,  # Kept for compatibility, not used
    **kwargs: Any
) -> str:
    """
    Backward-compatible LLM function.

    This function maintains compatibility with existing code while
    using the new AIClient internally.

    Args:
        prompt: The prompt to send
        model_type: "research" or "report"
        temperature: Sampling temperature
        thinking_level: "low" or "high"
        streaming: Ignored (kept for compatibility)
        **kwargs: Additional arguments

    Returns:
        Generated text response
    """
    return get_client().generate(
        prompt,
        model_type=model_type,
        temperature=temperature,
        thinking_level=thinking_level,
        **kwargs
    )


def llm_fast(prompt: str, model_type: str = "research") -> str:
    """
    Backward-compatible fast LLM function.

    Args:
        prompt: The prompt to send
        model_type: "research" or "report"

    Returns:
        Generated text response
    """
    return get_client().generate_fast(prompt, model_type=model_type)
