from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from primr.core.stage_route_comparison import StageRouteComparisonRow


@dataclass(frozen=True)
class StageQualityEvidence:
    stage_id: str
    backend_id: str
    quality_score: float
    sample_size: int
    source: str


@dataclass(frozen=True)
class StageEvalScorecardRow:
    stage_id: str
    backend_id: str
    inference_profile: str
    attempts: int
    selected_attempts: int
    fallback_attempts: int
    failed_attempts: int
    failure_rate: float
    actual_cost_usd: float
    avg_duration_seconds: float | None
    quality_score: float | None
    quality_sample_size: int
    quality_sources: tuple[str, ...]
    review_status: str
    blockers: tuple[str, ...]


def load_stage_quality_evidence(path: Path) -> list[StageQualityEvidence]:
    """Load explicit stage quality evidence from JSON."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid stage quality evidence JSON: {path}") from exc

    rows = _quality_evidence_payload_rows(payload)
    evidence: list[StageQualityEvidence] = []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"quality_evidence[{index}] must be an object")
        evidence.append(
            StageQualityEvidence(
                stage_id=_required_text(item, "stage_id", index),
                backend_id=_required_text(item, "backend_id", index),
                quality_score=_required_quality_score(item, index),
                sample_size=_required_sample_size(item, index),
                source=_required_text(item, "source", index),
            )
        )
    return evidence


def build_stage_eval_scorecard(
    *,
    route_rows: list[StageRouteComparisonRow],
    quality_evidence: list[StageQualityEvidence],
    min_quality_score: float,
    max_failure_rate: float = 0.0,
) -> list[StageEvalScorecardRow]:
    """Combine route observations and explicit quality evidence for review."""

    evidence_by_key = _aggregate_quality_evidence(quality_evidence)
    scorecard: list[StageEvalScorecardRow] = []
    for route in route_rows:
        quality = evidence_by_key.get((route.stage_id, route.backend_id))
        failure_rate = round(route.failed_attempts / route.attempts, 4) if route.attempts else 0.0
        blockers: list[str] = []
        if route.attempts <= 0:
            blockers.append("no_route_observations")
        if quality is None or quality.sample_size <= 0:
            blockers.append("missing_quality_evidence")
        elif quality.quality_score < min_quality_score:
            blockers.append("quality_below_threshold")
        if failure_rate > max_failure_rate:
            blockers.append("failure_rate_above_threshold")

        scorecard.append(
            StageEvalScorecardRow(
                stage_id=route.stage_id,
                backend_id=route.backend_id,
                inference_profile=route.inference_profile,
                attempts=route.attempts,
                selected_attempts=route.selected_attempts,
                fallback_attempts=route.fallback_attempts,
                failed_attempts=route.failed_attempts,
                failure_rate=failure_rate,
                actual_cost_usd=route.actual_cost_usd,
                avg_duration_seconds=route.avg_duration_seconds,
                quality_score=quality.quality_score if quality is not None else None,
                quality_sample_size=quality.sample_size if quality is not None else 0,
                quality_sources=quality.sources if quality is not None else (),
                review_status=_review_status(blockers),
                blockers=tuple(blockers),
            )
        )
    return sorted(
        scorecard,
        key=lambda row: (
            row.review_status != "candidate_for_human_review",
            -(row.quality_score or 0.0),
            row.actual_cost_usd,
            row.stage_id,
            row.backend_id,
        ),
    )


def write_stage_eval_scorecard_json(
    path: Path,
    *,
    rows: list[StageEvalScorecardRow],
    min_quality_score: float,
    max_failure_rate: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "decision_policy": "candidate_for_human_review_only",
        "min_quality_score": min_quality_score,
        "max_failure_rate": max_failure_rate,
        "rows": [asdict(row) for row in rows],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_stage_eval_scorecard_markdown(
    path: Path,
    *,
    rows: list[StageEvalScorecardRow],
    title: str = "Stage Eval Scorecard",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        "| Stage | Backend | Profile | Status | Quality | Samples | Failure Rate | Cost | Avg Seconds | Blockers |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        quality = f"{row.quality_score:.2f}" if row.quality_score is not None else ""
        avg_duration = (
            f"{row.avg_duration_seconds:.3f}" if row.avg_duration_seconds is not None else ""
        )
        blockers = ", ".join(row.blockers)
        lines.append(
            f"| {row.stage_id} | {row.backend_id} | {row.inference_profile} | "
            f"{row.review_status} | {quality} | {row.quality_sample_size} | "
            f"{row.failure_rate:.4f} | {row.actual_cost_usd:.8f} | "
            f"{avg_duration} | {blockers} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class _AggregatedQuality:
    quality_score: float
    sample_size: int
    sources: tuple[str, ...]


def _aggregate_quality_evidence(
    rows: list[StageQualityEvidence],
) -> dict[tuple[str, str], _AggregatedQuality]:
    buckets: dict[tuple[str, str], list[StageQualityEvidence]] = {}
    for row in rows:
        if row.sample_size <= 0:
            continue
        buckets.setdefault((row.stage_id, row.backend_id), []).append(row)

    out: dict[tuple[str, str], _AggregatedQuality] = {}
    for key, values in buckets.items():
        total_samples = sum(max(0, row.sample_size) for row in values)
        weighted_score = sum(row.quality_score * row.sample_size for row in values) / max(
            1, total_samples
        )
        sources = tuple(sorted({row.source for row in values if row.source.strip()}))
        out[key] = _AggregatedQuality(
            quality_score=round(weighted_score, 2),
            sample_size=total_samples,
            sources=sources,
        )
    return out


def _quality_evidence_payload_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        rows = payload.get("quality_evidence")
        if isinstance(rows, list):
            return rows
    raise ValueError("Stage quality evidence must be a list or an object with quality_evidence")


def _required_text(row: dict[str, Any], key: str, index: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"quality_evidence[{index}].{key} must be a non-empty string")
    return value.strip()


def _required_quality_score(row: dict[str, Any], index: int) -> float:
    value = row.get("quality_score")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"quality_evidence[{index}].quality_score must be numeric")
    score = float(value)
    if score < 0.0 or score > 100.0:
        raise ValueError(f"quality_evidence[{index}].quality_score must be between 0 and 100")
    return score


def _required_sample_size(row: dict[str, Any], index: int) -> int:
    value = row.get("sample_size")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"quality_evidence[{index}].sample_size must be a positive integer")
    if value <= 0:
        raise ValueError(f"quality_evidence[{index}].sample_size must be a positive integer")
    return value


def _review_status(blockers: list[str]) -> str:
    if not blockers:
        return "candidate_for_human_review"
    if "no_route_observations" in blockers:
        return "needs_route_observations"
    if "missing_quality_evidence" in blockers:
        return "needs_quality_eval"
    if "quality_below_threshold" in blockers:
        return "quality_below_bar"
    if "failure_rate_above_threshold" in blockers:
        return "needs_reliability_review"
    return "needs_quality_eval"
