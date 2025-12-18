"""
Observability utilities for logging, metrics, and tracing.

This module provides:
- Correlation IDs for request tracing
- Correlation context for structured logging
- Structured logging with JSON output mode
- Metrics collection and emission
- Job summary logging
- Timing decorators

Example:
    from primr.utils.observability import (
        correlation_scope, log_structured, emit_metrics, JobSummary
    )

    with correlation_scope("research") as ctx:
        log_structured("info", "Starting research", company="Tesla")
        result = perform_research()

    summary = JobSummary(
        correlation_id=ctx.correlation_id,
        company="Tesla",
        mode="deep",
        duration_seconds=120.5,
        api_calls=15,
        total_tokens=50000,
        sections_generated=8
    )
    log_job_summary(summary)

    @timed
    def slow_function():
        ...
"""

import functools
import json
import logging
import sys
import threading
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Global flag for JSON output mode
_json_output_mode = False


# =============================================================================
# JSON OUTPUT MODE
# =============================================================================


def set_json_output_mode(enabled: bool) -> None:
    """
    Enable or disable JSON output mode for structured logging.

    When enabled, log_structured outputs JSON to stdout instead of
    using the standard logger.

    Args:
        enabled: True to enable JSON mode, False for standard logging
    """
    global _json_output_mode
    _json_output_mode = enabled


def is_json_output_mode() -> bool:
    """Check if JSON output mode is enabled."""
    return _json_output_mode


# =============================================================================
# CORRELATION ID MANAGEMENT
# =============================================================================

# Thread-local storage for correlation context
_context_var = threading.local()


def get_correlation_id() -> str:
    """
    Get the current correlation ID or generate a new one.

    Returns:
        8-character correlation ID string
    """
    ctx: Any = getattr(_context_var, "context", None)
    if ctx is not None and hasattr(ctx, "correlation_id"):
        correlation_id: str = ctx.correlation_id
        return correlation_id
    return str(uuid.uuid4())[:8]


def set_correlation_id(correlation_id: str) -> None:
    """
    Set the correlation ID for the current thread.

    Args:
        correlation_id: The correlation ID to set
    """
    ctx = getattr(_context_var, "context", None)
    if ctx is not None:
        ctx.correlation_id = correlation_id


def get_current_context() -> "CorrelationContext | None":
    """
    Get the current correlation context if one exists.

    Returns:
        Current CorrelationContext or None if not in a scope
    """
    return getattr(_context_var, "context", None)


# =============================================================================
# CORRELATION CONTEXT
# =============================================================================


@dataclass
class CorrelationContext:
    """
    Thread-local correlation context for tracing operations.

    Provides correlation ID tracking across related operations,
    timing information, and metadata storage.

    Attributes:
        correlation_id: Unique ID for tracing related operations
        operation_name: Name of the operation (also accessible as 'operation')
        start_time: When the operation started (epoch seconds)
        metadata: Additional context data
    """

    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    operation_name: str = ""
    start_time: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Backward compatibility alias
    @property
    def operation(self) -> str:
        """Alias for operation_name for backward compatibility."""
        return self.operation_name

    @classmethod
    def create(cls, operation: str, **metadata: Any) -> "CorrelationContext":
        """
        Create new context with generated correlation ID.

        Args:
            operation: Name of the operation
            **metadata: Additional context data

        Returns:
            New CorrelationContext instance
        """
        return cls(
            correlation_id=str(uuid.uuid4())[:8],
            operation_name=operation,
            start_time=time.time(),
            metadata=metadata,
        )

    @property
    def duration_seconds(self) -> float:
        """Get duration since start in seconds."""
        return time.time() - self.start_time

    @property
    def start_datetime(self) -> datetime:
        """Get start time as datetime."""
        return datetime.fromtimestamp(self.start_time)


# Alias for backward compatibility
OperationContext = CorrelationContext


