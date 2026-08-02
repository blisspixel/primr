"""
Cost Estimator for Gemini API usage.

Provides estimated costs before running research to help users
make informed decisions about API spending.

Pricing as of February 2026 (from models.py single source of truth):
- Gemini 3 Flash: $0.50/$3.00 per 1M tokens (input/output)
- Gemini 3 Pro: $2.00/$12.00 per 1M tokens (input/output) — flat pricing
- Gemini 3.1 Pro: $2.00/$12.00 (<=200k prompts) | $4.00/$18.00 (>200k prompts) — tiered
- Deep Research: ~$2-3 per standard task, ~$3-5 per complex task (API doesn't expose tokens)
- Google Search Grounding: $35/1000 queries ($0.035/query)

Note: When AI_REASONING_MODEL is set to a tiered-pricing model (e.g. 3.1 Pro), cost
estimates use conservative high-tier pricing (>200k). Actual costs may be lower if most
prompts stay under the 200k token threshold.

Note: Actual search query counts are available in API response via
groundingMetadata.webSearchQueries. Typical reports use 10-30 searches,
not the 100+ that "thinking steps" might suggest.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from math import ceil

from primr.config.models import (
    DEEP_RESEARCH_COST,
    LITE_AI_STRATEGY_MAX_INPUT_TOKENS,
    LITE_AI_STRATEGY_MAX_OUTPUT_TOKENS,
    SEARCH_COST_PER_QUERY,
    GrokTier,
    PrimrModels,
    TokenCostBreakdown,
)
from primr.utils.cost_estimate_policy import (
    deep_path_hiring_overhead as _deep_path_hiring_overhead,
)
from primr.utils.cost_estimate_policy import (
    strategy_type_notes as _strategy_type_notes,
)
from primr.utils.cost_estimate_policy import (
    vendor_refresh_duration_suffix as _vendor_refresh_duration_suffix,
)
from primr.utils.cost_estimate_policy import (
    vendor_refresh_notes as _vendor_refresh_notes,
)


class ResearchModeType(Enum):
    """Research modes for cost estimation."""

    STRUCTURED = "structured"
    DEEP_RESEARCH = "deep-research"
    COMPLETE = "complete"
    HYBRID = "hybrid"


@dataclass
class CostEstimate:
    """Estimated cost breakdown for a research task."""

    mode: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_search_queries: int
    input_cost: float
    output_cost: float
    search_cost: float
    total_cost: float
    duration_minutes: str
    notes: list[str]
    deep_research_cost: float = 0.0
    estimated_live_input_tokens: int = 0
    estimated_cached_input_tokens: int = 0
    live_input_cost: float = 0.0
    cached_input_cost: float = 0.0
    long_context_surcharge_cost: float = 0.0

    def __str__(self) -> str:
        """Format cost estimate for display."""
        lines = [
            f"Mode: {self.mode}",
            f"Estimated Duration: {self.duration_minutes}",
            "",
            "Token Estimates:",
            f"  Input:  ~{self.estimated_input_tokens:,} tokens (${self.input_cost:.4f})",
            f"  Output: ~{self.estimated_output_tokens:,} tokens (${self.output_cost:.4f})",
        ]

        if self.estimated_cached_input_tokens > 0:
            lines.append(
                "  Cached input: "
                f"~{self.estimated_cached_input_tokens:,} tokens "
                f"(${self.cached_input_cost:.4f})"
            )

        if self.long_context_surcharge_cost > 0:
            lines.append(f"  Long-context surcharge: ${self.long_context_surcharge_cost:.4f}")

        if self.estimated_search_queries > 0:
            lines.append(
                f"  Search: ~{self.estimated_search_queries} queries (${self.search_cost:.4f})"
            )

        if self.deep_research_cost > 0:
            lines.append(f"  Deep Research: ${self.deep_research_cost:.2f} (approximate)")

        lines.extend(
            [
                "",
                f"Estimated Total: ${self.total_cost:.2f}",
            ]
        )

        if self.notes:
            lines.append("")
            for note in self.notes:
                lines.append(f"* {note}")

        return "\n".join(lines)


# =============================================================================
# Backward-compatible pricing aliases (derived from models.py)
# =============================================================================
GEMINI_3_PRO_INPUT_PRICE_SMALL = PrimrModels.get_price(PrimrModels.PRO_MODEL)[0]  # 2.00
GEMINI_3_PRO_OUTPUT_PRICE_SMALL = PrimrModels.get_price(PrimrModels.PRO_MODEL)[1]  # 12.00

GEMINI_3_FLASH_INPUT_PRICE = PrimrModels.get_price(PrimrModels.FLASH_MODEL)[0]  # 0.50
GEMINI_3_FLASH_OUTPUT_PRICE = PrimrModels.get_price(PrimrModels.FLASH_MODEL)[1]  # 3.00

GOOGLE_SEARCH_PRICE_PER_1000 = SEARCH_COST_PER_QUERY * 1000  # 35.00

_SONNET_5_TOKENIZER_MULTIPLIER = 1.30


def _provider_label_for_model(model_name: str) -> str:
    """Return a short display label for the model's provider."""
    config = PrimrModels.get_model_config(model_name)
    if config is None:
        return "LLM"
    return {
        "xai": "Grok",
        "google": "Gemini",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "ollama": "Ollama",
    }.get(config.provider, config.provider.title())


