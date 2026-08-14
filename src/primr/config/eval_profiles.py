"""
v1.24.0 cross-provider eval matrix.

Each registered profile slot here is one cell in the v1.24.0 cross-provider
scorecard. Adding a new candidate recipe = adding one register_eval_profile()
call here. The eval harness picks them up automatically via
list_eval_profile_names().

The hard goal: the *winner* of this matrix becomes the new default `primr`
recipe, replacing the then-current Grok-only 4.3 hybrid. The binding constraint
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
            "v1.24.0 headline candidate / current hybrid default. Grok 4.3 "
            "reasoning (cached input $0.20/M) + Gemini 3.1 Flash-Lite writing "
            "+ Gemini 3 Flash utility. Sub-$1 with margin."
        ),
    ),
    EvalProfileSlot(
        name="grok45-flashlite",
        recipe=ProfileRecipe(
            reasoning="grok-4.5",
            writing="gemini-3.1-flash-lite",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=1.20,
        description=(
            "Optional promotion candidate (not a default). Grok 4.5 reasoning "
            "(previous flagship, $2/$6) + Gemini Flash-Lite writing. Higher cost "
            "than grok43-flashlite; eval-gate before flipping hybrid. Distinct "
            "from --grok-tier max (4.5 everywhere)."
        ),
    ),
    EvalProfileSlot(
        name="grok46-flashlite",
        recipe=ProfileRecipe(
            reasoning="grok-4.6",
            writing="gemini-3.1-flash-lite",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=1.30,
        description=(
            "Current xAI flagship promotion candidate (not a default). Grok 4.6 "
            "reasoning ($2/$6, cached input $0.50) + Gemini Flash-Lite writing. "
            "Compare against the measured Grok 4.3 recipe under the aggregate "
            "evaluation ceiling before changing production routing."
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
            "writing & utility ($0.20/$1.25, 128K output). Retained as a "
            "measured historical candidate for reproducible comparisons."
        ),
    ),
    EvalProfileSlot(
        name="grok43-luna",
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="gpt-5.6-luna",
            utility="gpt-5.6-luna",
        ),
        estimated_cost_usd=0.55,
        description=(
            "Current OpenAI low-cost candidate. Grok 4.3 reasoning plus "
            "GPT-5.6 Luna writing and utility ($0.20/$1.20). Registered for a "
            "bounded comparison only; production routing remains unchanged."
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
            "with the same 128K output cap and a stronger historical small-model "
            "baseline."
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
# Gemini Flash PRO-tier evaluation
# =============================================================================
# Gemini 3.5 Flash (GA May 19, 2026) benchmarks above Gemini 3.1 Pro at lower
# cost ($1.50/$9 vs $2/$12). The eval-gated question (ROADMAP "model landscape
# refresh"): should the PRO/quality writing tier repoint from 3.1 Pro to
# 3.5 Flash? These two slots are a direct head-to-head — same reasoning +
# utility, only the quality-writing model differs — so the scorecard isolates
# the writer's quality/cost. The default pipeline does NOT change until this
# scorecard shows 3.5 Flash at-or-above 3.1 Pro quality at lower cost.

_GEMINI_35_PRO_TIER_EVAL = (
    EvalProfileSlot(
        name="protier-gemini31pro",  # reference (current PRO model)
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="gemini-3.1-pro-preview",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=1.30,
        description=(
            "PRO-tier REFERENCE: Gemini 3.1 Pro ($2/$12) as the quality writer. "
            "Baseline for the 3.5-Flash repoint decision."
        ),
    ),
    EvalProfileSlot(
        name="protier-gemini35flash",  # candidate (May 2026 refresh)
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="gemini-3.5-flash",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=1.05,
        description=(
            "PRO-tier CANDIDATE: Gemini 3.5 Flash ($1.50/$9) as the quality "
            "writer — benchmarks above 3.1 Pro at lower cost. If this slot "
            "matches or beats protier-gemini31pro on the scorecard, repoint the "
            "PRO/quality tier to gemini-3.5-flash."
        ),
    ),
    EvalProfileSlot(
        name="protier-gemini36flash",
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="gemini-3.6-flash",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=0.80,
        description=(
            "PRO-tier CANDIDATE: Gemini 3.6 Flash using its introductory "
            "through-2026 pricing. Production routing remains unchanged until "
            "a blinded artifact comparison supports promotion."
        ),
    ),
    EvalProfileSlot(
        name="protier-gemini37flash",
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="gemini-3.7-flash",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=0.80,
        description=(
            "PRO-tier CANDIDATE: current GA Gemini 3.7 Flash using its "
            "introductory through-2026 pricing. This is an evaluation slot, "
            "not a production-default change."
        ),
    ),
)


# =============================================================================
# Premium (Anthropic) candidates - the "is it worth the extra cash" tier
# =============================================================================
# Added once Anthropic keys were available. These probe the quality ceiling of
# the two upgrade levers separately: premium *reasoning* (cheap to upgrade,
# ~100K tokens) vs premium *writing* (expensive, ~1.7M tokens). The benchmark
# research (June 2026) flagged Opus 4.8's abstention behaviour as the strongest
# fit for sourced briefs, so these test whether that shows up in a real artifact.

_PREMIUM_CANDIDATES = (
    EvalProfileSlot(
        name="premium-opus-reason",
        recipe=ProfileRecipe(
            reasoning="claude-opus-4-8",
            writing="gemini-3.1-flash-lite",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=1.25,
        description=(
            "Premium REASONING, cheap writing. Opus 4.8 ($5/$25) for the "
            "analytical stages (gap analysis, workbook, cross-validation - only "
            "~100K tokens so the premium is cheap) + Gemini 3.1 Flash-Lite "
            "writing. Tests whether frontier reasoning + abstention improves the "
            "brief's analysis for ~+$0.50 over the Grok 4.3 standard."
        ),
    ),
    EvalProfileSlot(
        name="premium-sonnet-write",
        recipe=ProfileRecipe(
            reasoning="grok-4.3",
            writing="claude-sonnet-5",
            utility="gemini-3-flash-preview",
        ),
        estimated_cost_usd=2.50,
        description=(
            "Premium WRITING. Grok 4.3 reasoning + Sonnet 5 for the "
            "section-writing fan-out. The writing stage is the token-heavy one "
            "(~1.7M input), so this is the expensive lever - prompt caching of "
            "the shared context is what keeps it near $2-3. Tests whether better "
            "prose + instruction-following is worth the premium."
        ),
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
    estimated_cost_usd=5.09,
    description=(
        "Reference baseline: the Grok-only default that v1.24.0 set out to "
        "replace. Grok-only hybrid. Used to establish the quality "
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
        *_GEMINI_35_PRO_TIER_EVAL,
        *_PREMIUM_CANDIDATES,
        *_V1_24_0_LOCAL_CANDIDATES,
        _V1_24_0_CURRENT_BASELINE,
    )
    for slot in all_slots:
        register_eval_profile(slot, replace=True)
    logger.debug("Registered %d v1.24.0 cross-provider eval profile slots", len(all_slots))


_register_v1_24_0_matrix()
