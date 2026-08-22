"""Cost-gated Accordion Method test CLI.

``primr --test-accordion`` is experimental but still billable: one Deep
Research dossier plus serial Gemini Flash section writes. This module always
prints a priced estimate, supports ``--dry-run``, and refuses to launch
without interactive confirmation or ``--skip-confirm``.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from primr.utils.console import console, prompt_yes_no


def handle_test_accordion(config: Any) -> int:
    """Price, optionally preview, then run the standalone Accordion test."""
    topic = getattr(config, "test_accordion_topic", None)
    if not topic:
        console.error("No topic specified for Accordion test")
        console.info('Usage: primr --test-accordion "Oceanography 2026-2030"')
        return 1

    target_pages = int(getattr(config, "test_accordion_pages", 50) or 50)
    from primr.ai.accordion_test import RESEARCH_SECTIONS
    from primr.utils.cost_display import print_cost_estimate

    console.banner("Accordion Method Test")
    console.info(f"Topic: {topic}")
    console.info(f"Target: {target_pages} pages")
    console.muted(
        f"Plan: 1 Deep Research dossier + {len(RESEARCH_SECTIONS)} Gemini Flash section writes."
    )
    console.blank()

    # Price like a Deep Research run (one billed interaction + Accordion Flash
    # writing overhead already included in the deep-research planning floor).
    estimate = print_cost_estimate("deep-research", topic, include_ai_strategy=False)
    console.muted(
        "Accordion is experimental and still incurs provider spend. Use --dry-run to price only."
    )

    if getattr(config, "dry_run_requested", False):
        console.info("Dry-run only; no Accordion test started.")
        return 0

    budget = getattr(config, "budget_usd", None)
    if budget is not None:
        try:
            budget_value = float(budget)
        except (TypeError, ValueError):
            console.error(f"--budget must be a finite positive number, got {budget}")
            return 1
        if not isfinite(budget_value) or budget_value <= 0:
            console.error(f"--budget must be a finite positive number, got {budget}")
            return 1
        if estimate.total_cost > budget_value:
            console.error(
                f"Estimate ~${estimate.total_cost:.2f} exceeds --budget ${budget_value:.2f}. "
                "Raise the ceiling or use --dry-run only."
            )
            return 1
        console.info(
            f"Budget ceiling ${budget_value:.2f} covers estimate ~${estimate.total_cost:.2f}"
        )

    if not getattr(config, "skip_confirm", False):
        if not prompt_yes_no(
            f"Proceed with Accordion test (~${estimate.total_cost:.2f})?",
            default=False,
        ):
            console.info("Cancelled.")
            return 1

    from primr.ai.accordion_test import run_accordion_test
    from primr.utils.run_budget import clear_run_budget, set_run_budget

    budget_active = False
    try:
        if budget is not None:
            set_run_budget(float(budget))
            budget_active = True
        result = run_accordion_test(topic=topic, target_pages=target_pages)
    finally:
        if budget_active:
            clear_run_budget()
    if result.success:
        console.blank()
        console.success_box(
            f"Test completed: {result.page_estimate:.1f} pages",
            f"Output: {result.output_path}",
        )
        return 0

    console.blank()
    console.error(f"Test failed: {result.error or 'Unknown error'}")
    return 1
