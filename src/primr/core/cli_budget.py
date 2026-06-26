"""CLI helpers for activating a per-run budget."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from primr.core.budget_policy import describe_budget_enforcement
from primr.utils.console import console

if TYPE_CHECKING:
    from primr.core.cli import CLIConfig


@dataclass(frozen=True)
class BudgetActivation:
    """Result of validating and activating ``--budget``."""

    ok: bool
    active: bool


def estimate_vendor_count(config: CLIConfig) -> int:
    """Return the vendor count to feed research cost estimates."""
    if not config.ai_strategy:
        return 1
    return max(len(config.cloud_vendors), 1)


def activate_run_budget(
    config: CLIConfig, *, fast_mode: bool, premium_mode: bool
) -> BudgetActivation:
    """Validate ``--budget``, activate it when present, and explain runtime scope."""
    if config.budget_usd is None:
        return BudgetActivation(ok=True, active=False)
    if config.budget_usd <= 0:
        console.error(f"--budget must be positive, got {config.budget_usd}")
        return BudgetActivation(ok=False, active=False)

    from primr.utils.cost_estimator import estimate_cost
    from primr.utils.run_budget import set_run_budget

    estimate = estimate_cost(
        config.mode,
        config.ai_strategy,
        num_vendors=estimate_vendor_count(config),
        lite_strategy=config.lite_strategy,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
        grok_tier=config.grok_tier,
    )
    if estimate.total_cost > config.budget_usd:
        console.error(
            f"Estimated cost ${estimate.total_cost:.2f} exceeds "
            f"--budget ${config.budget_usd:.2f}. Not starting."
        )
        console.info(
            "Raise --budget, or use a cheaper mode (--mode scrape ~$0.10, "
            "--dry-run for the full breakdown)."
        )
        return BudgetActivation(ok=False, active=False)

    set_run_budget(config.budget_usd)
    console.info(f"Run budget: ${config.budget_usd:.2f} (estimated ${estimate.total_cost:.2f})")
    policy = describe_budget_enforcement(
        mode=config.mode,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
    )
    (console.info if policy.runtime_checkpoints else console.warn)(
        f"Budget runtime: {policy.runtime}."
    )
    return BudgetActivation(ok=True, active=True)
