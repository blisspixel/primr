"""Offline eval helpers for page-access classification.

The classifier decides whether fetched content is a real page or a challenge
shell. This module scores that decision against labeled local fixtures or
trace-derived predictions without persisting raw HTML, URLs, or page bodies in
the eval artifacts.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import PageAccessAssessment, PageAccessState, RenderSnapshotComparison
from .page_access import classify_page_access


@dataclass(frozen=True)
class PageAccessEvalCase:
    """One labeled classifier fixture.

    ``expected_real_content`` is true when the page body should count as real
    first-party content. The raw ``html`` and URL are inputs only and are not
    copied into eval reports.
    """

    case_id: str
    expected_real_content: bool
    html: bytes
    url: str
    http_status: int | None = None
    content_type: str | None = "text/html"
    final_url: str | None = None
    expected_markers: tuple[str, ...] = ()
    render_snapshot: RenderSnapshotComparison | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class PageAccessPrediction:
    """Body-free observed classification for one labeled case."""

    case_id: str
    expected_real_content: bool
    predicted_state: PageAccessState
    confidence: float = 0.0
    reason: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def predicted_real_content(self) -> bool:
        return self.predicted_state == PageAccessState.SUCCESS

    @property
    def correct(self) -> bool:
        return self.expected_real_content == self.predicted_real_content


@dataclass(frozen=True)
class PageAccessEvalMetrics:
    """Confusion metrics for page-access decisions."""

    sample_count: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    accuracy: float
    precision: float
    recall: float
    specificity: float
    false_positive_rate: float
    false_negative_rate: float
    f1: float
    balanced_accuracy: float


@dataclass(frozen=True)
class PageAccessEvalRow:
    """Body-free per-case eval result."""

    case_id: str
    expected_real_content: bool
    predicted_real_content: bool
    predicted_state: str
    correct: bool
    confidence: float
    reason: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class PageAccessEvalReport:
    """Body-free page-access eval report."""

    schema_version: int
    metrics: PageAccessEvalMetrics
    rows: tuple[PageAccessEvalRow, ...]
    by_tag: dict[str, PageAccessEvalMetrics] = field(default_factory=dict)

    @property
    def false_positive_case_ids(self) -> tuple[str, ...]:
        return tuple(
            row.case_id
            for row in self.rows
            if not row.expected_real_content and row.predicted_real_content
        )

    @property
    def false_negative_case_ids(self) -> tuple[str, ...]:
        return tuple(
            row.case_id
            for row in self.rows
            if row.expected_real_content and not row.predicted_real_content
        )


def evaluate_page_access_cases(cases: list[PageAccessEvalCase]) -> PageAccessEvalReport:
    """Run the page-access classifier over labeled fixtures and score it."""

    predictions: list[PageAccessPrediction] = []
    for case in cases:
        assessment = classify_page_access(
            case.html,
            url=case.url,
            http_status=case.http_status,
            content_type=case.content_type,
            final_url=case.final_url,
            expected_markers=list(case.expected_markers),
            render_snapshot=case.render_snapshot,
        )
        predictions.append(
            PageAccessPrediction(
                case_id=_required_case_id(case.case_id),
                expected_real_content=case.expected_real_content,
                predicted_state=assessment.state,
                confidence=assessment.confidence,
                reason=assessment.reason,
                tags=_clean_tags(case.tags),
            )
        )
    return score_page_access_predictions(predictions)


def prediction_from_access_assessment(
    *,
    case_id: str,
    expected_real_content: bool,
    access_assessment: PageAccessAssessment | dict[str, Any] | None,
    tags: tuple[str, ...] = (),
) -> PageAccessPrediction:
    """Build a body-free prediction from a trace access-assessment object."""

    if access_assessment is None:
        state = PageAccessState.UNKNOWN
        confidence = 0.0
        reason = "missing_access_assessment"
    elif isinstance(access_assessment, PageAccessAssessment):
        state = access_assessment.state
        confidence = access_assessment.confidence
        reason = access_assessment.reason
    else:
        raw_state = access_assessment.get("state")
        state = _parse_page_access_state(raw_state)
        raw_confidence = access_assessment.get("confidence", 0.0)
        confidence = float(raw_confidence) if isinstance(raw_confidence, int | float) else 0.0
        raw_reason = access_assessment.get("reason")
        reason = raw_reason if isinstance(raw_reason, str) else None

    return PageAccessPrediction(
        case_id=_required_case_id(case_id),
        expected_real_content=expected_real_content,
        predicted_state=state,
        confidence=max(0.0, min(1.0, confidence)),
        reason=reason,
        tags=_clean_tags(tags),
    )


def score_page_access_predictions(
    predictions: list[PageAccessPrediction],
) -> PageAccessEvalReport:
    """Score body-free page-access predictions against labels."""

    cleaned = [_clean_prediction(item) for item in predictions]
    rows = tuple(_row_from_prediction(item) for item in cleaned)
    by_tag: dict[str, PageAccessEvalMetrics] = {}
    for tag in sorted({tag for item in cleaned for tag in item.tags}):
        tagged = [item for item in cleaned if tag in item.tags]
        by_tag[tag] = _compute_metrics(tagged)

    return PageAccessEvalReport(
        schema_version=1,
        metrics=_compute_metrics(cleaned),
        rows=rows,
        by_tag=by_tag,
    )


def page_access_eval_payload(report: PageAccessEvalReport) -> dict[str, Any]:
    """Serialize a report without raw HTML, URLs, or page bodies."""

    payload = asdict(report)
    payload["false_positive_case_ids"] = list(report.false_positive_case_ids)
    payload["false_negative_case_ids"] = list(report.false_negative_case_ids)
    return payload


def write_page_access_eval_json(path: Path, report: PageAccessEvalReport) -> None:
    """Write a body-free page-access eval JSON artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(page_access_eval_payload(report), indent=2), encoding="utf-8")


