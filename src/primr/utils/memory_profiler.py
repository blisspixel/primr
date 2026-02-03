"""Memory profiling utilities for tracking allocation and detecting leaks.

This module provides memory profiling capabilities for long-running operations,
including allocation tracking, unbounded growth detection, and threshold-based warnings.

# Feature: phd-level-excellence
"""

from __future__ import annotations

import gc
import logging
import sys
import tracemalloc
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class MemorySnapshot:
    """A snapshot of memory usage at a point in time."""

    timestamp: datetime
    current_bytes: int
    peak_bytes: int
    allocation_count: int
    component: str = ""

    @property
    def current_mb(self) -> float:
        """Current memory in megabytes."""
        return self.current_bytes / (1024 * 1024)

    @property
    def peak_mb(self) -> float:
        """Peak memory in megabytes."""
        return self.peak_bytes / (1024 * 1024)


@dataclass
class MemoryReport:
    """Report of memory usage by component."""

    timestamp: datetime
    total_current_bytes: int
    total_peak_bytes: int
    by_component: dict[str, MemorySnapshot] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_current_mb(self) -> float:
        """Total current memory in megabytes."""
        return self.total_current_bytes / (1024 * 1024)

    @property
    def total_peak_mb(self) -> float:
        """Total peak memory in megabytes."""
        return self.total_peak_bytes / (1024 * 1024)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_current_mb": round(self.total_current_mb, 2),
            "total_peak_mb": round(self.total_peak_mb, 2),
            "by_component": {
                name: {
                    "current_mb": round(snap.current_mb, 2),
                    "peak_mb": round(snap.peak_mb, 2),
                    "allocation_count": snap.allocation_count,
                }
                for name, snap in self.by_component.items()
            },
            "warnings": self.warnings,
        }


@dataclass
class GrowthRecord:
    """Record of memory growth over time for an object type."""

    type_name: str
    initial_count: int
    current_count: int
    samples: list[tuple[datetime, int]] = field(default_factory=list)

    @property
    def growth_rate(self) -> float:
        """Calculate growth rate (objects per sample)."""
        if len(self.samples) < 2:
            return 0.0
        return (self.current_count - self.initial_count) / (len(self.samples) - 1)

    @property
    def is_growing(self) -> bool:
        """Check if object count is consistently growing."""
        if len(self.samples) < 3:
            return False
        # Check if last 3 samples show consistent growth
        recent = [count for _, count in self.samples[-3:]]
        return all(recent[i] < recent[i + 1] for i in range(len(recent) - 1))


@dataclass
class MemoryWarning:
    """Warning about memory usage."""

    timestamp: datetime
    message: str
    current_bytes: int
    threshold_bytes: int
    component: str = ""

    def __str__(self) -> str:
        return f"[{self.timestamp.isoformat()}] {self.message}"


