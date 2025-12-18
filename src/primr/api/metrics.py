"""
Metrics collection for monitoring and observability.

This module provides:
- Prometheus-compatible metrics
- Request/response tracking
- Performance metrics
- Cost tracking
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from primr.utils.logging_config import get_logger

logger = get_logger("api.metrics")


class MetricType(Enum):
    """Types of metrics."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricValue:
    """A single metric value."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class HistogramBucket:
    """A histogram bucket."""

    le: float  # Less than or equal
    count: int = 0


@dataclass
class Histogram:
    """Histogram metric with buckets."""

    name: str
    buckets: list[HistogramBucket] = field(default_factory=list)
    sum: float = 0.0
    count: int = 0
    labels: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.buckets:
            # Default buckets for response times (seconds)
            self.buckets = [
                HistogramBucket(le=0.005),
                HistogramBucket(le=0.01),
                HistogramBucket(le=0.025),
                HistogramBucket(le=0.05),
                HistogramBucket(le=0.1),
                HistogramBucket(le=0.25),
                HistogramBucket(le=0.5),
                HistogramBucket(le=1.0),
                HistogramBucket(le=2.5),
                HistogramBucket(le=5.0),
                HistogramBucket(le=10.0),
                HistogramBucket(le=float('inf')),
            ]

    def observe(self, value: float) -> None:
        """Record an observation."""
        self.sum += value
        self.count += 1

        for bucket in self.buckets:
            if value <= bucket.le:
                bucket.count += 1


class MetricsCollector:
    """
    Collects and exposes metrics for monitoring.

    Example:
        metrics = MetricsCollector()

        # Count requests
        metrics.increment("http_requests_total", labels={"method": "GET"})

        # Track response time
        metrics.observe_histogram("http_request_duration_seconds", 0.125)

        # Get Prometheus format
        output = metrics.export_prometheus()
    """

    def __init__(self):
        """Initialize the metrics collector."""
        self._counters: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: dict[str, dict[str, Histogram]] = defaultdict(dict)
        self._lock = threading.Lock()
        self._start_time = datetime.now()

        # Initialize default metrics
        self._init_default_metrics()

        logger.debug("MetricsCollector initialized")

    def _init_default_metrics(self) -> None:
        """Initialize default metrics."""
        self.set_gauge("process_start_time_seconds", time.time())

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Increment a counter.

        Args:
            name: Metric name
            value: Value to add
            labels: Optional labels
        """
        label_key = self._labels_to_key(labels)

        with self._lock:
            self._counters[name][label_key] += value

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Set a gauge value.

        Args:
            name: Metric name
            value: Value to set
            labels: Optional labels
        """
        label_key = self._labels_to_key(labels)

        with self._lock:
            self._gauges[name][label_key] = value

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a histogram observation.

        Args:
            name: Metric name
            value: Value to observe
            labels: Optional labels
        """
        label_key = self._labels_to_key(labels)

        with self._lock:
            if label_key not in self._histograms[name]:
                self._histograms[name][label_key] = Histogram(
                    name=name,
                    labels=labels or {},
                )
            self._histograms[name][label_key].observe(value)

    def get_counter(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float:
        """Get counter value."""
        label_key = self._labels_to_key(labels)

        with self._lock:
            return self._counters[name][label_key]

    def get_gauge(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float:
        """Get gauge value."""
        label_key = self._labels_to_key(labels)

        with self._lock:
            return self._gauges[name][label_key]

    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = []

        with self._lock:
            # Export counters
            for name, values in self._counters.items():
                lines.append(f"# TYPE {name} counter")
                for label_key, value in values.items():
                    labels_str = self._key_to_labels_str(label_key)
                    lines.append(f"{name}{labels_str} {value}")

            # Export gauges
            for name, values in self._gauges.items():
                lines.append(f"# TYPE {name} gauge")
                for label_key, value in values.items():
                    labels_str = self._key_to_labels_str(label_key)
                    lines.append(f"{name}{labels_str} {value}")

            # Export histograms
            for name, histograms in self._histograms.items():
                lines.append(f"# TYPE {name} histogram")
                for label_key, hist in histograms.items():
                    base_labels = self._key_to_labels_str(label_key)

                    for bucket in hist.buckets:
                        le_label = f'le="{bucket.le}"'
                        if base_labels:
                            bucket_labels = base_labels[:-1] + "," + le_label + "}"
                        else:
                            bucket_labels = "{" + le_label + "}"
                        lines.append(f"{name}_bucket{bucket_labels} {bucket.count}")

                    lines.append(f"{name}_sum{base_labels} {hist.sum}")
                    lines.append(f"{name}_count{base_labels} {hist.count}")

        return "\n".join(lines)

    def export_json(self) -> dict[str, Any]:
        """
        Export metrics as JSON.

        Returns:
            Dictionary of metrics
        """
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    name: {
                        label_key: {
                            "sum": hist.sum,
                            "count": hist.count,
                            "buckets": [
                                {"le": b.le, "count": b.count}
                                for b in hist.buckets
                            ],
                        }
                        for label_key, hist in histograms.items()
                    }
                    for name, histograms in self._histograms.items()
                },
                "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
        # Initialize default metrics outside the lock to avoid deadlock
        self._init_default_metrics()

    def _labels_to_key(self, labels: dict[str, str] | None) -> str:
        """Convert labels dict to a hashable key."""
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def _key_to_labels_str(self, key: str) -> str:
        """Convert key back to Prometheus labels string."""
        if not key:
            return ""
        parts = key.split(",")
        label_parts = []
        for part in parts:
            k, v = part.split("=")
            label_parts.append(f'{k}="{v}"')
        return "{" + ",".join(label_parts) + "}"


class RequestMetrics:
    """
    Middleware-style request metrics tracking.

    Example:
        metrics = RequestMetrics()

        with metrics.track_request("GET", "/api/research"):
            # Handle request
            pass
    """

    def __init__(self, collector: MetricsCollector | None = None):
        """Initialize request metrics."""
        self._collector = collector or MetricsCollector()

    def track_request(
        self,
        method: str,
        path: str,
        status_code: int = 200,
    ) -> "_RequestTracker":
        """
        Context manager for tracking request metrics.

        Args:
            method: HTTP method
            path: Request path
            status_code: Response status code
        """
        return _RequestTracker(self._collector, method, path, status_code)

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: float,
    ) -> None:
        """
        Record a completed request.

        Args:
            method: HTTP method
            path: Request path
            status_code: Response status code
            duration: Request duration in seconds
        """
        labels = {"method": method, "path": path, "status": str(status_code)}

        self._collector.increment("http_requests_total", labels=labels)
        self._collector.observe_histogram(
            "http_request_duration_seconds",
            duration,
            labels={"method": method, "path": path},
        )

    @property
    def collector(self) -> MetricsCollector:
        """Get the underlying collector."""
        return self._collector


