"""
Shared polling heuristics for Deep Research progress/status checks.
"""

from __future__ import annotations


def phase_name_for_elapsed(elapsed_seconds: float) -> str:
    """Map elapsed seconds to a human-readable phase name."""
    if elapsed_seconds < 60:
        return "Initializing"
    if elapsed_seconds < 180:
        return "Searching sources"
    if elapsed_seconds < 360:
        return "Analyzing findings"
    if elapsed_seconds < 600:
        return "Generating report"
    return "Finalizing"


def poll_interval_for_elapsed(
    elapsed_seconds: float,
    schedule: tuple[tuple[float, float], ...],
    default_interval: float,
) -> float:
    """
    Return polling interval based on elapsed time and a threshold schedule.

    Args:
        elapsed_seconds: Seconds since operation start.
        schedule: Ordered (threshold, interval) pairs where threshold is an
            exclusive upper bound.
        default_interval: Interval used when no threshold matches.
    """
    for threshold, interval in schedule:
        if elapsed_seconds < threshold:
            return interval
    return default_interval