def _split_cached_tokens(
    cached_input_tokens: int,
    first_input_tokens: int,
    second_input_tokens: int,
) -> tuple[int, int]:
    """Split cached tokens across two input buckets by their input-token share."""
    total_input_tokens = max(0, first_input_tokens) + max(0, second_input_tokens)
    cached_input_tokens = max(0, min(cached_input_tokens, total_input_tokens))
    if cached_input_tokens == 0 or total_input_tokens == 0:
        return (0, 0)

    first_cached = min(
        max(0, first_input_tokens),
        round(cached_input_tokens * max(0, first_input_tokens) / total_input_tokens),
    )
    second_cached = cached_input_tokens - first_cached
    second_cached = min(max(0, second_input_tokens), second_cached)
    first_cached = cached_input_tokens - second_cached
    return (first_cached, second_cached)


def _supports_cached_input_pricing(*model_names: str) -> bool:
    """Return true when any model has a published cached-input rate."""
    return any(
        (config := PrimrModels.get_model_config(model_name)) is not None
        and config.cost_per_1m_input_tokens_cached is not None
        for model_name in model_names
    )


def _apply_tokenizer_safety_factor(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
) -> tuple[int, int, bool]:
    """Inflate estimates for models with documented tokenizer expansion."""
    if model_name != "claude-sonnet-5":
        return (input_tokens, output_tokens, False)
    return (
        ceil(input_tokens * _SONNET_5_TOKENIZER_MULTIPLIER),
        ceil(output_tokens * _SONNET_5_TOKENIZER_MULTIPLIER),
        True,
    )


# Estimated token usage by mode (based on actual runs, split by model)
# Flash is used for scraping/filtering, Pro for writing/analysis
# deep_research_tasks: number of Deep Research API calls (per-task planning cost)
MODE_ESTIMATES = {
    "scrape-test": {
        "flash_input_tokens": 0,
        "flash_output_tokens": 0,
        "pro_input_tokens": 0,
        "pro_output_tokens": 0,
        "deep_research_tasks": 0,
        "search_queries": 0,
        "duration_min": 0,
        "duration_max": 2,
    },
    "scrape-only": {
        "flash_input_tokens": 20_000,
        "flash_output_tokens": 5_000,
        "pro_input_tokens": 0,
        "pro_output_tokens": 0,
        "deep_research_tasks": 0,
        "search_queries": 2,
        "duration_min": 2,
        "duration_max": 5,
    },
    "structured": {
        "flash_input_tokens": 30_000,
        "flash_output_tokens": 10_000,
        "pro_input_tokens": 50_000,
        "pro_output_tokens": 30_000,
        "deep_research_tasks": 0,
        "search_queries": 10,
        "duration_min": 20,
        "duration_max": 30,
    },
    "deep-research": {
        "flash_input_tokens": 0,
        "flash_output_tokens": 0,
        "pro_input_tokens": 0,
        "pro_output_tokens": 0,
        "deep_research_tasks": 1,
        "search_queries": 0,
        "duration_min": 8,
        "duration_max": 15,
    },
    "complete": {
        "flash_input_tokens": 30_000,
        "flash_output_tokens": 10_000,
        "pro_input_tokens": 50_000,
        "pro_output_tokens": 30_000,
        "deep_research_tasks": 1,
        "search_queries": 10,
        "duration_min": 45,
        "duration_max": 75,
    },
    "hybrid": {
        "flash_input_tokens": 30_000,
        "flash_output_tokens": 10_000,
        "pro_input_tokens": 50_000,
        "pro_output_tokens": 30_000,
        "deep_research_tasks": 1,
        "search_queries": 10,
        "duration_min": 20,
        "duration_max": 30,
    },
    # Fast mode: Flash scraping + Grok calls (gap analysis + analysis + 21 individual sections + coherence + cross-validation), no DR, no Pro
    "fast": {
        "flash_input_tokens": 40_000,  # more pages + more external scraping
        "flash_output_tokens": 10_000,
        "pro_input_tokens": 0,
        "pro_output_tokens": 0,
        # Split Grok tokens into reasoning (gap analysis, workbook, cross-val) and writing (sections, coherence, polish)
        # Calibrated from a real production run: 84K/4K reasoning, 1.7M/81K writing
        "grok_reasoning_input_tokens": 100_000,  # gap analysis + analysis workbook + cross-val (~84K actual + margin)
        "grok_reasoning_output_tokens": 5_000,  # gap + workbook + cross-val output (~4K actual + margin)
        "grok_writing_input_tokens": 1_750_000,  # 21 x ~60k per section + coherence + polish (~1.7M actual + margin)
        "grok_writing_output_tokens": 85_000,  # ~34k section writing + 25k coherence + polish (~81K actual + margin)
        "deep_research_tasks": 0,
        "search_queries": 0,  # DDG is free, not Google Search
        # Calibrated from real runs: scraping ~6-10 min, search ~8-12 min, analysis+writing ~15-20 min, cross-val ~5 min
        "duration_min": 30,
        "duration_max": 45,
    },
}

