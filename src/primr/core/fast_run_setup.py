"""Fast-run setup: model resolution, routing, run identity (roadmap #23, Batch A).

Extracted verbatim from the head of ``perform_fast_research`` — no behavior
change. Resolves the Grok model pair for the tier, applies cross-provider
writing routing and any active eval-recipe override, resolves the
continuous-reasoning flag (env wins over the parameter), and establishes the
run identity (display name, working folder) and phase plan.

Side effects preserved from the original: resets the Grok session counters,
prints the active eval recipe (the pre-spend correctness check), creates the
working folder when none was passed, and logs the continuous-reasoning
decision.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from primr.config.models import GrokTier, PrimrModels
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured
from primr.utils.url_helpers import normalized_hostname

logger = get_logger("core.fast_run_setup")


@dataclass(frozen=True)
class FastRunSetup:
    """Resolved configuration and identity for one fast-mode run."""

    grok_reasoning: str
    grok_writing: str
    grok_reasoning_effort: str | None
    continuous_reasoning: bool
    display_name: str
    folder_path: str
    has_strategies: bool
    total_phases: int


def resolve_fast_run_setup(
    *,
    company_name: str | None,
    website: str | None,
    ai_strategy: bool,
    strategy_types: list[str] | None,
    grok_tier: str,
    continuous_reasoning: bool,
    folder_path: str | None,
) -> FastRunSetup:
    """Resolve models, routing, flags, and run identity for a fast run."""
    from primr.ai.client import reset_run_usage_accounting
    from primr.core.workspace import create_working_folder

    # Resets the Grok session AND the Gemini client so a long-lived process
    # (MCP/A2A server) never bleeds a prior job's spend into this run's
    # checkpoints and usage records.
    reset_run_usage_accounting()

    # Resolve Grok model pair for this tier
    grok_reasoning, grok_writing = PrimrModels.get_grok_models(GrokTier(grok_tier))

    # Cross-provider writing routing (v1.24.4 fix): for FAST/HYBRID the
    # estimator already prices writing via pick_model_for_role(Role.WRITING),
    # which prefers gemini-3.1-flash-lite when GEMINI_API_KEY is set. Until
    # this fix, perform_fast_research kept using the Grok-tier writer
    # (grok-4.20-non-reasoning), so a max_estimated_cost_usd cap approved
    # against a ~$0.79 Gemini estimate could let through a real ~$5.09 Grok
    # run. MAX is the explicit "Grok everywhere" opt-in and still uses the
    # Grok-tier writer for both reasoning and writing.
    from primr.ai.routing import Role, get_active_eval_recipe, pick_model_for_role

    if grok_tier != "max":
        try:
            routed_writing = pick_model_for_role(Role.WRITING)
        except Exception as e:
            # Routing failure must not abort the run — fall back to the
            # tier-default Grok writer. The cap divergence is logged so an
            # operator can see why production didn't match the estimate.
            logger.warning("Writing-role routing failed (%s); falling back to %s", e, grok_writing)
        else:
            if routed_writing and routed_writing != grok_writing:
                logger.info(
                    "Cross-provider routing: writing %s -> %s", grok_writing, routed_writing
                )
                grok_writing = routed_writing

    # v1.24.0: when an eval recipe override is active, the recipe's writing
    # model wins over the Grok-tier writer. This is what makes cross-provider
    # eval cells actually use their declared writing model (e.g. Gemini 3.1
    # Flash-Lite) instead of always falling through to grok_writing. The
    # cross-provider dispatch in grok_llm handles non-Grok models correctly.
    _active_recipe = get_active_eval_recipe()
    if _active_recipe is not None and _active_recipe.writing:
        grok_writing = _active_recipe.writing
    # The recipe's reasoning model must win too, not just writing - otherwise a
    # cross-provider slot that declares e.g. reasoning="claude-opus-4-8" or
    # "o4-mini" silently runs Grok reasoning and the eval cell is invalid. The
    # grok_llm cross-provider dispatch routes the non-Grok model correctly.
    if _active_recipe is not None and _active_recipe.reasoning:
        grok_reasoning = _active_recipe.reasoning

    # Print the resolved models so an eval cell can verify (before any LLM
    # spend) that the recipe override actually flowed through. This is a
    # cheap correctness check — if the run-log shows grok_writing=grok-4.20-NR
    # when the recipe specified gemini-3.1-flash-lite, the override didn't
    # work and the cell should be aborted before paying for the full run.
    if _active_recipe is not None:
        from primr.utils.console import console as _console

        _console.info(
            f"Active eval recipe: writing={grok_writing}, reasoning={grok_reasoning} "
            f"(recipe declared writing={_active_recipe.writing}, "
            f"reasoning={_active_recipe.reasoning})"
        )

    # Determine reasoning_effort for the FAST tier — grok-4.3 supports
    # low/medium/high effort levels. FAST uses "low" to reduce cost/latency;
    # HYBRID and MAX use the default (no explicit effort = model decides).
    grok_reasoning_effort: str | None = "low" if grok_tier == "fast" else None

    # Continuous reasoning is on by default after the n=3 pilot — see ROADMAP
    # "Continuous Reasoning Session". When on, workbook generation (Phase 3)
    # and cross-validation (Phase 5) share a single Grok session so the
    # validator inherits the corpus + workbook reasoning instead of re-reading
    # the report cold. Pass --no-continuous-reasoning, or set
    # PRIMR_CONTINUOUS_REASONING=0/false to revert to the fresh-call topology.
    env_flag = os.getenv("PRIMR_CONTINUOUS_REASONING", "").strip().lower()
    if env_flag in ("0", "false", "no", "off"):
        continuous_reasoning = False
    elif env_flag in ("1", "true", "yes", "on"):
        continuous_reasoning = True

    if continuous_reasoning:
        log_structured(
            "info",
            "Continuous reasoning enabled — session will be constructed at workbook stage",
            model=grok_reasoning,
        )

    display_name = company_name or normalized_hostname(website or "", strip_www=True)
    resolved_folder = folder_path or create_working_folder(company_name, website)

    has_strategies = ai_strategy or bool(strategy_types)
    total_phases = 6 if has_strategies else 5

    return FastRunSetup(
        grok_reasoning=grok_reasoning,
        grok_writing=grok_writing,
        grok_reasoning_effort=grok_reasoning_effort,
        continuous_reasoning=continuous_reasoning,
        display_name=display_name,
        folder_path=resolved_folder,
        has_strategies=has_strategies,
        total_phases=total_phases,
    )
