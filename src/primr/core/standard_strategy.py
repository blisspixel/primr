"""Optional AI Strategy stage for the legacy structured research runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from primr.core.strategy_outcome import (
    StrategyOutcome,
    StrategyOutcomeTracker,
    StrategyTaskTracker,
    expected_strategy_targets,
    persist_strategy_outcome,
    strategy_target,
)
from primr.core.vendor_refresh_outcome import (
    VendorRefreshOutcome,
    VendorRefreshTracker,
    persist_vendor_refresh_outcome,
)
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("core.standard_strategy")


@dataclass(frozen=True)
class StandardStrategyResult:
    """Artifact and provider-task accounting for the standard strategy stage."""

    output_path: str | None
    outcome: StrategyOutcome
    deep_research_tasks_started: int = 0
    vendor_refresh_tasks_started: int = 0
    vendor_refresh_outcome: VendorRefreshOutcome = field(
        default_factory=lambda: VendorRefreshOutcome("not_requested", (), (), (), (), ())
    )


def run_standard_ai_strategy(
    *,
    enabled: bool,
    company_name: str,
    platform: str,
    folder_path: str,
    total_phases: int,
    refresh_vendor_research: bool,
    discovery_notes_content: str | None,
    lite_strategy: bool,
    output_dir: str | Path | None,
    diagnostics_dir: str | Path | None,
    write_txt: bool,
    consolidate_context: Callable[[str], str],
    generate_strategy: Callable[..., str | None],
) -> StandardStrategyResult:
    """Generate the standard route's single AI Strategy with exact accounting."""

    requested = ["ai"] if enabled else []
    tracker = StrategyOutcomeTracker(expected_strategy_targets(requested, (platform,)))
    refresh_tracker = VendorRefreshTracker(
        (platform,) if enabled and refresh_vendor_research else ()
    )
    if not enabled:
        outcome = tracker.snapshot()
        persist_strategy_outcome(folder_path, outcome)
        refresh_outcome = refresh_tracker.snapshot()
        persist_vendor_refresh_outcome(folder_path, refresh_outcome)
        return StandardStrategyResult(
            None,
            outcome,
            vendor_refresh_outcome=refresh_outcome,
        )

    from primr.core.run_state_io import _append_run_event, _update_run_state

    strategy_task_tracker = StrategyTaskTracker()
    target = strategy_target("ai", platform)
    console.phase_banner(
        5,
        total_phases,
        "AI Strategy Analysis",
        "Generating AI recommendations",
        "5-10 min",
    )
    _update_run_state(folder_path, current_phase="ai_strategy", status="running")
    _append_run_event(
        folder_path,
        "ai_strategy",
        "started",
        "AI strategy generation started",
    )

    failure_type: str | None = None
    try:
        context_file = consolidate_context(folder_path)
        output_path = generate_strategy(
            company_name,
            platform,
            company_research_path=context_file,
            force_refresh_vendor=refresh_vendor_research,
            discovery_notes_content=discovery_notes_content,
            lite_strategy=lite_strategy,
            output_dir=output_dir,
            diagnostics_dir=diagnostics_dir,
            write_txt=write_txt,
            vendor_refresh_observer=(
                refresh_tracker.observer(platform) if refresh_vendor_research else None
            ),
            strategy_task_observer=strategy_task_tracker.observe,
        )
    except Exception as exc:
        failure_type = type(exc).__name__
        output_path = None
        console.error(f"AI Strategy setup failed ({failure_type}); the base report was preserved")
        logger.warning(
            "Standard AI Strategy stage failed: failure_type=%s",
            failure_type,
        )
    if output_path:
        tracker.mark_completed(target)
        console.phase_complete("AI Strategy Analysis")
        _append_run_event(
            folder_path,
            "ai_strategy",
            "completed",
            "AI strategy generation completed",
            output=output_path,
            platform=platform,
        )
    else:
        tracker.mark_failed(target)
        _append_run_event(
            folder_path,
            "ai_strategy",
            "failed",
            "AI strategy generation failed",
            platform=platform,
            failure_type=failure_type,
        )

    outcome = tracker.snapshot()
    persist_strategy_outcome(folder_path, outcome)
    refresh_outcome = refresh_tracker.snapshot()
    persist_vendor_refresh_outcome(folder_path, refresh_outcome)
    return StandardStrategyResult(
        output_path=output_path,
        outcome=outcome,
        deep_research_tasks_started=strategy_task_tracker.started_count,
        vendor_refresh_tasks_started=refresh_outcome.started_count,
        vendor_refresh_outcome=refresh_outcome,
    )
