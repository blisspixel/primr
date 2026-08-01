from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from primr.core.stage_eval_scorecard import StageQualityEvidence

STANDING_CORPUS_ID = "source_relevance_standing_v1"
STANDING_CORPUS_FILENAME = "source_relevance_standing_v1.json"
STANDING_CORPUS_REQUIRED_BACKENDS: frozenset[str] = frozenset({"cloud-baseline", "codex-host"})
STANDING_CORPUS_MIN_CASES = 5


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


def standing_source_relevance_corpus_path() -> Path:
    """Return the packaged standing source-relevance corpus path.

    The corpus is body-free labeled keep-list evidence for review-only
    host-versus-cloud scorecards. It is not a promotion gate by itself.
    """

    return Path(__file__).resolve().parents[1] / "resources" / "eval" / STANDING_CORPUS_FILENAME


def load_source_relevance_eval_fixture(path: Path) -> list[SourceRelevanceEvalCase]:
    """Load labeled source-relevance cases without returning source bodies."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid source relevance eval fixture JSON: {path}") from exc

    return _cases_from_payload(payload)


def load_standing_source_relevance_corpus(
    path: Path | None = None,
) -> list[SourceRelevanceEvalCase]:
    """Load and integrity-check the standing source-relevance corpus."""

    corpus_path = path or standing_source_relevance_corpus_path()
    if not corpus_path.is_file():
        raise ValueError(f"Standing source-relevance corpus missing: {corpus_path}")
    try:
        payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid standing source-relevance corpus JSON: {corpus_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Standing source-relevance corpus root must be an object")
    inspection = inspect_standing_source_relevance_corpus(payload=payload)
    if inspection["status"] != "ready_for_scorecard":
        blockers = ", ".join(inspection["blockers"]) or "unknown integrity failure"
        raise ValueError(f"Standing source-relevance corpus is not scorecard-ready: {blockers}")
    return _cases_from_payload(payload)


def inspect_standing_source_relevance_corpus(
    *,
    path: Path | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return body-free readiness metadata for the standing corpus.

    The inspection never returns source bodies, URLs, or keep-list contents.
    A ready corpus is scorecard input only; promotion remains operator-owned.
    """

    corpus_fingerprint: dict[str, Any] | None = None
    if payload is None:
        loaded = _load_standing_corpus_payload(path)
        if loaded.get("error"):
            return loaded["error"]
        payload = loaded["payload"]
        corpus_fingerprint = loaded.get("fingerprint")

    blockers: list[str] = []
    corpus_id = payload.get("corpus_id")
    if corpus_id != STANDING_CORPUS_ID:
        blockers.append("corpus_id_mismatch")

    promotion_status = payload.get("promotion_status", "not_promoted")
    if promotion_status != "not_promoted":
        # Standing package must never ship as self-promoted.
        blockers.append("promotion_status_not_report_only")

    required_tags, tag_blockers = _standing_required_tags(payload)
    blockers.extend(tag_blockers)

    cases, case_blockers = _standing_cases(payload)
    blockers.extend(case_blockers)
    if len(cases) < STANDING_CORPUS_MIN_CASES:
        blockers.append("case_count_below_minimum")

    covered_tags, backends_present, field_blockers = _standing_case_coverage(payload)
    blockers.extend(field_blockers)

    missing_tags = sorted(set(required_tags) - covered_tags)
    if missing_tags:
        blockers.append("missing_representative_tags")

    missing_backends = sorted(STANDING_CORPUS_REQUIRED_BACKENDS - backends_present)
    if missing_backends:
        blockers.append("missing_required_backends")

    status = "ready_for_scorecard" if not blockers else "blocked"
    result: dict[str, Any] = {
        "schema_version": 1,
        "corpus_id": STANDING_CORPUS_ID if corpus_id is None else corpus_id,
        "status": status,
        "decision_policy": "scorecard_input_only",
        "promotion_status": (promotion_status if isinstance(promotion_status, str) else "unknown"),
        "blockers": sorted(set(blockers)),
        "case_count": len(cases),
        "covered_representative_tags": sorted(covered_tags),
        "missing_representative_tags": missing_tags,
        "backends_present": sorted(backends_present),
        "missing_required_backends": missing_backends,
        "min_cases": STANDING_CORPUS_MIN_CASES,
    }
    if corpus_fingerprint is not None:
        result["corpus_fingerprint"] = corpus_fingerprint
    return result


def _standing_error_snapshot(status: str, blocker: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "corpus_id": STANDING_CORPUS_ID,
        "status": status,
        "decision_policy": "scorecard_input_only",
        "promotion_status": "not_promoted",
        "blockers": [blocker],
        "case_count": 0,
        "covered_representative_tags": [],
        "missing_representative_tags": [],
        "backends_present": [],
    }


