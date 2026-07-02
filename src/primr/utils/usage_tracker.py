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

import contextlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from primr.utils.atomic_io import atomic_replace
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
    cached_input_tokens: int = 0  # Subset of input_tokens served from prompt cache

    @property
    def cache_hit_rate(self) -> float:
        """Fraction of input tokens served from the provider prompt cache (0.0-1.0)."""
        if self.input_tokens <= 0:
            return 0.0
        return min(1.0, self.cached_input_tokens / self.input_tokens)

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
        cached_input_tokens: int = 0,
        search_cost_per_query: float | None = None,
    ) -> "UsageRecord":
        """Create a usage record with costs.

        Args:
            pipeline_cost: Pre-calculated accurate cost from AI client
                (per-model, tier-aware). When provided, skips token-based
                pricing. When None, falls back to conservative pricing
                from tokens (backward compat).
            deep_research_cost: Flat per-task Deep Research cost ($2.50/task).
            cached_input_tokens: Subset of input_tokens served from the
                provider prompt cache. Cache hit rate is load-bearing on the
                sub-$1 default recipe, so it is persisted per run.
            search_cost_per_query: Billing rate for the run's search provider
                (0.0 for free DDG). None falls back to the legacy Gemini
                grounding rate for callers that predate provider-aware
                pricing.
        """
        from primr.config.models import SEARCH_COST_PER_QUERY

        if search_cost_per_query is None:
            search_cost_per_query = SEARCH_COST_PER_QUERY
        search_cost = search_queries * search_cost_per_query
        cached_input_tokens = max(0, min(cached_input_tokens, input_tokens))

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
                cached_input_tokens=cached_input_tokens,
            )

        # Fallback: estimate cost from tokens using active Pro model pricing
        from primr.config.models import PrimrModels

        active_pro = PrimrModels.get_active_pro_model()
        cost = PrimrModels.calculate_cost_breakdown(
            active_pro.name,
            input_tokens,
            output_tokens,
            cached_input_tokens=cached_input_tokens,
            force_high_tier=active_pro.has_tiered_pricing,
        )
        input_cost = cost.input_cost
        output_cost = cost.output_cost

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
            cached_input_tokens=cached_input_tokens,
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
        # Count of session records already flushed into history by save().
        # The tracker is a process-lifetime singleton, so without this a
        # multi-run process (MCP server, batch eval) re-appends every prior
        # run's records on each save - quadratic duplication in the history.
        self._flushed_session_records = 0
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
        cached_input_tokens: int = 0,
        search_cost_per_query: float | None = None,
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
            cached_input_tokens: Subset of input_tokens served from prompt cache
            search_cost_per_query: Billing rate for the run's search provider
                (0.0 for free DDG; None = legacy Gemini grounding rate)
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
            cached_input_tokens=cached_input_tokens,
            search_cost_per_query=search_cost_per_query,
        )

        self.session.add(record)
        logger.info(
            f"Recorded usage: {input_tokens:,} in / {output_tokens:,} out = ${record.total_cost:.4f}"
        )

    def save(self):
        """Save session usage to history file.

        Writes atomically: serialize to a sibling temp file, then
        ``os.replace`` it onto the real path. If the process is killed
        mid-write the existing history is untouched — without this, a
        crash between ``open(..., "w")`` and the final ``json.dump`` flush
        leaves a truncated or empty cost-history file, which downstream
        budgets / show-usage cannot recover from.
        """
        import os
        import tempfile

        try:
            # Only session records not yet flushed by an earlier save join the
            # history; the in-memory state is committed only after the file
            # swap succeeds, so a failed write can be retried without
            # duplicating records.
            unflushed = self.session.records[self._flushed_session_records :]
            new_history = self.history + [asdict(record) for record in unflushed]

            # Ensure directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            # Serialize to a temp file in the same directory so os.replace
            # is atomic (cross-filesystem renames are not).
            fd, tmp_name = tempfile.mkstemp(
                prefix=self.storage_path.name + ".",
                suffix=".tmp",
                dir=str(self.storage_path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(new_history, f, indent=2)
                atomic_replace(tmp_name, self.storage_path)
            except Exception:
                # Clean up the partial temp file if the swap never happened.
                with contextlib.suppress(OSError):
                    os.unlink(tmp_name)
                raise

            self.history = new_history
            # Increment by what was actually written, not len(session.records):
            # a record added by another thread between the slice above and this
            # commit must stay unflushed for the next save.
            self._flushed_session_records += len(unflushed)
            logger.info(f"Saved {len(unflushed)} usage records")
        except PermissionError as e:
            logger.error(
                "Could not save usage history (permission denied — file may be locked "
                "by OneDrive or another process): %s",
                e,
            )
        except OSError as e:
            logger.error("Could not save usage history (disk error — check available space): %s", e)
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
        # Use .get with defaults throughout: usage_history.json is persisted
        # across versions and may contain older-schema or hand-edited records
        # missing some fields; a direct r["..."] would KeyError and crash
        # `primr show-usage` / estimate updates.
        avg_input = sum(r.get("input_tokens", 0) for r in mode_records) / count
        avg_output = sum(r.get("output_tokens", 0) for r in mode_records) / count
        avg_searches = sum(r.get("search_queries", 0) for r in mode_records) / count
        avg_cost = sum(r.get("total_cost", 0) for r in mode_records) / count
        avg_duration = sum(r.get("duration_seconds", 0) for r in mode_records) / count
        avg_cached_input = sum(r.get("cached_input_tokens", 0) for r in mode_records) / count

        return {
            "mode": mode,
            "sample_size": count,
            "avg_input_tokens": avg_input,
            "avg_output_tokens": avg_output,
            "avg_cached_input_tokens": avg_cached_input,
            "avg_search_queries": avg_searches,
            "avg_cost": avg_cost,
            "avg_duration_seconds": avg_duration,
        }

    def get_cost_variability(self, mode: str, recent_n: int = 5) -> dict | None:
        """Cost-variability and efficiency-regression signals for one mode.

        Report-only analytics (roadmap #5): compares the most recent
        ``recent_n`` runs against the PRIOR history so a continuous-reasoning
        or cache-efficiency regression surfaces in ``show-usage`` instead of
        silently eroding the sub-$1 default. Never a gate. Returns None when
        fewer than ``recent_n + 1`` runs exist (the comparison needs history
        that predates the recent window).
        """
        if recent_n <= 0:
            raise ValueError(f"recent_n must be positive, got {recent_n}")
        # Sort by timestamp: multi-writer histories (CLI + MCP) are not
        # guaranteed chronological on disk, and "recent" must mean recent.
        mode_records = sorted(
            (r for r in self.history if r.get("mode") == mode),
            key=lambda r: r.get("timestamp", ""),
        )
        if len(mode_records) <= recent_n:
            return None

        def _cache_hit_rate(records: list[dict]) -> float:
            total_in = sum(r.get("input_tokens", 0) for r in records)
            cached = sum(r.get("cached_input_tokens", 0) for r in records)
            return cached / total_in if total_in > 0 else 0.0

        # Baseline = PRIOR history only. Including the recent window in the
        # baseline drags the mean toward the regression being measured: with
        # one prior run, even a 10x cost jump could not cross a 25% threshold.
        prior = mode_records[:-recent_n]
        recent = mode_records[-recent_n:]
        prior_costs = [r.get("total_cost", 0) for r in prior]
        baseline_avg = sum(prior_costs) / len(prior_costs)
        recent_costs = [r.get("total_cost", 0) for r in recent]
        recent_avg = sum(recent_costs) / len(recent_costs)

        all_costs = prior_costs + recent_costs
        lifetime_avg = sum(all_costs) / len(all_costs)
        variance = sum((c - lifetime_avg) ** 2 for c in all_costs) / len(all_costs)
        cost_stddev = variance**0.5

        cost_delta_pct = (
            (recent_avg - baseline_avg) / baseline_avg * 100 if baseline_avg > 0 else 0.0
        )
        baseline_cache = _cache_hit_rate(prior)
        recent_cache = _cache_hit_rate(recent)

        # Signal thresholds are deliberately coarse: this flags "look at it",
        # never blocks anything. Cost up >25% or cache rate down >10 points.
        regression = cost_delta_pct > 25.0 or (baseline_cache - recent_cache) > 0.10

        return {
            "mode": mode,
            "sample_size": len(mode_records),
            "recent_n": recent_n,
            "baseline_avg_cost": baseline_avg,
            "recent_avg_cost": recent_avg,
            "cost_stddev": cost_stddev,
            "cost_delta_pct": cost_delta_pct,
            "baseline_cache_hit_rate": baseline_cache,
            "recent_cache_hit_rate": recent_cache,
            "regression_signal": regression,
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
                    "cached_input_tokens": avg["avg_cached_input_tokens"],
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
        total_cached = sum(r.get("cached_input_tokens", 0) for r in self.history)

        lines.extend(
            [
                "All-Time Totals:",
                f"  Input Tokens:   {total_input:,}",
                f"  Output Tokens:  {total_output:,}",
                f"  Search Queries: {total_searches:,}",
                f"  Total Cost:     ${total_cost:.2f}",
            ]
        )
        if total_cached > 0 and total_input > 0:
            lines.append(
                f"  Cached Input:   {total_cached:,} "
                f"({total_cached / total_input:.0%} cache hit rate)"
            )
        if total_dr_cost > 0:
            lines.extend(
                [
                    f"    Token cost:   ${total_cost - total_dr_cost:.2f}",
                    f"    DR cost:      ${total_dr_cost:.2f}",
                ]
            )
        lines.extend(
            [
                f"  Total Time:     {total_duration / 60:.1f} minutes",
                "",
            ]
        )

        # Recorded search cost, summed from what each run actually persisted.
        # Records price searches by the run's provider (DDG free, Google CSE
        # paid), so a flat projection over query counts would resurrect the
        # phantom cost the provider-aware pricing removed.
        if total_searches > 0:
            recorded_search_cost = sum(r.get("search_cost", 0) for r in self.history)
            lines.extend(
                [
                    f"  Search Cost:    ${recorded_search_cost:.2f} ({total_searches} queries)",
                    "",
                ]
            )

        # Per-mode breakdown: observed modes first (so fast-mode runs and any
        # future mode show up), known-but-unobserved modes are simply omitted.
        observed_modes = sorted({r.get("mode", "?") for r in self.history})
        lines.append("By Mode (totals and actual averages):")
        lines.append("-" * 40)

        for mode in observed_modes:
            avg = self.get_average_by_mode(mode)
            if avg:
                status = (
                    "learning" if avg["sample_size"] >= 3 else f"need {3 - avg['sample_size']} more"
                )
                mode_total = sum(
                    r.get("total_cost", 0) for r in self.history if r.get("mode") == mode
                )
                lines.extend(
                    [
                        f"  {mode}:",
                        f"    Runs: {avg['sample_size']} ({status})",
                        f"    Total Cost:   ${mode_total:.2f}",
                        f"    Avg Cost:     ${avg['avg_cost']:.2f}",
                        f"    Avg Searches: {avg['avg_search_queries']}",
                        f"    Avg Time:     {avg['avg_duration_seconds'] / 60:.1f} min",
                        "",
                    ]
                )

        # Cost variability + regression signal per observed mode (report-only;
        # a rising fast-mode cost or falling cache hit rate silently erodes
        # the sub-$1 default unless it is surfaced here).
        variability_lines: list[str] = []
        for mode in observed_modes:
            stats = self.get_cost_variability(mode)
            if not stats:
                continue
            variability_lines.extend(
                [
                    f"  {mode}:",
                    (
                        f"    Cost: prior avg ${stats['baseline_avg_cost']:.2f} "
                        f"(stddev ${stats['cost_stddev']:.2f}), "
                        f"recent-{stats['recent_n']} avg ${stats['recent_avg_cost']:.2f} "
                        f"({stats['cost_delta_pct']:+.0f}%)"
                    ),
                    (
                        f"    Cache hit rate: prior "
                        f"{stats['baseline_cache_hit_rate']:.0%}, "
                        f"recent-{stats['recent_n']} {stats['recent_cache_hit_rate']:.0%}"
                    ),
                ]
            )
            if stats["regression_signal"]:
                variability_lines.append(
                    "    SIGNAL: recent runs cost more or cache less than history - "
                    "check provider pricing, prompt-cache recipe, and continuous reasoning"
                )
            variability_lines.append("")
        if variability_lines:
            lines.append("-" * 40)
            lines.append("Cost Variability (recent vs lifetime):")
            lines.extend(variability_lines)

        # Per-company history (top 10 by total spend)
        company_totals: dict[str, dict] = {}
        for r in self.history:
            company = r.get("company", "Unknown")
            bucket = company_totals.setdefault(company, {"runs": 0, "cost": 0.0, "last_run": ""})
            bucket["runs"] += 1
            bucket["cost"] += r.get("total_cost", 0)
            bucket["last_run"] = max(bucket["last_run"], r.get("timestamp", ""))

        lines.append("-" * 40)
        lines.append("By Company (top 10 by spend):")
        lines.append("")
        top_companies = sorted(company_totals.items(), key=lambda kv: kv[1]["cost"], reverse=True)[
            :10
        ]
        for company, stats in top_companies:
            last_run = stats["last_run"][:10]
            lines.append(
                f"  {company[:24]:<24} | {stats['runs']} run(s) | "
                f"${stats['cost']:.2f} | last {last_run}"
            )
        lines.append("")

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
            line = (
                f"  {timestamp} | {company:<20} | {mode:<12} | ${cost:.2f} "
                f"| {searches} srch | {duration:.0f}m"
            )
            cached = r.get("cached_input_tokens", 0)
            run_input = r.get("input_tokens", 0)
            if cached > 0 and run_input > 0:
                line += f" | {cached / run_input:.0%} cached"
            lines.append(line)

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
