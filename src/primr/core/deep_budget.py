"""Budget helpers for Deep Research execution paths."""

from __future__ import annotations

from primr.config.models import DEEP_RESEARCH_COST

_DEEP_RESEARCH_MODES = frozenset({"deep-research", "complete", "hybrid"})
_DEEP_RESEARCH_STRATEGIES = frozenset(
    {"customer_experience", "modern_security_compliance", "data_fabric_strategy"}
)


def count_main_deep_research_tasks(mode: str) -> int:
    """Return required Deep Research tasks for a non-fast run mode."""

    return 1 if mode in _DEEP_RESEARCH_MODES else 0


def strategy_uses_deep_research(strategy_name: str, *, lite_strategy: bool) -> bool:
    """Return whether one strategy document consumes a Deep Research task."""

    return (strategy_name == "ai" and not lite_strategy) or (
        strategy_name in _DEEP_RESEARCH_STRATEGIES
    )


def deep_research_flat_cost(task_count: int) -> float:
    """Return the planning cost for ``task_count`` Deep Research tasks."""

    return max(0, task_count) * DEEP_RESEARCH_COST.standard_task_cost


def deep_research_spend(
    *,
    mode: str,
    pipeline_cost: float,
    optional_strategy_tasks_started: int = 0,
) -> float:
    """Return observed non-fast spend from token usage plus flat DR tasks."""

    task_count = count_main_deep_research_tasks(mode) + max(0, optional_strategy_tasks_started)
    return max(0.0, pipeline_cost) + deep_research_flat_cost(task_count)


def skip_optional_strategy_if_over_budget(
    *,
    mode: str,
    optional_strategy_tasks_started: int,
    folder_path: str,
    strategy_name: str,
    platform: str,
) -> bool:
    """Return True after recording a run-state skip for an over-budget strategy."""

    from primr.ai.client import get_client
    from primr.core.run_state_io import _append_run_event
    from primr.utils.run_budget import skip_stage_if_over_budget

    usage = get_client().get_usage_summary()
    spend = deep_research_spend(
        mode=mode,
        pipeline_cost=usage.get("total_cost", 0.0),
        optional_strategy_tasks_started=optional_strategy_tasks_started,
    )
    if not skip_stage_if_over_budget(spend, "optional strategy generation"):
        return False

    _append_run_event(
        folder_path,
        "strategy_generation",
        "skipped",
        "Optional strategy generation skipped by run budget",
        strategy=strategy_name,
        platform=platform,
    )
    return True
