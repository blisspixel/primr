"""Human cost-estimate display (print + interactive confirm).

Separated from ``cost_estimator`` so pricing math stays under the file-size
ceiling while launch and confirm share one presentation path.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

from primr.utils.cost_estimator import CostEstimate


def estimate_cost(*args: Any, **kwargs: Any) -> CostEstimate:
    """Compatibility seam that resolves the estimator at call time."""
    from primr.utils.cost_estimator import estimate_cost as calculate

    return calculate(*args, **kwargs)


def format_cost_estimate_line(company_name: str, mode: str, estimate: CostEstimate) -> str:
    """One-line human estimate used at launch and interactive confirm."""
    return f"{company_name} | {mode} | ~${estimate.total_cost:.2f} | {estimate.duration_minutes}"


def estimate_cost_with_planning_floor(
    mode: str,
    include_ai_strategy: bool = False,
    num_vendors: int = 1,
    lite_strategy: bool = False,
    fast_mode: bool = False,
    premium_mode: bool = False,
    verify: bool = False,
    grok_tier: str = "hybrid",
    strategy_types: Sequence[str] | None = None,
    vendor_research_refreshes: int = 0,
) -> CostEstimate:
    """Return the higher of planning and historical estimates.

    Cheap historical samples must never lower the amount shown at launch below
    the planning floor used by dry-run, budget, MCP, and A2A authorization.
    """
    kwargs = {
        "num_vendors": num_vendors,
        "lite_strategy": lite_strategy,
        "fast_mode": fast_mode,
        "premium_mode": premium_mode,
        "verify": verify,
        "grok_tier": grok_tier,
        "strategy_types": strategy_types,
        "vendor_research_refreshes": vendor_research_refreshes,
    }
    planning = estimate_cost(mode, include_ai_strategy, use_historical=False, **kwargs)
    historical = estimate_cost(mode, include_ai_strategy, use_historical=True, **kwargs)
    if historical.total_cost <= planning.total_cost:
        return planning

    notes = list(historical.notes or [])
    if "Based on" not in " ".join(notes):
        notes.append(
            "Authorization floor raised by historical average "
            f"(planning was ${planning.total_cost:.2f})"
        )
        historical.notes = notes
    return historical


def print_cost_estimate(
    mode: str,
    company_name: str,
    include_ai_strategy: bool = False,
    num_vendors: int = 1,
    lite_strategy: bool = False,
    fast_mode: bool = False,
    premium_mode: bool = False,
    verify: bool = False,
    grok_tier: str = "hybrid",
    strategy_types: Sequence[str] | None = None,
    vendor_research_refreshes: int = 0,
) -> CostEstimate:
    """Price the run and print the canonical one-line estimate (no confirmation)."""
    estimate = estimate_cost_with_planning_floor(
        mode,
        include_ai_strategy,
        num_vendors=num_vendors,
        lite_strategy=lite_strategy,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
        verify=verify,
        grok_tier=grok_tier,
        strategy_types=strategy_types,
        vendor_research_refreshes=vendor_research_refreshes,
    )
    print(f"\n{format_cost_estimate_line(company_name, mode, estimate)}")
    sys.stdout.flush()
    return estimate


def display_cost_estimate(
    mode: str,
    company_name: str,
    include_ai_strategy: bool = False,
    num_vendors: int = 1,
    lite_strategy: bool = False,
    fast_mode: bool = False,
    premium_mode: bool = False,
    verify: bool = False,
    grok_tier: str = "hybrid",
    strategy_types: Sequence[str] | None = None,
    vendor_research_refreshes: int = 0,
) -> bool | None:
    """Display cost estimate and ask for confirmation.

    Return True for an explicit yes, False for a decline, and None when the
    input stream closes before an answer can be read.
    """
    print_cost_estimate(
        mode,
        company_name,
        include_ai_strategy=include_ai_strategy,
        num_vendors=num_vendors,
        lite_strategy=lite_strategy,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
        verify=verify,
        grok_tier=grok_tier,
        strategy_types=strategy_types,
        vendor_research_refreshes=vendor_research_refreshes,
    )

    try:
        sys.stdout.write("Proceed? [y/N] ")
        sys.stdout.flush()
        response = input().strip().lower()
        return response in ("y", "yes")
    except EOFError:
        print()
        return None
    except KeyboardInterrupt:
        print("\nCancelled.")
        return False


def get_cost_summary(mode: str, include_ai_strategy: bool = False) -> str:
    """One-line cost summary string for compact status surfaces."""
    estimate = estimate_cost_with_planning_floor(mode, include_ai_strategy)
    return f"~${estimate.total_cost:.2f} ({estimate.duration_minutes})"
