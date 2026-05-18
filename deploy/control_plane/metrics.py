"""
Control Plane Metrics - Metrics collection for the control plane API.

This module provides metrics for:
- Request counts and latencies
- Job submission rates
- Queue depth
- Success/failure rates

Requirements: 10.3
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone


def format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


@dataclass
class MetricValue:
    """A metric value with timestamp."""

    value: float
    timestamp: str
    labels: dict[str, str] = field(default_factory=dict)


class Counter:
    """Thread-safe counter metric."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def _label_key(self, labels: dict[str, str]) -> str:
        """Create a hashable key from labels."""
        return json.dumps(sorted(labels.items()))

    def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        """Increment the counter."""
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] += value

    def get(self, labels: dict[str, str] | None = None) -> float:
        """Get current counter value."""
        key = self._label_key(labels or {})
        with self._lock:
            return self._values.get(key, 0.0)

    def get_all(self) -> list[MetricValue]:
        """Get all counter values."""
        with self._lock:
            result = []
            for key, value in self._values.items():
                labels = dict(json.loads(key)) if key else {}
                result.append(
                    MetricValue(
                        value=value,
                        timestamp=format_timestamp(utc_now()),
                        labels=labels,
                    )
                )
            return result


class Gauge:
    """Thread-safe gauge metric."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[str, float] = {}
        self._lock = threading.Lock()

    def _label_key(self, labels: dict[str, str]) -> str:
        """Create a hashable key from labels."""
        return json.dumps(sorted(labels.items()))

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Set the gauge value."""
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] = value

    def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        """Increment the gauge."""
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + value

    def dec(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        """Decrement the gauge."""
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) - value

    def get(self, labels: dict[str, str] | None = None) -> float:
        """Get current gauge value."""
        key = self._label_key(labels or {})
        with self._lock:
            return self._values.get(key, 0.0)

    def get_all(self) -> list[MetricValue]:
        """Get all gauge values."""
        with self._lock:
            result = []
            for key, value in self._values.items():
                labels = dict(json.loads(key)) if key else {}
                result.append(
                    MetricValue(
                        value=value,
                        timestamp=format_timestamp(utc_now()),
                        labels=labels,
                    )
                )
            return result


class Histogram:
    """Thread-safe histogram metric for latency tracking."""

    # Default buckets for latency in seconds
    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._counts: dict[str, dict[float, int]] = defaultdict(lambda: defaultdict(int))
        self._sums: dict[str, float] = defaultdict(float)
        self._totals: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def _label_key(self, labels: dict[str, str]) -> str:
        """Create a hashable key from labels."""
        return json.dumps(sorted(labels.items()))

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Record an observation."""
        key = self._label_key(labels or {})
        with self._lock:
            self._sums[key] += value
            self._totals[key] += 1
            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[key][bucket] += 1

    def get_sum(self, labels: dict[str, str] | None = None) -> float:
        """Get sum of all observations."""
        key = self._label_key(labels or {})
        with self._lock:
            return self._sums.get(key, 0.0)

    def get_count(self, labels: dict[str, str] | None = None) -> int:
        """Get count of all observations."""
        key = self._label_key(labels or {})
        with self._lock:
            return self._totals.get(key, 0)

    def get_bucket_counts(self, labels: dict[str, str] | None = None) -> dict[float, int]:
        """Get bucket counts."""
        key = self._label_key(labels or {})
        with self._lock:
            return dict(self._counts.get(key, {}))


class ControlPlaneMetrics:
    """
    Metrics collector for the control plane.

    Provides pre-defined metrics for common operations.
    """

    def __init__(self) -> None:
        # Request metrics
        self.requests_total = Counter(
            "control_plane_requests_total",
            "Total number of API requests",
        )
        self.request_duration = Histogram(
            "control_plane_request_duration_seconds",
            "Request duration in seconds",
        )

        # Job metrics
        self.jobs_submitted = Counter(
            "control_plane_jobs_submitted_total",
            "Total number of jobs submitted",
        )
        self.jobs_completed = Counter(
            "control_plane_jobs_completed_total",
            "Total number of jobs completed",
        )
        self.jobs_active = Gauge(
            "control_plane_jobs_active",
            "Number of currently active jobs",
        )

        # Queue metrics
        self.queue_depth = Gauge(
            "control_plane_queue_depth",
            "Current queue depth",
        )

        # Rate limit metrics
        self.rate_limit_hits = Counter(
            "control_plane_rate_limit_hits_total",
            "Number of rate limit hits",
        )

    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record an API request."""
        labels = {
            "endpoint": endpoint,
            "method": method,
            "status": str(status_code),
        }
        self.requests_total.inc(labels)
        self.request_duration.observe(duration_seconds, labels)

    def record_job_submitted(self, mode: str, deployment: str) -> None:
        """Record a job submission."""
        labels = {"mode": mode, "deployment": deployment}
        self.jobs_submitted.inc(labels)
        self.jobs_active.inc(labels)

    def record_job_completed(self, mode: str, deployment: str, status: str) -> None:
        """Record a job completion."""
        labels = {"mode": mode, "deployment": deployment, "status": status}
        self.jobs_completed.inc(labels)
        self.jobs_active.dec({"mode": mode, "deployment": deployment})

    def set_queue_depth(self, depth: int, deployment: str) -> None:
        """Set current queue depth."""
        self.queue_depth.set(float(depth), {"deployment": deployment})

    def record_rate_limit_hit(self, api_key_hash: str) -> None:
        """Record a rate limit hit."""
        # Don't include full hash in metrics for privacy
        self.rate_limit_hits.inc({"key_prefix": api_key_hash[:8]})

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        # Helper to format metric lines
        def format_metric(name: str, values: list[MetricValue], metric_type: str) -> None:
            lines.append(f"# TYPE {name} {metric_type}")
            for v in values:
                if v.labels:
                    label_str = ",".join(f'{k}="{v}"' for k, v in v.labels.items())
                    lines.append(f"{name}{{{label_str}}} {v.value}")
                else:
                    lines.append(f"{name} {v.value}")

        # Export counters
        format_metric(self.requests_total.name, self.requests_total.get_all(), "counter")
        format_metric(self.jobs_submitted.name, self.jobs_submitted.get_all(), "counter")
        format_metric(self.jobs_completed.name, self.jobs_completed.get_all(), "counter")
        format_metric(self.rate_limit_hits.name, self.rate_limit_hits.get_all(), "counter")

        # Export gauges
        format_metric(self.jobs_active.name, self.jobs_active.get_all(), "gauge")
        format_metric(self.queue_depth.name, self.queue_depth.get_all(), "gauge")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Export metrics as JSON."""
        data = {
            "requests_total": [v.__dict__ for v in self.requests_total.get_all()],
            "jobs_submitted": [v.__dict__ for v in self.jobs_submitted.get_all()],
            "jobs_completed": [v.__dict__ for v in self.jobs_completed.get_all()],
            "jobs_active": [v.__dict__ for v in self.jobs_active.get_all()],
            "queue_depth": [v.__dict__ for v in self.queue_depth.get_all()],
            "rate_limit_hits": [v.__dict__ for v in self.rate_limit_hits.get_all()],
        }
        return json.dumps(data, indent=2)


# Global metrics instance
_metrics: ControlPlaneMetrics | None = None


def get_metrics() -> ControlPlaneMetrics:
    """Get or create the global metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = ControlPlaneMetrics()
    return _metrics


def reset_metrics() -> None:
    """Reset metrics (for testing)."""
    global _metrics
    _metrics = None
