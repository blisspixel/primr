"""Runtime-routing and approval policy for the top-level dispatcher.

The dispatcher owns side effects such as run-state updates and console output.
This module owns route selection, estimate fan-out, option compatibility, and
the matching confirmation call so the approved amount cannot drift from the
eventual pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from primr.utils.model_policy import unpriced_model_opt_ins


@dataclass(frozen=True)
class ResearchRuntimePlan:
    """Resolved route and cost-shaping inputs for one research run."""

    use_fast: bool
    runtime_platform_count: int
    vendor_refresh_tasks: int
    error_message: str | None = None


@dataclass(frozen=True)
class ResearchRuntimePreparation:
    """Runtime plan plus the outcome of its compatibility and approval gates."""

    plan: ResearchRuntimePlan
    status: Literal["ready", "invalid", "approval_required", "cancelled"]


def resolve_research_runtime_plan(
    *,
    mode: str,
    explicit_fast_mode: bool,
    premium_mode: bool,
    xai_available: bool,
    openrouter_available: bool = False,
    platform_count: int,
    ai_strategy: bool,
    strategy_types: Sequence[str] | None,
    refresh_vendor_research: bool,
) -> ResearchRuntimePlan:
    """Resolve runtime behavior before the confirmation and dispatch gates."""

    use_fast = explicit_fast_mode or (
        not premium_mode
        and mode in ("complete", "structured", "hybrid")
        and (xai_available or openrouter_available)
    )
    legacy_structured = not use_fast and mode == "structured"
    error_message: str | None = None
    if legacy_structured and strategy_types:
        error_message = (
            "Explicit strategy types are not supported by the legacy structured runtime. "
            "Use complete mode or the routed fast pipeline."
        )
    elif legacy_structured and platform_count > 1:
        error_message = (
            "Multiple strategy platforms are not supported by the legacy structured runtime. "
            "Use complete mode or the routed fast pipeline."
        )

    runtime_platform_count = 1 if legacy_structured else platform_count
    refresh_is_executable = use_fast or not strategy_types or "ai" in strategy_types
    vendor_refresh_tasks = (
        runtime_platform_count
        if refresh_vendor_research and ai_strategy and refresh_is_executable
        else 0
    )
    return ResearchRuntimePlan(
        use_fast=use_fast,
        runtime_platform_count=runtime_platform_count,
        vendor_refresh_tasks=vendor_refresh_tasks,
        error_message=error_message,
    )


def prepare_research_runtime(
    *,
    mode: str,
    display_name: str,
    explicit_fast_mode: bool,
    premium_mode: bool,
    xai_available: bool,
    openrouter_available: bool | None = None,
    platform_count: int,
    ai_strategy: bool,
    strategy_types: Sequence[str] | None,
    refresh_vendor_research: bool,
    skip_confirm: bool,
    lite_strategy: bool,
    verify: bool,
    grok_tier: str,
) -> ResearchRuntimePreparation:
    """Resolve a route and run the exact matching cost-confirmation gate."""

    if openrouter_available is None:
        from primr.ai.providers.openrouter import openrouter_routing_ready

        openrouter_available = openrouter_routing_ready()

    plan = resolve_research_runtime_plan(
        mode=mode,
        explicit_fast_mode=explicit_fast_mode,
        premium_mode=premium_mode,
        xai_available=xai_available,
        openrouter_available=openrouter_available,
        platform_count=platform_count,
        ai_strategy=ai_strategy,
        strategy_types=strategy_types,
        refresh_vendor_research=refresh_vendor_research,
    )
    if plan.error_message:
        return ResearchRuntimePreparation(plan=plan, status="invalid")
    unpriced = unpriced_model_opt_ins()
    if unpriced:
        invalid_plan = ResearchRuntimePlan(
            use_fast=plan.use_fast,
            runtime_platform_count=plan.runtime_platform_count,
            vendor_refresh_tasks=plan.vendor_refresh_tasks,
            error_message=(
                "Unpriced model-call environment options are not allowed in a governed run: "
                + ", ".join(unpriced)
                + ". Disable them until they are explicit estimate-bound options."
            ),
        )
        return ResearchRuntimePreparation(plan=invalid_plan, status="invalid")

    # An explicit --skip-confirm is non-interactive approval, but execution
    # still repeats the priced shape before provider work starts.
    if skip_confirm:
        from primr.utils.cost_display import print_cost_estimate

        print_cost_estimate(
            mode,
            display_name,
            ai_strategy,
            num_vendors=plan.runtime_platform_count,
            lite_strategy=lite_strategy,
            fast_mode=plan.use_fast,
            premium_mode=premium_mode,
            verify=verify,
            grok_tier=grok_tier,
            strategy_types=strategy_types,
            vendor_research_refreshes=plan.vendor_refresh_tasks,
        )
        return ResearchRuntimePreparation(plan=plan, status="ready")

    from primr.utils.cost_display import display_cost_estimate

    approved = display_cost_estimate(
        mode,
        display_name,
        ai_strategy,
        num_vendors=plan.runtime_platform_count,
        lite_strategy=lite_strategy,
        fast_mode=plan.use_fast,
        premium_mode=premium_mode,
        verify=verify,
        grok_tier=grok_tier,
        strategy_types=strategy_types,
        vendor_research_refreshes=plan.vendor_refresh_tasks,
    )
    status: Literal["ready", "approval_required", "cancelled"]
    if approved is None:
        status = "approval_required"
    else:
        status = "ready" if approved else "cancelled"
    return ResearchRuntimePreparation(plan=plan, status=status)
