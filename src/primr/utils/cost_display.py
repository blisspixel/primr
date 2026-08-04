"""Human cost-estimate display (print + interactive confirm).

Separated from ``cost_estimator`` so pricing math stays under the file-size
ceiling while launch and confirm share one presentation path.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from primr.utils.cost_estimator import CostEstimate, estimate_cost


def format_cost_estimate_line(company_name: str, mode: str, estimate: CostEstimate) -> str:
    """One-line human estimate used at launch and interactive confirm."""
    return f"{company_name} | {mode} | ~${estimate.total_cost:.2f} | {estimate.duration_minutes}"


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
    estimate = estimate_cost(
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
) -> bool:
    """Display cost estimate and ask for confirmation.

    Returns True if the user confirms with an explicit yes; empty Enter cancels.
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
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return False


def get_cost_summary(mode: str, include_ai_strategy: bool = False) -> str:
    """One-line cost summary string for compact status surfaces."""
    estimate = estimate_cost(mode, include_ai_strategy)
    return f"~${estimate.total_cost:.2f} ({estimate.duration_minutes})"
