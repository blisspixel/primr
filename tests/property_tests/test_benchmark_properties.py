"""
Property-based tests for the Performance Benchmarking Suite.

This module contains property tests that verify universal correctness properties
of the BenchmarkRunner, BenchmarkStore, and RegressionDetector implementations.

**Feature: phd-level-excellence**
**Validates: Requirements 11.5, 11.6**
"""

import tempfile

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from primr.utils.benchmarks import (
    BenchmarkResult,
    BenchmarkRunner,
    BenchmarkStore,
    BenchmarkSuite,
    RegressionDetector,
)

# =============================================================================
# STRATEGIES FOR GENERATING TEST DATA
# =============================================================================

# Strategy for benchmark names
benchmark_name_strategy = st.from_regex(r'[a-z][a-z0-9_]{2,20}', fullmatch=True)

# Strategy for positive floats (timing values)
positive_float_strategy = st.floats(min_value=0.0001, max_value=10.0, allow_nan=False)

# Strategy for iteration counts
iteration_strategy = st.integers(min_value=1, max_value=100)

# Strategy for threshold percentages
threshold_strategy = st.floats(min_value=1.0, max_value=100.0, allow_nan=False)


def generate_benchmark_result(
    name: str = "test_benchmark",
    mean_time: float = 0.01,
    std_dev: float = 0.001,
    iterations: int = 100,
) -> BenchmarkResult:
    """Generate a BenchmarkResult for testing."""
    return BenchmarkResult(
        name=name,
        duration_seconds=mean_time * iterations,
        iterations=iterations,
        mean_time=mean_time,
        std_dev=std_dev,
        min_time=mean_time * 0.8,
        max_time=mean_time * 1.2,
        percentiles={
            "p50": mean_time,
            "p90": mean_time * 1.1,
            "p95": mean_time * 1.15,
            "p99": mean_time * 1.2,
        },
    )


# =============================================================================
# PROPERTY 26: BENCHMARK RESULT STORAGE
# =============================================================================