def write_page_access_eval_markdown(
    path: Path,
    report: PageAccessEvalReport,
    *,
    title: str = "Page Access Classifier Eval",
) -> None:
    """Write a compact Markdown summary for human review."""

    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = report.metrics
    lines = [
        f"# {title}",
        "",
        "| Samples | Accuracy | Precision | Recall | FPR | FNR | F1 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| {metrics.sample_count} | {metrics.accuracy:.4f} | {metrics.precision:.4f} | "
            f"{metrics.recall:.4f} | {metrics.false_positive_rate:.4f} | "
            f"{metrics.false_negative_rate:.4f} | {metrics.f1:.4f} |"
        ),
        "",
        "| Case | Expected Real | Predicted Real | State | Correct | Confidence | Tags |",
        "|---|---:|---:|---|---:|---:|---|",
    ]
    for row in report.rows:
        tags = ", ".join(row.tags)
        lines.append(
            f"| {row.case_id} | {str(row.expected_real_content).lower()} | "
            f"{str(row.predicted_real_content).lower()} | {row.predicted_state} | "
            f"{str(row.correct).lower()} | {row.confidence:.4f} | {tags} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _clean_prediction(prediction: PageAccessPrediction) -> PageAccessPrediction:
    return PageAccessPrediction(
        case_id=_required_case_id(prediction.case_id),
        expected_real_content=prediction.expected_real_content,
        predicted_state=prediction.predicted_state,
        confidence=max(0.0, min(1.0, prediction.confidence)),
        reason=prediction.reason,
        tags=_clean_tags(prediction.tags),
    )


def _row_from_prediction(prediction: PageAccessPrediction) -> PageAccessEvalRow:
    return PageAccessEvalRow(
        case_id=prediction.case_id,
        expected_real_content=prediction.expected_real_content,
        predicted_real_content=prediction.predicted_real_content,
        predicted_state=prediction.predicted_state.value,
        correct=prediction.correct,
        confidence=prediction.confidence,
        reason=prediction.reason,
        tags=prediction.tags,
    )


def _compute_metrics(predictions: list[PageAccessPrediction]) -> PageAccessEvalMetrics:
    tp = sum(
        1 for item in predictions if item.expected_real_content and item.predicted_real_content
    )
    tn = sum(
        1
        for item in predictions
        if not item.expected_real_content and not item.predicted_real_content
    )
    fp = sum(
        1 for item in predictions if not item.expected_real_content and item.predicted_real_content
    )
    fn = sum(
        1 for item in predictions if item.expected_real_content and not item.predicted_real_content
    )
    sample_count = len(predictions)
    accuracy = _ratio(tp + tn, sample_count)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    specificity = _ratio(tn, tn + fp)
    false_positive_rate = _ratio(fp, fp + tn)
    false_negative_rate = _ratio(fn, fn + tp)
    f1 = _ratio(2 * precision * recall, precision + recall)
    balanced_accuracy = (recall + specificity) / 2 if predictions else 0.0
    return PageAccessEvalMetrics(
        sample_count=sample_count,
        true_positive=tp,
        true_negative=tn,
        false_positive=fp,
        false_negative=fn,
        accuracy=round(accuracy, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        specificity=round(specificity, 4),
        false_positive_rate=round(false_positive_rate, 4),
        false_negative_rate=round(false_negative_rate, 4),
        f1=round(f1, 4),
        balanced_accuracy=round(balanced_accuracy, 4),
    )


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _parse_page_access_state(value: object) -> PageAccessState:
    if isinstance(value, PageAccessState):
        return value
    if isinstance(value, str):
        try:
            return PageAccessState(value)
        except ValueError:
            return PageAccessState.UNKNOWN
    return PageAccessState.UNKNOWN


def _required_case_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Page-access eval case_id must be a non-empty string")
    return value.strip()


def _clean_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()}))