class MemoryProfiler:
    """Memory profiler with allocation tracking and growth detection.

    Provides capabilities for:
    - Tracking memory during job execution
    - Identifying objects growing over time
    - Generating reports by component
    - Emitting warnings when thresholds are exceeded
    """

    def __init__(
        self,
        threshold_mb: float = 500.0,
        growth_check_interval: int = 10,
        track_types: list[str] | None = None,
    ):
        """Initialize the memory profiler.

        Args:
            threshold_mb: Memory threshold in MB for warnings
            growth_check_interval: Number of samples between growth checks
            track_types: Specific type names to track for growth (None = auto-detect)
        """
        self.threshold_bytes = int(threshold_mb * 1024 * 1024)
        self.growth_check_interval = growth_check_interval
        self.track_types = track_types

        self._snapshots: list[MemorySnapshot] = []
        self._component_snapshots: dict[str, list[MemorySnapshot]] = defaultdict(list)
        self._growth_records: dict[str, GrowthRecord] = {}
        self._warnings: list[MemoryWarning] = []
        self._listeners: list[Callable[[MemoryWarning], None]] = []
        self._is_tracking = False
        self._sample_count = 0

    def start_tracking(self) -> None:
        """Start memory tracking with tracemalloc."""
        if not self._is_tracking:
            tracemalloc.start()
            self._is_tracking = True
            self._sample_count = 0
            logger.debug("Memory tracking started")

    def stop_tracking(self) -> None:
        """Stop memory tracking."""
        if self._is_tracking:
            tracemalloc.stop()
            self._is_tracking = False
            logger.debug("Memory tracking stopped")

    def take_snapshot(self, component: str = "") -> MemorySnapshot:
        """Take a memory snapshot.

        Args:
            component: Optional component name for categorization

        Returns:
            MemorySnapshot with current memory state
        """
        if self._is_tracking:
            current, peak = tracemalloc.get_traced_memory()
            # Get allocation count from tracemalloc snapshot
            snapshot = tracemalloc.take_snapshot()
            allocation_count = len(snapshot.statistics("lineno"))
        else:
            # Fallback to sys.getsizeof approximation
            gc.collect()
            current = sum(sys.getsizeof(obj) for obj in gc.get_objects()[:1000])
            peak = current
            allocation_count = len(gc.get_objects())

        snap = MemorySnapshot(
            timestamp=datetime.now(),
            current_bytes=current,
            peak_bytes=peak,
            allocation_count=allocation_count,
            component=component,
        )

        self._snapshots.append(snap)
        if component:
            self._component_snapshots[component].append(snap)

        self._sample_count += 1

        # Check threshold
        self._check_threshold(snap)

        # Periodic growth check
        if self._sample_count % self.growth_check_interval == 0:
            self._check_growth()

        return snap

    def _check_threshold(self, snapshot: MemorySnapshot) -> None:
        """Check if memory exceeds threshold and emit warning if so."""
        if snapshot.current_bytes > self.threshold_bytes:
            warning = MemoryWarning(
                timestamp=snapshot.timestamp,
                message=f"Memory usage ({snapshot.current_mb:.1f} MB) exceeds threshold ({self.threshold_bytes / (1024*1024):.1f} MB)",
                current_bytes=snapshot.current_bytes,
                threshold_bytes=self.threshold_bytes,
                component=snapshot.component,
            )
            self._warnings.append(warning)
            self._emit_warning(warning)

    def _emit_warning(self, warning: MemoryWarning) -> None:
        """Emit warning to all listeners."""
        logger.warning(str(warning))
        for listener in self._listeners:
            try:
                listener(warning)
            except Exception as e:
                logger.error(f"Warning listener error: {e}")

    def _check_growth(self) -> None:
        """Check for unbounded object growth."""
        gc.collect()
        type_counts: dict[str, int] = defaultdict(int)

        for obj in gc.get_objects():
            type_name = type(obj).__name__
            if self.track_types is None or type_name in self.track_types:
                type_counts[type_name] += 1

        now = datetime.now()
        for type_name, count in type_counts.items():
            if type_name not in self._growth_records:
                self._growth_records[type_name] = GrowthRecord(
                    type_name=type_name,
                    initial_count=count,
                    current_count=count,
                    samples=[(now, count)],
                )
            else:
                record = self._growth_records[type_name]
                record.current_count = count
                record.samples.append((now, count))

                # Emit warning if growing unboundedly
                if record.is_growing and record.growth_rate > 100:
                    warning = MemoryWarning(
                        timestamp=now,
                        message=f"Unbounded growth detected for {type_name}: {record.initial_count} -> {count} (rate: {record.growth_rate:.1f}/sample)",
                        current_bytes=0,
                        threshold_bytes=0,
                    )
                    self._warnings.append(warning)
                    self._emit_warning(warning)

    def add_warning_listener(self, listener: Callable[[MemoryWarning], None]) -> None:
        """Add a listener for memory warnings."""
        self._listeners.append(listener)

    def get_growing_objects(self) -> list[GrowthRecord]:
        """Get list of object types showing unbounded growth."""
        return [r for r in self._growth_records.values() if r.is_growing]

    def generate_report(self) -> MemoryReport:
        """Generate a memory usage report.

        Returns:
            MemoryReport with usage by component
        """
        if not self._snapshots:
            return MemoryReport(
                timestamp=datetime.now(),
                total_current_bytes=0,
                total_peak_bytes=0,
            )

        latest = self._snapshots[-1]
        peak = max(s.peak_bytes for s in self._snapshots)

        # Aggregate by component
        by_component: dict[str, MemorySnapshot] = {}
        for component, snaps in self._component_snapshots.items():
            if snaps:
                latest_comp = snaps[-1]
                peak_comp = max(s.peak_bytes for s in snaps)
                by_component[component] = MemorySnapshot(
                    timestamp=latest_comp.timestamp,
                    current_bytes=latest_comp.current_bytes,
                    peak_bytes=peak_comp,
                    allocation_count=latest_comp.allocation_count,
                    component=component,
                )

        return MemoryReport(
            timestamp=datetime.now(),
            total_current_bytes=latest.current_bytes,
            total_peak_bytes=peak,
            by_component=by_component,
            warnings=[str(w) for w in self._warnings],
        )

    def clear(self) -> None:
        """Clear all recorded data."""
        self._snapshots.clear()
        self._component_snapshots.clear()
        self._growth_records.clear()
        self._warnings.clear()
        self._sample_count = 0

    @contextmanager
    def profile(self, component: str = ""):
        """Context manager for profiling a code block.

        Args:
            component: Component name for the profiled block

        Yields:
            The profiler instance
        """
        was_tracking = self._is_tracking
        if not was_tracking:
            self.start_tracking()

        self.take_snapshot(component)
        try:
            yield self
        finally:
            self.take_snapshot(component)
            if not was_tracking:
                self.stop_tracking()


