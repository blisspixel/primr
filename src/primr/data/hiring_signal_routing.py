"""Route-ledger helpers for hiring-signal extraction."""

from __future__ import annotations

from typing import Any

from primr.ai import stage_routing
from primr.ai.provider_availability import LocalCapacityBusyError
from primr.utils.observability import log_structured


def record_hiring_route(
    folder_path: str | None,
    route: stage_routing.StageModelRoute,
    *,
    outcome: str,
    input_count: int,
    output_count: int,
    duration_seconds: float,
    failure_class: str | None = None,
    failure: Exception | None = None,
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
        failure=failure,
        usage_delta=usage_delta,
    )


def record_hiring_capacity_busy(
    folder_path: str | None,
    route: stage_routing.StageModelRoute | None,
    error: LocalCapacityBusyError,
    *,
    input_count: int,
    duration_seconds: float,
    usage_delta: dict[str, Any] | None = None,
) -> None:
    """Record and log only the typed error's body-free capacity metadata."""

    if route is not None:
        record_hiring_route(
            folder_path,
            route,
            outcome="fallback",
            input_count=input_count,
            output_count=0,
            duration_seconds=duration_seconds,
            failure_class=stage_routing.stage_route_failure_class(route, error),
            failure=error,
            usage_delta=usage_delta,
        )
    log_structured(
        "warning",
        "Hiring signals local capacity busy",
        posting_count=input_count,
        **error.as_metadata(),
    )