@contextmanager
def correlation_scope(
    operation: str, **metadata: Any
) -> Generator[CorrelationContext, None, None]:
    """
    Context manager for correlation tracking.

    Creates a correlation context that is accessible via get_correlation_id()
    and get_current_context() within the scope.

    Args:
        operation: Name of the operation
        **metadata: Additional context to include

    Yields:
        CorrelationContext with correlation ID and timing info

    Example:
        with correlation_scope("research", company="Tesla") as ctx:
            log_structured("info", "Starting", company="Tesla")
            perform_research()
            log_structured("info", "Done", duration=ctx.duration_seconds)
    """
    ctx = CorrelationContext.create(operation, **metadata)

    # Store in thread-local
    old_context = getattr(_context_var, "context", None)
    _context_var.context = ctx

    # Log entry
    log_structured(
        "debug",
        f"Starting operation '{operation}'",
        **metadata,
    )

    try:
        yield ctx

        # Log success
        log_structured(
            "debug",
            f"Operation '{operation}' completed",
            duration_seconds=round(ctx.duration_seconds, 3),
        )

    except Exception as e:
        # Log error
        log_structured(
            "error",
            f"Operation '{operation}' failed",
            error=str(e),
            error_type=type(e).__name__,
            duration_seconds=round(ctx.duration_seconds, 3),
        )
        raise

    finally:
        # Restore previous context
        _context_var.context = old_context


@contextmanager
def operation_context(
    operation: str, **metadata: Any
) -> Generator[CorrelationContext, None, None]:
    """
    Context manager for tracking operations with correlation IDs.

    This is an alias for correlation_scope for backward compatibility.

    Args:
        operation: Name of the operation
        **metadata: Additional context to include in logs

    Yields:
        CorrelationContext with correlation ID and timing info
    """
    with correlation_scope(operation, **metadata) as ctx:
        yield ctx


# =============================================================================
# STRUCTURED LOGGING
# =============================================================================


def log_structured(
    level: Literal["debug", "info", "warning", "error", "critical"],
    message: str,
    **fields: Any,
) -> None:
    """
    Log with correlation context and structured fields.

    In JSON mode, outputs a JSON object to stdout.
    In standard mode, logs via the standard logger with fields appended.

    Args:
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        **fields: Additional structured fields to include

    Example:
        log_structured("info", "API call completed",
                      endpoint="/research", status=200, duration_ms=150)
    """
    # Get correlation context
    correlation_id = get_correlation_id()
    timestamp = datetime.now().isoformat()

    # Build log entry
    entry: dict[str, Any] = {
        "timestamp": timestamp,
        "level": level.upper(),
        "message": message,
        "correlation_id": correlation_id,
    }

    # Add any additional fields
    entry.update(fields)

    if _json_output_mode:
        # JSON output mode - write to stdout
        print(json.dumps(entry), file=sys.stdout, flush=True)
    else:
        # Standard logging mode
        log_func = getattr(logger, level)
        fields_str = ", ".join(f"{k}={v}" for k, v in fields.items())
        if fields_str:
            log_func(f"{message} ({fields_str}) [{correlation_id}]")
        else:
            log_func(f"{message} [{correlation_id}]")


# =============================================================================
# TIMING DECORATOR
# =============================================================================

