"""
Performance Benchmarking Suite for Primr.

This module provides infrastructure for benchmarking critical paths,
storing historical results, and detecting performance regressions.

**Feature: phd-level-excellence**
**Validates: Requirements 11.1-11.6**

Components:
- BenchmarkResult: Result of a single benchmark run
- BenchmarkSuite: Collection of benchmarks with result storage
- BenchmarkRunner: Executes benchmarks and tracks results
- RegressionDetector: Compares results against baselines
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class BenchmarkResult:
    """
    Result of a single benchmark run.

    Attributes:
        name: Benchmark identifier
        duration_seconds: Total execution time
        iterations: Number of iterations run
        mean_time: Mean time per iteration
        std_dev: Standard deviation of iteration times
        min_time: Minimum iteration time
        max_time: Maximum iteration time
        percentiles: Dict of percentile values (p50, p90, p95, p99)
        timestamp: When the benchmark was run
        metadata: Additional benchmark-specific data
    """

    name: str
    duration_seconds: float
    iterations: int
    mean_time: float
    std_dev: float
    min_time: float
    max_time: float
    percentiles: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "duration_seconds": self.duration_seconds,
            "iterations": self.iterations,
            "mean_time": self.mean_time,
            "std_dev": self.std_dev,
            "min_time": self.min_time,
            "max_time": self.max_time,
            "percentiles": self.percentiles,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkResult:
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            duration_seconds=data["duration_seconds"],
            iterations=data["iterations"],
            mean_time=data["mean_time"],
            std_dev=data["std_dev"],
            min_time=data["min_time"],
            max_time=data["max_time"],
            percentiles=data.get("percentiles", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class RegressionWarning:
    """
    Warning about a performance regression.

    Attributes:
        benchmark_name: Name of the regressed benchmark
        baseline_value: Previous baseline value
        current_value: Current measured value
        percentage_change: Percentage change from baseline
        threshold: Threshold that was exceeded
        message: Human-readable warning message
    """

    benchmark_name: str
    baseline_value: float
    current_value: float
    percentage_change: float
    threshold: float
    message: str


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================


class BenchmarkRunner:
    """
    Executes benchmarks and calculates statistics.

    Example:
        runner = BenchmarkRunner()

        def my_operation():
            # ... do something ...
            pass

        result = runner.run("my_benchmark", my_operation, iterations=100)
        print(f"Mean time: {result.mean_time:.4f}s")
    """

    def __init__(self, warmup_iterations: int = 3):
        """
        Initialize the benchmark runner.

        Args:
            warmup_iterations: Number of warmup iterations before timing
        """
        self.warmup_iterations = warmup_iterations

    def run(
        self,
        name: str,
        operation: Callable[[], Any],
        iterations: int = 100,
        metadata: dict[str, Any] | None = None,
    ) -> BenchmarkResult:
        """
        Run a benchmark and collect statistics.

        Args:
            name: Benchmark identifier
            operation: Function to benchmark
            iterations: Number of iterations to run
            metadata: Additional metadata to store

        Returns:
            BenchmarkResult with timing statistics
        """
        # Warmup
        for _ in range(self.warmup_iterations):
            operation()

        # Timed runs
        times = []
        start_total = time.perf_counter()

        for _ in range(iterations):
            start = time.perf_counter()
            operation()
            end = time.perf_counter()
            times.append(end - start)

        end_total = time.perf_counter()

        # Calculate statistics
        mean_time = statistics.mean(times)
        std_dev = statistics.stdev(times) if len(times) > 1 else 0.0

        # Calculate percentiles
        sorted_times = sorted(times)
        percentiles = {
            "p50": self._percentile(sorted_times, 50),
            "p90": self._percentile(sorted_times, 90),
            "p95": self._percentile(sorted_times, 95),
            "p99": self._percentile(sorted_times, 99),
        }

        return BenchmarkResult(
            name=name,
            duration_seconds=end_total - start_total,
            iterations=iterations,
            mean_time=mean_time,
            std_dev=std_dev,
            min_time=min(times),
            max_time=max(times),
            percentiles=percentiles,
            metadata=metadata or {},
        )

    def _percentile(self, sorted_data: list[float], p: int) -> float:
        """Calculate percentile from sorted data."""
        if not sorted_data:
            return 0.0
        k = (len(sorted_data) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


# =============================================================================
# RESULT STORAGE
# =============================================================================


class BenchmarkStore:
    """
    Stores and retrieves benchmark results.

    Results are stored in JSON format with timestamps for historical comparison.

    Example:
        store = BenchmarkStore("benchmarks/results")
        store.save(result)

        history = store.get_history("my_benchmark", limit=10)
        baseline = store.get_baseline("my_benchmark")
    """

    def __init__(self, storage_path: Path | str):
        """
        Initialize the benchmark store.

        Args:
            storage_path: Directory to store benchmark results
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save(self, result: BenchmarkResult) -> Path:
        """
        Save a benchmark result.

        Args:
            result: BenchmarkResult to save

        Returns:
            Path to saved file
        """
        # Create filename with timestamp including microseconds for uniqueness
        timestamp = result.timestamp.strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{result.name}_{timestamp}.json"
        filepath = self.storage_path / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

        return filepath

    def get_history(
        self,
        benchmark_name: str,
        limit: int | None = None,
    ) -> list[BenchmarkResult]:
        """
        Get historical results for a benchmark.

        Args:
            benchmark_name: Name of the benchmark
            limit: Maximum number of results to return

        Returns:
            List of BenchmarkResult, newest first
        """
        results = []

        for filepath in sorted(self.storage_path.glob(f"{benchmark_name}_*.json"), reverse=True):
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
                results.append(BenchmarkResult.from_dict(data))

                if limit and len(results) >= limit:
                    break
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load benchmark result {filepath}: {e}")

        return results

    def get_baseline(self, benchmark_name: str) -> BenchmarkResult | None:
        """
        Get the baseline result for a benchmark.

        The baseline is the oldest result in the store.

        Args:
            benchmark_name: Name of the benchmark

        Returns:
            Baseline BenchmarkResult or None if no history
        """
        history = self.get_history(benchmark_name)
        return history[-1] if history else None

    def get_latest(self, benchmark_name: str) -> BenchmarkResult | None:
        """
        Get the most recent result for a benchmark.

        Args:
            benchmark_name: Name of the benchmark

        Returns:
            Latest BenchmarkResult or None if no history
        """
        history = self.get_history(benchmark_name, limit=1)
        return history[0] if history else None

    def clear(self, benchmark_name: str | None = None) -> int:
        """
        Clear stored results.

        Args:
            benchmark_name: If provided, only clear results for this benchmark

        Returns:
            Number of files deleted
        """
        pattern = f"{benchmark_name}_*.json" if benchmark_name else "*.json"
        count = 0

        for filepath in self.storage_path.glob(pattern):
            filepath.unlink()
            count += 1

        return count


