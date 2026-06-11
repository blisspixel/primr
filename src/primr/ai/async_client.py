"""
Async AI client for parallel LLM operations.

This module provides:
- Async AI client for concurrent requests
- Batch processing for multiple prompts
- Semaphore-based concurrency control
- Compatible with the sync AIClient interface
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from primr.ai.genai_factory import default_genai_http_options

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
    is_timeout_error,
)
from primr.config.settings import get_settings
from primr.utils.errors import AIError, calculate_retry_delay, is_rate_limit_error
from primr.utils.logging_config import get_logger

logger = get_logger("ai.async_client")

T = TypeVar("T")


def _require_genai_dependency() -> None:
    """Raise a clear error when google.genai is unavailable."""
    if _GENAI_IMPORT_ERROR is None:
        return
    # Allow tests or callers to inject/patch a working client implementation.
    if (
        _FALLBACK_CLIENT_CLASS is not None
        and getattr(genai, "Client", None) is not _FALLBACK_CLIENT_CLASS
    ):
        return
    raise AIError(
        "google.genai is not available. Install compatible dependencies "
        "(Python 3.11+ and project requirements).",
        cause=_GENAI_IMPORT_ERROR,
    ) from _GENAI_IMPORT_ERROR


@dataclass
class BatchResult:
    """Result of a batch AI operation."""

    prompt: str
    response: str | None = None
    error: Exception | None = None
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        """Whether the request succeeded."""
        return self.error is None and self.response is not None


@dataclass
class BatchStats:
    """Statistics for a batch operation."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    total_duration_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage."""
        return (self.succeeded / self.total * 100) if self.total > 0 else 0.0

    @property
    def avg_duration_ms(self) -> float:
        """Average duration per request."""
        return self.total_duration_ms / self.total if self.total > 0 else 0.0


