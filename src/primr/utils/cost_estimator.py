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

from dataclasses import dataclass
from enum import Enum

from primr.config.models import (
    DEEP_RESEARCH_COST,
    SEARCH_COST_PER_QUERY,
    PrimrModels,
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

        if self.estimated_search_queries > 0:
            lines.append(f"  Search: ~{self.estimated_search_queries} queries (${self.search_cost:.4f})")

        if self.deep_research_cost > 0:
            lines.append(f"  Deep Research: ${self.deep_research_cost:.2f} (approximate)")

        lines.extend([
            "",
            f"Estimated Total: ${self.total_cost:.2f}",
        ])

        if self.notes:
            lines.append("")
            for note in self.notes:
                lines.append(f"* {note}")

        return "\n".join(lines)


# =============================================================================
# Backward-compatible pricing aliases (derived from models.py)
# =============================================================================
GEMINI_3_PRO_INPUT_PRICE_SMALL = PrimrModels.get_price(PrimrModels.PRO_MODEL)[0]    # 2.00
GEMINI_3_PRO_OUTPUT_PRICE_SMALL = PrimrModels.get_price(PrimrModels.PRO_MODEL)[1]   # 12.00

GEMINI_3_FLASH_INPUT_PRICE = PrimrModels.get_price(PrimrModels.FLASH_MODEL)[0]      # 0.50
GEMINI_3_FLASH_OUTPUT_PRICE = PrimrModels.get_price(PrimrModels.FLASH_MODEL)[1]     # 3.00

GOOGLE_SEARCH_PRICE_PER_1000 = SEARCH_COST_PER_QUERY * 1000  # 35.00


# Estimated token usage by mode (based on actual runs, split by model)
# Flash is used for scraping/filtering, Pro for writing/analysis
# deep_research_tasks: number of Deep Research API calls (flat per-task cost)
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
    # Fast mode: Flash scraping + 6 Grok calls (1 analysis + 5 report batches), no DR, no Pro
    "fast": {
        "flash_input_tokens": 15_000,
        "flash_output_tokens": 4_000,
        "pro_input_tokens": 0,
        "pro_output_tokens": 0,
        "grok_input_tokens": 250_000,  # analysis ~40k + 5 batches x ~40k
        "grok_output_tokens": 30_000,  # analysis ~12k + 5 batches x ~3.5k
        "deep_research_tasks": 0,
        "search_queries": 5,
        "duration_min": 8,
        "duration_max": 15,
    },
}

# AI Strategy adds another Deep Research call per vendor
AI_STRATEGY_OVERHEAD = {
    "deep_research_tasks": 1,
    "duration_min": 8,
    "duration_max": 15,
}


