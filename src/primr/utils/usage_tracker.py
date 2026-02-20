"""
Usage Tracker for Gemini API calls.

Tracks actual token usage and costs during research runs,
and can update cost estimates based on historical data.

Usage:
    tracker = UsageTracker()
    tracker.record_usage("structured", input_tokens=150000, output_tokens=80000)
    tracker.save()

    # Get actual cost
    print(tracker.get_session_cost())

    # Update estimates based on history
    tracker.update_estimates()
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from primr.utils.logging_config import get_logger

logger = get_logger("utils.usage_tracker")

# Default storage location
USAGE_FILE = Path(__file__).parent.parent.parent.parent / "logs" / "usage_history.json"


@dataclass
class UsageRecord:
    """Record of a single API usage event."""
    timestamp: str
    mode: str
    company: str
    input_tokens: int
    output_tokens: int
    search_queries: int
    duration_seconds: float
    input_cost: float
    output_cost: float
    search_cost: float
    total_cost: float
    deep_research_cost: float = 0.0  # Flat per-task DR cost

    @classmethod
    def create(
        cls,
        mode: str,
        company: str,
        input_tokens: int,
        output_tokens: int,
        search_queries: int = 0,
        duration_seconds: float = 0.0,
        pipeline_cost: float | None = None,
        deep_research_cost: float = 0.0,
    ) -> "UsageRecord":
        """Create a usage record with costs.

        Args:
            pipeline_cost: Pre-calculated accurate cost from AI client
                (per-model, tier-aware). When provided, skips token-based
                pricing. When None, falls back to conservative pricing
                from tokens (backward compat).
            deep_research_cost: Flat per-task Deep Research cost ($2.50/task).
        """
        from primr.config.models import SEARCH_COST_PER_QUERY

        search_cost = search_queries * SEARCH_COST_PER_QUERY

        if pipeline_cost is not None:
            # Use pre-calculated accurate cost from AI client
            return cls(
                timestamp=datetime.now().isoformat(),
                mode=mode,
                company=company,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                search_queries=search_queries,
                duration_seconds=duration_seconds,
                input_cost=0.0,
                output_cost=0.0,
                search_cost=search_cost,
                total_cost=pipeline_cost + search_cost + deep_research_cost,
                deep_research_cost=deep_research_cost,
            )

        # Fallback: estimate cost from tokens using active Pro model pricing
        from primr.config.models import PrimrModels

        active_pro = PrimrModels.get_active_pro_model()

        # For tiered models, use high-tier pricing (conservative)
        if active_pro.has_tiered_pricing:
            INPUT_PRICE = active_pro.cost_per_1m_input_tokens_high  # type: ignore[assignment]
            OUTPUT_PRICE = active_pro.cost_per_1m_output_tokens_high  # type: ignore[assignment]
        else:
            INPUT_PRICE = active_pro.cost_per_1m_input_tokens
            OUTPUT_PRICE = active_pro.cost_per_1m_output_tokens

        input_cost = (input_tokens / 1_000_000) * INPUT_PRICE
        output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE

        return cls(
            timestamp=datetime.now().isoformat(),
            mode=mode,
            company=company,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            search_queries=search_queries,
            duration_seconds=duration_seconds,
            input_cost=input_cost,
            output_cost=output_cost,
            search_cost=search_cost,
            total_cost=input_cost + output_cost + search_cost + deep_research_cost,
            deep_research_cost=deep_research_cost,
        )


@dataclass
class SessionUsage:
    """Tracks usage for the current session."""
    records: list[UsageRecord] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_search_queries: int = 0
    total_cost: float = 0.0

    def add(self, record: UsageRecord) -> None:
        """Add a usage record to the session."""
        self.records.append(record)
        self.total_input_tokens += record.input_tokens
        self.total_output_tokens += record.output_tokens
        self.total_search_queries += record.search_queries
        self.total_cost += record.total_cost


class UsageTracker:
    """
    Tracks API usage and costs across sessions.

    Features:
    - Records actual token usage per API call
    - Calculates real costs based on Gemini pricing
    - Persists history to update cost estimates
    - Provides session summaries
    """

    def __init__(self, storage_path: Path | None = None):
        """Initialize the usage tracker."""
        self.storage_path = storage_path or USAGE_FILE
        self.session = SessionUsage()
        self.history: list[dict] = []
        self._load_history()

    def _load_history(self):
        """Load usage history from file."""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, encoding="utf-8") as f:
                    self.history = json.load(f)
                logger.debug(f"Loaded {len(self.history)} usage records")
        except Exception as e:
            logger.warning(f"Could not load usage history: {e}")
            self.history = []

    def record_usage(
        self,
        mode: str,
        company: str,
        input_tokens: int,
        output_tokens: int,
        search_queries: int = 0,
        duration_seconds: float = 0.0,
        pipeline_cost: float | None = None,
        deep_research_cost: float = 0.0,
    ) -> None:
        """
        Record API usage for the current session.

        Args:
            mode: Research mode used
            company: Company name researched
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            search_queries: Number of search queries made
            duration_seconds: Duration of the operation
            pipeline_cost: Pre-calculated accurate cost from AI client
            deep_research_cost: Flat per-task Deep Research cost
        """
        record = UsageRecord.create(
            mode=mode,
            company=company,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            search_queries=search_queries,
            duration_seconds=duration_seconds,
            pipeline_cost=pipeline_cost,
            deep_research_cost=deep_research_cost,
        )

        self.session.add(record)
        logger.info(
            f"Recorded usage: {input_tokens:,} in / {output_tokens:,} out = ${record.total_cost:.4f}"
        )

    def save(self):
        """Save session usage to history file."""
        try:
            # Add session records to history
            for record in self.session.records:
                self.history.append(asdict(record))

            # Ensure directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            # Save to file
            with open(self.storage_path, 'w', encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)

            logger.info(f"Saved {len(self.session.records)} usage records")
        except Exception as e:
            logger.error(f"Could not save usage history: {e}")

    def get_session_summary(self) -> str:
        """Get a summary of the current session's usage."""
        if not self.session.records:
            return "No usage recorded this session"

        lines = [
            "Session Usage Summary",
            "=" * 40,
            f"API Calls: {len(self.session.records)}",
            f"Input Tokens: {self.session.total_input_tokens:,}",
            f"Output Tokens: {self.session.total_output_tokens:,}",
            f"Search Queries: {self.session.total_search_queries}",
            "",
            f"Total Cost: ${self.session.total_cost:.4f}",
        ]

        return "\n".join(lines)

    def get_session_cost(self) -> float:
        """Get the total cost for the current session."""
        return self.session.total_cost

    def get_average_by_mode(self, mode: str) -> dict | None:
        """
        Get average usage statistics for a specific mode.

        Args:
            mode: Research mode to get averages for

        Returns:
            Dict with average input_tokens, output_tokens, search_queries, cost, or None
        """
        mode_records = [r for r in self.history if r.get("mode") == mode]

        if not mode_records:
            return None

        count = len(mode_records)
        avg_input = sum(r["input_tokens"] for r in mode_records) / count
        avg_output = sum(r["output_tokens"] for r in mode_records) / count
        avg_searches = sum(r.get("search_queries", 0) for r in mode_records) / count
        avg_cost = sum(r["total_cost"] for r in mode_records) / count
        avg_duration = sum(r.get("duration_seconds", 0) for r in mode_records) / count

        return {
            "mode": mode,
            "sample_size": count,
            "avg_input_tokens": avg_input,
            "avg_output_tokens": avg_output,
            "avg_search_queries": avg_searches,
            "avg_cost": avg_cost,
            "avg_duration_seconds": avg_duration,
        }

    def get_updated_estimates(self) -> dict[str, dict]:
        """
        Get updated cost estimates based on historical usage.

        Returns:
            Dict mapping mode -> estimated values
        """
        modes = ["structured", "deep-research", "complete", "hybrid", "ai-strategy"]
        estimates = {}

        for mode in modes:
            avg = self.get_average_by_mode(mode)
            if avg and avg["sample_size"] >= 3:  # Need at least 3 samples
                estimates[mode] = {
                    "input_tokens": avg["avg_input_tokens"],
                    "output_tokens": avg["avg_output_tokens"],
                    "estimated_cost": avg["avg_cost"],
                    "avg_duration_seconds": avg["avg_duration_seconds"],
                    "sample_size": avg["sample_size"],
                }

        return estimates

    def display_usage_history(self) -> str:
        """
        Generate a formatted display of historical usage statistics.

        Returns:
            Formatted string with usage history summary
        """
        if not self.history:
            return "No usage history recorded yet."

        lines = [
            "=" * 60,
            "USAGE HISTORY SUMMARY",
            "=" * 60,
            "",
            f"Total Records: {len(self.history)}",
            "",
        ]

        # Calculate totals
        total_input = sum(r.get("input_tokens", 0) for r in self.history)
        total_output = sum(r.get("output_tokens", 0) for r in self.history)
        total_searches = sum(r.get("search_queries", 0) for r in self.history)
        total_cost = sum(r.get("total_cost", 0) for r in self.history)
        total_duration = sum(r.get("duration_seconds", 0) for r in self.history)
        total_dr_cost = sum(r.get("deep_research_cost", 0) for r in self.history)

        lines.extend([
            "All-Time Totals:",
            f"  Input Tokens:   {total_input:,}",
            f"  Output Tokens:  {total_output:,}",
            f"  Search Queries: {total_searches:,}",
            f"  Total Cost:     ${total_cost:.2f}",
        ])
        if total_dr_cost > 0:
            lines.extend([
                f"    Token cost:   ${total_cost - total_dr_cost:.2f}",
                f"    DR cost:      ${total_dr_cost:.2f}",
            ])
        lines.extend([
            f"  Total Time:     {total_duration / 60:.1f} minutes",
            "",
        ])

        # Show search cost projection (after Jan 5, 2026)
        if total_searches > 0:
            from primr.config.models import SEARCH_COST_PER_QUERY
            projected_search_cost = total_searches * SEARCH_COST_PER_QUERY
            lines.extend([
                f"  Search Cost (after Jan 5): +${projected_search_cost:.2f}",
                "",
            ])

        # Per-mode breakdown with current estimates
        modes = ["structured", "deep-research", "complete", "hybrid", "ai-strategy"]
        lines.append("By Mode (actual averages):")
        lines.append("-" * 40)

        for mode in modes:
            avg = self.get_average_by_mode(mode)
            if avg:
                status = "✓ learning" if avg['sample_size'] >= 3 else f"need {3 - avg['sample_size']} more"
                lines.extend([
                    f"  {mode}:",
                    f"    Runs: {avg['sample_size']} ({status})",
                    f"    Avg Cost:     ${avg['avg_cost']:.2f}",
                    f"    Avg Searches: {avg['avg_search_queries']}",
                    f"    Avg Time:     {avg['avg_duration_seconds'] / 60:.1f} min",
                    "",
                ])

        # Recent runs (last 5)
        lines.append("-" * 40)
        lines.append("Recent Runs:")
        lines.append("")

        recent = sorted(self.history, key=lambda r: r.get("timestamp", ""), reverse=True)[:5]
        for r in recent:
            timestamp = r.get("timestamp", "")[:10]  # Just date
            company = r.get("company", "Unknown")[:20]
            mode = r.get("mode", "?")
            cost = r.get("total_cost", 0)
            searches = r.get("search_queries", 0)
            duration = r.get("duration_seconds", 0) / 60
            lines.append(f"  {timestamp} | {company:<20} | {mode:<12} | ${cost:.2f} | {searches} srch | {duration:.0f}m")

        lines.extend(["", "=" * 60])

        return "\n".join(lines)


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

import threading

_tracker: UsageTracker | None = None
_tracker_lock = threading.Lock()


def get_usage_tracker() -> UsageTracker:
    """
    Get the global usage tracker instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety
    while minimizing lock contention.
    """
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            # Double-check after acquiring lock
            if _tracker is None:
                _tracker = UsageTracker()
    return _tracker


def reset_usage_tracker() -> None:
    """Reset the global tracker (useful for testing)."""
    global _tracker
    with _tracker_lock:
        _tracker = None
