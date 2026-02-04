"""
Retry manager with exponential backoff and jitter.

This module provides the RetryManager class for managing retry logic
with configurable backoff behavior.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from primr.utils.errors.base import RetryConfig, calculate_backoff_delay

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryManager:
    """
    Manages retry logic with exponential backoff and jitter.

    Provides both sync and async execution with configurable retry behavior,
    callbacks for retry events, and detailed tracking.

    Example:
        manager = RetryManager(RetryConfig(max_retries=3))

        # Sync usage
        result = manager.execute_sync(lambda: risky_operation())

        # Async usage
        result = await manager.execute(async_risky_operation)

        # With retry callback
        def on_retry(attempt, error):
            print(f"Retry {attempt}: {error}")
        result = manager.execute_sync(operation, on_retry=on_retry)
    """

    def __init__(
        self,
        config: RetryConfig | None = None,
        retryable_exceptions: tuple[type[Exception], ...] = (
            ConnectionError,
            TimeoutError,
            OSError,
        )
    ):
        """
        Initialize RetryManager.

        Args:
            config: Retry configuration (uses defaults if None)
            retryable_exceptions: Exception types that trigger retry
        """
        self.config = config or RetryConfig()
        self.retryable_exceptions = retryable_exceptions
        self._last_attempt_count = 0
        self._last_total_delay = 0.0

    @property
    def last_attempt_count(self) -> int:
        """Number of attempts in last execution."""
        return self._last_attempt_count

    @property
    def last_total_delay(self) -> float:
        """Total delay time in last execution (seconds)."""
        return self._last_total_delay

    async def execute(
        self,
        operation: Callable[[], Any],
        on_retry: Callable[[int, Exception], None] | None = None
    ) -> Any:
        """
        Execute async operation with retry logic.

        Args:
            operation: Async callable to execute
            on_retry: Optional callback called on each retry (attempt, error)

        Returns:
            Result of successful operation

        Raises:
            Last exception if all retries exhausted
        """
        import asyncio

        self._last_attempt_count = 0
        self._last_total_delay = 0.0
        last_exception: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            self._last_attempt_count = attempt + 1
            try:
                # Handle both sync and async callables
                result = operation()
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = calculate_backoff_delay(attempt, self.config)
                    self._last_total_delay += delay

                    if on_retry:
                        try:
                            on_retry(attempt + 1, e)
                        except Exception:
                            pass  # Don't let callback errors affect retry

                    logger.warning(
                        f"Retry {attempt + 1}/{self.config.max_retries}: {e} "
                        f"(waiting {delay:.2f}s)"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All {self.config.max_retries} retries exhausted: {e}"
                    )

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Unexpected state: no exception captured")

    def execute_sync(
        self,
        operation: Callable[[], T],
        on_retry: Callable[[int, Exception], None] | None = None
    ) -> T:
        """
        Execute sync operation with retry logic.

        Args:
            operation: Callable to execute
            on_retry: Optional callback called on each retry (attempt, error)

        Returns:
            Result of successful operation

        Raises:
            Last exception if all retries exhausted
        """
        import time

        self._last_attempt_count = 0
        self._last_total_delay = 0.0
        last_exception: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            self._last_attempt_count = attempt + 1
            try:
                return operation()
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = calculate_backoff_delay(attempt, self.config)
                    self._last_total_delay += delay

                    if on_retry:
                        try:
                            on_retry(attempt + 1, e)
                        except Exception:
                            pass  # Don't let callback errors affect retry

                    logger.warning(
                        f"Retry {attempt + 1}/{self.config.max_retries}: {e} "
                        f"(waiting {delay:.2f}s)"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"All {self.config.max_retries} retries exhausted: {e}"
                    )

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Unexpected state: no exception captured")