class _RequestTracker:
    """Context manager for tracking request duration."""

    def __init__(
        self,
        collector: MetricsCollector,
        method: str,
        path: str,
        status_code: int,
    ):
        self._collector = collector
        self._method = method
        self._path = path
        self._status_code = status_code
        self._start_time: float = 0

    def __enter__(self):
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self._start_time

        labels = {
            "method": self._method,
            "path": self._path,
            "status": str(self._status_code),
        }

        self._collector.increment("http_requests_total", labels=labels)
        self._collector.observe_histogram(
            "http_request_duration_seconds",
            duration,
            labels={"method": self._method, "path": self._path},
        )

        return False


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def reset_metrics_collector() -> None:
    """Reset the global metrics collector."""
    global _collector
    _collector = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def increment_counter(
    name: str,
    value: float = 1.0,
    labels: dict[str, str] | None = None,
) -> None:
    """Increment a counter metric."""
    get_metrics_collector().increment(name, value, labels)


def set_gauge(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """Set a gauge metric."""
    get_metrics_collector().set_gauge(name, value, labels)


def observe_histogram(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """Record a histogram observation."""
    get_metrics_collector().observe_histogram(name, value, labels)


def export_metrics(format: str = "prometheus") -> str:
    """Export metrics in the specified format."""
    collector = get_metrics_collector()
    if format == "json":
        import json
        return json.dumps(collector.export_json(), indent=2)
    return collector.export_prometheus()