def estimate_cost(
    mode: str,
    include_ai_strategy: bool = False,
    search_free: bool = False,  # Free period ended Jan 5, 2026
    use_historical: bool = True,  # Use historical averages when available
    num_vendors: int = 1,
    lite_strategy: bool = False,
    fast_mode: bool = False,
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
        fast_mode: If True, use Grok 4.1 fast mode estimates

    Returns:
        CostEstimate with breakdown
    """
    # Fast mode: completely different cost model (Flash + Grok, no DR, no Pro)
    if fast_mode:
        return _estimate_fast_mode_cost(include_ai_strategy, num_vendors, search_free)

    estimates = MODE_ESTIMATES.get(mode, MODE_ESTIMATES["scrape-only"])

    flash_in = estimates["flash_input_tokens"]
    flash_out = estimates["flash_output_tokens"]
    pro_in = estimates["pro_input_tokens"]
    pro_out = estimates["pro_output_tokens"]
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
            total_hist_in = hist["avg_input_tokens"]
            total_hist_out = hist["avg_output_tokens"]
            # Preserve the flash/pro ratio from defaults
            default_total_in = flash_in + pro_in
            default_total_out = flash_out + pro_out
            if default_total_in > 0:
                flash_in = int(total_hist_in * flash_in / default_total_in)
                pro_in = total_hist_in - flash_in
            else:
                pro_in = total_hist_in
            if default_total_out > 0:
                flash_out = int(total_hist_out * flash_out / default_total_out)
                pro_out = total_hist_out - flash_out
            else:
                pro_out = total_hist_out

            # Calculate duration range from historical (avg +/- 20%)
            avg_mins = hist["avg_duration_seconds"] / 60
            duration_min = int(avg_mins * 0.8)
            duration_max = int(avg_mins * 1.2)
            historical_used = True

    # Add AI strategy overhead (use historical if available)
    ai_strategy_hist = None
    if include_ai_strategy:
        if lite_strategy:
            # Lite strategy: Pro model instead of Deep Research per vendor
            # ~50k input + ~10k output tokens per vendor
            pro_in += 50_000 * num_vendors
            pro_out += 10_000 * num_vendors
            duration_min += 2 * num_vendors
            duration_max += 3 * num_vendors
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

    # Format duration string
    duration = f"{duration_min}-{duration_max} min"
    if include_ai_strategy:
        duration += " + AI strategy (Pro)" if lite_strategy else " + AI strategy"

    # Resolve the active Pro model (honours AI_REASONING_MODEL env var)
    active_pro = PrimrModels.get_active_pro_model()

    # Calculate blended cost from Flash + active Pro model
    flash_cost = PrimrModels.calculate_flash_cost(flash_in, flash_out)
    # For estimates, use conservative (highest tier) pricing
    pro_cost = PrimrModels.calculate_cost_conservative(active_pro.name, pro_in, pro_out)

    # Per-component cost for display
    flash_inp_price, flash_out_price = PrimrModels.get_price(PrimrModels.FLASH_MODEL)
    if active_pro.has_tiered_pricing:
        pro_inp_price = active_pro.cost_per_1m_input_tokens_high  # type: ignore[assignment]
        pro_out_price = active_pro.cost_per_1m_output_tokens_high  # type: ignore[assignment]
    else:
        pro_inp_price = active_pro.cost_per_1m_input_tokens
        pro_out_price = active_pro.cost_per_1m_output_tokens
    input_cost = (flash_in / 1_000_000) * flash_inp_price + (pro_in / 1_000_000) * pro_inp_price
    output_cost = (flash_out / 1_000_000) * flash_out_price + (pro_out / 1_000_000) * pro_out_price

    # Deep Research cost (flat per-task)
    deep_research_cost = dr_tasks * DEEP_RESEARCH_COST.standard_task_cost

    # Search cost
    if search_free:
        search_cost = 0.0
    else:
        search_cost = PrimrModels.calculate_search_cost(search_queries)

    total_cost = flash_cost + pro_cost + deep_research_cost + search_cost

    # Build notes
    notes: list[str] = []
    if historical_used and hist is not None:
        notes.append(f"Based on {hist['sample_size']} previous runs")
    if include_ai_strategy and lite_strategy:
        notes.append("AI Strategy using Pro model (lite mode)")
    elif include_ai_strategy and ai_strategy_hist and ai_strategy_hist["sample_size"] >= 3:
        notes.append(f"AI Strategy based on {ai_strategy_hist['sample_size']} runs")

    # Note tiered pricing when active model has it
    if active_pro.has_tiered_pricing:
        threshold_k = active_pro.tier_threshold_tokens // 1000  # type: ignore[operator]
        notes.append(
            f"Using {active_pro.display_name} with tiered pricing. "
            f"Estimate uses conservative (>{threshold_k}k) tier. "
            "Actual cost may be lower."
        )

    # Total tokens for backward compat display
    total_input_tokens = flash_in + pro_in
    total_output_tokens = flash_out + pro_out

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
    )


def _estimate_fast_mode_cost(
    include_ai_strategy: bool,
    num_vendors: int,
    search_free: bool,
) -> CostEstimate:
    """Estimate cost for fast mode (Grok 4.1 pipeline)."""
    fast = MODE_ESTIMATES["fast"]
    flash_in = fast["flash_input_tokens"]
    flash_out = fast["flash_output_tokens"]
    grok_in = fast["grok_input_tokens"]
    grok_out = fast["grok_output_tokens"]
    search_queries = fast["search_queries"]
    duration_min = fast["duration_min"]
    duration_max = fast["duration_max"]

    # AI strategy adds Grok tokens per vendor
    if include_ai_strategy:
        grok_in += 100_000 * num_vendors   # strategy prompt + context
        grok_out += 10_000 * num_vendors   # strategy output
        duration_min += 2 * num_vendors
        duration_max += 3 * num_vendors

    # Costs
    flash_cost = PrimrModels.calculate_flash_cost(flash_in, flash_out)
    grok_cost = PrimrModels.calculate_cost(PrimrModels.GROK_MODEL, grok_in, grok_out)
    search_cost = 0.0 if search_free else PrimrModels.calculate_search_cost(search_queries)

    total_cost = flash_cost + grok_cost + search_cost

    # Split for display
    flash_input_cost = (flash_in / 1_000_000) * GEMINI_3_FLASH_INPUT_PRICE
    flash_output_cost = (flash_out / 1_000_000) * GEMINI_3_FLASH_OUTPUT_PRICE
    grok_input_price, grok_output_price = PrimrModels.get_price(PrimrModels.GROK_MODEL)
    grok_input_cost = (grok_in / 1_000_000) * grok_input_price
    grok_output_cost = (grok_out / 1_000_000) * grok_output_price

    total_input_cost = flash_input_cost + grok_input_cost
    total_output_cost = flash_output_cost + grok_output_cost

    duration = f"{duration_min}-{duration_max} min"
    if include_ai_strategy:
        duration += " + AI strategy (Grok)"

    notes = ["Fast mode: Grok 4.1 accordion (1 analysis + 5 report batches, no Deep Research)"]
    if include_ai_strategy:
        notes.append(f"AI Strategy via Grok ({num_vendors} vendor(s))")

    total_input_tokens = flash_in + grok_in
    total_output_tokens = flash_out + grok_out

    return CostEstimate(
        mode="fast",
        estimated_input_tokens=total_input_tokens,
        estimated_output_tokens=total_output_tokens,
        estimated_search_queries=search_queries,
        input_cost=total_input_cost,
        output_cost=total_output_cost,
        search_cost=search_cost,
        total_cost=total_cost,
        duration_minutes=duration,
        notes=notes,
        deep_research_cost=0.0,
    )


def display_cost_estimate(
    mode: str,
    company_name: str,
    include_ai_strategy: bool = False,
    num_vendors: int = 1,
    lite_strategy: bool = False,
    fast_mode: bool = False,
) -> bool:
    """
    Display cost estimate and ask for confirmation.

    Args:
        mode: Research mode
        company_name: Company being researched
        include_ai_strategy: Whether AI strategy is included
        num_vendors: Number of vendor strategies
        lite_strategy: If True, strategy uses Pro model instead of DR
        fast_mode: If True, use Grok 4.1 fast mode estimates

    Returns:
        True if user confirms, False to cancel
    """
    import sys
    estimate = estimate_cost(mode, include_ai_strategy, num_vendors=num_vendors, lite_strategy=lite_strategy, fast_mode=fast_mode)

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
