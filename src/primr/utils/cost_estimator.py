"""
Cost Estimator for Gemini API usage.

Provides estimated costs before running research to help users
make informed decisions about API spending.

Pricing as of December 2025:
- Gemini 3 Pro: $2/$12 per 1M tokens (input/output) for prompts <= 200k
- Gemini 3 Pro: $4/$18 per 1M tokens (input/output) for prompts > 200k
- Deep Research: Uses Gemini 3 Pro pricing + Google Search (free until Jan 5, 2026)
- Google Search Grounding: Free until Jan 5, 2026, then $14/1000 queries
"""

from dataclasses import dataclass
from enum import Enum

from primr.utils.console import get_console


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
    notes: list

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

        lines.extend([
            "",
            f"Estimated Total: ${self.total_cost:.2f}",
        ])

        if self.notes:
            lines.append("")
            for note in self.notes:
                lines.append(f"* {note}")

        return "\n".join(lines)


# Pricing constants (per 1M tokens, USD)
GEMINI_3_PRO_INPUT_PRICE_SMALL = 2.00  # prompts <= 200k tokens
GEMINI_3_PRO_INPUT_PRICE_LARGE = 4.00  # prompts > 200k tokens
GEMINI_3_PRO_OUTPUT_PRICE_SMALL = 12.00  # prompts <= 200k tokens
GEMINI_3_PRO_OUTPUT_PRICE_LARGE = 18.00  # prompts > 200k tokens

# Google Search pricing (free until Jan 5, 2026)
GOOGLE_SEARCH_PRICE_PER_1000 = 14.00  # $14 per 1000 queries after free period
GOOGLE_SEARCH_FREE_UNTIL = "January 5, 2026"

# Estimated token usage by mode (based on actual runs Dec 2025)
# These are fallback defaults - actual estimates come from usage_history.json
MODE_ESTIMATES = {
    "structured": {
        "input_tokens": 80_000,   # Website content + prompts
        "output_tokens": 40_000,  # 18 sections
        "search_queries": 10,     # Google Custom Search
        "duration_min": 20,       # Minutes (low estimate)
        "duration_max": 30,       # Minutes (high estimate)
    },
    "deep-research": {
        "input_tokens": 50_000,   # Prompt + context (estimated, API doesn't expose)
        "output_tokens": 15_000,  # ~14k actual from runs
        "search_queries": 30,     # Deep Research autonomous search
        "duration_min": 8,
        "duration_max": 15,
    },
    "complete": {
        "input_tokens": 100_000,  # Step 1 + Step 2
        "output_tokens": 30_000,  # ~14k per step
        "search_queries": 40,     # Both engines
        "duration_min": 25,
        "duration_max": 40,
    },
    "hybrid": {
        "input_tokens": 100_000,  # Both engines parallel
        "output_tokens": 30_000,  # Combined output
        "search_queries": 40,     # Both engines
        "duration_min": 20,
        "duration_max": 30,
    },
}

# AI Strategy adds another Deep Research call
AI_STRATEGY_OVERHEAD = {
    "input_tokens": 50_000,   # Prompt + company context + vendor research
    "output_tokens": 12_000,  # ~10-12k actual
    "duration_min": 8,
    "duration_max": 15,
}


