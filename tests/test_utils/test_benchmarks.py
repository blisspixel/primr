"""Tests for primr.utils.benchmarks.

Covers BenchmarkResult round-trip, BenchmarkRunner statistics calculation,
BenchmarkStore persistence + history retrieval, RegressionDetector
threshold logic, BenchmarkSuite registration/run/summary, and the
factory that builds the Primr-specific suite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from primr.utils.benchmarks import (
    BenchmarkResult,
    BenchmarkRunner,
    BenchmarkStore,
    BenchmarkSuite,
    RegressionDetector,
    RegressionWarning,
    create_primr_benchmark_suite,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# BenchmarkResult dataclass
# ---------------------------------------------------------------------------


class TestBenchmarkResult:
    def _sample(self, name: str = "bm") -> BenchmarkResult:
        return BenchmarkResult(
            name=name,
            duration_seconds=1.5,
            iterations=10,
            mean_time=0.15,
            std_dev=0.01,
            min_time=0.13,
            max_time=0.18,
            percentiles={"p50": 0.15, "p90": 0.17, "p95": 0.175, "p99": 0.18},
            metadata={"git_sha": "abc"},
        )

    def test_to_dict_includes_all_fields(self):
        r = self._sample()
        d = r.to_dict()
        assert d["name"] == "bm"
        assert d["duration_seconds"] == 1.5
        assert d["iterations"] == 10
        assert d["mean_time"] == 0.15
        assert d["std_dev"] == 0.01
        assert d["min_time"] == 0.13
        assert d["max_time"] == 0.18
        assert d["percentiles"]["p95"] == 0.175
        assert d["metadata"]["git_sha"] == "abc"
        assert "timestamp" in d  # ISO string

    def test_from_dict_round_trip(self):
        r = self._sample()
        clone = BenchmarkResult.from_dict(r.to_dict())
        assert clone.name == r.name
        assert clone.duration_seconds == r.duration_seconds
        assert clone.iterations == r.iterations
        assert clone.mean_time == r.mean_time
        assert clone.percentiles == r.percentiles
        assert clone.metadata == r.metadata

    def test_from_dict_defaults_for_missing_optional(self):
        minimal = {
            "name": "x",
            "duration_seconds": 0.5,
            "iterations": 5,
            "mean_time": 0.1,
            "std_dev": 0.01,
            "min_time": 0.09,
            "max_time": 0.11,
            "timestamp": self._sample().timestamp.isoformat(),
        }
        r = BenchmarkResult.from_dict(minimal)
        assert r.percentiles == {}
        assert r.metadata == {}


# ---------------------------------------------------------------------------
# BenchmarkRunner
# ---------------------------------------------------------------------------


class TestBenchmarkRunner:
    def test_run_collects_iterations_and_stats(self):
        runner = BenchmarkRunner(warmup_iterations=1)
        calls = [0]

        def op():
            calls[0] += 1

        r = runner.run("noop", op, iterations=10)
        assert r.name == "noop"
        assert r.iterations == 10
        # 10 timed + 1 warmup = 11 actual invocations
        assert calls[0] == 11
        assert r.mean_time >= 0
        assert r.min_time <= r.max_time
        assert set(r.percentiles.keys()) == {"p50", "p90", "p95", "p99"}

    def test_run_with_metadata(self):
        runner = BenchmarkRunner()
        r = runner.run("with_meta", lambda: None, iterations=5, metadata={"k": "v"})
        assert r.metadata == {"k": "v"}

    def test_single_iteration_zero_stddev(self):
        runner = BenchmarkRunner(warmup_iterations=0)
        r = runner.run("solo", lambda: None, iterations=1)
        assert r.iterations == 1
        assert r.std_dev == 0.0

    def test_percentile_empty_data_returns_zero(self):
        runner = BenchmarkRunner()
        assert runner._percentile([], 50) == 0.0

    def test_percentile_interpolation(self):
        runner = BenchmarkRunner()
        # Sorted data [1, 2, 3, 4, 5]
        # p50 is the middle value (index 2.0) = 3.0
        assert runner._percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == pytest.approx(3.0)

    def test_percentile_at_max(self):
        runner = BenchmarkRunner()
        # p100 should be exactly the max
        assert runner._percentile([1.0, 2.0, 3.0], 100) == 3.0


# ---------------------------------------------------------------------------
# BenchmarkStore
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> BenchmarkStore:
    return BenchmarkStore(tmp_path / "bench")


def _make_result(name: str = "bm", mean_time: float = 0.1) -> BenchmarkResult:
    return BenchmarkResult(
        name=name,
        duration_seconds=1.0,
        iterations=10,
        mean_time=mean_time,
        std_dev=0.01,
        min_time=mean_time - 0.01,
        max_time=mean_time + 0.01,
        percentiles={"p95": mean_time + 0.005},
    )


class TestBenchmarkStore:
    def test_save_creates_file(self, store: BenchmarkStore):
        r = _make_result()
        path = store.save(r)
        assert path.exists()
        assert path.suffix == ".json"
        assert path.name.startswith("bm_")

    def test_save_then_get_latest(self, store: BenchmarkStore):
        r = _make_result(mean_time=0.5)
        store.save(r)
        latest = store.get_latest("bm")
        assert latest is not None
        assert latest.mean_time == 0.5

    def test_get_latest_returns_none_when_empty(self, store: BenchmarkStore):
        assert store.get_latest("nonexistent") is None

    def test_get_history_returns_newest_first(self, store: BenchmarkStore):
        import time

        for _i, mean in enumerate([0.1, 0.2, 0.3]):
            r = _make_result(mean_time=mean)
            store.save(r)
            time.sleep(0.01)  # ensure distinct microsecond timestamps in filename

        history = store.get_history("bm")
        assert len(history) == 3
        # Newest first (highest mean_time saved last)
        assert history[0].mean_time == 0.3
        assert history[-1].mean_time == 0.1

    def test_get_history_respects_limit(self, store: BenchmarkStore):
        import time

        for i in range(5):
            store.save(_make_result(mean_time=0.1 + i * 0.01))
            time.sleep(0.005)

        history = store.get_history("bm", limit=2)
        assert len(history) == 2

    def test_get_baseline_is_oldest(self, store: BenchmarkStore):
        import time

        store.save(_make_result(mean_time=0.10))
        time.sleep(0.01)
        store.save(_make_result(mean_time=0.50))

        baseline = store.get_baseline("bm")
        assert baseline is not None
        assert baseline.mean_time == 0.10

    def test_get_baseline_returns_none_when_empty(self, store: BenchmarkStore):
        assert store.get_baseline("nope") is None

    def test_clear_specific_benchmark(self, store: BenchmarkStore):
        store.save(_make_result("a"))
        store.save(_make_result("b"))
        cleared = store.clear("a")
        assert cleared == 1
        assert store.get_latest("a") is None
        assert store.get_latest("b") is not None

    def test_clear_all(self, store: BenchmarkStore):
        store.save(_make_result("a"))
        store.save(_make_result("b"))
        cleared = store.clear()
        assert cleared == 2

    def test_get_history_skips_corrupted_files(self, store: BenchmarkStore):
        store.save(_make_result("bm"))
        # Plant a corrupt file matching the glob pattern
        (store.storage_path / "bm_BADTIMESTAMP.json").write_text("{not json")
        history = store.get_history("bm")
        # Corrupt entry is logged + skipped; valid one remains
        assert len(history) == 1


# ---------------------------------------------------------------------------
# RegressionDetector
# ---------------------------------------------------------------------------


class TestRegressionDetector:
    def test_no_baseline_returns_empty(self):
        d = RegressionDetector()
        assert d.check(_make_result(), None) == []

    def test_no_regression_when_within_threshold(self):
        d = RegressionDetector(threshold_percent=10.0)
        baseline = _make_result(mean_time=0.10)
        current = _make_result(mean_time=0.105)  # 5% slower
        warnings = d.check(current, baseline)
        assert warnings == []

    def test_mean_time_regression_above_threshold(self):
        d = RegressionDetector(threshold_percent=10.0)
        baseline = _make_result(mean_time=0.10)
        current = _make_result(mean_time=0.15)  # 50% slower
        warnings = d.check(current, baseline)
        assert any("mean time" in w.message for w in warnings)
        warn = next(w for w in warnings if "mean time" in w.message)
        assert isinstance(warn, RegressionWarning)
        assert warn.percentage_change == pytest.approx(50.0)

    def test_p95_regression_above_threshold(self):
        d = RegressionDetector(threshold_percent=10.0)
        baseline = BenchmarkResult(
            name="x",
            duration_seconds=1.0,
            iterations=10,
            mean_time=0.10,
            std_dev=0.01,
            min_time=0.09,
            max_time=0.11,
            percentiles={"p95": 0.10},
        )
        current = BenchmarkResult(
            name="x",
            duration_seconds=1.0,
            iterations=10,
            mean_time=0.10,  # same mean
            std_dev=0.01,
            min_time=0.09,
            max_time=0.20,
            percentiles={"p95": 0.20},  # but p95 doubled
        )
        warnings = d.check(current, baseline)
        assert any("P95" in w.message for w in warnings)

    def test_no_p95_warning_when_baseline_p95_missing(self):
        d = RegressionDetector(threshold_percent=10.0)
        baseline = _make_result(mean_time=0.10)
        baseline.percentiles = {}
        current = _make_result(mean_time=0.10)
        current.percentiles = {"p95": 99.0}
        warnings = d.check(current, baseline)
        # No p95 warning since baseline p95 is 0/missing
        assert not any("P95" in w.message for w in warnings)

    def test_zero_baseline_mean_skips_warning(self):
        d = RegressionDetector(threshold_percent=10.0)
        baseline = _make_result(mean_time=0.0)
        current = _make_result(mean_time=10.0)
        warnings = d.check(current, baseline)
        assert not any("mean time" in w.message for w in warnings)


# ---------------------------------------------------------------------------
# BenchmarkSuite
# ---------------------------------------------------------------------------


@pytest.fixture
def suite(tmp_path: Path) -> BenchmarkSuite:
    return BenchmarkSuite(tmp_path / "suite_results", regression_threshold=15.0)


class TestBenchmarkSuite:
    def test_register_and_run(self, suite: BenchmarkSuite):
        suite.register("simple", lambda: None, iterations=5)
        r = suite.run("simple")
        assert r.name == "simple"
        assert r.iterations == 5

    def test_register_with_metadata(self, suite: BenchmarkSuite):
        suite.register("simple", lambda: None, iterations=3, metadata={"k": "v"})
        r = suite.run("simple")
        assert r.metadata == {"k": "v"}

    def test_run_unknown_raises(self, suite: BenchmarkSuite):
        with pytest.raises(KeyError, match="nonexistent"):
            suite.run("nonexistent")

    def test_decorator_registers(self, suite: BenchmarkSuite):
        @suite.benchmark("decorated", iterations=5)
        def _op():
            return 42

        r = suite.run("decorated")
        assert r.name == "decorated"

    def test_run_all(self, suite: BenchmarkSuite):
        suite.register("a", lambda: None, iterations=3)
        suite.register("b", lambda: None, iterations=3)
        results = suite.run_all()
        assert set(results.keys()) == {"a", "b"}

    def test_check_regressions_with_no_history_is_empty(self, suite: BenchmarkSuite):
        suite.register("a", lambda: None, iterations=3)
        suite.run("a")
        # Only one result so baseline == current → no warning
        assert suite.check_regressions() == []

    def test_check_regressions_with_provided_results(self, suite: BenchmarkSuite):
        suite.register("a", lambda: None, iterations=3)
        # Pre-populate baseline
        suite.store.save(_make_result("a", mean_time=0.01))
        bad = _make_result("a", mean_time=1.0)  # 9900% slower
        warnings = suite.check_regressions({"a": bad})
        assert len(warnings) >= 1

    def test_check_regressions_skips_none_results(self, suite: BenchmarkSuite):
        suite.register("a", lambda: None, iterations=3)
        warnings = suite.check_regressions({"a": None})
        assert warnings == []

    def test_get_summary(self, suite: BenchmarkSuite):
        suite.register("a", lambda: None, iterations=3)
        suite.run("a")
        s = suite.get_summary()
        assert "a" in s
        assert s["a"]["latest"] is not None
        assert s["a"]["history_count"] >= 1


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestPrimrBenchmarkSuite:
    def test_factory_returns_configured_suite(self, tmp_path: Path):
        suite = create_primr_benchmark_suite(storage_path=tmp_path / "primr_bench")
        assert isinstance(suite, BenchmarkSuite)
        assert "prompt_composition" in suite._benchmarks
        assert "json_serialization" in suite._benchmarks

    def test_factory_default_storage_path(self):
        # Just verify it doesn't crash with the default path
        suite = create_primr_benchmark_suite()
        assert isinstance(suite, BenchmarkSuite)

    def test_factory_benchmarks_are_callable(self, tmp_path: Path):
        suite = create_primr_benchmark_suite(storage_path=tmp_path / "primr_bench")
        # Just run JSON serialization since it has no external deps
        r = suite.run("json_serialization")
        assert r.iterations > 0
        assert r.mean_time >= 0