# Verification overhead: 2 Flash LLM calls (~15k input, ~3k output) + free DDG searches
VERIFICATION_OVERHEAD = {
    "flash_input_tokens": 15_000,
    "flash_output_tokens": 3_000,
    "duration_min": 3,
    "duration_max": 5,
}

# AI Strategy adds another Deep Research call per vendor
AI_STRATEGY_OVERHEAD = {
    "deep_research_tasks": 1,
    "duration_min": 8,
    "duration_max": 15,
}

# Lite standalone and in-pipeline AI strategies use the same bounded reasoning-model
# call shape. Keep the token and duration assumptions named so every estimate
# surface prices the live runtime consistently.
LITE_AI_STRATEGY_OVERHEAD = {
    "input_tokens": LITE_AI_STRATEGY_MAX_INPUT_TOKENS,
    "output_tokens": LITE_AI_STRATEGY_MAX_OUTPUT_TOKENS,
    "duration_min": 2,
    "duration_max": 3,
}

# One strategy document in fast mode = one Grok WRITING bundle (shared
# context prefix + strategy prompt + enrichment + cross-validation + polish).
# Shared by the AI-vendor and YAML-strategy estimate branches so the two
# cannot drift apart.
FAST_STRATEGY_BUNDLE = {
    "writing_input_tokens": 200_000,
    "writing_output_tokens": 50_000,
    "duration_min": 3,
    "duration_max": 6,
}


def _yaml_strategy_overhead(
    yaml_strategy_types: Sequence[str], lite_strategy: bool
) -> tuple[int, int, int, list[str], list[str]]:
    """Price YAML strategy documents for the non-fast estimate paths.

    Returns (dr_tasks, duration_min, duration_max, priced, unavailable)
    deltas. On the non-fast runtime only Deep-Research-backed types are
    implemented (each is a single flat-cost DR task); every other type is a
    placeholder the run warn-skips at $0, so pricing it would tell the user
    they are paying for a document they will not get.
    """
    # Lazy: utils stays import-light; deep_budget owns which strategies use DR.
    from primr.core.deep_budget import strategy_uses_deep_research

    dr_tasks, dmin, dmax = 0, 0, 0
    priced: list[str] = []
    unavailable: list[str] = []
    for stype in yaml_strategy_types:
        if strategy_uses_deep_research(stype, lite_strategy=lite_strategy):
            dr_tasks += 1
            dmin += AI_STRATEGY_OVERHEAD["duration_min"]
            dmax += AI_STRATEGY_OVERHEAD["duration_max"]
            priced.append(stype)
        else:
            unavailable.append(stype)
    return dr_tasks, dmin, dmax, priced, unavailable


def _lite_strategy_cost_breakdown(
    input_tokens: int,
    output_tokens: int,
) -> tuple[str | None, TokenCostBreakdown | None, int, int, bool]:
    """Price the exact reasoning model and bounded token shape used at runtime."""
    if not input_tokens and not output_tokens:
        return (None, None, input_tokens, output_tokens, False)

    from primr.ai.routing import Role, pick_model_for_role

    model_name = pick_model_for_role(Role.REASONING)
    input_tokens, output_tokens, tokenizer_adjusted = _apply_tokenizer_safety_factor(
        model_name,
        input_tokens,
        output_tokens,
    )
    config = PrimrModels.get_model_config(model_name)
    if config is None:
        raise KeyError(f"Unknown lite strategy model: {model_name}")
    breakdown = PrimrModels.calculate_cost_breakdown(
        model_name,
        input_tokens,
        output_tokens,
        force_high_tier=config.has_tiered_pricing,
    )
    return (model_name, breakdown, input_tokens, output_tokens, tokenizer_adjusted)