class MemoryProfilerFixture:
    """Pytest fixture helper for memory regression tests.

    Usage in pytest:
        @pytest.fixture
        def memory_profiler():
            return MemoryProfilerFixture(threshold_mb=100)

        def test_no_memory_leak(memory_profiler):
            with memory_profiler.track("my_operation"):
                # ... code to test ...
            memory_profiler.assert_no_growth()
    """

    def __init__(self, threshold_mb: float = 100.0, max_growth_rate: float = 10.0):
        """Initialize the fixture.

        Args:
            threshold_mb: Memory threshold for warnings
            max_growth_rate: Maximum allowed growth rate before failure
        """
        self.profiler = MemoryProfiler(threshold_mb=threshold_mb)
        self.max_growth_rate = max_growth_rate
        self._warnings: list[MemoryWarning] = []
        self.profiler.add_warning_listener(self._warnings.append)

    @contextmanager
    def track(self, component: str = ""):
        """Track memory for a code block."""
        with self.profiler.profile(component):
            yield

    def assert_no_growth(self, allowed_types: list[str] | None = None) -> None:
        """Assert no unbounded memory growth.

        Args:
            allowed_types: Type names that are allowed to grow

        Raises:
            AssertionError: If unbounded growth is detected
        """
        allowed = set(allowed_types or [])
        growing = self.profiler.get_growing_objects()

        problematic = [
            r for r in growing
            if r.type_name not in allowed and r.growth_rate > self.max_growth_rate
        ]

        if problematic:
            details = "\n".join(
                f"  - {r.type_name}: {r.initial_count} -> {r.current_count} (rate: {r.growth_rate:.1f})"
                for r in problematic
            )
            raise AssertionError(f"Unbounded memory growth detected:\n{details}")

    def assert_under_threshold(self) -> None:
        """Assert memory stayed under threshold.

        Raises:
            AssertionError: If threshold was exceeded
        """
        if self._warnings:
            raise AssertionError(f"Memory threshold exceeded: {self._warnings[0]}")

    def get_report(self) -> MemoryReport:
        """Get the memory report."""
        return self.profiler.generate_report()
