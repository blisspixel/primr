"""Budget-aware explicit vendor refresh preparation for non-fast strategies."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from primr.config.models import DEEP_RESEARCH_COST
from primr.core.vendor_refresh_outcome import (
    VendorRefreshOutcome,
    VendorRefreshTracker,
    persist_vendor_refresh_outcome,
)
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class DeepVendorRefreshResult:
    """Run-local accounting for a serial explicit refresh batch."""

    planned_count: int = 0
    started_count: int = 0
    skipped_budget_count: int = 0
    outcome: VendorRefreshOutcome = field(
        default_factory=lambda: VendorRefreshOutcome("not_requested", (), (), (), (), ())
    )


def prepare_deep_strategy_vendor_refreshes(
    refresh_requested: bool,
    strategies: Sequence[str],
    platforms: tuple[str, ...],
    mode: str,
    folder_path: str,
) -> DeepVendorRefreshResult:
    """Resolve whether an explicit AI refresh batch applies to this run."""

    if not refresh_requested or "ai" not in strategies:
        outcome = VendorRefreshTracker(()).snapshot()
        persist_vendor_refresh_outcome(folder_path, outcome)
        return DeepVendorRefreshResult(outcome=outcome)
    from primr.core.strategy_loop import strategy_vendors

    return refresh_deep_strategy_vendors(
        mode=mode,
        vendors=strategy_vendors("ai", platforms),
        folder_path=folder_path,
    )


def refresh_deep_strategy_vendors(
    *,
    mode: str,
    vendors: Sequence[str],
    folder_path: str,
) -> DeepVendorRefreshResult:
    """Refresh each unique AI vendor only when the run budget covers the next task."""

    from primr.ai.client import get_client
    from primr.core.deep_budget import deep_research_spend
    from primr.core.run_state_io import _append_run_event
    from primr.core.vendor_research import get_or_generate_vendor_research_sync
    from primr.utils.run_budget import skip_stage_if_cost_would_exceed

    selected = tuple(dict.fromkeys(vendors))
    tracker = VendorRefreshTracker(selected)
    skipped = 0
    for vendor in selected:
        started = tracker.snapshot().started_count
        pipeline_cost = get_client().get_usage_summary().get("total_cost", 0.0)
        observed_spend = deep_research_spend(
            mode=mode,
            pipeline_cost=pipeline_cost,
            vendor_refresh_tasks_started=started,
        )
        if skip_stage_if_cost_would_exceed(
            observed_spend,
            DEEP_RESEARCH_COST.standard_task_cost,
            f"vendor research refresh ({vendor})",
        ):
            skipped += 1
            tracker.mark_skipped(vendor)
            _append_run_event(
                folder_path,
                "vendor_research_refresh",
                "skipped",
                "Vendor research refresh skipped by run budget",
                platform=vendor,
            )
            continue
        try:
            get_or_generate_vendor_research_sync(
                vendor,
                force_refresh=True,
                allow_auto_refresh=False,
                task_observer=tracker.observer(vendor),
            )
        except Exception as exc:
            tracker.observe(vendor, "failed")
            logger.warning(
                "Vendor research refresh failed before strategy generation: "
                "vendor=%s failure_type=%s",
                vendor,
                type(exc).__name__,
            )

    outcome = tracker.snapshot()
    persist_vendor_refresh_outcome(folder_path, outcome)
    return DeepVendorRefreshResult(
        planned_count=len(selected),
        started_count=outcome.started_count,
        skipped_budget_count=skipped,
        outcome=outcome,
    )