def _load_standing_corpus_payload(path: Path | None) -> dict[str, Any]:
    corpus_path = path or standing_source_relevance_corpus_path()
    if not corpus_path.is_file():
        return {"error": _standing_error_snapshot("missing", "corpus_file_missing")}
    try:
        raw_bytes = corpus_path.read_bytes()
    except OSError:
        return {"error": _standing_error_snapshot("invalid", "corpus_unreadable")}
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"error": _standing_error_snapshot("invalid", "corpus_json_invalid")}
    if not isinstance(raw, dict):
        return {"error": _standing_error_snapshot("invalid", "corpus_root_not_object")}
    return {
        "payload": raw,
        "fingerprint": {
            "path": str(corpus_path),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "size_bytes": len(raw_bytes),
        },
    }


def _standing_required_tags(payload: dict[str, Any]) -> tuple[tuple[str, ...], list[str]]:
    try:
        required_tags = _normalized_tag_list(
            payload.get("required_representative_tags"),
            label="required_representative_tags",
        )
    except ValueError:
        return (), ["required_representative_tags_invalid"]
    if not required_tags:
        return (), ["required_representative_tags_empty"]
    return required_tags, []


def _standing_cases(
    payload: dict[str, Any],
) -> tuple[list[SourceRelevanceEvalCase], list[str]]:
    try:
        return _cases_from_payload(payload), []
    except ValueError:
        return [], ["cases_invalid"]


def _standing_case_coverage(
    payload: dict[str, Any],
) -> tuple[set[str], set[str], list[str]]:
    blockers: list[str] = []
    covered_tags: set[str] = set()
    backends_present: set[str] = set()
    try:
        raw_case_list = _fixture_cases(payload)
    except ValueError:
        return covered_tags, backends_present, ["cases_invalid"]

    for index, raw_case in enumerate(raw_case_list, start=1):
        if not isinstance(raw_case, dict):
            continue
        try:
            covered_tags.update(
                _normalized_tag_list(
                    raw_case.get("representative_tags"),
                    label=f"cases[{index}].representative_tags",
                    allow_empty=True,
                )
            )
        except ValueError:
            blockers.append("case_representative_tags_invalid")
        backends_present.update(_candidate_backend_ids(raw_case.get("candidates")))
        if _case_has_body_fields(raw_case):
            blockers.append("case_contains_source_body_fields")
    return covered_tags, backends_present, blockers


def _candidate_backend_ids(candidates: Any) -> set[str]:
    backends: set[str] = set()
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict):
                backend = candidate.get("backend_id")
                if isinstance(backend, str) and backend.strip():
                    backends.add(backend.strip())
    elif isinstance(candidates, dict):
        backends.update(key.strip() for key in candidates if isinstance(key, str) and key.strip())
    return backends


def _case_has_body_fields(raw_case: dict[str, Any]) -> bool:
    for forbidden in ("source_url", "source_text", "url", "text", "body", "snippet"):
        if forbidden in raw_case and raw_case[forbidden] not in (None, "", [], {}):
            return True
    return False


def _cases_from_payload(payload: Any) -> list[SourceRelevanceEvalCase]:
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


def _normalized_tag_list(
    value: Any,
    *,
    label: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if value is None:
        if allow_empty:
            return ()
        raise ValueError(f"{label} must be a list of non-empty strings")
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of non-empty strings")
    tags: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label} must contain only non-empty strings")
        tag = item.strip()
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    if not tags and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    return tuple(tags)


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


