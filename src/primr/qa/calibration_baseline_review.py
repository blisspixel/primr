"""Operator-review metadata for calibration baseline artifacts."""

from __future__ import annotations

from typing import Any


def operator_review_summary(
    *,
    ready: bool,
    reasons: list[str],
    totals: dict[str, Any],
    evidence: dict[str, Any],
    agreement: dict[str, Any],
    representation: dict[str, Any],
    gate_recommendation: dict[str, Any],
) -> dict[str, Any]:
    """Build the explicit human-review step before any hard gate is armed."""
    disagreement_cases = max(
        0,
        _safe_int(agreement.get("compared")) - _safe_int(agreement.get("agreed")),
    )
    gate_candidate = gate_recommendation.get("status") == "candidate" and isinstance(
        gate_recommendation.get("env_assignment"), str
    )
    if not ready:
        return {
            "decision_status": "blocked_by_readiness",
            "reason": reasons[0] if reasons else "baseline_not_ready",
            "human_review_required": True,
            "automatic_gate_arming_allowed": False,
            "operator_may_arm_after_review": False,
            "disagreement_cases": disagreement_cases,
            "items": [
                {
                    "id": "readiness_blockers",
                    "required": True,
                    "action": (
                        "Resolve the baseline readiness blockers before reviewing any "
                        "traceability threshold."
                    ),
                    "evidence": {
                        "reasons": reasons,
                        "reports": _safe_int(totals.get("reports")),
                    },
                }
            ],
        }

    decision_status = "pending_operator_review" if gate_candidate else "report_only_recommended"
    items = [
        {
            "id": "representative_coverage",
            "required": True,
            "action": (
                "Confirm the selected reports still represent the required coverage tags "
                "and current report format."
            ),
            "evidence": {
                "required_tags": _string_list(representation.get("required_tags")),
                "present_tags": _string_list(representation.get("present_tags")),
            },
        },
        {
            "id": "evidence_review_dimensions",
            "required": True,
            "action": (
                "Review support, contradiction, source independence, source authority, "
                "reasoning strength, uncertainty honesty, and business relevance rates."
            ),
            "evidence": {
                "source_reviews": _safe_int(evidence.get("source_reviews")),
                "reports_with_evidence_reviews": _safe_int(
                    totals.get("reports_with_evidence_reviews")
                ),
            },
        },
        {
            "id": "judge_agreement",
            "required": True,
            "action": (
                "Review cloud-vs-local disagreement cases before trusting the local "
                "judge path or any threshold derived from it."
            ),
            "evidence": {
                "compared": _safe_int(agreement.get("compared")),
                "agreed": _safe_int(agreement.get("agreed")),
                "agreement_rate": _optional_rate(agreement.get("agreement_rate")),
                "disagreement_cases": disagreement_cases,
            },
        },
        {
            "id": "false_positive_false_negative_spot_check",
            "required": True,
            "action": (
                "Spot-check sampled traceable and untraceable verdicts for false "
                "positives and false negatives before arming a hard gate."
            ),
            "evidence": {
                "gate_reason": gate_recommendation.get("reason"),
                "measured_floor": _optional_rate(gate_recommendation.get("measured_floor")),
            },
        },
        {
            "id": "threshold_decision",
            "required": gate_candidate,
            "action": (
                "If the review passes, set the recommended threshold deliberately; "
                "otherwise leave the gate report-only."
            ),
            "evidence": {
                "environment_variable": gate_recommendation.get("environment_variable"),
                "env_assignment": gate_recommendation.get("env_assignment"),
            },
        },
    ]
    return {
        "decision_status": decision_status,
        "reason": gate_recommendation.get("reason"),
        "human_review_required": True,
        "automatic_gate_arming_allowed": False,
        "operator_may_arm_after_review": gate_candidate,
        "disagreement_cases": disagreement_cases,
        "items": items,
    }


def inspection_operator_review(
    operator_review: Any,
    *,
    ready: bool,
    reasons: list[str],
) -> dict[str, Any]:
    """Return operator-review metadata adjusted for current artifact integrity."""
    if not isinstance(operator_review, dict):
        return {
            "decision_status": "missing_operator_review",
            "human_review_required": True,
            "automatic_gate_arming_allowed": False,
            "operator_may_arm_after_review": False,
            "disagreement_cases": 0,
            "items": [],
        }
    if ready:
        return dict(operator_review)
    blocked = dict(operator_review)
    blocked["decision_status"] = "blocked_by_inspection"
    blocked["reason"] = reasons[0] if reasons else "inspection_not_ready"
    blocked["automatic_gate_arming_allowed"] = False
    blocked["operator_may_arm_after_review"] = False
    return blocked


def render_operator_review_markdown(operator_review: dict[str, Any]) -> list[str]:
    """Render the operator-review section for a calibration baseline summary."""
    lines = [
        "## Operator Review",
        "",
        f"Decision status: {operator_review.get('decision_status', 'required')}",
        (
            "Automatic gate arming allowed: "
            f"{'yes' if operator_review.get('automatic_gate_arming_allowed') else 'no'}"
        ),
        (
            "Operator may arm after review: "
            f"{'yes' if operator_review.get('operator_may_arm_after_review') else 'no'}"
        ),
        f"Disagreement cases needing review: {operator_review.get('disagreement_cases', 0)}",
        "",
        "| Review Item | Required | Action |",
        "|---|---:|---|",
    ]
    lines.extend(_render_operator_review_items(operator_review))
    return lines


def _render_operator_review_items(operator_review: dict[str, Any]) -> list[str]:
    items = operator_review.get("items", [])
    if not isinstance(items, list):
        return []
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            f"| {item.get('id', '')} | "
            f"{'yes' if item.get('required') else 'no'} | "
            f"{item.get('action', '')} |"
        )
    return rows


def _optional_rate(value: Any) -> float | None:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    if rate < 0 or rate > 1:
        return None
    return round(rate, 3)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]
