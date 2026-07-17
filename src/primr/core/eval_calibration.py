"""Calibration sidecar helpers for offline model evaluation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def load_calibration_counts(report_path: Path) -> dict[str, int] | None:
    """Read calibration counts from a report sidecar, if present."""
    from primr.qa.calibration_sidecars import (
        calibration_sidecar_matches_report,
        sidecar_path_for,
    )

    sidecar = sidecar_path_for(report_path)
    if not sidecar.exists():
        return None
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(payload, dict):
        return None
    if not calibration_sidecar_matches_report(report_path, payload):
        return None
    return calibration_counts_from_payload(payload)


def calibration_counts_from_payload(payload: dict[str, Any]) -> dict[str, int]:
    """Read calibration counts from an already-loaded sidecar payload."""
    per_label = payload.get("per_label", {})
    if not isinstance(per_label, dict):
        per_label = {}

    counts: dict[str, int] = {}
    for label in ("Confirmed", "Reported"):
        stats = per_label.get(label, {})
        if not isinstance(stats, dict):
            stats = {}
        traceable = _safe_int(stats.get("traceable", 0))
        decidable = (
            traceable
            + _safe_int(stats.get("untraceable", 0))
            + _safe_int(stats.get("no_source", 0))
        )
        counts[f"{label.lower()}_traceable"] = traceable
        counts[f"{label.lower()}_decidable"] = decidable
    for label in ("Estimated", "Hypothesis"):
        stats = per_label.get(label, {})
        if not isinstance(stats, dict):
            stats = {}
        counts[f"{label.lower()}_source_copied"] = _safe_int(stats.get("source_copied", 0))
    counts["inference_source_copied"] = (
        counts["estimated_source_copied"] + counts["hypothesis_source_copied"]
    )

    rubric = payload.get("validation_rubric", {})
    if not isinstance(rubric, dict):
        rubric = {}

    def _count(section: str, key: str) -> int:
        values = rubric.get(section, {})
        if not isinstance(values, dict):
            return 0
        return _safe_int(values.get(key, 0))

    counts["evidence_source_reviews"] = _safe_int(rubric.get("source_reviews", 0))
    counts["evidence_supported_reviews"] = _count("support", "supported")
    counts["evidence_contradicted_reviews"] = _count("contradiction", "direct") + _count(
        "contradiction", "partial"
    )
    counts["evidence_independent_reviews"] = _count("source_independence", "independent")
    counts["evidence_high_authority_reviews"] = _count("source_authority", "high")
    counts["evidence_strong_reasoning_reviews"] = _count("reasoning_strength", "strong")
    counts["evidence_honest_uncertainty_reviews"] = _count("uncertainty_honesty", "honest")
    counts["evidence_high_relevance_reviews"] = _count("business_relevance", "high")

    agreement = payload.get("judge_agreement", {})
    if not isinstance(agreement, dict):
        agreement = {}
    counts["judge_agreement_compared"] = _safe_int(agreement.get("compared", 0))
    counts["judge_agreement_agreed"] = _safe_int(agreement.get("agreed", 0))
    return counts


def calibration_gate_threshold() -> float | None:
    """The Confirmed-claim traceability hard-gate threshold, if armed."""
    raw = os.environ.get("PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring malformed PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY=%r", raw)
        return None
    if not 0.0 < value <= 1.0:
        logger.warning(
            "Ignoring out-of-range PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY=%r (need 0-1]", raw
        )
        return None
    return value


def calibration_gate_description() -> str:
    gate = calibration_gate_threshold()
    if gate is None:
        return (
            "not armed (PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY unset; "
            "report-only until a baseline exists)"
        )
    return f"Confirmed >= {gate:.0%} (PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY)"


def calibration_status(
    calibrated_report_count: int,
    confirmed_traceability: float | None,
    gate: float | None,
) -> str:
    if calibrated_report_count == 0:
        return "no data"
    if confirmed_traceability is None:
        return "no decidable Confirmed claims"
    if gate is not None and confirmed_traceability < gate:
        return "BELOW GATE"
    return "ok"


def percent_or_dash(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "-"


def round_or_blank(value: float | None) -> float | str:
    return round(value, 3) if value is not None else ""


def calibration_csv_columns() -> list[str]:
    """CSV columns owned by calibration sidecar metrics."""
    return [
        "confirmed_traceability",
        "reported_traceability",
        "evidence_source_reviews",
        "evidence_support_rate",
        "evidence_contradiction_rate",
        "evidence_independence_rate",
        "evidence_high_authority_rate",
        "evidence_strong_reasoning_rate",
        "evidence_honest_uncertainty_rate",
        "evidence_high_relevance_rate",
        "judge_agreement_compared",
        "judge_agreement_rate",
        "inference_source_copied",
    ]


def calibration_csv_values(metric: Any) -> list[object]:
    """CSV row values owned by calibration sidecar metrics."""
    judge_agreement_rate = (
        metric.judge_agreement_agreed / metric.judge_agreement_compared
        if metric.judge_agreement_compared
        else None
    )
    return [
        round_or_blank(metric.traceability("Confirmed")),
        round_or_blank(metric.traceability("Reported")),
        metric.evidence_source_reviews,
        round_or_blank(metric.evidence_rate(metric.evidence_supported_reviews)),
        round_or_blank(metric.evidence_rate(metric.evidence_contradicted_reviews)),
        round_or_blank(metric.evidence_rate(metric.evidence_independent_reviews)),
        round_or_blank(metric.evidence_rate(metric.evidence_high_authority_reviews)),
        round_or_blank(metric.evidence_rate(metric.evidence_strong_reasoning_reviews)),
        round_or_blank(metric.evidence_rate(metric.evidence_honest_uncertainty_reviews)),
        round_or_blank(metric.evidence_rate(metric.evidence_high_relevance_reviews)),
        metric.judge_agreement_compared,
        round_or_blank(judge_agreement_rate),
        metric.inference_source_copied,
    ]


def append_calibration_sections(lines: list[str], summaries: list[Any]) -> None:
    """Append calibration and evidence-review Markdown sections."""
    lines.append("")
    lines.append("## Label Calibration")
    lines.append("")
    lines.append(
        "Traceability of (Confirmed)/(Reported) claims against the fetched text "
        "of their cited sources, pooled from `primr calibrate` sidecars. "
        f"Gate threshold: {calibration_gate_description()}."
    )
    lines.append("")
    lines.append("| Profile | Calibrated Reports | Confirmed | Reported | Status |")
    lines.append("|---|---:|---:|---:|---|")
    gate = calibration_gate_threshold()
    for summary in summaries:
        confirmed = percent_or_dash(summary.confirmed_traceability)
        reported = percent_or_dash(summary.reported_traceability)
        status = calibration_status(
            summary.calibrated_report_count,
            summary.confirmed_traceability,
            gate,
        )
        lines.append(
            f"| {summary.profile} | {summary.calibrated_report_count} | "
            f"{confirmed} | {reported} | {status} |"
        )

    lines.append("")
    lines.append("## Evidence Review")
    lines.append("")
    lines.append(
        "Source-level review dimensions from calibration sidecars. These are "
        "report-only signals until a baseline and judge-agreement record make "
        "a hard gate defensible."
    )
    lines.append("")
    lines.append(
        "| Profile | Source Reviews | Supported | Contradicted | Independent | "
        "High Authority | Strong Reasoning | Honest Uncertainty | High Relevance |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for summary in summaries:
        lines.append(
            f"| {summary.profile} | {summary.evidence_source_reviews} | "
            f"{percent_or_dash(summary.evidence_support_rate)} | "
            f"{percent_or_dash(summary.evidence_contradiction_rate)} | "
            f"{percent_or_dash(summary.evidence_independence_rate)} | "
            f"{percent_or_dash(summary.evidence_high_authority_rate)} | "
            f"{percent_or_dash(summary.evidence_strong_reasoning_rate)} | "
            f"{percent_or_dash(summary.evidence_honest_uncertainty_rate)} | "
            f"{percent_or_dash(summary.evidence_high_relevance_rate)} |"
        )

    lines.append("")
    lines.append("## Inference Label Checks")
    lines.append("")
    lines.append(
        "(Estimated)/(Hypothesis) claims are inference-class labels. They are "
        "not required to trace to a source, but should not be copied verbatim "
        "from cited source text. This is a report-only signal until a baseline "
        "defines acceptable behavior."
    )
    lines.append("")
    lines.append("| Profile | Source-Copied Inference Claims |")
    lines.append("|---|---:|")
    for summary in summaries:
        lines.append(f"| {summary.profile} | {summary.inference_source_copied} |")

    lines.append("")
    lines.append("## Judge Agreement")
    lines.append("")
    lines.append(
        "Cloud-vs-local agreement recorded by `primr calibrate --judge-compare`, "
        "pooled across calibrated report sidecars. This is a baseline-readiness "
        "signal, not a gate."
    )
    lines.append("")
    lines.append("| Profile | Compared Claims | Agreement |")
    lines.append("|---|---:|---:|")
    for summary in summaries:
        lines.append(
            f"| {summary.profile} | {summary.judge_agreement_compared} | "
            f"{percent_or_dash(summary.judge_agreement_rate)} |"
        )
