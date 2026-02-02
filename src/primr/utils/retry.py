"""
Retry Policy Manager for automatic retry handling.

This module provides:
- RetryPolicy dataclass for configuring retry behavior
- RetryAttempt dataclass for tracking retry attempts
- RetryPolicyManager class for managing retry logic based on error classification

The retry policy manager integrates with the typed error hierarchy to provide
automatic retry decisions based on error type, with support for exponential
backoff, jitter, and error-specific retry delays.

**Feature: phd-level-excellence**
**Validates: Requirements 2.1-2.8**
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, ParamSpec, TypeVar

from primr.utils.errors import (
    PrimrError,
    TransientError,
    QuotaError,
)

logger = logging.getLogger(__name__)

P = ParamSpec('P')
T = TypeVar('T')


# =============================================================================
# RETRY POLICY CONFIGURATION
# =============================================================================

@dataclass
class RetryPolicy:
    """
    Configuration for retry behavior.
    
    This dataclass defines the parameters that control how retries are performed,
    including the maximum number of retries, delay calculations, and which error
    categories are eligible for retry.
    
    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries, just initial attempt)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay cap in seconds
        exponential_base: Base for exponential growth (typically 2.0)
        jitter_factor: Random jitter as fraction of delay (0.0-1.0)
        retryable_categories: Set of error categories that are eligible for retry
    
    Example:
        policy = RetryPolicy(
            max_retries=3,
            base_delay=1.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter_factor=0.1,
            retryable_categories={"transient", "rate_limit", "network"}
        )
    
    **Validates: Requirements 2.6**
    """
    
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter_factor: float = 0.1
    retryable_categories: set[str] = field(default_factory=lambda: {
        "transient", "rate_limit", "quota", "network"
    })
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.base_delay <= 0:
            raise ValueError("base_delay must be positive")
        if self.max_delay <= 0:
            raise ValueError("max_delay must be positive")
        if self.exponential_base <= 1:
            raise ValueError("exponential_base must be greater than 1")
        if not 0 <= self.jitter_factor <= 1:
            raise ValueError("jitter_factor must be between 0 and 1")


# =============================================================================
# RETRY ATTEMPT TRACKING
# =============================================================================

@dataclass
class RetryAttempt:
    """
    Record of a single retry attempt.
    
    This dataclass captures information about each retry attempt for
    tracking and debugging purposes.
    
    Attributes:
        attempt_number: The attempt number (0-indexed)
        error: The error that triggered the retry
        delay_seconds: The delay before the next retry
        timestamp: When the attempt occurred
    
    **Validates: Requirements 2.8**
    """
    
    attempt_number: int
    error: PrimrError
    delay_seconds: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "attempt": self.attempt_number,
            "error": str(self.error),
            "error_type": type(self.error).__name__,
            "delay": self.delay_seconds,
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# TELEMETRY PROTOCOL (Optional Dependency)
# =============================================================================

class TelemetryProtocol:
    """
    Protocol for telemetry system integration.
    
    This is a minimal interface that allows the RetryPolicyManager to emit
    metrics without requiring a hard dependency on the telemetry module.
    """
    
    def emit_metric(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None
    ) -> None:
        """Emit a metric with optional tags."""
        pass


# =============================================================================
# RETRY POLICY MANAGER
# =============================================================================

class RetryPolicyManager:
    """
    Manages retry logic based on error classification.
    
    The RetryPolicyManager determines whether an error should be retried,
    calculates appropriate delays, and executes operations with automatic
    retry handling. It integrates with the typed error hierarchy to make
    intelligent retry decisions.
    
    Key features:
    - Retry eligibility based on error type hierarchy
    - Exponential backoff with jitter
    - Respect for error-specific retry_after values
    - Retry history tracking and attachment to final errors
    - Optional telemetry integration for metrics
    
    Example:
        policy = RetryPolicy(max_retries=3)
        manager = RetryPolicyManager(policy)
        
        # Check if error should be retried
        if manager.should_retry(error, attempt=1):
            delay = manager.get_delay(error, attempt=1)
            await asyncio.sleep(delay)
        
        # Or use automatic retry execution
        result = await manager.execute_with_retry(async_operation)
    
    **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
    """
    
    def __init__(
        self,
        policy: RetryPolicy | None = None,
        telemetry: TelemetryProtocol | None = None
    ):
        """
        Initialize RetryPolicyManager.
        
        Args:
            policy: Retry configuration (uses defaults if None)
            telemetry: Optional telemetry system for metrics emission
        """
        self.policy = policy or RetryPolicy()
        self.telemetry = telemetry
        self._attempts: list[RetryAttempt] = []
    
    @property
    def attempts(self) -> list[RetryAttempt]:
        """Get the list of retry attempts from the last execution."""
        return self._attempts.copy()
    
    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        Determine if an error should be retried.
        
        An error is eligible for retry if:
        1. It is a PrimrError (or subclass)
        2. It has recoverable=True
        3. Its category is in the retryable_categories set
        4. The attempt count is below max_retries
        
        Args:
            error: The exception that occurred
            attempt: Current attempt number (0-indexed)
        
        Returns:
            True if the error should be retried, False otherwise
        
        Example:
            if manager.should_retry(error, attempt=1):
                # Retry the operation
                pass
        
        **Validates: Requirements 2.1, 2.2, 2.3**
        """
        # Must be a PrimrError
        if not isinstance(error, PrimrError):
            return False
        
        # Must be recoverable
        if not error.recoverable:
            return False
        
        # Category must be in retryable set
        if error.category not in self.policy.retryable_categories:
            return False
        
        # Must not exceed max retries
        return attempt < self.policy.max_retries
    
    def get_delay(self, error: Exception, attempt: int) -> float:
        """
        Calculate delay before next retry.
        
        The delay is determined by:
        1. For RateLimitError: Use retry_after_seconds if set
        2. For QuotaError: Calculate time to quota_reset_time if set
        3. Otherwise: Use exponential backoff with jitter
        
        Args:
            error: The exception that occurred
            attempt: Current attempt number (0-indexed)
        
        Returns:
            Delay in seconds before the next retry (always >= 0)
        
        Example:
            delay = manager.get_delay(error, attempt=1)
            await asyncio.sleep(delay)
        
        **Validates: Requirements 2.4, 2.5**
        """
        # Check for error-specific retry_after
        if isinstance(error, PrimrError) and error.retry_after is not None:
            return max(0.0, error.retry_after)
        
        # For QuotaError, calculate time to reset
        if isinstance(error, QuotaError) and error.quota_reset_time is not None:
            delta = (error.quota_reset_time - datetime.now()).total_seconds()
            return max(0.0, delta)
        
        # Calculate exponential backoff with jitter
        delay = self.policy.base_delay * (self.policy.exponential_base ** attempt)
        delay = min(delay, self.policy.max_delay)
        
        # Add jitter: random value in range [-jitter, +jitter]
        jitter_range = delay * self.policy.jitter_factor
        jitter = random.uniform(-jitter_range, jitter_range)
        
        return max(0.0, delay + jitter)
    
    def _record_attempt(
        self,
        attempt: int,
        error: PrimrError,
        delay: float
    ) -> None:
        """
        Record a retry attempt for history tracking.
        
        Args:
            attempt: The attempt number
            error: The error that triggered the retry
            delay: The delay before the next retry
        
        **Validates: Requirements 2.8**
        """
        record = RetryAttempt(
            attempt_number=attempt,
            error=error,
            delay_seconds=delay,
        )
        self._attempts.append(record)
    
    def _emit_retry_metric(
        self,
        error: PrimrError,
        attempt: int,
        delay: float
    ) -> None:
        """
        Emit metrics for a retry attempt.
        
        Args:
            error: The error that triggered the retry
            attempt: The attempt number
            delay: The delay before the next retry
        
        **Validates: Requirements 2.7**
        """
        if self.telemetry is None:
            return
        
        try:
            self.telemetry.emit_metric(
                name="retry_attempt",
                value=1.0,
                tags={
                    "error_type": type(error).__name__,
                    "error_category": error.category,
                    "attempt": str(attempt),
                    "delay_seconds": f"{delay:.2f}",
                }
            )
        except Exception as e:
            # Don't let telemetry errors affect retry logic
            logger.debug(f"Failed to emit retry metric: {e}")
    
    def _attach_retry_history(self, error: PrimrError) -> None:
        """
        Attach retry history to the final error's context.
        
        Args:
            error: The error to attach history to
        
        **Validates: Requirements 2.8**
        """
        if self._attempts:
            error.context["retry_history"] = [
                attempt.to_dict() for attempt in self._attempts
            ]
    
    async def execute_with_retry(
        self,
        operation: Callable[..., T],
        *args: Any,
        **kwargs: Any
    ) -> T:
        """
        Execute operation with automatic retry on transient errors.
        
        This method executes the given operation and automatically retries
        on transient errors according to the retry policy. It handles both
        sync and async operations.
        
        Args:
            operation: The callable to execute (sync or async)
            *args: Positional arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation
        
        Returns:
            The result of the successful operation
        
        Raises:
            The last error if all retries are exhausted, with retry_history
            attached to the error's context
        
        Example:
            async def fetch_data():
                return await api.get("/data")
            
            result = await manager.execute_with_retry(fetch_data)
        
        **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.8**
        """
        self._attempts = []
        last_error: Exception | None = None
        
        for attempt in range(self.policy.max_retries + 1):
            try:
                result = operation(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            except PrimrError as e:
                last_error = e
                
                if not self.should_retry(e, attempt):
                    # Not retryable or max retries reached
                    self._attach_retry_history(e)
                    raise
                
                delay = self.get_delay(e, attempt)
                self._record_attempt(attempt, e, delay)
                self._emit_retry_metric(e, attempt, delay)
                
                logger.warning(
                    f"Retry {attempt + 1}/{self.policy.max_retries}: "
                    f"{type(e).__name__}: {e} (waiting {delay:.2f}s)"
                )
                
                await asyncio.sleep(delay)
            except Exception as e:
                # Non-PrimrError exceptions are not retried
                last_error = e
                raise
        
        # All retries exhausted
        if last_error is not None:
            if isinstance(last_error, PrimrError):
                self._attach_retry_history(last_error)
            raise last_error
        
        raise RuntimeError("Unexpected state: no exception captured")
    
    def execute_with_retry_sync(
        self,
        operation: Callable[..., T],
        *args: Any,
        **kwargs: Any
    ) -> T:
        """
        Execute operation with automatic retry on transient errors (sync version).
        
        This is the synchronous version of execute_with_retry for use in
        non-async contexts.
        
        Args:
            operation: The callable to execute
            *args: Positional arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation
        
        Returns:
            The result of the successful operation
        
        Raises:
            The last error if all retries are exhausted, with retry_history
            attached to the error's context
        
        Example:
            def fetch_data():
                return api.get("/data")
            
            result = manager.execute_with_retry_sync(fetch_data)
        """
        import time
        
        self._attempts = []
        last_error: Exception | None = None
        
        for attempt in range(self.policy.max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except PrimrError as e:
                last_error = e
                
                if not self.should_retry(e, attempt):
                    self._attach_retry_history(e)
                    raise
                
                delay = self.get_delay(e, attempt)
                self._record_attempt(attempt, e, delay)
                self._emit_retry_metric(e, attempt, delay)
                
                logger.warning(
                    f"Retry {attempt + 1}/{self.policy.max_retries}: "
                    f"{type(e).__name__}: {e} (waiting {delay:.2f}s)"
                )
                
                time.sleep(delay)
            except Exception as e:
                last_error = e
                raise
        
        if last_error is not None:
            if isinstance(last_error, PrimrError):
                self._attach_retry_history(last_error)
            raise last_error
        
        raise RuntimeError("Unexpected state: no exception captured")
