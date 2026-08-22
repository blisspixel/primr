"""Orchestrated research CLI handler with a mandatory cost gate.

``primr orchestrate`` is experimental but still billable. This module always
prints a priced estimate, supports ``--dry-run``, and refuses to launch without
either interactive confirmation or an explicit ``--max-cost`` ceiling.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any

from primr.utils.console import console


def handle_orchestrate(config: Any) -> int:
    """Run experimental orchestrated research behind the standard cost gate."""
    from primr.agentic import HookSystem, SSRFGuardHook
    from primr.agentic.memory import ResearchMemory
    from primr.agentic.orchestrator import OrchestratorConfig, ResearchOrchestrator
    from primr.core.cli_batch import _ensure_valid_url
    from primr.utils.async_utils import run_sync
    from primr.utils.cost_display import print_cost_estimate

    company_name = config.company_name
    website = config.website

    # Positional form: ``primr orchestrate "Company" url`` can leave the verb
    # in the company_name slot depending on parse path.
    if company_name and company_name.lower() == "orchestrate":
        company_name = website
        website = None

    if not company_name or not website:
        console.error("Company name and website required")
        console.info('Usage: primr orchestrate "Company Name" https://company.com')
        console.info('   or: primr "Company Name" https://company.com --orchestrate')
        console.info("Always pass --dry-run first, then --max-cost <usd> or confirm interactively.")
        return 1

    from primr.utils import validators

    website = _ensure_valid_url(website)
    if not website:
        console.error("Website URL is required after normalization")
        return 1
    try:
        website = validators.validate_url(website)
    except validators.InputValidationError as exc:
        console.error(f"Invalid website URL: {exc.reason}")
        return 1

    console.banner("Orchestrated Research (Experimental)")
    console.info(f"Company: {company_name}")
    console.info(f"Website: {website}")
    console.blank()

    # Price like a full provider-backed run (orchestrator mode="full").
    # Respect explicit --fast-mode; otherwise auto-detect when XAI is available.
    use_fast_mode = bool(getattr(config, "fast_mode", False)) or bool(os.environ.get("XAI_API_KEY"))
    estimate = print_cost_estimate(
        "complete",
        company_name,
        include_ai_strategy=True,
        fast_mode=use_fast_mode,
        premium_mode=False,
        verify=bool(getattr(config, "verify", False)),
        grok_tier=getattr(config, "grok_tier", "hybrid") or "hybrid",
    )
    console.muted(
        "Orchestrated research is experimental and still incurs provider spend. "
        "Use --dry-run to price only."
    )

    if getattr(config, "dry_run_requested", False):
        console.info("Dry-run only; no orchestrated research started.")
        if config.orchestrate_max_cost is not None:
            console.info(
                f"Configured --max-cost ${config.orchestrate_max_cost:.2f} "
                f"(estimate ~${estimate.total_cost:.2f})"
            )
        else:
            console.info(
                "Next: re-run without --dry-run, either with --max-cost <usd> "
                "or by answering Proceed interactively."
            )
        return 0

    max_cost = config.orchestrate_max_cost
    if max_cost is not None:
        if not _finite_positive(max_cost):
            console.error(f"--max-cost must be a finite positive number, got {max_cost}")
            return 1
        if estimate.total_cost > max_cost:
            console.error(
                f"Estimate ~${estimate.total_cost:.2f} exceeds --max-cost ${max_cost:.2f}. "
                "Raise the ceiling or narrow the run."
            )
            return 1
        console.info(
            f"Proceeding under --max-cost ${max_cost:.2f} (estimate ~${estimate.total_cost:.2f})"
        )
        spend_ceiling = float(max_cost)
    else:
        if not _confirm_orchestrate_spend(estimate.total_cost):
            console.info("Cancelled.")
            return 1
        # Explicit yes without a budget flag still gets a runtime ceiling so
        # spend cannot run unbounded after approval.
        spend_ceiling = round(estimate.total_cost * 1.25, 4)
        console.info(f"Runtime cost guard set to ${spend_ceiling:.2f} (estimate + 25%)")

    from primr.utils.run_budget import clear_run_budget, set_run_budget

    memory = ResearchMemory()
    hooks = HookSystem()
    clear_run_budget()
    budget = set_run_budget(spend_ceiling)
    # Same CostGuardHook the run-budget checkpoints write to — a second,
    # unbound hook would never see recorded spend (paper ceiling).
    hooks.register(budget.as_hook())
    hooks.register(SSRFGuardHook())

    output_path = Path(getattr(config, "output_dir", None) or "./output")
    orchestrator = ResearchOrchestrator(
        config=OrchestratorConfig(output_dir=output_path, fail_fast=False),
        memory=memory,
        hook_system=hooks,
    )

    console.step("Running orchestrated pipeline...")
    try:
        result = run_sync(
            orchestrator.research(
                company_name=company_name,
                company_url=website,
                mode="full",
            )
        )
    except Exception as exc:
        console.error(f"Orchestration failed: {exc}")
        return 1
    finally:
        clear_run_budget()

    console.blank()
    if result.is_success:
        console.success_box("Research completed", f"Duration: {result.duration_seconds:.1f}s")
        if result.report_path:
            console.info(f"Report: {result.report_path}")
        console.info(f"Hypotheses: {len(result.hypotheses)}")
        console.info(f"Stages: {', '.join(result.completed_stages)}")
        return 0

    console.error("Research failed")
    for error in result.errors:
        console.error(f"  • {error}")
    if result.completed_stages:
        console.info(f"Completed stages: {', '.join(result.completed_stages)}")
    return 1


def _confirm_orchestrate_spend(estimated_total: float) -> bool:
    """Interactive yes-only confirm after the estimate line was already printed."""
    try:
        sys.stdout.write(f"Proceed with orchestrated research (~${estimated_total:.2f})? [y/N] ")
        sys.stdout.flush()
        response = input().strip().lower()
        return response in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return False


def _finite_positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0
