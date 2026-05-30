"""
v1.24.0 cross-provider eval matrix.

Each registered profile slot here is one cell in the v1.24.0 cross-provider
scorecard. Adding a new candidate recipe = adding one register_eval_profile()
call here. The eval harness picks them up automatically via
list_eval_profile_names().

The hard goal: the *winner* of this matrix becomes the new default `primr`
recipe, replacing the current ~$4.27 Grok 4.3 hybrid. The binding constraint
is total run cost < $1.00 with quality at or above the current 4.3 baseline.

See docs/EVAL_V1_24_0.md for decision criteria, eval corpus, and process.

Slot naming convention: <reasoning-tag>-<writing-tag>[-<utility-tag>], where
tag is short for the model. Filesystem-safe (kebab-case, no slashes).

Cost estimates here are *pre-eval directional* — the actual cost from a real
run replaces this number once the eval pass is done. Estimates assume:
  - ~1M cumulative input tokens (heavy repetition, cache-favoring)
  - ~100K output tokens spread across all stages
  - 80% cache hit rate where the model supports cached input
  - DDG search overhead ~$0.10
"""

from __future__ import annotations

from primr.core.model_eval import (
    EvalProfileSlot,
    ProfileRecipe,
    register_eval_profile,
)
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Cloud sub-$1 candidates (the headline group)
# =============================================================================
#
# All combinations keep Grok 4.3 (or o4-mini) for reasoning where
# cached-input pricing makes it cheap, and rotate the writing-stage model
# across the cheapest viable cross-provider options.

_V1_24_0_CLOUD_CANDIDATES = (
    EvalProfileSlot(
        name="grok43-flashlite",
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="gemini-3.1-flash-lite",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=0.65,
        description=(
            "v1.24.0 headline candidate. Grok 4.3 reasoning (cached input "
            "$0.20/M makes this competitive) + Gemini 3.1 Flash-Lite writing "
            "($0.25/$1.50, cheapest Gemini-3-era writer) + Gemini 3 Flash "
            "utility. Sub-$1 with margin."
        ),
    ),
    EvalProfileSlot(
        name="grok43-nano",
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="gpt-5.4-nano",
            utility="gpt-5.4-nano",
        ),
        estimated_cost_usd=0.55,
        description=(
            "Cheapest cloud candidate. Grok 4.3 reasoning + GPT-5.4-nano "
            "writing & utility ($0.20/$1.25). Risk: nano's 16K output cap may "
            "force per-section chunking which complicates the section-writing "
            "fan-out. If quality matches, this is the cost floor."
        ),
    ),
    EvalProfileSlot(
        name="grok43-mini",
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="gpt-5.4-mini",
            utility="gpt-5.4-mini",
        ),
        estimated_cost_usd=0.85,
        description=(
            "GPT-5.4-mini writing instead of nano. More expensive ($0.75/$4.50) "
            "but uncapped output and stronger small-model quality. Tests "
            "whether nano's output cap is actually a problem in practice."
        ),
    ),
    EvalProfileSlot(
        name="grok43-haiku-batch",
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="claude-haiku-4-5",
            utility="claude-haiku-4-5",
        ),
        estimated_cost_usd=0.80,
        description=(
            "Anthropic-side cheap candidate. Haiku 4.5 batch-API rate "
            "($0.50/$2.50 effective, 50% off standard $1.00/$5.00) for the "
            "section-writing fan-out. Note: batch adds up to 24h SLA so this "
            "is an async-acceptable recipe only. Cost estimate assumes "
            "batch-API plumbing lands as part of v1.24.0 follow-on."
        ),
    ),
    EvalProfileSlot(
        name="all-gemini",
        recipe=ProfileRecipe(
            reasoning="gemini-3.1-pro-preview",
            writing="gemini-3.1-flash-lite",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=0.95,
        description=(
            "Single-vendor simplicity. Gemini 3.1 Pro reasoning + 3.1 "
            "Flash-Lite writing + 3 Flash utility. Loses Grok 4.3's $0.20 "
            "cached-input advantage, sits right at the $1 ceiling. Useful as "
            "the 'no Grok required' fallback recipe."
        ),
    ),
    EvalProfileSlot(
        name="o4mini-flashlite",
        recipe=ProfileRecipe(
            reasoning="o4-mini",
            writing="gemini-3.1-flash-lite",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=0.55,
        description=(
            "Cross-provider reasoning swap. OpenAI o4-mini reasoning "
            "($1.10/$4.40 — cheaper output than Grok 4.3) + Gemini 3.1 "
            "Flash-Lite writing. Tests whether o4-mini matches Grok 4.3 on "
            "the analytical depth that primr's reasoning stages require."
        ),
    ),
)


# =============================================================================
# Quality-ceiling candidate (over budget, baseline for soft-gate scoring)
# =============================================================================

_V1_24_0_CEILING_CANDIDATE = EvalProfileSlot(
    name="grok43max-flashlite",
    recipe=ProfileRecipe(
        reasoning="grok-4.3",  # max reasoning effort
        writing="gemini-3-flash-preview",  # 3 Flash, not Flash-Lite — slightly stronger
        utility="gemini-3-flash-preview",
    ),
    estimated_cost_usd=1.50,
    description=(
        "Quality-ceiling reference, expected to fail the <$1 hard gate but "
        "useful as an upper bound for utility-per-dollar comparison. Grok 4.3 "
        "with maximum reasoning intensity + Gemini 3 Flash (not Flash-Lite) "
        "for richer writing. If a sub-$1 candidate gets within 90% of this "
        "slot's quality score, the budget pick is justified."
    ),
)


# =============================================================================
# Local / hybrid candidates (zero or low cost, RTX 4090 ceiling tests)
# =============================================================================
#
# These slots exist to test "how good can free get" and "is hybrid cheaper
# than fully cloud while preserving quality." Local cells trivially win
# utility-per-dollar (cost = 0); the binding question is absolute quality.

_V1_24_0_LOCAL_CANDIDATES = (
    EvalProfileSlot(
        name="local-llama4scout",
        recipe=ProfileRecipe(
            reasoning="llama4:scout",
            writing="llama4:scout",
            utility="llama4:scout",
        ),
        estimated_cost_usd=0.00,
        description=(
            "Pure local. Llama 4 Scout for everything. Unique 10M-token "
            "context window means primr's full corpus + workbook + "
            "cross-validation chain could fit in one continuous session. "
            "Tests whether unified long-context reasoning beats fragmented "
            "cloud calls. Zero marginal cost."
        ),
    ),
    EvalProfileSlot(
        name="local-qwen32b",
        recipe=ProfileRecipe(
            reasoning="qwen3:32b",
            writing="qwen3:32b",
            utility="qwen3:7b",
        ),
        estimated_cost_usd=0.00,
        description=(
            "Pure local, dense workhorse. Qwen3 32B for reasoning + writing "
            "(strong general intelligence on 24GB), Qwen3 7B for cheap "
            "utility tasks. Tests the daily-driver dense-model floor."
        ),
    ),
    EvalProfileSlot(
        name="hybrid-grok-local",
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="qwen3.6:35b-a3b",
            utility="qwen3:7b",
        ),
        estimated_cost_usd=0.30,
        description=(
            "Hybrid floor. Cloud reasoning where quality matters most "
            "(Grok 4.3 with cache), local writing & utility where they don't. "
            "Tests whether splitting the pipeline at the reasoning/writing "
            "seam preserves cloud quality on the high-leverage stages while "
            "amortizing the cost-heavy bulk-writing stage to free local "
            "inference."
        ),
    ),
)