class AsyncAIClient:
    """
    Async AI client for parallel LLM operations.

    Example:
        async with AsyncAIClient() as client:
            response = await client.generate("What is Python?")

            # Batch processing
            results = await client.generate_batch([
                "Summarize company A",
                "Summarize company B",
                "Summarize company C",
            ])
    """

    def __init__(
        self,
        api_key: str | None = None,
        max_concurrent: int = 5,
    ):
        """
        Initialize the async AI client.

        Args:
            api_key: Optional API key override
            max_concurrent: Maximum concurrent requests
        """
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client: genai.Client | None = None
        self._settings = settings.ai
        self._max_concurrent = max_concurrent
        self._semaphore: asyncio.Semaphore | None = None
        logger.debug(f"Async AI client initialized (max_concurrent={max_concurrent})")

    async def __aenter__(self) -> "AsyncAIClient":
        """Async context manager entry."""
        _require_genai_dependency()
        self._client = genai.Client(
            api_key=self._api_key, http_options=default_genai_http_options()
        )
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.aclose()

    async def aclose(self) -> None:
        """Best-effort close of underlying client resources."""
        if self._client is not None:
            aclose_fn = getattr(self._client, "aclose", None)
            close_fn = getattr(self._client, "close", None)

            try:
                if callable(aclose_fn):
                    result = aclose_fn()
                    if asyncio.iscoroutine(result):
                        await result
                elif callable(close_fn):
                    close_fn()
            except Exception as e:
                logger.warning("Failed to close async AI client: %s", e)

        self._client = None
        self._semaphore = None

    def _ensure_initialized(self) -> None:
        """Ensure client is initialized."""
        _require_genai_dependency()
        if self._client is None:
            self._client = genai.Client(
                api_key=self._api_key, http_options=default_genai_http_options()
            )
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)

    async def generate(
        self,
        prompt: str,
        model_type: str = "research",
        temperature: float = 1.0,
        thinking_level: str = "high",
        max_retries: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """
        Generate content asynchronously.

        Args:
            prompt: The prompt to send
            model_type: "research" or "report"
            temperature: Sampling temperature
            thinking_level: "low" or "high"
            max_retries: Override default retry count
            timeout: Request timeout in seconds (across retries)

        Returns:
            Generated text response

        Raises:
            AIError: If all retries fail
        """
        self._ensure_initialized()

        model = self._get_model(model_type)
        retries = max_retries if max_retries is not None else self._settings.max_retries

        config = types.GenerateContentConfig(
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level),  # type: ignore[arg-type]
        )

        last_error = None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout if timeout is not None else None

        async with self._semaphore:  # type: ignore
            for attempt in range(retries):
                try:
                    logger.debug(f"Async AI call attempt {attempt + 1}/{retries}")

                    # Run sync call in thread pool
                    request = loop.run_in_executor(
                        None,
                        lambda: self._client.models.generate_content(  # type: ignore
                            model=model, contents=prompt, config=config
                        ),
                    )
                    if deadline is None:
                        response = await request
                    else:
                        remaining = deadline - loop.time()
                        if remaining <= 0:
                            raise TimeoutError(f"AI call timed out after {timeout:.2f}s")
                        try:
                            response = await asyncio.wait_for(request, timeout=remaining)
                        except Exception as e:
                            is_asyncio_timeout = (
                                e.__class__.__name__ == "TimeoutError"
                                and e.__class__.__module__.startswith("asyncio")
                            )
                            if not (isinstance(e, TimeoutError) or is_asyncio_timeout):
                                raise
                            raise TimeoutError(f"AI call timed out after {timeout:.2f}s") from e

                    result = (response.text or "").strip()
                    logger.debug(f"Async AI response: {len(result)} chars")
                    return result

                except Exception as e:
                    last_error = e
                    if is_daily_quota_exhausted(e):
                        logger.error("Daily API quota exhausted - stopping immediately")
                        raise AIError(
                            "Daily API quota exhausted. Wait until quota resets or upgrade your plan. "
                            "Check status with: primr --check-quota",
                            cause=e,
                        ) from e

                    if is_timeout_error(e):
                        raise AIError(str(e), cause=e) from e

                    logger.warning(f"Async AI call failed (attempt {attempt + 1}): {e}")

                    if attempt < retries - 1:
                        delay = calculate_retry_delay(
                            attempt, is_rate_limited=is_rate_limit_error(e)
                        )
                        await asyncio.sleep(delay)

        raise AIError(f"Async AI call failed after {retries} attempts", cause=last_error)

    async def generate_fast(self, prompt: str, model_type: str = "research") -> str:
        """Fast generation with minimal thinking."""
        return await self.generate(prompt, model_type=model_type, thinking_level="low")

    async def generate_batch(
        self,
        prompts: list[str],
        model_type: str = "research",
        temperature: float = 1.0,
        thinking_level: str = "high",
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[BatchResult]:
        """
        Generate responses for multiple prompts in parallel.

        Args:
            prompts: List of prompts to process
            model_type: "research" or "report"
            temperature: Sampling temperature
            thinking_level: "low" or "high"
            on_progress: Optional callback(completed, total)

        Returns:
            List of BatchResult objects
        """
        import time

        self._ensure_initialized()
        completed = 0

        async def process_one(prompt: str) -> BatchResult:
            nonlocal completed
            start = time.perf_counter()

            try:
                response = await self.generate(
                    prompt,
                    model_type=model_type,
                    temperature=temperature,
                    thinking_level=thinking_level,
                )
                duration = (time.perf_counter() - start) * 1000
                result = BatchResult(prompt=prompt, response=response, duration_ms=duration)
            except Exception as e:
                duration = (time.perf_counter() - start) * 1000
                result = BatchResult(prompt=prompt, error=e, duration_ms=duration)

            completed += 1
            if on_progress:
                on_progress(completed, len(prompts))

            return result

        tasks = [process_one(p) for p in prompts]
        results = await asyncio.gather(*tasks)

        return list(results)

    async def generate_batch_with_context(
        self,
        items: list[dict[str, Any]],
        prompt_template: str,
        model_type: str = "research",
        **kwargs: Any,
    ) -> list[BatchResult]:
        """
        Generate responses for items using a template.

        Args:
            items: List of context dictionaries
            prompt_template: Template string with {key} placeholders
            model_type: "research" or "report"
            **kwargs: Additional arguments for generate_batch

        Returns:
            List of BatchResult objects
        """
        prompts = [prompt_template.format(**item) for item in items]
        return await self.generate_batch(prompts, model_type=model_type, **kwargs)

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
        if model_type in (
            "scraping",
            "link_selection",
            "filtering",
            "fast",
            "research",
            "summarization",
        ):
            return self._settings.flash_model
        # Pro model tasks (expensive, smart)
        elif model_type in ("section_writing", "analysis", "reasoning", "report"):
            return self._settings.pro_model
        else:
            return self._settings.flash_model


def get_batch_stats(results: list[BatchResult]) -> BatchStats:
    """
    Calculate statistics for batch results.

    Args:
        results: List of BatchResult objects

    Returns:
        BatchStats with aggregated metrics
    """
    stats = BatchStats(total=len(results))

    for r in results:
        if r.success:
            stats.succeeded += 1
        else:
            stats.failed += 1
        stats.total_duration_ms += r.duration_ms

    return stats


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


async def generate_parallel(
    prompts: list[str], model_type: str = "research", max_concurrent: int = 5, **kwargs: Any
) -> list[BatchResult]:
    """
    Generate responses for multiple prompts in parallel.

    Convenience function that creates a client and processes prompts.

    Args:
        prompts: List of prompts to process
        model_type: "research" or "report"
        max_concurrent: Maximum concurrent requests
        **kwargs: Additional arguments for generate_batch

    Returns:
        List of BatchResult objects
    """
    async with AsyncAIClient(max_concurrent=max_concurrent) as client:
        return await client.generate_batch(prompts, model_type=model_type, **kwargs)


def run_parallel(
    prompts: list[str], model_type: str = "research", max_concurrent: int = 5, **kwargs: Any
) -> list[BatchResult]:
    """
    Synchronous wrapper for parallel generation.

    Use this when you need parallel AI calls from sync code.

    Args:
        prompts: List of prompts to process
        model_type: "research" or "report"
        max_concurrent: Maximum concurrent requests
        **kwargs: Additional arguments

    Returns:
        List of BatchResult objects
    """
    return asyncio.run(
        generate_parallel(prompts, model_type=model_type, max_concurrent=max_concurrent, **kwargs)
    )
