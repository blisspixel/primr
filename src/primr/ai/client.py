"""
Unified AI client for all LLM operations.

This module provides:
- Single AI client with consistent interface
- Automatic retry with exponential backoff
- Model fallback support
- Proper error handling and logging
- Token usage tracking for cost monitoring
"""

import time
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

from primr.config.settings import get_settings
from primr.utils.errors import AIError
from primr.utils.logging_config import get_logger
from primr.utils.type_guards import is_valid_type

logger = get_logger("ai.client")


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
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client = genai.Client(api_key=self._api_key)
        self._settings = settings.ai
        self._track_usage = track_usage

        # Token usage tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0

        logger.debug("AI client initialized")

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
        retries = max_retries or self._settings.max_retries

        config = types.GenerateContentConfig(
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level)  # type: ignore[arg-type]
        )

        last_error = None
        for attempt in range(retries):
            try:
                logger.debug(f"AI call attempt {attempt + 1}/{retries} to {model}")

                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )

                # Validate and extract response text using type guards
                result = self._validate_response_text(response)

                # Track token usage if available
                usage = self._extract_usage(response)
                if usage and self._track_usage:
                    self.total_input_tokens += usage.input_tokens
                    self.total_output_tokens += usage.output_tokens
                    self.call_count += 1
                    logger.debug(
                        f"Token usage: {usage.input_tokens:,} in / {usage.output_tokens:,} out"
                    )

                logger.debug(f"AI response received: {len(result)} chars")
                return result

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check for quota exhaustion (daily limit hit) - STOP IMMEDIATELY
                # Multiple patterns to catch various API error formats
                quota_patterns = [
                    "resource_exhausted" in error_str and "per_day" in error_str,
                    "resource_exhausted" in error_str and "quota" in error_str,
                    "quota exceeded" in error_str,
                    "daily limit" in error_str,
                    "rate limit exceeded" in error_str and "daily" in error_str,
                    "requests per day" in error_str,
                ]
                is_quota_exhausted = any(quota_patterns)

                if is_quota_exhausted:
                    logger.error("Daily API quota exhausted - stopping immediately")
                    raise AIError(
                        "Daily API quota exhausted. Wait until quota resets or upgrade your plan. "
                        "Check status with: primr --check-quota",
                        model=model,
                        cause=e
                    ) from e

                # Check for invalid API key
                if "invalid" in error_str and ("api" in error_str or "key" in error_str):
                    logger.error("Invalid API key - stopping immediately")
                    raise AIError(
                        "Invalid API key. Check your GEMINI_API_KEY in .env file.",
                        model=model,
                        cause=e
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
                    # Use longer backoff for rate limits
                    if "429" in str(e) or "resource_exhausted" in error_str:
                        delay = min(2 ** attempt * 5, 60)  # 5s, 10s, 20s, max 60s
                    else:
                        delay = 2 ** attempt  # 1s, 2s, 4s
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

            # Validate non-negative values (input_tokens and output_tokens are validated as int above)
            if input_tokens is None or output_tokens is None:
                return None
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

        Returns:
            Dict with usage statistics and estimated cost
        """
        # Pricing constants (per 1M tokens) - Gemini API
        # These are the canonical values; settings.pricing is for configuration
        INPUT_PRICE = 2.00
        OUTPUT_PRICE = 12.00

        input_cost = (self.total_input_tokens / 1_000_000) * INPUT_PRICE
        output_cost = (self.total_output_tokens / 1_000_000) * OUTPUT_PRICE
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
