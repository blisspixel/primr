"""
Tests for the metrics collection module.
"""

import time

import pytest

from primr.api.metrics import (
    Histogram,
    MetricsCollector,
    RequestMetrics,
    export_metrics,
    get_metrics_collector,
    increment_counter,
    observe_histogram,
    reset_metrics_collector,
    set_gauge,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def reset_singleton():
    """Reset singleton before each test."""
    reset_metrics_collector()
    yield
    reset_metrics_collector()


@pytest.fixture
def collector():
    """Create a fresh metrics collector."""
    return MetricsCollector()


# =============================================================================
# HISTOGRAM TESTS
# =============================================================================


class TestHistogram:
    """Tests for Histogram class."""

    def test_default_buckets(self):
        """Test default buckets are created."""
        hist = Histogram(name="test")
        assert len(hist.buckets) > 0
        assert hist.buckets[-1].le == float("inf")

    def test_observe(self):
        """Test observing values."""
        hist = Histogram(name="test")
        hist.observe(0.1)
        hist.observe(0.5)
        hist.observe(1.0)

        assert hist.count == 3
        assert hist.sum == pytest.approx(1.6)

    def test_bucket_counts(self):
        """Test bucket counts are updated."""
        hist = Histogram(name="test")
        hist.observe(0.001)  # Should be in 0.005 bucket
        hist.observe(0.1)  # Should be in 0.1 bucket
        hist.observe(5.0)  # Should be in 5.0 bucket

        # All values should be in inf bucket
        assert hist.buckets[-1].count == 3


# =============================================================================
# METRICS COLLECTOR TESTS
# =============================================================================


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def test_increment_counter(self, collector):
        """Test counter increment."""
        collector.increment("requests_total")
        collector.increment("requests_total")

        assert collector.get_counter("requests_total") == 2

    def test_increment_with_value(self, collector):
        """Test counter increment with value."""
        collector.increment("bytes_total", value=100)
        collector.increment("bytes_total", value=50)

        assert collector.get_counter("bytes_total") == 150

    def test_increment_with_labels(self, collector):
        """Test counter with labels."""
        collector.increment("requests_total", labels={"method": "GET"})
        collector.increment("requests_total", labels={"method": "POST"})
        collector.increment("requests_total", labels={"method": "GET"})

        assert collector.get_counter("requests_total", {"method": "GET"}) == 2
        assert collector.get_counter("requests_total", {"method": "POST"}) == 1

    def test_set_gauge(self, collector):
        """Test gauge setting."""
        collector.set_gauge("temperature", 25.5)
        assert collector.get_gauge("temperature") == 25.5

        collector.set_gauge("temperature", 30.0)
        assert collector.get_gauge("temperature") == 30.0

    def test_gauge_with_labels(self, collector):
        """Test gauge with labels."""
        collector.set_gauge("cpu_usage", 50.0, {"core": "0"})
        collector.set_gauge("cpu_usage", 75.0, {"core": "1"})

        assert collector.get_gauge("cpu_usage", {"core": "0"}) == 50.0
        assert collector.get_gauge("cpu_usage", {"core": "1"}) == 75.0

    def test_observe_histogram(self, collector):
        """Test histogram observation."""
        collector.observe_histogram("response_time", 0.1)
        collector.observe_histogram("response_time", 0.2)
        collector.observe_histogram("response_time", 0.3)

        # Check via export
        output = collector.export_prometheus()
        assert "response_time_count" in output
        assert "response_time_sum" in output

    def test_reset(self, collector):
        """Test metrics reset."""
        collector.increment("requests_total")
        collector.set_gauge("temperature", 25.0)

        collector.reset()

        assert collector.get_counter("requests_total") == 0
        assert collector.get_gauge("temperature") == 0


# =============================================================================
# PROMETHEUS EXPORT TESTS
# =============================================================================


class TestPrometheusExport:
    """Tests for Prometheus format export."""

    def test_export_counter(self, collector):
        """Test counter export."""
        collector.increment("http_requests_total", labels={"method": "GET"})

        output = collector.export_prometheus()

        assert "# TYPE http_requests_total counter" in output
        assert 'http_requests_total{method="GET"}' in output

    def test_export_gauge(self, collector):
        """Test gauge export."""
        collector.set_gauge("temperature", 25.5)

        output = collector.export_prometheus()

        assert "# TYPE temperature gauge" in output
        assert "temperature 25.5" in output

    def test_export_histogram(self, collector):
        """Test histogram export."""
        collector.observe_histogram("response_time", 0.1)

        output = collector.export_prometheus()

        assert "# TYPE response_time histogram" in output
        assert "response_time_bucket" in output
        assert "response_time_sum" in output
        assert "response_time_count" in output


# =============================================================================
# JSON EXPORT TESTS
# =============================================================================


class TestJsonExport:
    """Tests for JSON format export."""

    def test_export_json(self, collector):
        """Test JSON export."""
        collector.increment("requests_total")
        collector.set_gauge("temperature", 25.0)

        data = collector.export_json()

        assert "counters" in data
        assert "gauges" in data
        assert "uptime_seconds" in data

    def test_export_json_histograms(self, collector):
        """Test JSON export with histograms."""
        collector.observe_histogram("response_time", 0.1)

        data = collector.export_json()

        assert "histograms" in data
        assert "response_time" in data["histograms"]


# =============================================================================
# REQUEST METRICS TESTS
# =============================================================================


class TestRequestMetrics:
    """Tests for RequestMetrics class."""

    def test_track_request(self):
        """Test request tracking context manager."""
        metrics = RequestMetrics()

        with metrics.track_request("GET", "/api/test", 200):
            time.sleep(0.01)

        output = metrics.collector.export_prometheus()
        assert "http_requests_total" in output
        assert "http_request_duration_seconds" in output

    def test_record_request(self):
        """Test manual request recording."""
        metrics = RequestMetrics()

        metrics.record_request("POST", "/api/research", 201, 0.5)

        output = metrics.collector.export_prometheus()
        assert "http_requests_total" in output


# =============================================================================
# SINGLETON TESTS
# =============================================================================


class TestSingleton:
    """Tests for singleton access."""

    def test_get_collector_returns_same(self):
        """Test get_metrics_collector returns same instance."""
        c1 = get_metrics_collector()
        c2 = get_metrics_collector()
        assert c1 is c2

    def test_reset_collector(self):
        """Test reset creates new instance."""
        c1 = get_metrics_collector()
        reset_metrics_collector()
        c2 = get_metrics_collector()
        assert c1 is not c2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_increment_counter_function(self):
        """Test increment_counter convenience function."""
        increment_counter("test_counter")
        increment_counter("test_counter")

        assert get_metrics_collector().get_counter("test_counter") == 2

    def test_set_gauge_function(self):
        """Test set_gauge convenience function."""
        set_gauge("test_gauge", 42.0)

        assert get_metrics_collector().get_gauge("test_gauge") == 42.0

    def test_observe_histogram_function(self):
        """Test observe_histogram convenience function."""
        observe_histogram("test_histogram", 0.5)

        output = export_metrics()
        assert "test_histogram" in output

    def test_export_metrics_prometheus(self):
        """Test export_metrics with prometheus format."""
        increment_counter("test")

        output = export_metrics("prometheus")
        assert "# TYPE test counter" in output

    def test_export_metrics_json(self):
        """Test export_metrics with json format."""
        increment_counter("test")

        output = export_metrics("json")
        assert '"counters"' in output


# =============================================================================
# THREAD SAFETY TESTS
# =============================================================================


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_increments(self, collector):
        """Test concurrent counter increments."""
        import threading

        def increment_many():
            for _ in range(100):
                collector.increment("concurrent_counter")

        threads = [threading.Thread(target=increment_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert collector.get_counter("concurrent_counter") == 1000
