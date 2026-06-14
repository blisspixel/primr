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

from primr.ai.routing import EvalRecipeOverride
from primr.core.model_eval import get_eval_profile
from primr.core.research_agent import perform_research
from primr.utils.console import console


def main() -> int:
    ap = argparse.ArgumentParser(description="Run one primr brief under a recipe")
    ap.add_argument("--company", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--recipe", required=True, help="eval-profile slot name, or 'standard'")
    ap.add_argument("--mode", default="complete")
    args = ap.parse_args()

    recipe = None
    if args.recipe not in ("standard", "default"):
        slot = get_eval_profile(args.recipe)
        if slot is None:
            console.error(f"Unknown recipe '{args.recipe}'")
            return 1
        recipe = slot.recipe
        console.info(
            f"Recipe {args.recipe}: reasoning={recipe.reasoning} "
            f"writing={recipe.writing} utility={recipe.utility}"
        )

    t0 = time.monotonic()
    with EvalRecipeOverride(recipe):
        result = perform_research(
            company_name=args.company,
            website=args.url,
            mode=args.mode,
            ai_strategy=False,  # brief only - keep cost predictable, no Deep Research
            skip_confirm=True,  # cost pre-approved by the operator
            fast_mode=False,  # recipe override drives model choice, not fast routing
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
