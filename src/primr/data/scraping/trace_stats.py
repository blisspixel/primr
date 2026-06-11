"""Aggregate scrape-trace analytics for `primr doctor --scraper-stats`.

Reads the per-run JSONL trace files written by :class:`~primr.data.scraping.trace.TraceLogger`
(`logs/scrape_traces/*.jsonl`) and aggregates per-tier success rate, latency
p95, and content-quality signals across recent runs. Pure read-side analytics:
no scraping state is touched, and a missing/empty trace directory simply
yields ``None``.

This is the observability half of the sticky-tier / circuit-breaker design:
the engine already *learns* per-domain (``logs/domain_profiles.json``); this
module makes the fleet-wide behavior visible to the operator so tier policy
and breaker thresholds can be tuned from data instead of anecdotes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from primr.utils.logging_config import get_logger

from .trace import read_trace_file

logger = get_logger("data.scraping.trace_stats")

DEFAULT_TRACE_DIR = Path("logs") / "scrape_traces"
# Pages whose extracted text is below this are counted as thin content.
THIN_CONTENT_CHARS = 500


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (pct in [0, 100]) of a non-empty list."""
    if not values:
        raise ValueError("percentile() requires at least one value")
    ordered = sorted(values)
    if pct <= 0:
        return ordered[0]
    if pct >= 100:
        return ordered[-1]
    rank = math.ceil(pct / 100.0 * len(ordered))
    return ordered[rank - 1]


@dataclass
class TierAggregate:
    """Per-tier outcome aggregate across the analyzed runs."""

    tier: str
    attempts: int = 0
    successes: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    @property
    def p95_latency_ms(self) -> float | None:
        return percentile(self.latencies_ms, 95) if self.latencies_ms else None

    @property
    def avg_latency_ms(self) -> float | None:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else None


@dataclass
class ScraperStatsSummary:
    """Aggregated scraper analytics across recent trace files."""

    runs_analyzed: int
    urls_total: int
    urls_succeeded: int
    tiers: list[TierAggregate]
    text_lengths: list[int]
    valid_pages: int
    validated_pages: int

    @property
    def overall_success_rate(self) -> float:
        return self.urls_succeeded / self.urls_total if self.urls_total else 0.0

    @property
    def avg_text_length(self) -> float | None:
        return sum(self.text_lengths) / len(self.text_lengths) if self.text_lengths else None

    @property
    def thin_pages(self) -> int:
        return sum(1 for length in self.text_lengths if length < THIN_CONTENT_CHARS)

    @property
    def content_valid_rate(self) -> float | None:
        if not self.validated_pages:
            return None
        return self.valid_pages / self.validated_pages


def aggregate_scraper_stats(
    trace_dir: Path | None = None,
    max_runs: int = 20,
) -> ScraperStatsSummary | None:
    """Aggregate per-tier stats from the most recent ``max_runs`` trace files.

    Returns ``None`` when no readable trace files exist. Unreadable or
    partially-written files are skipped with a debug log — analytics must
    never break doctor.
    """
    directory = trace_dir if trace_dir is not None else DEFAULT_TRACE_DIR
    if not directory.is_dir():
        return None

    trace_files = sorted(directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[
        :max_runs
    ]
    if not trace_files:
        return None

    tiers: dict[str, TierAggregate] = {}
    runs_analyzed = 0
    urls_total = 0
    urls_succeeded = 0
    text_lengths: list[int] = []
    valid_pages = 0
    validated_pages = 0

    for path in trace_files:
        try:
            _header, entries = read_trace_file(path)
        except Exception as e:
            logger.debug("Skipping unreadable trace file %s: %s", path, e)
            continue
        runs_analyzed += 1

        for entry in entries:
            urls_total += 1
            if entry.success_tier:
                urls_succeeded += 1

            for attempt in entry.tier_attempts or []:
                tier_name = str(attempt.get("tier") or "unknown")
                bucket = tiers.setdefault(tier_name, TierAggregate(tier=tier_name))
                bucket.attempts += 1
                if attempt.get("success"):
                    bucket.successes += 1
                elapsed = attempt.get("elapsed_ms")
                if isinstance(elapsed, int | float) and elapsed >= 0:
                    bucket.latencies_ms.append(float(elapsed))

            if entry.success_tier and entry.extracted_text_length is not None:
                text_lengths.append(int(entry.extracted_text_length))

            validation = entry.validation_result
            if isinstance(validation, dict) and "valid" in validation:
                validated_pages += 1
                if validation.get("valid"):
                    valid_pages += 1

    if runs_analyzed == 0:
        return None

    ordered_tiers = sorted(tiers.values(), key=lambda t: -t.attempts)
    return ScraperStatsSummary(
        runs_analyzed=runs_analyzed,
        urls_total=urls_total,
        urls_succeeded=urls_succeeded,
        tiers=ordered_tiers,
        text_lengths=text_lengths,
        valid_pages=valid_pages,
        validated_pages=validated_pages,
    )


def format_scraper_stats(summary: ScraperStatsSummary) -> str:
    """Render the aggregate as the text block doctor prints."""
    lines = [
        f"Analyzed {summary.runs_analyzed} recent run(s), {summary.urls_total} page(s)",
        f"Overall page success rate: {summary.overall_success_rate:.0%}",
        "",
        f"{'Tier':<24} {'Attempts':>8} {'Success':>8} {'p95 ms':>9} {'avg ms':>9}",
        "-" * 62,
    ]
    for tier in summary.tiers:
        p95 = f"{tier.p95_latency_ms:.0f}" if tier.p95_latency_ms is not None else "-"
        avg = f"{tier.avg_latency_ms:.0f}" if tier.avg_latency_ms is not None else "-"
        lines.append(
            f"{tier.tier:<24} {tier.attempts:>8} {tier.success_rate:>7.0%} {p95:>9} {avg:>9}"
        )

    lines.append("")
    if summary.avg_text_length is not None:
        lines.append(
            f"Content quality: avg {summary.avg_text_length:,.0f} chars/page, "
            f"{summary.thin_pages} thin page(s) (<{THIN_CONTENT_CHARS} chars)"
        )
    if summary.content_valid_rate is not None:
        lines.append(
            f"Content validation pass rate: {summary.content_valid_rate:.0%} "
            f"({summary.valid_pages}/{summary.validated_pages} validated pages)"
        )
    return "\n".join(lines)
