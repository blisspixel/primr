"""Offline calibration runner: audit label traceability on shipped reports.

The runner turns the label-calibration harness (``qa.label_calibration``)
into a one-command audit over reports already on disk — no research run
required. Per report it samples labeled claims (free, deterministic),
fetches cited sources, and judges traceability, persisting the result as a
``<report>.calibration.json`` sidecar that the model_eval scorecard reads.

Cost profile: claim extraction is free; the paid part is bounded one-word
judge calls (``max_per_label`` x 2 labels x ``max_sources_per_claim``), a
fraction of a cent per report on the fast tier. ``dry_run=True`` stops
after extraction and reports exactly how many judge calls a live pass
would make.

All effects (fetching, judging, sidecar writes) are injectable or
switchable so tests stay offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from primr.qa.label_calibration import (
    DEFAULT_MAX_PER_LABEL,
    TRACEABLE_LABELS,
    calibrate_claims,
    extract_labeled_claims,
)
from primr.utils.logging_config import get_logger

logger = get_logger("qa.calibration_runner")

# Sidecar filename suffix appended to the full report filename, so the
# pairing survives reports that share a stem across extensions.
SIDECAR_SUFFIX = ".calibration.json"

# Default per-judge-call cost assumption for the dry-run preview (fast-tier,
# one-word answer, ~1.2k tokens in). Deliberately conservative.
_EST_COST_PER_JUDGE_CALL_USD = 0.0005
_MAX_SOURCES_PER_CLAIM = 2


@dataclass(frozen=True)
class ReportCalibrationOutcome:
    """Result of calibrating (or dry-running) one report."""

    report_path: Path
    claims_sampled: int
    judgeable_claims: int
    estimated_judge_calls: int
    sidecar_path: Path | None = None
    per_label: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def sidecar_path_for(report_path: Path) -> Path:
    """The calibration sidecar path for a report file."""
    return report_path.with_name(report_path.name + SIDECAR_SUFFIX)


def resolve_reports(
    target: str | None,
    *,
    recent: int | None = None,
    output_dir: Path | None = None,
) -> list[Path]:
    """Resolve the report files a calibration run covers.

    ``target`` may be an explicit file path or a company name (resolved to
    the company's most recent markdown Strategic Overview). ``recent``
    selects the N most recent Strategic Overview reports instead, one per
    company (latest wins). Markdown is preferred over txt because the
    harness parses markdown structure.
    """
    out_dir = output_dir if output_dir is not None else Path("output")

    if target:
        candidate = Path(target)
        if candidate.is_file():
            return [candidate]
        if any(sep in target for sep in ("/", "\\")) or candidate.suffix:
            raise FileNotFoundError(f"Report file not found: {target}")
        matches = [
            p
            for p in out_dir.glob(f"*{target}*Strategic_Overview*.md")
            if not p.name.endswith(SIDECAR_SUFFIX)
        ]
        if not matches:
            raise FileNotFoundError(
                f"No Strategic Overview markdown found for company '{target}' in {out_dir}"
            )
        return [max(matches, key=lambda p: p.stat().st_mtime)]

    count = recent if recent is not None else 1
    candidates = sorted(
        (p for p in out_dir.glob("*Strategic_Overview*.md") if not p.name.endswith(SIDECAR_SUFFIX)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    latest_per_company: dict[str, Path] = {}
    for path in candidates:
        company = path.name.split("_Strategic_Overview")[0]
        if company not in latest_per_company:
            latest_per_company[company] = path
        if len(latest_per_company) >= count:
            break
    if not latest_per_company:
        raise FileNotFoundError(f"No Strategic Overview markdown reports found in {out_dir}")
    return list(latest_per_company.values())


def _estimate_judge_calls(claims: list[Any]) -> int:
    return sum(
        min(_MAX_SOURCES_PER_CLAIM, len(c.source_urls))
        for c in claims
        if c.label in TRACEABLE_LABELS and c.source_urls
    )


def estimate_cost_usd(judge_calls: int) -> float:
    """Conservative dry-run cost preview for a number of judge calls."""
    return round(judge_calls * _EST_COST_PER_JUDGE_CALL_USD, 4)


def run_calibration(
    report_paths: list[Path],
    *,
    max_per_label: int = DEFAULT_MAX_PER_LABEL,
    dry_run: bool = False,
    write_sidecar: bool = True,
    fetch_fn: Callable[[str], str] | None = None,
    judge_fn: Callable[[str, str], bool] | None = None,
) -> list[ReportCalibrationOutcome]:
    """Calibrate each report, persisting a sidecar JSON per report.

    With ``dry_run`` the run stops after the free extraction step and the
    outcomes carry the claim counts and the judge-call estimate only. A
    report that cannot be read or parsed records an ``error`` outcome
    instead of failing the batch.
    """
    outcomes: list[ReportCalibrationOutcome] = []
    for path in report_paths:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            outcomes.append(
                ReportCalibrationOutcome(
                    report_path=path,
                    claims_sampled=0,
                    judgeable_claims=0,
                    estimated_judge_calls=0,
                    error=f"unreadable: {e}",
                )
            )
            continue

        claims = extract_labeled_claims(content, max_per_label=max_per_label)
        judgeable = [c for c in claims if c.label in TRACEABLE_LABELS and c.source_urls]
        judge_calls = _estimate_judge_calls(claims)

        if dry_run:
            outcomes.append(
                ReportCalibrationOutcome(
                    report_path=path,
                    claims_sampled=len(claims),
                    judgeable_claims=len(judgeable),
                    estimated_judge_calls=judge_calls,
                )
            )
            continue

        report = calibrate_claims(claims, fetch_fn=fetch_fn, judge_fn=judge_fn)
        payload = report.to_dict()
        payload["report_file"] = path.name
        payload["max_per_label"] = max_per_label

        sidecar: Path | None = None
        if write_sidecar:
            sidecar = sidecar_path_for(path)
            sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("Calibration sidecar written: %s", sidecar)

        outcomes.append(
            ReportCalibrationOutcome(
                report_path=path,
                claims_sampled=len(claims),
                judgeable_claims=len(judgeable),
                estimated_judge_calls=judge_calls,
                sidecar_path=sidecar,
                per_label=payload["per_label"],
            )
        )
    return outcomes


def aggregate_per_label(outcomes: list[ReportCalibrationOutcome]) -> dict[str, dict[str, int]]:
    """Sum per-label verdict counts across calibrated outcomes."""
    totals: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        for label, stats in outcome.per_label.items():
            bucket = totals.setdefault(
                label,
                {
                    "sampled": 0,
                    "traceable": 0,
                    "untraceable": 0,
                    "no_source": 0,
                    "unfetchable": 0,
                    "exempt": 0,
                },
            )
            for key in bucket:
                bucket[key] += int(stats.get(key, 0))
    return totals


def aggregate_precision(totals: dict[str, dict[str, int]], label: str) -> float | None:
    """Pooled traceability precision for a label across reports."""
    stats = totals.get(label)
    if not stats:
        return None
    decidable = stats["traceable"] + stats["untraceable"] + stats["no_source"]
    if not decidable:
        return None
    return stats["traceable"] / decidable
