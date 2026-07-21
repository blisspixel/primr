"""CLI helpers for activating a per-run budget."""

from __future__ import annotations

import os
from dataclasses import dataclass
from math import isfinite
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
    error_message: str | None = None
    hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeSelection:
    """Provider-backed runtime route shared by preview and execution."""

    fast_mode: bool
    premium_mode: bool
    auto_fast_mode: bool


def resolve_runtime_selection(config: CLIConfig) -> RuntimeSelection:
    """Resolve the fast/premium route exactly once for every CLI surface."""

    auto_fast_mode = bool(
        not config.fast_mode
        and not config.premium_mode
        and config.mode in ("complete", "structured", "hybrid")
        and os.environ.get("XAI_API_KEY")
    )
    return RuntimeSelection(
        fast_mode=config.fast_mode or auto_fast_mode,
        premium_mode=config.premium_mode,
        auto_fast_mode=auto_fast_mode,
    )


def resolve_batch_modes(config: CLIConfig) -> tuple[bool, bool, str] | str:
    """Resolve and validate the runtime shape shared by a batch."""

    if config.premium_mode and config.fast_mode:
        return "Cannot use both --fast and --premium. Choose one."
    selection = resolve_runtime_selection(config)
    full_modes = ("complete", "structured", "hybrid")
    if selection.fast_mode and config.mode not in full_modes:
        return f"--fast only works with full mode, not --mode {config.mode}"
    if selection.premium_mode and config.mode not in full_modes:
        return f"--premium only works with full mode, not --mode {config.mode}"
    if selection.premium_mode:
        mode_label = "premium (Gemini + Deep Research)"
    elif selection.fast_mode:
        from primr.core.cli_dryrun import _full_mode_label

        mode_label = _full_mode_label(config.grok_tier)
    else:
        mode_label = config.mode
    return (selection.fast_mode, selection.premium_mode, mode_label)


def estimate_vendor_count(config: CLIConfig) -> int:
    """Return the vendor count to feed research cost estimates."""
    if not config.ai_strategy:
        return 1
    return max(len(config.cloud_vendors), 1)


def _estimate_runtime_vendor_count(config: CLIConfig, *, fast_mode: bool) -> int:
    """Return the vendor fan-out the selected runtime actually executes."""

    if not fast_mode and config.mode == "structured":
        return 1
    return estimate_vendor_count(config)


def estimate_strategy_types(config: CLIConfig) -> list[str]:
    """Return the YAML strategy documents (``--strategy-type``) to price.

    The "ai" type is covered by the ``include_ai_strategy`` estimate flag;
    everything else is a full strategy document the run will generate, so
    the pre-flight gate and dry-run must price it or they understate spend.
    """
    stype = getattr(config, "strategy_type", "ai")
    return [stype] if stype and stype != "ai" else []


def strategy_runtime_error(config: CLIConfig, *, fast_mode: bool) -> str | None:
    """Reject option shapes the selected runtime would silently ignore."""

    if fast_mode or config.mode != "structured":
        return None
    strategy_types = estimate_strategy_types(config)
    if strategy_types:
        return (
            f"--strategy-type {strategy_types[0]} is not supported by the legacy "
            "structured runtime. Use --mode complete or configure XAI fast mode."
        )
    platforms = tuple(getattr(config, "platforms", ()) or ())
    if len(platforms) > 1:
        return (
            "Multiple --platform values are not supported by the legacy structured "
            "runtime. Use --mode complete or configure XAI fast mode."
        )
    return None


def estimate_vendor_refresh_count(config: CLIConfig, *, fast_mode: bool) -> int:
    """Return estimate-bound vendor refresh tasks for this runtime shape."""

    if not getattr(config, "refresh_vendor_research", False) or not config.ai_strategy:
        return 0
    if not fast_mode and estimate_strategy_types(config):
        return 0
    return _estimate_runtime_vendor_count(config, fast_mode=fast_mode)


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
        num_vendors=_estimate_runtime_vendor_count(config, fast_mode=fast_mode),
        lite_strategy=config.lite_strategy,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
        verify=config.verify,
        grok_tier=config.grok_tier,
        strategy_types=estimate_strategy_types(config),
        vendor_research_refreshes=estimate_vendor_refresh_count(
            config,
            fast_mode=fast_mode,
        ),
    )
    from primr.core.cli_inference import append_inference_estimate_note

    append_inference_estimate_note(config, estimate)
    return estimate


def activate_run_budget(
    config: CLIConfig,
    *,
    fast_mode: bool,
    premium_mode: bool,
    emit_output: bool = True,
) -> BudgetActivation:
    """Validate ``--budget``, activate it when present, and explain runtime scope."""
    if config.budget_usd is None:
        return BudgetActivation(ok=True, active=False)
    if not isfinite(config.budget_usd) or config.budget_usd <= 0:
        message = f"--budget must be a finite positive number, got {config.budget_usd}"
        if emit_output:
            console.error(message)
        return BudgetActivation(ok=False, active=False, error_message=message)

    from primr.utils.run_budget import set_run_budget

    estimate = build_run_estimate(config, fast_mode=fast_mode, premium_mode=premium_mode)
    if estimate.total_cost > config.budget_usd:
        message = (
            f"Estimated cost ${estimate.total_cost:.2f} exceeds "
            f"--budget ${config.budget_usd:.2f}. Not starting."
        )
        hint = (
            "Raise --budget, or use a cheaper mode (--mode scrape ~$0.10, "
            "--dry-run for the full breakdown)."
        )
        if emit_output:
            console.error(message)
            console.info(hint)
        return BudgetActivation(
            ok=False,
            active=False,
            error_message=message,
            hints=(hint,),
        )

    set_run_budget(config.budget_usd)
    policy = describe_budget_enforcement(
        mode=config.mode,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
    )
    if emit_output:
        console.info(f"Run budget: ${config.budget_usd:.2f} (estimated ${estimate.total_cost:.2f})")
        (console.info if policy.runtime_checkpoints else console.warn)(
            f"Budget runtime: {policy.runtime}."
        )
    return BudgetActivation(ok=True, active=True)