# =============================================================================
# REGRESSION DETECTION
# =============================================================================


class RegressionDetector:
    """
    Detects performance regressions by comparing against baselines.

    Example:
        detector = RegressionDetector(threshold_percent=10.0)

        warnings = detector.check(current_result, baseline_result)
        for warning in warnings:
            print(warning.message)
    """

    def __init__(self, threshold_percent: float = 10.0):
        """
        Initialize the regression detector.

        Args:
            threshold_percent: Percentage increase that triggers a warning
        """
        self.threshold_percent = threshold_percent

    def check(
        self,
        current: BenchmarkResult,
        baseline: BenchmarkResult | None,
    ) -> list[RegressionWarning]:
        """
        Check for regressions against a baseline.

        Args:
            current: Current benchmark result
            baseline: Baseline to compare against

        Returns:
            List of RegressionWarning for any detected regressions
        """
        if baseline is None:
            return []

        warnings = []

        # Check mean time
        if baseline.mean_time > 0:
            pct_change = ((current.mean_time - baseline.mean_time) / baseline.mean_time) * 100

            if pct_change > self.threshold_percent:
                warnings.append(
                    RegressionWarning(
                        benchmark_name=current.name,
                        baseline_value=baseline.mean_time,
                        current_value=current.mean_time,
                        percentage_change=pct_change,
                        threshold=self.threshold_percent,
                        message=(
                            f"Performance regression in '{current.name}': "
                            f"mean time increased by {pct_change:.1f}% "
                            f"(baseline: {baseline.mean_time:.4f}s, current: {current.mean_time:.4f}s)"
                        ),
                    )
                )

        # Check p95 latency
        baseline_p95 = baseline.percentiles.get("p95", 0)
        current_p95 = current.percentiles.get("p95", 0)

        if baseline_p95 > 0:
            pct_change_p95 = ((current_p95 - baseline_p95) / baseline_p95) * 100

            if pct_change_p95 > self.threshold_percent:
                warnings.append(
                    RegressionWarning(
                        benchmark_name=current.name,
                        baseline_value=baseline_p95,
                        current_value=current_p95,
                        percentage_change=pct_change_p95,
                        threshold=self.threshold_percent,
                        message=(
                            f"P95 latency regression in '{current.name}': "
                            f"increased by {pct_change_p95:.1f}% "
                            f"(baseline: {baseline_p95:.4f}s, current: {current_p95:.4f}s)"
                        ),
                    )
                )

        return warnings


# =============================================================================
# BENCHMARK SUITE
# =============================================================================