def estimate_cost(
    mode: str,
    include_ai_strategy: bool = False,
    search_free: bool = False,  # Free period ended Jan 5, 2026
    use_historical: bool = True,  # Use historical averages when available
    num_vendors: int = 1,
    lite_strategy: bool = False,
    fast_mode: bool = False,
    premium_mode: bool = False,
    verify: bool = False,
    grok_tier: str = "hybrid",
    strategy_types: Sequence[str] | None = None,
    vendor_research_refreshes: int = 0,
) -> CostEstimate:
    """
    Estimate the cost of a research task.

    Uses historical data from actual runs when available (3+ samples),
    otherwise falls back to default estimates. Calculates blended cost
    across Flash (scraping) and Pro (writing) models.

    Args:
        mode: Research mode (scrape-only, structured, deep-research, complete, hybrid)
        include_ai_strategy: Whether AI strategy analysis is included
        search_free: Whether Google Search is in free period
        use_historical: Whether to use historical averages (requires 3+ samples)
        num_vendors: Number of vendor strategies to generate
        lite_strategy: If True, strategy uses Pro model instead of Deep Research
        fast_mode: If True, use Grok fast mode estimates
        premium_mode: If True, force Gemini + Deep Research estimates
        strategy_types: YAML strategy documents to generate (``--strategy-type``,
            excluding "ai" which is covered by ``include_ai_strategy``). Each is
            a full writing+enrichment bundle; on Deep Research paths some types
            consume a planned-cost Deep Research task. Omitting them understates
            the estimate the ``--budget`` pre-flight gate approves against.
        vendor_research_refreshes: Explicitly requested vendor research refresh
            tasks. Each is priced as a separate Deep Research task.

    Returns:
        CostEstimate with breakdown
    """
    yaml_strategy_types = [s for s in (strategy_types or []) if s and s != "ai"]

    # Fast mode: completely different cost model (Flash + Grok, no DR, no Pro)
    # premium_mode overrides fast_mode (explicit Gemini + DR request)
    if fast_mode and not premium_mode:
        return _estimate_fast_mode_cost(
            include_ai_strategy,
            num_vendors,
            search_free,
            verify=verify,
            grok_tier=grok_tier,
            yaml_strategy_types=yaml_strategy_types,
            vendor_research_refreshes=vendor_research_refreshes,
        )

    # The non-fast runtime treats explicit strategies as REPLACING the default
    # AI strategy (`if strategies: ... elif ai_strategy: ["ai"]` in
    # research_agent), while fast mode runs both. Mirror that precedence here
    # or the gate double-prices the AI strategy on --strategy-type runs. But
    # when the explicit list ALSO names "ai", the runtime runs the AI strategy
    # too, so keep it priced (via include_ai_strategy) rather than dropping it.
    lists_ai_explicitly = any(s == "ai" for s in (strategy_types or []))
    if yaml_strategy_types and not lists_ai_explicitly:
        include_ai_strategy = False

    estimates = MODE_ESTIMATES.get(mode, MODE_ESTIMATES["scrape-only"])

    flash_in = estimates["flash_input_tokens"]
    flash_out = estimates["flash_output_tokens"]
    pro_in = estimates["pro_input_tokens"]
    pro_out = estimates["pro_output_tokens"]
    lite_strategy_in = 0
    lite_strategy_out = 0
    cached_in = 0
    dr_tasks = estimates["deep_research_tasks"]
    search_queries = estimates["search_queries"]
    duration_min = estimates["duration_min"]
    duration_max = estimates["duration_max"]

    # Check for historical data to refine estimates
    historical_used = False
    hist = None
    if use_historical:
        from primr.utils.usage_tracker import get_usage_tracker

        tracker = get_usage_tracker()
        hist = tracker.get_average_by_mode(mode)

        if hist and hist["sample_size"] >= 3:
            # Use historical averages — distribute across flash+pro
            total_hist_in = round(hist["avg_input_tokens"])
            total_hist_out = round(hist["avg_output_tokens"])
            cached_in = round(hist.get("avg_cached_input_tokens", 0))
            # Preserve the flash/pro ratio from defaults
            default_total_in = flash_in + pro_in
            default_total_out = flash_out + pro_out
            if default_total_in > 0:
                flash_in = int(total_hist_in * flash_in / default_total_in)
                pro_in = total_hist_in - flash_in
            else:
                flash_in = 0
                pro_in = total_hist_in
            if default_total_out > 0:
                flash_out = int(total_hist_out * flash_out / default_total_out)
                pro_out = total_hist_out - flash_out
            else:
                flash_out = 0
                pro_out = total_hist_out
            cached_in = max(0, min(cached_in, flash_in + pro_in))

            # Calculate duration range from historical (avg +/- 20%)
            avg_mins = hist["avg_duration_seconds"] / 60
            duration_min = max(1, int(avg_mins * 0.8))
            duration_max = max(1, int(avg_mins * 1.2))
            historical_used = True

    # Add AI strategy overhead (use historical if available)
    ai_strategy_hist = None
    if include_ai_strategy:
        if lite_strategy:
            # Keep this bucket separate so pricing uses the exact reasoning
            # model selected by the live lite-strategy runtime.
            lite_strategy_in = LITE_AI_STRATEGY_OVERHEAD["input_tokens"] * num_vendors
            lite_strategy_out = LITE_AI_STRATEGY_OVERHEAD["output_tokens"] * num_vendors
            duration_min += LITE_AI_STRATEGY_OVERHEAD["duration_min"] * num_vendors
            duration_max += LITE_AI_STRATEGY_OVERHEAD["duration_max"] * num_vendors
        else:
            if use_historical:
                from primr.utils.usage_tracker import get_usage_tracker

                tracker = get_usage_tracker()
                ai_strategy_hist = tracker.get_average_by_mode("ai-strategy")

            if ai_strategy_hist and ai_strategy_hist["sample_size"] >= 3:
                # Historical AI strategy data — each vendor = 1 DR task + historical duration
                dr_tasks += AI_STRATEGY_OVERHEAD["deep_research_tasks"] * num_vendors
                ai_avg_mins = ai_strategy_hist["avg_duration_seconds"] / 60
                duration_min += int(ai_avg_mins * 0.8) * num_vendors
                duration_max += int(ai_avg_mins * 1.2) * num_vendors
            else:
                # Default: each AI strategy = 1 Deep Research task per vendor
                dr_tasks += AI_STRATEGY_OVERHEAD["deep_research_tasks"] * num_vendors
                duration_min += AI_STRATEGY_OVERHEAD["duration_min"] * num_vendors
                duration_max += AI_STRATEGY_OVERHEAD["duration_max"] * num_vendors

    refresh_tasks = max(0, vendor_research_refreshes)
    dr_tasks += refresh_tasks
    duration_min += AI_STRATEGY_OVERHEAD["duration_min"] * refresh_tasks
    duration_max += AI_STRATEGY_OVERHEAD["duration_max"] * refresh_tasks

    # Add YAML strategy documents (--strategy-type). Deep-Research-backed
    # types consume a flat-cost DR task; the rest are placeholders this
    # runtime warn-skips at $0, surfaced in the notes instead of priced.
    (
        dr_delta,
        dmin_delta,
        dmax_delta,
        priced_strategy_types,
        unavailable_strategy_types,
    ) = _yaml_strategy_overhead(yaml_strategy_types, lite_strategy)
    dr_tasks += dr_delta
    duration_min += dmin_delta
    duration_max += dmax_delta

    # Add verification overhead
    if verify:
        flash_in += VERIFICATION_OVERHEAD["flash_input_tokens"]
        flash_out += VERIFICATION_OVERHEAD["flash_output_tokens"]
        duration_min += VERIFICATION_OVERHEAD["duration_min"]
        duration_max += VERIFICATION_OVERHEAD["duration_max"]

    # Hiring signals ride on the Deep Research paths too (fenced stage-1
    # context). Sub-cent LLM cost on the routed utility model - noted rather
    # than tokenized (it degrades to $0 when no routed key is present).
    hiring_dmin, hiring_dmax, hiring_notes = _deep_path_hiring_overhead(mode)
    duration_min += hiring_dmin
    duration_max += hiring_dmax

    # Format duration string
    duration = f"{duration_min}-{duration_max} min"
    if include_ai_strategy:
        duration += " + AI strategy (Pro)" if lite_strategy else " + AI strategy"
    if priced_strategy_types:
        duration += f" + {len(priced_strategy_types)} strategy doc(s)"
    duration += _vendor_refresh_duration_suffix(refresh_tasks)
    if verify:
        duration += " + verification"

    # Resolve the active Pro model (honours AI_REASONING_MODEL env var)
    active_pro = PrimrModels.get_active_pro_model()
    pro_in, pro_out, sonnet_5_tokenizer_adjusted = _apply_tokenizer_safety_factor(
        active_pro.name, pro_in, pro_out
    )

    flash_cached, pro_cached = _split_cached_tokens(cached_in, flash_in, pro_in)
    flash_breakdown = PrimrModels.calculate_cost_breakdown(
        PrimrModels.FLASH_MODEL,
        flash_in,
        flash_out,
        cached_input_tokens=flash_cached,
    )
    # For estimates, use conservative (highest tier) pricing.
    pro_breakdown = PrimrModels.calculate_cost_breakdown(
        active_pro.name,
        pro_in,
        pro_out,
        cached_input_tokens=pro_cached,
        force_high_tier=active_pro.has_tiered_pricing,
    )

    (
        lite_strategy_model,
        lite_strategy_breakdown,
        lite_strategy_in,
        lite_strategy_out,
        lite_strategy_tokenizer_adjusted,
    ) = _lite_strategy_cost_breakdown(lite_strategy_in, lite_strategy_out)

    flash_cost = flash_breakdown.total_cost
    pro_cost = pro_breakdown.total_cost
    lite_cost = lite_strategy_breakdown.total_cost if lite_strategy_breakdown else 0.0
    input_cost = (
        flash_breakdown.input_cost
        + pro_breakdown.input_cost
        + (lite_strategy_breakdown.input_cost if lite_strategy_breakdown else 0.0)
    )
    output_cost = (
        flash_breakdown.output_cost
        + pro_breakdown.output_cost
        + (lite_strategy_breakdown.output_cost if lite_strategy_breakdown else 0.0)
    )
    live_input_cost = (
        flash_breakdown.live_input_cost
        + pro_breakdown.live_input_cost
        + (lite_strategy_breakdown.live_input_cost if lite_strategy_breakdown else 0.0)
    )
    cached_input_cost = flash_breakdown.cached_input_cost + pro_breakdown.cached_input_cost
    long_context_surcharge_cost = (
        flash_breakdown.long_context_surcharge_cost
        + pro_breakdown.long_context_surcharge_cost
        + (lite_strategy_breakdown.long_context_surcharge_cost if lite_strategy_breakdown else 0.0)
    )

    # Deep Research planning cost per task; actual token and tool billing varies.
    deep_research_cost = dr_tasks * DEEP_RESEARCH_COST.standard_task_cost

    # Search cost
    if search_free:
        search_cost = 0.0
    else:
        search_cost = PrimrModels.calculate_search_cost(search_queries)

    total_cost = flash_cost + pro_cost + lite_cost + deep_research_cost + search_cost

    # Build notes
    notes: list[str] = []
    if historical_used and hist is not None:
        notes.append(f"Based on {hist['sample_size']} previous runs")
        if cached_in > 0:
            notes.append(f"Historical cache hits included: ~{cached_in:,} cached input tokens")
    if include_ai_strategy and lite_strategy:
        lite_label = (
            PrimrModels.get_model_config(lite_strategy_model).display_name
            if lite_strategy_model and PrimrModels.get_model_config(lite_strategy_model)
            else lite_strategy_model
        )
        notes.append(f"AI Strategy using {lite_label} reasoning model (lite mode)")
    elif include_ai_strategy and ai_strategy_hist and ai_strategy_hist["sample_size"] >= 3:
        notes.append(f"AI Strategy based on {ai_strategy_hist['sample_size']} runs")
    notes.extend(_strategy_type_notes(priced_strategy_types, unavailable_strategy_types))
    notes.extend(_vendor_refresh_notes(refresh_tasks))

    if verify:
        notes.append("Includes claim verification (~$0.01, DDG searches are free)")
    notes.extend(hiring_notes)

    # Note tiered pricing when active model has it
    if active_pro.has_tiered_pricing:
        threshold_k = active_pro.tier_threshold_tokens // 1000  # type: ignore[operator]
        notes.append(
            f"Using {active_pro.display_name} with tiered pricing. "
            f"Estimate uses conservative (>{threshold_k}k) tier. "
            "Actual cost may be lower."
        )
    if sonnet_5_tokenizer_adjusted:
        notes.append("Claude Sonnet 5 token estimates include a 30% tokenizer safety factor.")
    if lite_strategy_tokenizer_adjusted:
        notes.append("Lite strategy estimate includes a 30% tokenizer safety factor.")

    if cached_in == 0 and _supports_cached_input_pricing(PrimrModels.FLASH_MODEL, active_pro.name):
        notes.append(
            "No pre-run prompt-cache savings assumed; actual cache hits are recorded in usage."
        )

    # Total tokens for backward compat display
    total_input_tokens = flash_in + pro_in + lite_strategy_in
    total_output_tokens = flash_out + pro_out + lite_strategy_out

    return CostEstimate(
        mode=mode,
        estimated_input_tokens=total_input_tokens,
        estimated_output_tokens=total_output_tokens,
        estimated_search_queries=search_queries,
        input_cost=input_cost,
        output_cost=output_cost,
        search_cost=search_cost,
        total_cost=total_cost,
        duration_minutes=duration,
        notes=notes,
        deep_research_cost=deep_research_cost,
        estimated_live_input_tokens=flash_breakdown.live_input_tokens
        + pro_breakdown.live_input_tokens
        + (lite_strategy_breakdown.live_input_tokens if lite_strategy_breakdown else 0),
        estimated_cached_input_tokens=flash_breakdown.cached_input_tokens
        + pro_breakdown.cached_input_tokens,
        live_input_cost=live_input_cost,
        cached_input_cost=cached_input_cost,
        long_context_surcharge_cost=long_context_surcharge_cost,
    )


