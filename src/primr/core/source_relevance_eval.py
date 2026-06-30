from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from primr.core.stage_eval_scorecard import StageQualityEvidence


@dataclass(frozen=True)
class SourceRelevanceEvalCandidate:
    backend_id: str
    kept_source_ids: tuple[int, ...]


@dataclass(frozen=True)
class SourceRelevanceEvalCase:
    case_id: str
    company: str
    source_count: int
    expected_keep_ids: tuple[int, ...]
    candidates: tuple[SourceRelevanceEvalCandidate, ...]


@dataclass(frozen=True)
class SourceRelevanceEvalRow:
    case_id: str
    company: str
    backend_id: str
    source_count: int
    expected_keep_count: int
    predicted_keep_count: int
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float
    recall: float
    f1_score: float
    exact_match: bool


def load_source_relevance_eval_fixture(path: Path) -> list[SourceRelevanceEvalCase]:
    """Load labeled source-relevance cases without returning source bodies."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid source relevance eval fixture JSON: {path}") from exc

    raw_cases = _fixture_cases(payload)
    cases: list[SourceRelevanceEvalCase] = []
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"cases[{index}] must be an object")
        source_count = _required_positive_int(
            raw_case.get("source_count"),
            f"cases[{index}].source_count",
        )
        cases.append(
            SourceRelevanceEvalCase(
                case_id=_required_text(raw_case, "case_id", index, default=f"case-{index}"),
                company=_required_text(raw_case, "company", index),
                source_count=source_count,
                expected_keep_ids=_normalized_source_ids(
                    raw_case.get("expected_keep", raw_case.get("expected_keep_ids")),
                    f"cases[{index}].expected_keep",
                    source_count=source_count,
                    require_in_range=True,
                ),
                candidates=_fixture_candidates(
                    raw_case.get("candidates", raw_case.get("candidate_keep")),
                    case_index=index,
                ),
            )
        )
    return cases


def build_source_relevance_eval_rows(
    cases: list[SourceRelevanceEvalCase],
) -> list[SourceRelevanceEvalRow]:
    """Score labeled source-relevance keep lists with structural set metrics."""

    rows: list[SourceRelevanceEvalRow] = []
    for case in cases:
        expected = set(case.expected_keep_ids)
        for candidate in case.candidates:
            predicted = set(candidate.kept_source_ids)
            true_positive = len(expected & predicted)
            precision = _precision(
                true_positive=true_positive,
                predicted_count=len(predicted),
                expected_count=len(expected),
            )
            recall = _recall(true_positive=true_positive, expected_count=len(expected))
            rows.append(
                SourceRelevanceEvalRow(
                    case_id=case.case_id,
                    company=case.company,
                    backend_id=candidate.backend_id,
                    source_count=case.source_count,
                    expected_keep_count=len(expected),
                    predicted_keep_count=len(predicted),
                    true_positive_count=true_positive,
                    false_positive_count=len(predicted - expected),
                    false_negative_count=len(expected - predicted),
                    precision=precision,
                    recall=recall,
                    f1_score=_f1(precision=precision, recall=recall),
                    exact_match=expected == predicted,
                )
            )
    return rows


def write_source_relevance_stage_eval_report(
    path: Path,
    *,
    eval_id: str,
    fixture_path: Path,
    rows: list[SourceRelevanceEvalRow],
) -> None:
    """Write body-free labeled source-relevance eval results."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "eval_id": eval_id,
        "stage": "source-relevance",
        "stage_id": "fast.source_relevance",
        "evidence_type": "source_relevance_labeled_eval",
        "decision_policy": "scorecard_input_only",
        "fixture_path": str(fixture_path),
        "cases_evaluated": len({row.case_id for row in rows}),
        "backends_evaluated": len({row.backend_id for row in rows}),
        "results": [asdict(row) for row in _backend_summaries(rows)],
        "rows": [asdict(row) for row in rows],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_source_relevance_stage_eval_markdown(
    path: Path,
    *,
    eval_id: str,
    rows: list[SourceRelevanceEvalRow],
) -> None:
    """Write a compact Markdown summary for source-relevance fixture evals."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Source Relevance Stage Eval: {eval_id}",
        "",
        "| Backend | Cases | Avg F1 | Avg Precision | Avg Recall | Exact Match Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for summary in _backend_summaries(rows):
        lines.append(
            f"| {summary.backend_id} | {summary.cases_evaluated} | "
            f"{summary.avg_f1_score:.2f} | {summary.avg_precision:.2f} | "
            f"{summary.avg_recall:.2f} | {summary.exact_match_rate_pct:.2f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_source_relevance_stage_quality_evidence(
    *,
    eval_id: str,
    rows: list[SourceRelevanceEvalRow],
    stage_id: str = "fast.source_relevance",
) -> list[StageQualityEvidence]:
    """Build scorecard-ready quality evidence from labeled keep-list rows."""

    return sorted(
        [
            StageQualityEvidence(
                stage_id=stage_id,
                backend_id=summary.backend_id,
                quality_score=summary.avg_f1_score,
                sample_size=summary.cases_evaluated,
                source=f"source_relevance_labeled:{eval_id}:{summary.backend_id}",
            )
            for summary in _backend_summaries(rows)
        ],
        key=lambda row: (row.stage_id, row.backend_id),
    )


def write_source_relevance_stage_quality_evidence(
    path: Path,
    *,
    eval_id: str,
    rows: list[SourceRelevanceEvalRow],
    stage_id: str = "fast.source_relevance",
) -> None:
    """Write labeled source-relevance quality evidence for stage scorecards."""

    path.parent.mkdir(parents=True, exist_ok=True)
    evidence = build_source_relevance_stage_quality_evidence(
        eval_id=eval_id,
        rows=rows,
        stage_id=stage_id,
    )
    payload = {
        "schema_version": 1,
        "evidence_type": "source_relevance_labeled_quality",
        "decision_policy": "scorecard_input_only",
        "metric": "macro_avg_f1_score",
        "eval_id": eval_id,
        "stage_id": stage_id,
        "quality_evidence": [asdict(row) for row in evidence],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class _BackendSummary:
    backend_id: str
    cases_evaluated: int
    avg_f1_score: float
    avg_precision: float
    avg_recall: float
    exact_match_rate_pct: float


def _backend_summaries(rows: list[SourceRelevanceEvalRow]) -> list[_BackendSummary]:
    by_backend: dict[str, list[SourceRelevanceEvalRow]] = {}
    for row in rows:
        by_backend.setdefault(row.backend_id, []).append(row)

    summaries: list[_BackendSummary] = []
    for backend_id, backend_rows in by_backend.items():
        row_count = len(backend_rows)
        exact_count = sum(1 for row in backend_rows if row.exact_match)
        summaries.append(
            _BackendSummary(
                backend_id=backend_id,
                cases_evaluated=row_count,
                avg_f1_score=round(
                    sum(row.f1_score for row in backend_rows) / max(1, row_count),
                    2,
                ),
                avg_precision=round(
                    sum(row.precision for row in backend_rows) / max(1, row_count),
                    2,
                ),
                avg_recall=round(
                    sum(row.recall for row in backend_rows) / max(1, row_count),
                    2,
                ),
                exact_match_rate_pct=round((exact_count / max(1, row_count)) * 100.0, 2),
            )
        )
    return sorted(
        summaries,
        key=lambda row: (-row.avg_f1_score, -row.avg_precision, row.backend_id),
    )


def _fixture_cases(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        raw_cases = payload.get("cases", payload.get("items"))
        if isinstance(raw_cases, list):
            return raw_cases
    raise ValueError("Source relevance eval fixture must be a list or object with cases")


def _required_text(
    row: dict[str, Any],
    key: str,
    index: int,
    *,
    default: str | None = None,
) -> str:
    value = row.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"cases[{index}].{key} must be a non-empty string")
    return value.strip()


def _required_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _normalized_source_ids(
    value: Any,
    label: str,
    *,
    source_count: int | None = None,
    require_in_range: bool = False,
) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of positive source numbers")
    normalized: set[int] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise ValueError(f"{label} must contain only positive source numbers")
        if require_in_range and source_count is not None and item > source_count:
            raise ValueError(f"{label} contains source number outside source_count")
        normalized.add(item)
    return tuple(sorted(normalized))


def _fixture_candidates(
    value: Any,
    *,
    case_index: int,
) -> tuple[SourceRelevanceEvalCandidate, ...]:
    if isinstance(value, dict):
        raw_candidates: list[Any] = [
            {"backend_id": backend_id, "kept_source_ids": kept_ids}
            for backend_id, kept_ids in value.items()
        ]
    elif isinstance(value, list):
        raw_candidates = value
    else:
        raise ValueError(f"cases[{case_index}].candidates must be an object or list")

    candidates: list[SourceRelevanceEvalCandidate] = []
    for candidate_index, raw_candidate in enumerate(raw_candidates, start=1):
        if not isinstance(raw_candidate, dict):
            raise ValueError(f"cases[{case_index}].candidates[{candidate_index}] must be an object")
        backend_id = raw_candidate.get("backend_id")
        if not isinstance(backend_id, str) or not backend_id.strip():
            raise ValueError(
                f"cases[{case_index}].candidates[{candidate_index}].backend_id "
                "must be a non-empty string"
            )
        candidates.append(
            SourceRelevanceEvalCandidate(
                backend_id=backend_id.strip(),
                kept_source_ids=_normalized_source_ids(
                    raw_candidate.get("kept", raw_candidate.get("kept_source_ids")),
                    f"cases[{case_index}].candidates[{candidate_index}].kept",
                ),
            )
        )
    return tuple(candidates)


def _precision(
    *,
    true_positive: int,
    predicted_count: int,
    expected_count: int,
) -> float:
    if predicted_count <= 0:
        return 100.0 if expected_count <= 0 else 0.0
    return round((true_positive / predicted_count) * 100.0, 2)


def _recall(*, true_positive: int, expected_count: int) -> float:
    if expected_count <= 0:
        return 100.0
    return round((true_positive / expected_count) * 100.0, 2)


def _f1(*, precision: float, recall: float) -> float:
    if precision + recall <= 0.0:
        return 0.0
    return round((2.0 * precision * recall) / (precision + recall), 2)
