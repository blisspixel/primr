"""Operator-review metadata for calibration baseline artifacts."""

from __future__ import annotations

from typing import Any

DECISION_TEMPLATE_FORMAT = "primr.calibration_gate_decision_template.v1"
BLOCKING_GATE_REASONS = frozenset(
    {
        "baseline_not_ready",
        "inspection_not_ready",
        "missing_gate_recommendation",
    }
)


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
    gate_status = str(gate_recommendation.get("status") or "not_recommended")
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
                "reports_total": _safe_int(gate_recommendation.get("reports_total")),
                "reports_considered": _safe_int(gate_recommendation.get("reports_considered")),
                "reports_without_decidable_confirmed": _safe_int(
                    gate_recommendation.get("reports_without_decidable_confirmed")
                ),
                "confirmed_traceability_floor_complete": bool(
                    gate_recommendation.get("confirmed_traceability_floor_complete")
                ),
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
                "gate_status": gate_status,
                "gate_reason": gate_recommendation.get("reason"),
                "reports_without_decidable_confirmed": _safe_int(
                    gate_recommendation.get("reports_without_decidable_confirmed")
                ),
            },
        },
    ]
    if not gate_candidate:
        items.append(
            {
                "id": "report_only_gate_decision",
                "required": True,
                "action": (
                    "Document why the baseline remains report-only and leave the "
                    "hard calibration gate unset."
                ),
                "evidence": {
                    "gate_status": gate_status,
                    "gate_reason": gate_recommendation.get("reason"),
                    "reports_total": _safe_int(gate_recommendation.get("reports_total")),
                    "reports_considered": _safe_int(gate_recommendation.get("reports_considered")),
                    "reports_without_decidable_confirmed": _safe_int(
                        gate_recommendation.get("reports_without_decidable_confirmed")
                    ),
                },
            }
        )
    return {
        "decision_status": decision_status,
        "reason": gate_recommendation.get("reason"),
        "human_review_required": True,
        "automatic_gate_arming_allowed": False,
        "operator_may_arm_after_review": gate_candidate,
        "disagreement_cases": disagreement_cases,
        "items": items,
    }