def _estimate_fast_mode_cost(
    include_ai_strategy: bool,
    num_vendors: int,
    search_free: bool,
    verify: bool = False,
    grok_tier: str = "hybrid",
    yaml_strategy_types: Sequence[str] = (),
    vendor_research_refreshes: int = 0,
) -> CostEstimate:
    """Estimate cost for fast mode (Grok pipeline)."""
    fast = MODE_ESTIMATES["fast"]
    flash_in = fast["flash_input_tokens"]
    flash_out = fast["flash_output_tokens"]
    grok_reasoning_in = fast["grok_reasoning_input_tokens"]
    grok_reasoning_out = fast["grok_reasoning_output_tokens"]
    grok_writing_in = fast["grok_writing_input_tokens"]
    grok_writing_out = fast["grok_writing_output_tokens"]
    search_queries = fast["search_queries"]
    duration_min = fast["duration_min"]
    duration_max = fast["duration_max"]
    refresh_tasks = max(0, vendor_research_refreshes)
    duration_min += AI_STRATEGY_OVERHEAD["duration_min"] * refresh_tasks
    duration_max += AI_STRATEGY_OVERHEAD["duration_max"] * refresh_tasks

    # AI strategy adds Grok writing tokens per vendor (enriched context + CV + polish)
    if include_ai_strategy:
        grok_writing_in += FAST_STRATEGY_BUNDLE["writing_input_tokens"] * num_vendors
        grok_writing_out += FAST_STRATEGY_BUNDLE["writing_output_tokens"] * num_vendors
        duration_min += FAST_STRATEGY_BUNDLE["duration_min"] * num_vendors
        duration_max += FAST_STRATEGY_BUNDLE["duration_max"] * num_vendors

    # YAML strategy documents (--strategy-type): fast mode has no Deep
    # Research, so each is the same writing bundle as one AI-strategy vendor,
    # and unlike the non-fast path they run IN ADDITION to the AI strategy.
    if yaml_strategy_types:
        n = len(yaml_strategy_types)
        grok_writing_in += FAST_STRATEGY_BUNDLE["writing_input_tokens"] * n
        grok_writing_out += FAST_STRATEGY_BUNDLE["writing_output_tokens"] * n
        duration_min += FAST_STRATEGY_BUNDLE["duration_min"] * n
        duration_max += FAST_STRATEGY_BUNDLE["duration_max"] * n

    # Verification overhead (Flash model for claim extraction + classification)
    if verify:
        flash_in += VERIFICATION_OVERHEAD["flash_input_tokens"]
        flash_out += VERIFICATION_OVERHEAD["flash_output_tokens"]
        duration_min += VERIFICATION_OVERHEAD["duration_min"]
        duration_max += VERIFICATION_OVERHEAD["duration_max"]

    # Hiring-signals overhead: two Grok calls (triage + batched extraction)
    # off the writing model. Conservative budget assumes we actually find
    # postings — roughly half of mid-market companies do. Whole-token budget
    # is small enough that we always bake it in rather than gating it.
    grok_writing_in += 25_000
    grok_writing_out += 3_500
    duration_min += 1
    duration_max += 2

    # Resolve the model pair.
    #
    # For ``--grok-tier max`` the user has explicitly opted into Grok-
    # everywhere (no Gemini writing). For ``fast`` and ``hybrid`` tiers, defer
    # the writing model to the cross-provider router so the estimate matches
    # what the live pipeline actually runs (the v1.24.0 sub-$1 default uses
    # gemini-3.1-flash-lite for bulk writing when GEMINI_API_KEY is set).
    # The router for REASONING already returns Grok 4.3 when XAI_API_KEY is
    # set, which is what every supported tier uses for reasoning.
    tier_reasoning_model, tier_writing_model = PrimrModels.get_grok_models(GrokTier(grok_tier))
    if grok_tier == "max":
        reasoning_model, writing_model = tier_reasoning_model, tier_writing_model
        utility_model = tier_writing_model
    else:
        from primr.ai.routing import Role, pick_model_for_role

        utility_model = pick_model_for_role(Role.UTILITY)
        reasoning_model = pick_model_for_role(Role.REASONING)
        writing_model = pick_model_for_role(Role.WRITING)

    utility_tokenizer_adjusted = False
    reasoning_tokenizer_adjusted = False
    writing_tokenizer_adjusted = False
    flash_in, flash_out, utility_tokenizer_adjusted = _apply_tokenizer_safety_factor(
        utility_model, flash_in, flash_out
    )
    grok_reasoning_in, grok_reasoning_out, reasoning_tokenizer_adjusted = (
        _apply_tokenizer_safety_factor(reasoning_model, grok_reasoning_in, grok_reasoning_out)
    )
    grok_writing_in, grok_writing_out, writing_tokenizer_adjusted = _apply_tokenizer_safety_factor(
        writing_model, grok_writing_in, grok_writing_out
    )

    # Costs: price each bucket using the resolved model. Pre-run estimates do
    # not assume prompt-cache hits. Pass prompt_tokens so ≥200k long-context
    # surcharges (Grok 4.3/4.5) apply when stage input estimates are large.
    utility_breakdown = PrimrModels.calculate_cost_breakdown(
        utility_model, flash_in, flash_out, prompt_tokens=flash_in
    )
    reasoning_breakdown = PrimrModels.calculate_cost_breakdown(
        reasoning_model, grok_reasoning_in, grok_reasoning_out, prompt_tokens=grok_reasoning_in
    )
    writing_breakdown = PrimrModels.calculate_cost_breakdown(
        writing_model, grok_writing_in, grok_writing_out, prompt_tokens=grok_writing_in
    )
    utility_cost = utility_breakdown.total_cost
    reasoning_cost = reasoning_breakdown.total_cost
    writing_cost = writing_breakdown.total_cost
    search_cost = 0.0 if search_free else PrimrModels.calculate_search_cost(search_queries)

    refresh_cost = refresh_tasks * DEEP_RESEARCH_COST.standard_task_cost
    total_cost = utility_cost + reasoning_cost + writing_cost + search_cost + refresh_cost

    # Split for display.
    total_input_cost = (
        utility_breakdown.input_cost + reasoning_breakdown.input_cost + writing_breakdown.input_cost
    )
    total_output_cost = (
        utility_breakdown.output_cost
        + reasoning_breakdown.output_cost
        + writing_breakdown.output_cost
    )
    live_input_cost = (
        utility_breakdown.live_input_cost
        + reasoning_breakdown.live_input_cost
        + writing_breakdown.live_input_cost
    )
    cached_input_cost = (
        utility_breakdown.cached_input_cost
        + reasoning_breakdown.cached_input_cost
        + writing_breakdown.cached_input_cost
    )
    long_context_surcharge_cost = (
        utility_breakdown.long_context_surcharge_cost
        + reasoning_breakdown.long_context_surcharge_cost
        + writing_breakdown.long_context_surcharge_cost
    )

    grok_in_total = grok_reasoning_in + grok_writing_in
    grok_out_total = grok_reasoning_out + grok_writing_out

    # Strategy stages flow through the reasoning stack, so attribute their
    # duration suffix to whichever provider is doing the reasoning.
    strategy_provider = _provider_label_for_model(reasoning_model)

    duration = f"{duration_min}-{duration_max} min"
    if include_ai_strategy:
        duration += f" + AI strategy ({strategy_provider})"
    if yaml_strategy_types:
        duration += f" + {len(yaml_strategy_types)} strategy doc(s)"
    duration += _vendor_refresh_duration_suffix(refresh_tasks)

    tier_labels = {
        "fast": "Grok 4.3 (low-effort)",
        "hybrid": "Grok 4.3 hybrid",
        "max": "Grok 4.5 max",
    }
    tier_label = tier_labels.get(grok_tier, "Grok")
    mode_provider = _provider_label_for_model(reasoning_model)
    # Product CLI mode name is "full"; parenthetical names the priced backend path.
    estimate_mode = (
        f"full ({tier_label})"
        if mode_provider == "Grok" or grok_tier == "max"
        else f"full ({mode_provider} routed)"
    )
    tier_desc = f"{reasoning_model} reasoning + {writing_model} writing + {utility_model} utility"
    if grok_tier == "fast":
        tier_desc = (
            f"{reasoning_model} (reasoning_effort=low) + {writing_model} writing "
            f"+ {utility_model} utility"
        )
    elif grok_tier == "max":
        tier_desc = f"{reasoning_model} for all stages (max tier)"
    notes = [f"Full mode: {tier_desc}"]
    if include_ai_strategy:
        notes.append(f"AI Strategy via {strategy_provider} ({num_vendors} vendor(s))")
    if yaml_strategy_types:
        notes.append(f"Strategy documents included: {', '.join(yaml_strategy_types)}")
    notes.extend(_vendor_refresh_notes(refresh_tasks))
    if verify:
        notes.append("Claim verification via Flash (~$0.01, 3-5 min)")
    notes.append(
        "Hiring signals via ATS / careers page (~$0.01, +1-2 min; skip with PRIMR_SKIP_HIRING_SIGNALS=1)"
    )
    if utility_tokenizer_adjusted or reasoning_tokenizer_adjusted or writing_tokenizer_adjusted:
        notes.append("Claude Sonnet 5 token estimates include a 30% tokenizer safety factor.")
    if _supports_cached_input_pricing(utility_model, reasoning_model, writing_model):
        notes.append(
            "No pre-run prompt-cache savings assumed; actual cache hits are recorded in usage."
        )

    total_input_tokens = flash_in + grok_in_total
    total_output_tokens = flash_out + grok_out_total
    total_live_input_tokens = (
        utility_breakdown.live_input_tokens
        + reasoning_breakdown.live_input_tokens
        + writing_breakdown.live_input_tokens
    )
    total_cached_input_tokens = (
        utility_breakdown.cached_input_tokens
        + reasoning_breakdown.cached_input_tokens
        + writing_breakdown.cached_input_tokens
    )

    return CostEstimate(
        mode=estimate_mode,
        estimated_input_tokens=total_input_tokens,
        estimated_output_tokens=total_output_tokens,
        estimated_search_queries=search_queries,
        input_cost=total_input_cost,
        output_cost=total_output_cost,
        search_cost=search_cost,
        total_cost=total_cost,
        duration_minutes=duration,
        notes=notes,
        deep_research_cost=refresh_cost,
        estimated_live_input_tokens=total_live_input_tokens,
        estimated_cached_input_tokens=total_cached_input_tokens,
        live_input_cost=live_input_cost,
        cached_input_cost=cached_input_cost,
        long_context_surcharge_cost=long_context_surcharge_cost,
    )