def timed(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to log function entry, exit, and duration.

    Logs at DEBUG level with correlation ID.

    Args:
        func: Function to wrap

    Returns:
        Wrapped function that logs timing

    Example:
        @timed
        def slow_function():
            time.sleep(1)
            return "done"
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        correlation_id = get_correlation_id()
        func_name = f"{func.__module__}.{func.__name__}"

        logger.debug(f"Entering {func_name} [{correlation_id}]")
        start = time.time()

        try:
            result = func(*args, **kwargs)
            duration = time.time() - start
            logger.debug(
                f"Exiting {func_name} after {duration:.3f}s [{correlation_id}]"
            )
            return result
        except Exception as e:
            duration = time.time() - start
            logger.debug(
                f"Exiting {func_name} with error after {duration:.3f}s: {e} "
                f"[{correlation_id}]"
            )
            raise

    return wrapper


# =============================================================================
# METRICS
# =============================================================================

@dataclass
class Metrics:
    """
    Structured metrics for research operations.

    Attributes:
        operation: Name of the operation
        duration_seconds: How long the operation took
        success: Whether the operation succeeded
        input_tokens: Number of input tokens (for AI operations)
        output_tokens: Number of output tokens (for AI operations)
        cost_usd: Estimated cost in USD
        error_type: Type of error if failed
        correlation_id: Correlation ID for tracing
        timestamp: When the metrics were recorded
    """
    operation: str
    duration_seconds: float
    success: bool
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error_type: str | None = None
    correlation_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.correlation_id:
            self.correlation_id = get_correlation_id()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/export."""
        return {
            "operation": self.operation,
            "duration_seconds": round(self.duration_seconds, 3),
            "success": self.success,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 4),
            "error_type": self.error_type,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
            **self.metadata
        }


def emit_metrics(metrics: Metrics) -> None:
    """
    Emit structured metrics.

    Currently logs as JSON at INFO level. Can be extended for
    Prometheus, StatsD, or other metrics backends.

    Args:
        metrics: Metrics to emit
    """
    metrics_dict = metrics.to_dict()
    logger.info(f"METRICS: {json.dumps(metrics_dict)}")


@contextmanager
def tracked_operation(
    operation: str,
    **metadata: Any
) -> Generator[dict[str, Any], None, None]:
    """
    Context manager that tracks operation and emits metrics.

    Combines operation_context with automatic metrics emission.

    Args:
        operation: Name of the operation
        **metadata: Additional context

    Yields:
        Dict to store additional metrics (tokens, cost, etc.)

    Example:
        with tracked_operation("ai_call", model="gemini") as tracker:
            result = call_ai()
            tracker["input_tokens"] = result.input_tokens
            tracker["output_tokens"] = result.output_tokens
    """
    tracker: dict[str, Any] = {}
    start_time = time.time()
    correlation_id = get_correlation_id()
    success = True
    error_type = None

    try:
        with operation_context(operation, **metadata):
            yield tracker
    except Exception as e:
        success = False
        error_type = type(e).__name__
        raise
    finally:
        duration = time.time() - start_time
        metrics = Metrics(
            operation=operation,
            duration_seconds=duration,
            success=success,
            input_tokens=tracker.get("input_tokens", 0),
            output_tokens=tracker.get("output_tokens", 0),
            cost_usd=tracker.get("cost_usd", 0.0),
            error_type=error_type,
            correlation_id=correlation_id,
            metadata=metadata
        )
        emit_metrics(metrics)


# =============================================================================
# API CALL LOGGING
# =============================================================================


@dataclass
class APICallLog:
    """
    Structured log entry for API calls.

    Captures all required fields for API call tracing per Property 17.

    Attributes:
        correlation_id: Correlation ID for tracing
        timestamp: When the call was made
        operation: Name of the API operation
        request_params: Parameters sent with the request
        response_status: HTTP status code or status string
        duration_ms: Duration in milliseconds
        tokens_used: Number of tokens used (for AI APIs)
        error: Error message if the call failed
    """

    correlation_id: str
    timestamp: str
    operation: str
    request_params: dict[str, Any]
    response_status: int | str
    duration_ms: float
    tokens_used: int | None = None
    error: str | None = None

    @classmethod
    def create(
        cls,
        operation: str,
        request_params: dict[str, Any],
        response_status: int | str,
        duration_ms: float,
        tokens_used: int | None = None,
        error: str | None = None,
    ) -> "APICallLog":
        """
        Create an API call log with current correlation ID and timestamp.

        Args:
            operation: Name of the API operation
            request_params: Parameters sent with the request
            response_status: HTTP status code or status string
            duration_ms: Duration in milliseconds
            tokens_used: Number of tokens used (optional)
            error: Error message if failed (optional)

        Returns:
            New APICallLog instance
        """
        return cls(
            correlation_id=get_correlation_id(),
            timestamp=datetime.now().isoformat(),
            operation=operation,
            request_params=request_params,
            response_status=response_status,
            duration_ms=duration_ms,
            tokens_used=tokens_used,
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/export."""
        result: dict[str, Any] = {
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "operation": self.operation,
            "request_params": self.request_params,
            "response_status": self.response_status,
            "duration_ms": round(self.duration_ms, 2),
        }
        if self.tokens_used is not None:
            result["tokens_used"] = self.tokens_used
        if self.error is not None:
            result["error"] = self.error
        return result

    def has_required_fields(self) -> bool:
        """
        Check if all required fields are present.

        Required fields per Property 17:
        - correlation_id
        - request_params
        - response_status
        - duration_ms

        Returns:
            True if all required fields are present
        """
        return (
            bool(self.correlation_id)
            and self.request_params is not None
            and self.response_status is not None
            and self.duration_ms is not None
        )


def log_api_call(log_entry: APICallLog) -> None:
    """
    Log an API call with structured data.

    Args:
        log_entry: The API call log entry to record
    """
    log_structured(
        "info",
        f"API call: {log_entry.operation}",
        **log_entry.to_dict(),
    )


# =============================================================================
# JOB SUMMARY
# =============================================================================


@dataclass
class JobSummary:
    """
    Summary of a completed research job.

    Captures all relevant metrics and status for a research job.

    Attributes:
        correlation_id: Correlation ID for the job
        company: Company being researched
        mode: Research mode (scrape, deep, etc.)
        duration_seconds: Total job duration
        api_calls: Number of API calls made
        total_tokens: Total tokens used
        sections_generated: Number of report sections generated
        errors: List of error messages encountered
        warnings: List of warning messages
        output_path: Path to the generated report (if any)
        timestamp: When the job completed
    """

    correlation_id: str
    company: str
    mode: str
    duration_seconds: float
    api_calls: int
    total_tokens: int
    sections_generated: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    output_path: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        company: str,
        mode: str,
        duration_seconds: float,
        api_calls: int = 0,
        total_tokens: int = 0,
        sections_generated: int = 0,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
        output_path: str | None = None,
    ) -> "JobSummary":
        """
        Create a job summary with current correlation ID.

        Args:
            company: Company being researched
            mode: Research mode
            duration_seconds: Total job duration
            api_calls: Number of API calls made
            total_tokens: Total tokens used
            sections_generated: Number of sections generated
            errors: List of errors (optional)
            warnings: List of warnings (optional)
            output_path: Path to output file (optional)

        Returns:
            New JobSummary instance
        """
        return cls(
            correlation_id=get_correlation_id(),
            company=company,
            mode=mode,
            duration_seconds=duration_seconds,
            api_calls=api_calls,
            total_tokens=total_tokens,
            sections_generated=sections_generated,
            errors=errors or [],
            warnings=warnings or [],
            output_path=output_path,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/export."""
        result: dict[str, Any] = {
            "correlation_id": self.correlation_id,
            "company": self.company,
            "mode": self.mode,
            "duration_seconds": round(self.duration_seconds, 2),
            "api_calls": self.api_calls,
            "total_tokens": self.total_tokens,
            "sections_generated": self.sections_generated,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.errors:
            result["errors"] = self.errors
            result["error_count"] = len(self.errors)
        if self.warnings:
            result["warnings"] = self.warnings
            result["warning_count"] = len(self.warnings)
        if self.output_path:
            result["output_path"] = self.output_path
        return result

    @property
    def success(self) -> bool:
        """Check if job completed without errors."""
        return len(self.errors) == 0


def log_job_summary(summary: JobSummary) -> None:
    """
    Log a job summary on completion.

    Logs at INFO level with all job metrics.

    Args:
        summary: The job summary to log
    """
    status = "completed" if summary.success else "completed with errors"
    log_structured(
        "info",
        f"Job {status}: {summary.company} ({summary.mode})",
        **summary.to_dict(),
    )