def operator_decision_template(
    *,
    gate_recommendation: dict[str, Any],
    operator_review: dict[str, Any],
    measurement: dict[str, Any],
    next_actions: dict[str, Any],
) -> dict[str, Any]:
    """Return a body-free template for recording an operator gate decision."""
    gate_status = str(gate_recommendation.get("status") or "not_recommended")
    gate_reason = str(gate_recommendation.get("reason") or "")
    decision_status = str(operator_review.get("decision_status") or "required")
    can_arm_after_review = _can_arm_after_review(
        gate_recommendation=gate_recommendation,
        operator_review=operator_review,
    )
    decision_blocked = _decision_blocked(
        decision_status=decision_status,
        gate_reason=gate_reason,
    )
    recommended_workflow = _recommended_workflow(
        gate_status=gate_status,
        gate_reason=gate_reason,
        decision_status=decision_status,
        can_arm_after_review=can_arm_after_review,
    )
    allowed_decisions = _allowed_decisions(
        can_arm_after_review=can_arm_after_review,
        decision_blocked=decision_blocked,
    )
    return {
        "template_format": DECISION_TEMPLATE_FORMAT,
        "decision_status": decision_status,
        "recommended_decision": _recommended_recordable_decision(allowed_decisions),
        "recommended_workflow": recommended_workflow,
        "allowed_decisions": allowed_decisions,
        "automatic_gate_arming_allowed": False,
        "operator_may_arm_after_review": can_arm_after_review,
        "environment_variable": gate_recommendation.get("environment_variable"),
        "env_assignment": gate_recommendation.get("env_assignment"),
        "gate_status": gate_status,
        "gate_reason": gate_reason,
        "hard_gate_action": next_actions.get("hard_gate_action"),
        "measurement_status": measurement.get("status"),
        "required_review_items": _required_review_item_ids(operator_review),
        "evidence": {
            "reports_total": _safe_int(gate_recommendation.get("reports_total")),
            "reports_considered": _safe_int(gate_recommendation.get("reports_considered")),
            "reports_without_decidable_confirmed": _safe_int(
                gate_recommendation.get("reports_without_decidable_confirmed")
            ),
            "confirmed_traceability_floor_complete": bool(
                gate_recommendation.get("confirmed_traceability_floor_complete")
            ),
            "judge_agreement_rate": _optional_rate(gate_recommendation.get("judge_agreement_rate")),
        },
        "operator_supplied_fields": [
            "decision",
            "reviewed_at_utc",
            "reviewer",
            "rationale",
            "representative_coverage_notes",
            "evidence_dimension_notes",
            "judge_disagreement_notes",
            "false_positive_false_negative_notes",
        ],
        "decision_policy": (
            "Only an explicit operator decision may set the hard gate. "
            "Report-only decisions leave PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY unset."
        ),
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


def render_operator_decision_template_markdown(template: dict[str, Any]) -> list[str]:
    """Render the operator decision template section for Markdown summaries."""
    allowed = ", ".join(str(item) for item in template.get("allowed_decisions", []))
    required = ", ".join(str(item) for item in template.get("required_review_items", []))
    fields = ", ".join(str(item) for item in template.get("operator_supplied_fields", []))
    evidence = template.get("evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
    return [
        "## Operator Decision Template",
        "",
        f"Decision status: {template.get('decision_status', 'required')}",
        f"Recommended decision: {template.get('recommended_decision') or 'none'}",
        f"Recommended workflow: {template.get('recommended_workflow', '')}",
        f"Allowed decisions: {allowed or 'none'}",
        f"Hard-gate action: {template.get('hard_gate_action', '')}",
        f"Gate reason: {template.get('gate_reason', '')}",
        (
            "Selected reports: "
            f"{evidence.get('reports_total', 0)} total, "
            f"{evidence.get('reports_considered', 0)} with decidable Confirmed floor, "
            f"{evidence.get('reports_without_decidable_confirmed', 0)} without"
        ),
        f"Required review items: {required or 'none'}",
        f"Operator-supplied fields: {fields or 'none'}",
        f"Decision policy: {template.get('decision_policy', '')}",
    ]


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


def _can_arm_after_review(
    *,
    gate_recommendation: dict[str, Any],
    operator_review: dict[str, Any],
) -> bool:
    return (
        bool(operator_review.get("operator_may_arm_after_review"))
        and gate_recommendation.get("status") == "candidate"
        and isinstance(gate_recommendation.get("env_assignment"), str)
        and bool(gate_recommendation.get("env_assignment"))
    )


def _recommended_workflow(
    *,
    gate_status: str,
    gate_reason: str,
    decision_status: str,
    can_arm_after_review: bool,
) -> str:
    if can_arm_after_review and gate_status == "candidate":
        return "operator_review_before_arm_gate"
    if _decision_blocked(decision_status=decision_status, gate_reason=gate_reason):
        return "resolve_blockers_before_gate_decision"
    return "keep_report_only"


def _decision_blocked(*, decision_status: str, gate_reason: str) -> bool:
    return decision_status.startswith("blocked_by") or gate_reason in BLOCKING_GATE_REASONS


def _recommended_recordable_decision(allowed_decisions: list[str]) -> str | None:
    if "arm_gate" in allowed_decisions:
        return "arm_gate"
    if "keep_report_only" in allowed_decisions:
        return "keep_report_only"
    return None


def _allowed_decisions(
    *,
    can_arm_after_review: bool,
    decision_blocked: bool,
) -> list[str]:
    if decision_blocked:
        return []
    if can_arm_after_review:
        return ["arm_gate", "keep_report_only"]
    return ["keep_report_only"]


def _required_review_item_ids(operator_review: dict[str, Any]) -> list[str]:
    items = operator_review.get("items", [])
    if not isinstance(items, list):
        return []
    return [
        str(item.get("id"))
        for item in items
        if isinstance(item, dict) and item.get("required") and item.get("id")
    ]


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
