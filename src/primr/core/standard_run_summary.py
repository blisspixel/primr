"""Final cost, usage, and lifecycle accounting for the standard runtime."""

from __future__ import annotations

from datetime import datetime

from primr.core.standard_strategy import StandardStrategyResult
from primr.utils.console import console
from primr.utils.observability import JobSummary, log_job_summary


def finalize_standard_run(
    *,
    mode: str,
    display_name: str,
    folder_path: str,
    elapsed: float,
    time_str: str,
    sections_generated: int,
    docx_path: str | None,
    strategy: StandardStrategyResult,
) -> float:
    """Persist one standard run's exact token and flat-task cost components."""

    from primr.ai.client import get_client
    from primr.core.deep_budget import deep_research_flat_cost

    usage = get_client().get_usage_summary()
    pipeline_cost = usage.get("total_cost", 0.0)
    strategy_cost = deep_research_flat_cost(strategy.deep_research_tasks_started)
    vendor_refresh_cost = deep_research_flat_cost(strategy.vendor_refresh_tasks_started)
    actual_cost = pipeline_cost + strategy_cost + vendor_refresh_cost

    summary_items = [
        ("Duration", time_str),
        ("Cost", f"${actual_cost:.2f}"),
    ]
    if strategy.vendor_refresh_tasks_started:
        summary_items.append(
            (
                "Vendor Refresh",
                f"{strategy.vendor_refresh_tasks_started} task(s)  ~${vendor_refresh_cost:.2f}",
            )
        )
    if strategy.outcome.status != "not_requested":
        summary_items.append(("Strategy Status", strategy.outcome.status.upper()))
    if strategy.vendor_refresh_outcome.status != "not_requested":
        summary_items.append(
            ("Vendor Refresh Status", strategy.vendor_refresh_outcome.status.upper())
        )
    console.summary(summary_items)

    from primr.utils.usage_tracker import get_usage_tracker

    tracker = get_usage_tracker()
    tracker.record_usage(
        mode=mode,
        company=display_name,
        input_tokens=usage.get("total_input_tokens", 0),
        output_tokens=usage.get("total_output_tokens", 0),
        duration_seconds=elapsed,
        pipeline_cost=pipeline_cost,
        deep_research_cost=strategy_cost,
    )
    tracker.save()

    log_job_summary(
        JobSummary.create(
            company=display_name,
            mode=mode,
            duration_seconds=elapsed,
            api_calls=usage.get("api_calls", 0),
            total_tokens=usage.get("total_input_tokens", 0) + usage.get("total_output_tokens", 0),
            sections_generated=sections_generated,
            output_path=docx_path,
        )
    )

    from primr.core.run_state_io import _append_run_event, _update_run_state

    _update_run_state(
        folder_path,
        status="completed",
        current_phase="complete",
        completed_at=datetime.now().isoformat(),
        duration_seconds=elapsed,
        actual_cost_usd=round(actual_cost, 4),
    )
    _append_run_event(folder_path, "complete", "completed", f"Run completed in {time_str}")
    return actual_cost
