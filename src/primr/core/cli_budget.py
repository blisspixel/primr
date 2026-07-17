"""CLI helpers for activating a per-run budget."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from primr.core.budget_policy import describe_budget_enforcement
from primr.utils.console import console

if TYPE_CHECKING:
    from primr.core.cli import CLIConfig
    from primr.utils.cost_estimator import CostEstimate


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


def estimate_strategy_types(config: CLIConfig) -> list[str]:
    """Return the YAML strategy documents (``--strategy-type``) to price.

    The "ai" type is covered by the ``include_ai_strategy`` estimate flag;
    everything else is a full strategy document the run will generate, so
    the pre-flight gate and dry-run must price it or they understate spend.
    """
    stype = getattr(config, "strategy_type", "ai")
    return [stype] if stype and stype != "ai" else []


def build_run_estimate(config: CLIConfig, *, fast_mode: bool, premium_mode: bool) -> CostEstimate:
    """Price a run the way it will actually execute.

    The single source of the estimate-shaping kwargs, so every surface that
    quotes a run -- ``--dry-run``, the ``--budget`` pre-flight gate, and (by
    mirroring these flags) the interactive confirm prompt -- prices the same run
    identically. Each cost-shaping input the runtime honours (vendor fan-out,
    lite strategy, fast/premium routing, Grok tier, post-QA ``--verify``, and
    ``--strategy-type`` documents) is forwarded here; anything omitted would let
    one surface silently understate spend, which is exactly the drift this
    helper exists to prevent. ``fast_mode``/``premium_mode`` stay explicit
    because callers resolve them differently (dry-run auto-promotes; the gate
    receives the already-resolved values).
    """
    from primr.utils.cost_estimator import estimate_cost

    estimate = estimate_cost(
        config.mode,
        config.ai_strategy,
        num_vendors=estimate_vendor_count(config),
        lite_strategy=config.lite_strategy,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
        verify=config.verify,
        grok_tier=config.grok_tier,
        strategy_types=estimate_strategy_types(config),
    )
    from primr.core.cli_inference import append_inference_estimate_note

    append_inference_estimate_note(config, estimate)
    return estimate


def activate_run_budget(
    config: CLIConfig, *, fast_mode: bool, premium_mode: bool
) -> BudgetActivation:
    """Validate ``--budget``, activate it when present, and explain runtime scope."""
    if config.budget_usd is None:
        return BudgetActivation(ok=True, active=False)
    if config.budget_usd <= 0:
        console.error(f"--budget must be positive, got {config.budget_usd}")
        return BudgetActivation(ok=False, active=False)

    from primr.utils.run_budget import set_run_budget

    estimate = build_run_estimate(config, fast_mode=fast_mode, premium_mode=premium_mode)
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
