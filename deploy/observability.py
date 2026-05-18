"""
Observability - OpenTelemetry tracing and metrics for cloud deployment.

This module provides:
- OpenTelemetry tracing with job_id propagation
- Structured logging with correlation IDs
- Metrics collection for job execution

Requirements: 10.1, 10.2, 10.3
"""

from __future__ import annotations

import json
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

# Try to import OpenTelemetry, but make it optional
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None  # type: ignore


# Sensitive patterns to redact
SENSITIVE_PATTERNS = [
    (
        re.compile(
            r'(api[_-]?key|apikey|secret|password|token|auth)["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
            re.IGNORECASE,
        ),
        r"\1=***REDACTED***",
    ),
    (re.compile(r"(Bearer\s+)([A-Za-z0-9\-_]+\.?)+", re.IGNORECASE), r"\1***REDACTED***"),
    (re.compile(r"(sk-[a-zA-Z0-9]{20,})", re.IGNORECASE), "***REDACTED_API_KEY***"),
    (re.compile(r"(AIza[a-zA-Z0-9_-]{35})", re.IGNORECASE), "***REDACTED_GOOGLE_KEY***"),
]


def redact_sensitive(text: str) -> str:
    """
    Redact sensitive information from text.

    Removes API keys, tokens, passwords, and other secrets.

    Args:
        text: Text that may contain sensitive data

    Returns:
        Text with sensitive data redacted
    """
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively redact sensitive values from a dictionary.

    Args:
        data: Dictionary that may contain sensitive data

    Returns:
        Dictionary with sensitive data redacted
    """
    sensitive_keys = {"api_key", "apikey", "secret", "password", "token", "auth", "key"}
    result = {}

    for key, value in data.items():
        key_lower = key.lower()

        # Check if key suggests sensitive data
        if any(s in key_lower for s in sensitive_keys):
            result[key] = "***REDACTED***"
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, str):
            result[key] = redact_sensitive(value)
        elif isinstance(value, list):
            result[key] = [
                redact_dict(v)
                if isinstance(v, dict)
                else redact_sensitive(v)
                if isinstance(v, str)
                else v
                for v in value
            ]
        else:
            result[key] = value

    return result


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


@dataclass
class TraceContext:
    """Context for distributed tracing."""

    trace_id: str
    span_id: str
    job_id: str
    deployment: str

    def to_dict(self) -> dict[str, str]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "job_id": self.job_id,
            "deployment": self.deployment,
        }


class StructuredLogger:
    """
    Structured JSON logger with correlation IDs.

    Outputs JSON logs with:
    - Timestamp
    - Log level
    - Event name
    - Job ID correlation
    - Trace context (if available)
    - Redacted sensitive data
    """

    def __init__(
        self,
        name: str = "primr",
        job_id: str | None = None,
        deployment: str | None = None,
        output: Any = None,
    ) -> None:
        """
        Initialize structured logger.

        Args:
            name: Logger name
            job_id: Job ID for correlation
            deployment: Deployment namespace
            output: Output stream (defaults to stderr)
        """
        self.name = name
        self.job_id = job_id
        self.deployment = deployment
        self.output = output or sys.stderr
        self._trace_context: TraceContext | None = None

    def set_trace_context(self, ctx: TraceContext) -> None:
        """Set trace context for log correlation."""
        self._trace_context = ctx

    def _format_entry(
        self,
        level: str,
        event: str,
        **kwargs: Any,
    ) -> str:
        """Format a log entry as JSON."""
        entry = {
            "ts": format_timestamp(utc_now()),
            "level": level,
            "logger": self.name,
            "event": event,
        }

        # Add correlation IDs
        if self.job_id:
            entry["job_id"] = self.job_id
        if self.deployment:
            entry["deployment"] = self.deployment

        # Add trace context
        if self._trace_context:
            entry["trace_id"] = self._trace_context.trace_id
            entry["span_id"] = self._trace_context.span_id

        # Add extra fields (redacted)
        for key, value in kwargs.items():
            if isinstance(value, dict):
                entry[key] = redact_dict(value)
            elif isinstance(value, str):
                entry[key] = redact_sensitive(value)
            else:
                entry[key] = value

        return json.dumps(entry)

    def _write(self, entry: str) -> None:
        """Write log entry to output."""
        self.output.write(entry + "\n")
        self.output.flush()

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._write(self._format_entry("debug", event, **kwargs))

    def info(self, event: str, **kwargs: Any) -> None:
        """Log info message."""
        self._write(self._format_entry("info", event, **kwargs))

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._write(self._format_entry("warning", event, **kwargs))

    def error(self, event: str, **kwargs: Any) -> None:
        """Log error message."""
        self._write(self._format_entry("error", event, **kwargs))


class Tracer:
    """
    OpenTelemetry tracer wrapper.

    Provides tracing with job_id as a span attribute.
    Falls back to no-op if OpenTelemetry is not available.
    """

    def __init__(
        self,
        service_name: str = "primr-runner",
        job_id: str | None = None,
        deployment: str | None = None,
    ) -> None:
        """
        Initialize tracer.

        Args:
            service_name: Service name for traces
            job_id: Job ID to attach to all spans
            deployment: Deployment namespace
        """
        self.service_name = service_name
        self.job_id = job_id
        self.deployment = deployment
        self._tracer: Any = None

        if OTEL_AVAILABLE:
            self._setup_tracer()

    def _setup_tracer(self) -> None:
        """Setup OpenTelemetry tracer."""
        if not OTEL_AVAILABLE:
            return

        # Create resource with service info
        resource = Resource.create(
            {
                "service.name": self.service_name,
                "service.version": "1.0.0",
                "deployment.environment": self.deployment or "unknown",
            }
        )

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Add console exporter for local debugging
        # In production, configure OTLP exporter via env vars
        if os.environ.get("OTEL_EXPORTER_CONSOLE", "").lower() == "true":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        # Set as global provider
        trace.set_tracer_provider(provider)

        # Get tracer
        self._tracer = trace.get_tracer(self.service_name)

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Any, None, None]:
        """
        Create a trace span.

        Args:
            name: Span name
            attributes: Additional span attributes

        Yields:
            Span object (or None if tracing not available)
        """
        if not OTEL_AVAILABLE or self._tracer is None:
            yield None
            return

        # Build attributes
        span_attrs = {}
        if self.job_id:
            span_attrs["job.id"] = self.job_id
        if self.deployment:
            span_attrs["deployment"] = self.deployment
        if attributes:
            span_attrs.update(attributes)

        with self._tracer.start_as_current_span(name, attributes=span_attrs) as span:
            yield span

    def record_exception(self, span: Any, exception: Exception) -> None:
        """Record an exception on a span."""
        if not OTEL_AVAILABLE or span is None:
            return

        span.record_exception(exception)
        span.set_status(Status(StatusCode.ERROR, str(exception)))

    def set_success(self, span: Any) -> None:
        """Mark span as successful."""
        if not OTEL_AVAILABLE or span is None:
            return

        span.set_status(Status(StatusCode.OK))


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: str
    labels: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "labels": self.labels,
        }


class MetricsCollector:
    """
    Simple metrics collector.

    Collects metrics and outputs them as JSON for ingestion
    by cloud monitoring systems.
    """

    def __init__(
        self,
        job_id: str | None = None,
        deployment: str | None = None,
    ) -> None:
        """
        Initialize metrics collector.

        Args:
            job_id: Job ID for metric labels
            deployment: Deployment namespace
        """
        self.job_id = job_id
        self.deployment = deployment
        self._metrics: list[MetricPoint] = []

    def _base_labels(self) -> dict[str, str]:
        """Get base labels for all metrics."""
        labels = {}
        if self.job_id:
            labels["job_id"] = self.job_id
        if self.deployment:
            labels["deployment"] = self.deployment
        return labels

    def record(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a metric value.

        Args:
            name: Metric name
            value: Metric value
            labels: Additional labels
        """
        all_labels = self._base_labels()
        if labels:
            all_labels.update(labels)

        point = MetricPoint(
            name=name,
            value=value,
            timestamp=format_timestamp(utc_now()),
            labels=all_labels,
        )
        self._metrics.append(point)

    def record_duration(
        self,
        name: str,
        duration_seconds: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a duration metric."""
        self.record(f"{name}_seconds", duration_seconds, labels)

    def record_count(
        self,
        name: str,
        count: int = 1,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a count metric."""
        self.record(f"{name}_total", float(count), labels)

    def get_metrics(self) -> list[dict[str, Any]]:
        """Get all collected metrics as dicts."""
        return [m.to_dict() for m in self._metrics]

    def to_json(self) -> str:
        """Export metrics as JSON."""
        return json.dumps(self.get_metrics(), indent=2)

    def clear(self) -> None:
        """Clear collected metrics."""
        self._metrics.clear()
