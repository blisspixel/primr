"""Small helpers shared by compact MCP summary resources."""

from __future__ import annotations

from typing import Any


def safe_int(value: Any) -> int:
    """Return a non-negative integer, or zero when parsing fails."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float | None:
    """Return a float when a value is numeric, otherwise None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def scalar_or_none(value: Any) -> str | int | float | bool | None:
    """Return JSON-scalar values only."""
    if isinstance(value, str | int | float | bool):
        return value
    return None


def sorted_counts(counts: dict[str, int]) -> list[dict[str, int | str]]:
    """Return count buckets sorted by descending frequency, then value."""
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
