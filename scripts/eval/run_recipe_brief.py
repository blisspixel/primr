"""Run one full primr brief under a named recipe, for recipe A/B comparison.

Generic and committable: the company name and URL are runtime arguments, never
hardcoded, so no real-company data lands in the repo. Output goes to primr's
normal OUTPUT_DIR (gitignored).

    py -3.12 scripts/eval/run_recipe_brief.py \
        --company "ExampleCo" --url https://example.co --recipe premium-opus-reason

--recipe is an eval-profile slot name (see config/eval_profiles.py), or
"standard" / "default" to run with no override (the routed default recipe). The
recipe's reasoning/writing/utility models are installed via EvalRecipeOverride.
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

    # Per-recipe output dir so parallel/sequential recipe runs of the SAME
    # company don't overwrite each other's brief (the default output path is
    # keyed on company+date only).
    out_dir = Path("output/eval/briefs") / args.recipe
    out_dir.mkdir(parents=True, exist_ok=True)
    console.info(f"Output dir: {out_dir}")

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