def build_source_relevance_backend_comparison(
    rows: list[SourceRelevanceEvalRow],
    *,
    baseline_backend: str = "cloud-baseline",
    candidate_backend: str = "codex-host",
) -> dict[str, Any]:
    """Compare two backends on shared labeled cases without keep-list bodies.

    Returns body-free aggregate and per-case metric deltas for operator review.
    Does not decide promotion.
    """

    by_case: dict[str, dict[str, SourceRelevanceEvalRow]] = {}
    for row in rows:
        by_case.setdefault(row.case_id, {})[row.backend_id] = row

    case_deltas: list[dict[str, Any]] = []
    for case_id, backend_rows in sorted(by_case.items()):
        baseline = backend_rows.get(baseline_backend)
        candidate = backend_rows.get(candidate_backend)
        if baseline is None or candidate is None:
            continue
        case_deltas.append(
            {
                "case_id": case_id,
                "company": baseline.company,
                "baseline_backend": baseline_backend,
                "candidate_backend": candidate_backend,
                "baseline_f1": baseline.f1_score,
                "candidate_f1": candidate.f1_score,
                "f1_delta": round(candidate.f1_score - baseline.f1_score, 2),
                "baseline_precision": baseline.precision,
                "candidate_precision": candidate.precision,
                "precision_delta": round(candidate.precision - baseline.precision, 2),
                "baseline_recall": baseline.recall,
                "candidate_recall": candidate.recall,
                "recall_delta": round(candidate.recall - baseline.recall, 2),
                "baseline_exact_match": baseline.exact_match,
                "candidate_exact_match": candidate.exact_match,
            }
        )

    if not case_deltas:
        return {
            "schema_version": 1,
            "evidence_type": "source_relevance_backend_comparison",
            "decision_policy": "scorecard_input_only",
            "promotion_status": "not_promoted",
            "baseline_backend": baseline_backend,
            "candidate_backend": candidate_backend,
            "comparable_cases": 0,
            "aggregate": {},
            "cases": [],
            "blockers": ["no_comparable_case_pairs"],
        }

    def _avg(key: str) -> float:
        return round(sum(item[key] for item in case_deltas) / len(case_deltas), 2)

    return {
        "schema_version": 1,
        "evidence_type": "source_relevance_backend_comparison",
        "decision_policy": "scorecard_input_only",
        "promotion_status": "not_promoted",
        "baseline_backend": baseline_backend,
        "candidate_backend": candidate_backend,
        "comparable_cases": len(case_deltas),
        "aggregate": {
            "avg_baseline_f1": _avg("baseline_f1"),
            "avg_candidate_f1": _avg("candidate_f1"),
            "avg_f1_delta": _avg("f1_delta"),
            "avg_precision_delta": _avg("precision_delta"),
            "avg_recall_delta": _avg("recall_delta"),
            "baseline_exact_match_rate_pct": round(
                100.0
                * sum(1 for item in case_deltas if item["baseline_exact_match"])
                / len(case_deltas),
                2,
            ),
            "candidate_exact_match_rate_pct": round(
                100.0
                * sum(1 for item in case_deltas if item["candidate_exact_match"])
                / len(case_deltas),
                2,
            ),
        },
        "cases": case_deltas,
        "blockers": [],
        "review_note": (
            "Offline labeled comparison only. Live host execution, billing "
            "provenance, and human review remain required before promotion."
        ),
    }


def write_source_relevance_backend_comparison(
    path: Path,
    *,
    eval_id: str,
    rows: list[SourceRelevanceEvalRow],
    baseline_backend: str = "cloud-baseline",
    candidate_backend: str = "codex-host",
    corpus_inspection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write body-free backend comparison JSON for operator review."""

    path.parent.mkdir(parents=True, exist_ok=True)
    comparison = build_source_relevance_backend_comparison(
        rows,
        baseline_backend=baseline_backend,
        candidate_backend=candidate_backend,
    )
    payload = {
        **comparison,
        "eval_id": eval_id,
        "stage_id": "fast.source_relevance",
        "corpus_inspection": corpus_inspection,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def write_source_relevance_backend_comparison_markdown(
    path: Path,
    *,
    eval_id: str,
    comparison: dict[str, Any],
) -> None:
    """Write a compact Markdown summary of the backend comparison."""

    path.parent.mkdir(parents=True, exist_ok=True)
    aggregate = comparison.get("aggregate") or {}
    lines = [
        f"# Source Relevance Backend Comparison: {eval_id}",
        "",
        f"- Baseline: `{comparison.get('baseline_backend')}`",
        f"- Candidate: `{comparison.get('candidate_backend')}`",
        f"- Comparable cases: {comparison.get('comparable_cases', 0)}",
        f"- Decision policy: `{comparison.get('decision_policy')}`",
        f"- Promotion status: `{comparison.get('promotion_status')}`",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Avg baseline F1 | {aggregate.get('avg_baseline_f1', 'n/a')} |",
        f"| Avg candidate F1 | {aggregate.get('avg_candidate_f1', 'n/a')} |",
        f"| Avg F1 delta (candidate - baseline) | {aggregate.get('avg_f1_delta', 'n/a')} |",
        f"| Avg precision delta | {aggregate.get('avg_precision_delta', 'n/a')} |",
        f"| Avg recall delta | {aggregate.get('avg_recall_delta', 'n/a')} |",
        f"| Baseline exact-match rate % | {aggregate.get('baseline_exact_match_rate_pct', 'n/a')} |",
        f"| Candidate exact-match rate % | {aggregate.get('candidate_exact_match_rate_pct', 'n/a')} |",
        "",
        comparison.get("review_note", ""),
        "",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_standing_corpus_integrity_sidecar(
    path: Path,
    *,
    inspection: dict[str, Any],
) -> None:
    """Persist body-free standing-corpus integrity inspection next to eval outputs."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inspection, indent=2), encoding="utf-8")


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