class BenchmarkSuite:
    """
    Collection of benchmarks with integrated storage and regression detection.

    Example:
        suite = BenchmarkSuite("benchmarks/results")

        @suite.benchmark("string_concat", iterations=1000)
        def test_string_concat():
            return "hello" + " " + "world"

        results = suite.run_all()
        warnings = suite.check_regressions()
    """

    def __init__(
        self,
        storage_path: Path | str,
        regression_threshold: float = 10.0,
    ):
        """
        Initialize the benchmark suite.

        Args:
            storage_path: Directory to store results
            regression_threshold: Percentage threshold for regression warnings
        """
        self.runner = BenchmarkRunner()
        self.store = BenchmarkStore(storage_path)
        self.detector = RegressionDetector(regression_threshold)
        self._benchmarks: dict[str, tuple[Callable, int, dict]] = {}

    def register(
        self,
        name: str,
        operation: Callable[[], Any],
        iterations: int = 100,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Register a benchmark.

        Args:
            name: Benchmark identifier
            operation: Function to benchmark
            iterations: Number of iterations
            metadata: Additional metadata
        """
        self._benchmarks[name] = (operation, iterations, metadata or {})

    def benchmark(
        self,
        name: str,
        iterations: int = 100,
        metadata: dict[str, Any] | None = None,
    ) -> Callable:
        """
        Decorator to register a benchmark.

        Args:
            name: Benchmark identifier
            iterations: Number of iterations
            metadata: Additional metadata

        Returns:
            Decorator function
        """

        def decorator(func: Callable) -> Callable:
            self.register(name, func, iterations, metadata)
            return func

        return decorator

    def run(self, name: str) -> BenchmarkResult:
        """
        Run a single benchmark.

        Args:
            name: Benchmark identifier

        Returns:
            BenchmarkResult

        Raises:
            KeyError: If benchmark not found
        """
        if name not in self._benchmarks:
            raise KeyError(f"Benchmark '{name}' not found")

        operation, iterations, metadata = self._benchmarks[name]
        result = self.runner.run(name, operation, iterations, metadata)
        self.store.save(result)
        return result

    def run_all(self) -> dict[str, BenchmarkResult]:
        """
        Run all registered benchmarks.

        Returns:
            Dict mapping benchmark names to results
        """
        results = {}
        for name in self._benchmarks:
            results[name] = self.run(name)
        return results

    def check_regressions(
        self,
        results: dict[str, BenchmarkResult] | None = None,
    ) -> list[RegressionWarning]:
        """
        Check for regressions in benchmark results.

        Args:
            results: Results to check (uses latest if not provided)

        Returns:
            List of RegressionWarning
        """
        warnings = []

        if results is None:
            results = {name: self.store.get_latest(name) for name in self._benchmarks}

        for name, result in results.items():
            if result is None:
                continue

            baseline = self.store.get_baseline(name)
            warnings.extend(self.detector.check(result, baseline))

        return warnings

    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of all benchmarks.

        Returns:
            Dict with benchmark summaries
        """
        summary = {}

        for name in self._benchmarks:
            latest = self.store.get_latest(name)
            baseline = self.store.get_baseline(name)

            summary[name] = {
                "latest": latest.to_dict() if latest else None,
                "baseline": baseline.to_dict() if baseline else None,
                "history_count": len(self.store.get_history(name)),
            }

        return summary


# =============================================================================
# BUILT-IN BENCHMARKS
# =============================================================================


def create_primr_benchmark_suite(storage_path: Path | str = "benchmarks") -> BenchmarkSuite:
    """
    Create a benchmark suite with Primr-specific benchmarks.

    Args:
        storage_path: Directory to store results

    Returns:
        Configured BenchmarkSuite
    """
    suite = BenchmarkSuite(storage_path)

    # Prompt composition benchmark
    @suite.benchmark("prompt_composition", iterations=100)
    def benchmark_prompt_composition():
        """Benchmark prompt composition from YAML."""
        from primr.prompts import build_company_overview_prompt

        return build_company_overview_prompt("Test Company", website_url="https://test.com")

    # JSON serialization benchmark
    @suite.benchmark("json_serialization", iterations=1000)
    def benchmark_json_serialization():
        """Benchmark JSON serialization of complex objects."""
        data = {
            "name": "Test",
            "sections": [{"id": f"s{i}", "content": "x" * 100} for i in range(20)],
            "metadata": {"key": "value" * 10},
        }
        return json.dumps(data)

    return suite


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "BenchmarkResult",
    "BenchmarkRunner",
    "BenchmarkStore",
    "BenchmarkSuite",
    "RegressionDetector",
    "RegressionWarning",
    "create_primr_benchmark_suite",
]
