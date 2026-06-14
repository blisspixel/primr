"""Run one full primr brief under a named recipe, for recipe A/B comparison.

Generic and committable: the company name and URL are runtime arguments, never
hardcoded, so no real-company data lands in the repo. Output goes to primr's
normal OUTPUT_DIR (gitignored).

    py -3.12 scripts/eval/run_recipe_brief.py \
        --company "ExampleCo" --url https://example.co --recipe premium-opus-reason

--recipe is an eval-profile slot name (see config/eval_profiles.py), or
"standard" / "default" to run with no override (the routed default recipe). The
recipe's reasoning/writing/utility models are installed via EvalRecipeOverride.

Tradecraft Step 4 A/B (framed vs unframed, same recipe + company):

    # 1. framed arm (operator intent steers framing + hypothesis tree + gap queries)
    py -3.12 scripts/eval/run_recipe_brief.py --company "ExampleCo" --url https://example.co \
        --recipe standard --tag standard-framed \
        --purpose diligence --question "Is the near-term cloud spend Azure or on-prem?"
    # 2. unframed arm (today's default path)
    py -3.12 scripts/eval/run_recipe_brief.py --company "ExampleCo" --url https://example.co \
        --recipe standard --tag standard-unframed
    # 3. grade pairwise (free local judges while developing)
    py -3.12 scripts/eval/grade_pairwise.py --label framing \
        --baseline output/eval/briefs/standard-unframed/<brief>.md \
        --candidate output/eval/briefs/standard-framed/<brief>.md \
        --judges "ollama:qwen3:8b"

Both briefs cost a normal run each; grading is free. This is the measurement the
agentic-balance doctrine requires before adding more agentic collection depth.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from primr.ai.routing import EvalRecipeOverride
from primr.core.model_eval import get_eval_profile
from primr.core.research_agent import perform_research
from primr.utils.console import console


def main() -> int:
    ap = argparse.ArgumentParser(description="Run one primr brief under a recipe")
    ap.add_argument("--company", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--recipe", required=True, help="eval-profile slot name, or 'standard'")
    ap.add_argument(
        "--recipe-models",
        default=None,
        help="Ad-hoc 'reasoning,writing,utility' model IDs - builds a recipe at "
        "runtime so machine-specific tags (e.g. a local Ollama model) stay out of "
        "the repo. Overrides --recipe when given.",
    )
    ap.add_argument("--mode", default="complete")
    ap.add_argument(
        "--tag",
        default=None,
        help="Output-dir key under output/eval/briefs/ (defaults to --recipe). Use "
        "distinct tags for the framed vs unframed arm so they don't overwrite.",
    )
    # Tradecraft framing (Step 4): supplying any of these makes the run 'framed',
    # which threads operator intent into the workbook, forms the Day-1 hypothesis
    # tree, and steers gap queries. Omit all four for the unframed (default) arm.
    ap.add_argument("--purpose", default=None)
    ap.add_argument("--audience", default=None)
    ap.add_argument("--decision", default=None)
    ap.add_argument("--question", default=None)
    args = ap.parse_args()

    recipe = None
    if args.recipe_models:
        from primr.core.model_eval import ProfileRecipe

        parts = [p.strip() for p in args.recipe_models.split(",")]
        if len(parts) != 3:
            console.error("--recipe-models needs exactly 'reasoning,writing,utility'")
            return 1
        recipe = ProfileRecipe(reasoning=parts[0], writing=parts[1], utility=parts[2])
        console.info(f"Ad-hoc recipe: reasoning={parts[0]} writing={parts[1]} utility={parts[2]}")
    elif args.recipe not in ("standard", "default"):
        slot = get_eval_profile(args.recipe)
        if slot is None:
            console.error(f"Unknown recipe '{args.recipe}'")
            return 1
        recipe = slot.recipe
        console.info(
            f"Recipe {args.recipe}: reasoning={recipe.reasoning} "
            f"writing={recipe.writing} utility={recipe.utility}"
        )

    # Per-tag output dir so parallel/sequential runs of the SAME company (e.g. the
    # framed vs unframed arm) don't overwrite each other's brief (the default
    # output path is keyed on company+date only).
    out_dir = Path("output/eval/briefs") / (args.tag or args.recipe)
    out_dir.mkdir(parents=True, exist_ok=True)
    console.info(f"Output dir: {out_dir}")

    framed = any((args.purpose, args.audience, args.decision, args.question))
    console.info(f"Framing: {'ON' if framed else 'off (unframed/default arm)'}")

    t0 = time.monotonic()
    with EvalRecipeOverride(recipe):
        result = perform_research(
            company_name=args.company,
            website=args.url,
            mode=args.mode,
            ai_strategy=False,  # brief only - keep cost predictable, no Deep Research
            skip_confirm=True,  # cost pre-approved by the operator
            fast_mode=False,  # recipe override drives model choice, not fast routing
            output_dir=str(out_dir),
            framing_purpose=args.purpose,
            framing_audience=args.audience,
            framing_decision=args.decision,
            framing_question=args.question,
        )
    elapsed = time.monotonic() - t0

    console.blank()
    if result:
        console.ok(f"[{args.recipe}] brief complete in {elapsed / 60:.1f} min")
        # Surface whatever the result object exposes (output path, cost, usage).
        for attr in ("output_path", "report_path", "total_cost", "cost", "usage"):
            val = getattr(result, attr, None)
            if val is not None:
                console.info(f"  {attr}: {val}")
        return 0
    console.error(f"[{args.recipe}] run returned no result")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