# =============================================================================
# Current baseline (the regression we're trying to fix)
# =============================================================================

_V1_24_0_CURRENT_BASELINE = EvalProfileSlot(
    name="grok43-current-default",
    recipe=ProfileRecipe(
        reasoning="grok-4.3",
        writing="grok-4.20-non-reasoning",
        utility="grok-4.20-non-reasoning",
    ),
    estimated_cost_usd=4.27,
    description=(
        "Reference baseline: the current ~$4.27 default that v1.24.0 is "
        "trying to replace. Grok-only hybrid. Used to establish the quality "
        "bar that sub-$1 candidates must meet or exceed."
    ),
)


# =============================================================================
# Registration
# =============================================================================


def _register_v1_24_0_matrix() -> None:
    """Register all v1.24.0 cross-provider eval candidate slots.

    Idempotent (uses replace=True) so reloading the module during dev doesn't
    raise. The legacy built-in slots (full / lite / fast) are registered by
    primr.core.model_eval._register_builtin_profiles() and are not touched here.
    """
    all_slots: tuple[EvalProfileSlot, ...] = (
        *_V1_24_0_CLOUD_CANDIDATES,
        _V1_24_0_CEILING_CANDIDATE,
        *_V1_24_0_LOCAL_CANDIDATES,
        _V1_24_0_CURRENT_BASELINE,
    )
    for slot in all_slots:
        register_eval_profile(slot, replace=True)
    logger.debug("Registered %d v1.24.0 cross-provider eval profile slots", len(all_slots))


_register_v1_24_0_matrix()