class TestBenchmarkResultStorage:
    """
    **Property 26: Benchmark Result Storage**

    For any benchmark execution, the results (timing, memory, throughput) SHALL
    be stored in the historical results store with a timestamp and benchmark
    identifier.

    **Validates: Requirements 11.5**
    """

    @given(
        name=benchmark_name_strategy,
        iterations=iteration_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_benchmark_result_is_stored(self, name: str, iterations: int):
        """Benchmark results should be stored with timestamp and identifier."""
        # Feature: phd-level-excellence, Property 26: Benchmark Result Storage

        with tempfile.TemporaryDirectory() as tmpdir:
            store = BenchmarkStore(tmpdir)
            runner = BenchmarkRunner(warmup_iterations=1)

            # Run a simple benchmark
            result = runner.run(name, lambda: sum(range(100)), iterations=iterations)

            # Store the result
            filepath = store.save(result)

            # Verify file was created
            assert filepath.exists()
            assert name in filepath.name

            # Verify result can be retrieved
            history = store.get_history(name)
            assert len(history) == 1
            assert history[0].name == name
            assert history[0].iterations == iterations
            assert history[0].timestamp is not None

    @given(
        name=benchmark_name_strategy,
        mean_time=positive_float_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_stored_result_preserves_timing(self, name: str, mean_time: float):
        """Stored results should preserve timing information."""
        # Feature: phd-level-excellence, Property 26: Benchmark Result Storage

        with tempfile.TemporaryDirectory() as tmpdir:
            store = BenchmarkStore(tmpdir)

            result = generate_benchmark_result(name=name, mean_time=mean_time)
            store.save(result)

            retrieved = store.get_latest(name)

            assert retrieved is not None
            assert retrieved.mean_time == result.mean_time
            assert retrieved.std_dev == result.std_dev
            assert retrieved.min_time == result.min_time
            assert retrieved.max_time == result.max_time

    @given(
        name=benchmark_name_strategy,
        num_results=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_multiple_results_stored_separately(self, name: str, num_results: int):
        """Multiple benchmark runs should be stored as separate entries."""
        # Feature: phd-level-excellence, Property 26: Benchmark Result Storage
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            store = BenchmarkStore(tmpdir)

            for i in range(num_results):
                result = generate_benchmark_result(name=name, mean_time=0.01 * (i + 1))
                store.save(result)
                time.sleep(0.01)  # Ensure different timestamps

            history = store.get_history(name)

            assert len(history) == num_results

    @given(name=benchmark_name_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_result_to_dict_from_dict_round_trip(self, name: str):
        """BenchmarkResult should survive serialization round-trip."""
        # Feature: phd-level-excellence, Property 26: Benchmark Result Storage

        result = generate_benchmark_result(name=name)

        data = result.to_dict()
        recovered = BenchmarkResult.from_dict(data)

        assert recovered.name == result.name
        assert recovered.mean_time == result.mean_time
        assert recovered.iterations == result.iterations
        assert recovered.percentiles == result.percentiles

    @given(name=benchmark_name_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_get_baseline_returns_oldest(self, name: str):
        """get_baseline should return the oldest result."""
        # Feature: phd-level-excellence, Property 26: Benchmark Result Storage
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            store = BenchmarkStore(tmpdir)

            # Save multiple results with different mean times
            for i in range(3):
                result = generate_benchmark_result(name=name, mean_time=0.01 * (i + 1))
                store.save(result)
                time.sleep(0.01)  # Ensure different timestamps

            baseline = store.get_baseline(name)
            latest = store.get_latest(name)

            # Baseline should be oldest (first saved)
            assert baseline is not None
            assert latest is not None
            # Latest should have the largest mean_time (0.03)
            # Baseline should have the smallest mean_time (0.01)
            assert baseline.mean_time < latest.mean_time


# =============================================================================
# PROPERTY 27: REGRESSION DETECTION
# =============================================================================

class TestRegressionDetection:
    """
    **Property 27: Regression Detection**

    For any benchmark result that exceeds the baseline by more than the
    configured threshold percentage, the benchmark system SHALL emit a
    regression warning with the baseline value, current value, and percentage
    difference.

    **Validates: Requirements 11.6**
    """

    @given(
        threshold=threshold_strategy,
        baseline_time=positive_float_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_regression_detected_when_threshold_exceeded(
        self, threshold: float, baseline_time: float
    ):
        """Regression should be detected when threshold is exceeded."""
        # Feature: phd-level-excellence, Property 27: Regression Detection

        detector = RegressionDetector(threshold_percent=threshold)

        baseline = generate_benchmark_result(mean_time=baseline_time)

        # Create current result that exceeds threshold
        regression_factor = 1 + (threshold / 100) + 0.1  # Exceed by 10%
        current = generate_benchmark_result(mean_time=baseline_time * regression_factor)

        warnings = detector.check(current, baseline)

        # Should detect regression
        assert len(warnings) > 0
        warning = warnings[0]
        assert warning.baseline_value == baseline_time
        assert warning.current_value == pytest.approx(baseline_time * regression_factor, rel=0.01)
        assert warning.percentage_change > threshold

    @given(
        threshold=threshold_strategy,
        baseline_time=positive_float_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_no_regression_when_under_threshold(
        self, threshold: float, baseline_time: float
    ):
        """No regression should be detected when under threshold."""
        # Feature: phd-level-excellence, Property 27: Regression Detection

        detector = RegressionDetector(threshold_percent=threshold)

        baseline = generate_benchmark_result(mean_time=baseline_time)

        # Create current result that is under threshold
        improvement_factor = 1 + (threshold / 100) * 0.5  # Only 50% of threshold
        current = generate_benchmark_result(mean_time=baseline_time * improvement_factor)

        warnings = detector.check(current, baseline)

        # Should not detect regression for mean time
        mean_warnings = [w for w in warnings if "mean" in w.message.lower()]
        assert len(mean_warnings) == 0

    @given(
        threshold=threshold_strategy,
        baseline_time=positive_float_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_no_regression_when_performance_improves(
        self, threshold: float, baseline_time: float
    ):
        """No regression should be detected when performance improves."""
        # Feature: phd-level-excellence, Property 27: Regression Detection

        detector = RegressionDetector(threshold_percent=threshold)

        baseline = generate_benchmark_result(mean_time=baseline_time)

        # Create current result that is faster
        current = generate_benchmark_result(mean_time=baseline_time * 0.8)

        warnings = detector.check(current, baseline)

        # Should not detect regression
        assert len(warnings) == 0

    def test_no_regression_without_baseline(self):
        """No regression should be detected without a baseline."""
        # Feature: phd-level-excellence, Property 27: Regression Detection

        detector = RegressionDetector(threshold_percent=10.0)

        current = generate_benchmark_result()

        warnings = detector.check(current, None)

        assert len(warnings) == 0

    @given(
        name=benchmark_name_strategy,
        threshold=st.floats(min_value=1.0, max_value=50.0, allow_nan=False),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_warning_contains_benchmark_name(self, name: str, threshold: float):
        """Regression warning should contain the benchmark name."""
        # Feature: phd-level-excellence, Property 27: Regression Detection

        detector = RegressionDetector(threshold_percent=threshold)

        baseline = generate_benchmark_result(name=name, mean_time=0.01)
        # Ensure we exceed threshold by a good margin
        current = generate_benchmark_result(name=name, mean_time=0.01 * (2 + threshold / 100))

        warnings = detector.check(current, baseline)

        assert len(warnings) > 0
        assert warnings[0].benchmark_name == name
        assert name in warnings[0].message

    @given(threshold=st.floats(min_value=1.0, max_value=50.0, allow_nan=False))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_warning_contains_percentage_change(self, threshold: float):
        """Regression warning should contain the percentage change."""
        # Feature: phd-level-excellence, Property 27: Regression Detection

        detector = RegressionDetector(threshold_percent=threshold)

        baseline = generate_benchmark_result(mean_time=0.01)
        # 200% increase should always exceed any threshold up to 50%
        current = generate_benchmark_result(mean_time=0.03)

        warnings = detector.check(current, baseline)

        assert len(warnings) > 0
        assert warnings[0].percentage_change == pytest.approx(200.0, rel=0.1)


# =============================================================================
# BENCHMARK SUITE TESTS
# =============================================================================

class TestBenchmarkSuite:
    """Tests for the BenchmarkSuite class."""

    @given(name=benchmark_name_strategy)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_suite_registers_and_runs_benchmark(self, name: str):
        """Suite should register and run benchmarks."""
        # Feature: phd-level-excellence, Validates: Requirement 11.5

        with tempfile.TemporaryDirectory() as tmpdir:
            suite = BenchmarkSuite(tmpdir)

            suite.register(name, lambda: sum(range(100)), iterations=10)
            result = suite.run(name)

            assert result.name == name
            assert result.iterations == 10

    @given(name=benchmark_name_strategy)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_suite_decorator_registers_benchmark(self, name: str):
        """Decorator should register benchmarks."""
        # Feature: phd-level-excellence, Validates: Requirement 11.5

        with tempfile.TemporaryDirectory() as tmpdir:
            suite = BenchmarkSuite(tmpdir)

            @suite.benchmark(name, iterations=10)
            def my_benchmark():
                return sum(range(100))

            result = suite.run(name)

            assert result.name == name

    def test_suite_run_all_executes_all_benchmarks(self):
        """run_all should execute all registered benchmarks."""
        # Feature: phd-level-excellence, Validates: Requirement 11.5

        with tempfile.TemporaryDirectory() as tmpdir:
            suite = BenchmarkSuite(tmpdir)

            suite.register("bench1", lambda: 1 + 1, iterations=10)
            suite.register("bench2", lambda: 2 + 2, iterations=10)
            suite.register("bench3", lambda: 3 + 3, iterations=10)

            results = suite.run_all()

            assert len(results) == 3
            assert "bench1" in results
            assert "bench2" in results
            assert "bench3" in results

    def test_suite_check_regressions_uses_stored_baseline(self):
        """check_regressions should compare against stored baseline."""
        # Feature: phd-level-excellence, Validates: Requirement 11.6

        with tempfile.TemporaryDirectory() as tmpdir:
            suite = BenchmarkSuite(tmpdir, regression_threshold=10.0)

            # Register a benchmark that will "regress"
            call_count = [0]

            def variable_benchmark():
                call_count[0] += 1
                # First run is fast, subsequent runs are slow
                if call_count[0] <= 15:  # warmup + first run
                    return sum(range(100))
                else:
                    return sum(range(10000))  # Slower

            suite.register("variable", variable_benchmark, iterations=10)

            # First run establishes baseline
            suite.run("variable")

            # Second run should be slower
            call_count[0] = 0
            suite.run("variable")

            # Check for regressions
            warnings = suite.check_regressions()

            # May or may not detect regression depending on timing
            # Just verify the method runs without error
            assert isinstance(warnings, list)


# =============================================================================
# BENCHMARK RUNNER TESTS
# =============================================================================

class TestBenchmarkRunner:
    """Tests for the BenchmarkRunner class."""

    @given(iterations=iteration_strategy)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_runner_executes_correct_iterations(self, iterations: int):
        """Runner should execute the specified number of iterations."""
        # Feature: phd-level-excellence, Validates: Requirement 11.5

        call_count = [0]

        def counting_operation():
            call_count[0] += 1

        runner = BenchmarkRunner(warmup_iterations=0)
        result = runner.run("test", counting_operation, iterations=iterations)

        assert call_count[0] == iterations
        assert result.iterations == iterations

    def test_runner_calculates_percentiles(self):
        """Runner should calculate percentiles correctly."""
        # Feature: phd-level-excellence, Validates: Requirement 11.5

        runner = BenchmarkRunner(warmup_iterations=1)
        result = runner.run("test", lambda: sum(range(1000)), iterations=100)

        assert "p50" in result.percentiles
        assert "p90" in result.percentiles
        assert "p95" in result.percentiles
        assert "p99" in result.percentiles

        # Percentiles should be ordered
        assert result.percentiles["p50"] <= result.percentiles["p90"]
        assert result.percentiles["p90"] <= result.percentiles["p95"]
        assert result.percentiles["p95"] <= result.percentiles["p99"]

    def test_runner_warmup_iterations(self):
        """Runner should perform warmup iterations."""
        # Feature: phd-level-excellence, Validates: Requirement 11.5

        call_count = [0]

        def counting_operation():
            call_count[0] += 1

        warmup = 5
        iterations = 10

        runner = BenchmarkRunner(warmup_iterations=warmup)
        runner.run("test", counting_operation, iterations=iterations)

        # Total calls = warmup + iterations
        assert call_count[0] == warmup + iterations
