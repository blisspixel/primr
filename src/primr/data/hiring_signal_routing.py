"""Route-ledger helpers for hiring-signal extraction."""

from __future__ import annotations

from typing import Any

from primr.ai import stage_routing


def record_hiring_route(
    folder_path: str | None,
    route: stage_routing.StageModelRoute,
    *,
    outcome: str,
    input_count: int,
    output_count: int,
    duration_seconds: float,
    failure_class: str | None = None,
    usage_delta: dict[str, Any] | None = None,
) -> None:
    """Record body-free hiring-signal route metadata in run state."""

    stage_routing.record_stage_route_usage(
        folder_path,
        route,
        outcome=outcome,
        input_items=input_count,
        output_items=output_count,
        duration_seconds=duration_seconds,
        failure_class=failure_class,
        usage_delta=usage_delta,
    )