def display_cost_estimate(
    mode: str,
    company_name: str,
    include_ai_strategy: bool = False,
    num_vendors: int = 1,
    lite_strategy: bool = False,
    fast_mode: bool = False,
    premium_mode: bool = False,
    verify: bool = False,
    grok_tier: str = "hybrid",
    strategy_types: Sequence[str] | None = None,
    vendor_research_refreshes: int = 0,
) -> bool:
    """
    Display cost estimate and ask for confirmation.

    Args:
        mode: Research mode
        company_name: Company being researched
        include_ai_strategy: Whether AI strategy is included
        num_vendors: Number of vendor strategies
        lite_strategy: If True, strategy uses Pro model instead of DR
        fast_mode: If True, use Grok fast mode estimates
        premium_mode: If True, force Gemini + Deep Research estimates
        strategy_types: YAML strategy documents to price (must match what
            ``--dry-run`` and the ``--budget`` gate price, or the interactive
            approval number diverges from the run's actual spend)
        vendor_research_refreshes: Explicit vendor research refresh tasks to
            include in the displayed approval amount.

    Returns:
        True if user confirms, False to cancel
    """
    import sys

    estimate = estimate_cost(
        mode,
        include_ai_strategy,
        num_vendors=num_vendors,
        lite_strategy=lite_strategy,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
        verify=verify,
        grok_tier=grok_tier,
        strategy_types=strategy_types,
        vendor_research_refreshes=vendor_research_refreshes,
    )

    # Clean single line with visible text
    print(f"\n{company_name} | {mode} | ~${estimate.total_cost:.2f} | {estimate.duration_minutes}")
    sys.stdout.flush()

    # Ask for confirmation with visible prompt
    try:
        sys.stdout.write("Proceed? [Y/n] ")
        sys.stdout.flush()
        response = input().strip().lower()
        return response in ("", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return False


def get_cost_summary(mode: str, include_ai_strategy: bool = False) -> str:
    """
    Get a one-line cost summary for display.

    Args:
        mode: Research mode
        include_ai_strategy: Whether AI strategy is included

    Returns:
        One-line summary string
    """
    estimate = estimate_cost(mode, include_ai_strategy)
    return f"~${estimate.total_cost:.2f} ({estimate.duration_minutes})"
