"""Approval helpers for billable ``primr --eval`` paths.

``--eval-max-estimated-cost`` and ``--eval-judge-max-cost`` are spend ceilings,
not approval. Paid eval work still quotes, honors ``--dry-run``, and requires
``--skip-confirm`` or an explicit yes. This module is the single confirm
seam for ``--eval-run-missing`` and ``--eval-llm-judge`` so those flags
cannot treat a cap as consent or ignore ``--dry-run``.
"""

from __future__ import annotations

import glob
import shutil
from collections.abc import Callable, Sequence
from math import isfinite
from pathlib import Path
from typing import Any

from primr.utils.console import console, prompt_yes_no


def valid_eval_spend_ceiling(value: float) -> bool:
    """Return whether an eval spend ceiling is finite and positive."""

    return isfinite(value) and value > 0


def approve_eval_spend(config: Any, estimated_total: float, label: str) -> int | None:
    """Return an exit code to stop, or ``None`` when spend is approved.

    The caller prints the planned work first. This helper repeats the dollar
    amount, refuses to launch on ``--dry-run``, and treats a cost cap as a
    ceiling rather than consent. Interactive decline is a hard stop (exit 1)
    so a cancelled eval cannot fall through into ``perform_research``.
    """
    if not isfinite(estimated_total) or estimated_total < 0:
        console.error(f"{label}: invalid estimate {estimated_total!r}; no eval spend started")
        return 1
    console.info(f"{label}: estimated ${estimated_total:.2f}")
    if getattr(config, "dry_run_requested", False):
        console.info("Dry-run only; no eval spend started.")
        return 0
    # Caps such as --eval-max-estimated-cost are checked by the caller.
    # Approval is only --skip-confirm or an explicit yes.
    if getattr(config, "skip_confirm", False):
        console.info(f"Proceeding with {label} under --skip-confirm")
        return None
    if not prompt_yes_no(
        f"Proceed with {label} (~${estimated_total:.2f})?",
        default=False,
    ):
        console.info("Cancelled.")
        return 1
    return None


def estimate_eval_profile_cost(profile: str) -> float:
    """Return the authorization floor for one eval-run-missing profile."""

    from primr.core.model_eval import get_eval_profile
    from primr.utils.cost_display import estimate_cost_with_planning_floor

    slot = get_eval_profile(profile)
    if slot is not None and slot.estimated_cost_usd is not None:
        return float(slot.estimated_cost_usd)
    if profile == "fast":
        return estimate_cost_with_planning_floor(
            "complete", include_ai_strategy=True, fast_mode=True
        ).total_cost
    if profile == "lite":
        return estimate_cost_with_planning_floor(
            "complete", include_ai_strategy=True, lite_strategy=True
        ).total_cost
    return estimate_cost_with_planning_floor("complete", include_ai_strategy=True).total_cost


def execute_eval_run_missing(
    *,
    to_run: Sequence[tuple[str, str]],
    websites: dict[str, str],
    eval_dir: Path,
    max_cost_usd: float,
    output_dir: str,
    perform_research: Callable[..., str | None],
) -> None:
    """Run approved eval-missing companies under the remaining spend ceiling.

    Each started run reserves its planning estimate. Individual research runs
    reset their model counters, so carrying only observed process usage would
    forget earlier eval cells and allow a later run past the batch cap.
    """

    from primr.ai.routing import EvalRecipeOverride
    from primr.core.model_eval import get_eval_profile
    from primr.utils.run_budget import (
        clear_run_budget,
        set_run_budget,
        skip_stage_if_cost_would_exceed,
    )

    if not valid_eval_spend_ceiling(max_cost_usd):
        raise ValueError(f"Eval spend ceiling must be finite and positive, got {max_cost_usd}")

    budget_active = False
    committed_cost_usd = 0.0
    try:
        for company, profile in to_run:
            website = websites.get(company.lower())
            if not website:
                console.warn(f"Skipping {company} ({profile}): website missing in manifest")
                continue
            next_cost = estimate_eval_profile_cost(profile)
            set_run_budget(max_cost_usd)
            budget_active = True
            if skip_stage_if_cost_would_exceed(
                committed_cost_usd,
                next_cost,
                f"eval run-missing ({company} [{profile}])",
            ):
                continue

            # Run-local counters restart inside perform_research. Give that run
            # only the uncommitted remainder so its own checkpoints cannot use
            # headroom already reserved by earlier eval cells.
            set_run_budget(max_cost_usd - committed_cost_usd)
            profile_output = eval_dir / profile
            profile_output.mkdir(parents=True, exist_ok=True)
            slot = get_eval_profile(profile)
            slot_recipe = slot.recipe if slot is not None else None
            console.info(f"Running {company} [{profile}]")
            try:
                with EvalRecipeOverride(slot_recipe):
                    run_result = perform_research(
                        company_name=company,
                        website=website,
                        mode="complete",
                        ai_strategy=True,
                        skip_confirm=True,
                        lite_strategy=(profile == "lite"),
                        fast_mode=(profile == "fast"),
                    )
            finally:
                # Provider work may have spent before a failed/partial return,
                # so reserve the quote once launch began regardless of result.
                committed_cost_usd += next_cost
            if not run_result:
                console.warn(f"Run failed: {company} [{profile}]")
                continue
            _stage_eval_report(company, profile, profile_output, output_dir=output_dir)
    finally:
        if budget_active:
            clear_run_budget()


def _stage_eval_report(
    company: str,
    profile: str,
    profile_output: Path,
    *,
    output_dir: str,
) -> None:
    """Copy the latest Strategic Overview into the eval profile folder."""

    output_root = Path(output_dir)
    company_prefix_underscore = company.replace(" ", "_")
    matches: list[Path] = []
    for ext in ("*.md", "*.txt"):
        matches.extend(
            output_root.glob(f"{glob.escape(company_prefix_underscore)}_Strategic_Overview_{ext}")
        )
        matches.extend(output_root.glob(f"{glob.escape(company)}_Strategic_Overview_{ext}"))
    matches = list(dict.fromkeys(matches).keys())
    if matches:
        latest = max(matches, key=lambda p: p.stat().st_mtime)
        canonical_name = f"{company_prefix_underscore}_Strategic_Overview{latest.suffix}"
        shutil.copy2(latest, profile_output / canonical_name)
        console.info(f"Staged report into eval folder: {profile_output.name}/{canonical_name}")
        return
    console.warn(f"Could not locate output artifact to copy for {company} [{profile}]")