def estimate_cost(
    mode: str,
    include_ai_strategy: bool = False,
    search_free: bool = True,  # Free until Jan 5, 2026
    use_historical: bool = True,  # Use historical averages when available
) -> CostEstimate:
    """
    Estimate the cost of a research task.

    Uses historical data from actual runs when available (3+ samples),
    otherwise falls back to default estimates.

    Args:
        mode: Research mode (structured, deep-research, complete, hybrid)
        include_ai_strategy: Whether AI strategy analysis is included
        search_free: Whether Google Search is in free period
        use_historical: Whether to use historical averages (requires 3+ samples)

    Returns:
        CostEstimate with breakdown
    """
    estimates = MODE_ESTIMATES.get(mode, MODE_ESTIMATES["structured"])

    input_tokens = estimates["input_tokens"]
    output_tokens = estimates["output_tokens"]
    search_queries = estimates["search_queries"]
    duration_min = estimates["duration_min"]
    duration_max = estimates["duration_max"]

    # Check for historical data to refine estimates
    historical_used = False
    if use_historical:
        from primr.utils.usage_tracker import get_usage_tracker
        tracker = get_usage_tracker()
        hist = tracker.get_average_by_mode(mode)

        if hist and hist["sample_size"] >= 3:
            # Use historical averages
            input_tokens = hist["avg_input_tokens"]
            output_tokens = hist["avg_output_tokens"]

            # Calculate duration range from historical (avg +/- 20%)
            avg_mins = hist["avg_duration_seconds"] / 60
            duration_min = int(avg_mins * 0.8)
            duration_max = int(avg_mins * 1.2)
            historical_used = True

    # Add AI strategy overhead (use historical if available)
    ai_strategy_hist = None
    if include_ai_strategy:
        if use_historical:
            from primr.utils.usage_tracker import get_usage_tracker
            tracker = get_usage_tracker()
            ai_strategy_hist = tracker.get_average_by_mode("ai-strategy")

        if ai_strategy_hist and ai_strategy_hist["sample_size"] >= 3:
            # Use historical AI strategy data
            input_tokens += ai_strategy_hist["avg_input_tokens"]
            output_tokens += ai_strategy_hist["avg_output_tokens"]
            ai_avg_mins = ai_strategy_hist["avg_duration_seconds"] / 60
            duration_min += int(ai_avg_mins * 0.8)
            duration_max += int(ai_avg_mins * 1.2)
        else:
            # Use default estimates
            input_tokens += AI_STRATEGY_OVERHEAD["input_tokens"]
            output_tokens += AI_STRATEGY_OVERHEAD["output_tokens"]
            duration_min += AI_STRATEGY_OVERHEAD["duration_min"]
            duration_max += AI_STRATEGY_OVERHEAD["duration_max"]

    # Format duration string
    duration = f"{duration_min}-{duration_max} min"
    if include_ai_strategy:
        duration += " + AI strategy"

    # Calculate costs
    # Use small context pricing (most research fits in 200k)
    input_cost = (input_tokens / 1_000_000) * GEMINI_3_PRO_INPUT_PRICE_SMALL
    output_cost = (output_tokens / 1_000_000) * GEMINI_3_PRO_OUTPUT_PRICE_SMALL

    # Search cost (free until Jan 5, 2026)
    if search_free:
        search_cost = 0.0
    else:
        search_cost = (search_queries / 1000) * GOOGLE_SEARCH_PRICE_PER_1000

    total_cost = input_cost + output_cost + search_cost

    # Build notes
    notes: list[str] = []
    if historical_used and hist is not None:
        notes.append(f"Based on {hist['sample_size']} previous runs")
    if include_ai_strategy and ai_strategy_hist and ai_strategy_hist["sample_size"] >= 3:
        notes.append(f"AI Strategy based on {ai_strategy_hist['sample_size']} runs")
    if search_free:
        notes.append(f"Google Search FREE until {GOOGLE_SEARCH_FREE_UNTIL}")

    return CostEstimate(
        mode=mode,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_search_queries=search_queries,
        input_cost=input_cost,
        output_cost=output_cost,
        search_cost=search_cost,
        total_cost=total_cost,
        duration_minutes=duration,
        notes=notes,
    )


def display_cost_estimate(
    mode: str,
    company_name: str,
    include_ai_strategy: bool = False,
) -> bool:
    """
    Display cost estimate and ask for confirmation.

    Args:
        mode: Research mode
        company_name: Company being researched
        include_ai_strategy: Whether AI strategy is included

    Returns:
        True if user confirms, False to cancel
    """
    console = get_console()

    estimate = estimate_cost(mode, include_ai_strategy)

    console.blank()
    console.text("=" * 60)
    console.text(f"COST ESTIMATE: Research for {company_name}")
    console.text("=" * 60)
    console.blank()
    console.text(str(estimate))
    console.blank()
    console.text("=" * 60)
    console.blank()

    # Ask for confirmation
    try:
        response = input("Proceed with research? [Y/n]: ").strip().lower()
        return response in ("", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        console.text("\nCancelled.")
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
