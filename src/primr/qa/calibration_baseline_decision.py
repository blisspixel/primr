"""Body-free operator decision records for calibration baselines."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from primr.qa.artifact_fingerprints import artifact_fingerprint
from primr.qa.calibration_baseline import inspect_calibration_baseline

DECISION_RECORD_FORMAT = "primr.calibration_gate_decision_record.v1"
ALLOWED_DECISIONS = frozenset({"arm_gate", "keep_report_only"})


def write_operator_decision_record(
    output_path: Path,
    *,
    baseline_path: Path,
    baseline: dict[str, Any],
    decision: str,
    reviewer: str,
    rationale: str,
    reviewed_at_utc: str | None = None,
    notes: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Write a body-free record of an explicit operator gate decision."""
    if _same_path(output_path, baseline_path):
        raise ValueError("--baseline-decision-out must not overwrite the baseline artifact")
    record = build_operator_decision_record(
        baseline_path=baseline_path,
        baseline=baseline,
        decision=decision,
        reviewer=reviewer,
        rationale=rationale,
        reviewed_at_utc=reviewed_at_utc,
        notes=notes,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def build_operator_decision_record(
    *,
    baseline_path: Path,
    baseline: dict[str, Any],
    decision: str,
    reviewer: str,
    rationale: str,
    reviewed_at_utc: str | None = None,
    notes: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return a body-free operator decision record after inspection validation."""
    normalized_decision = _required_text("decision", decision)
    if normalized_decision not in ALLOWED_DECISIONS:
        raise ValueError(
            f"Decision '{normalized_decision}' is invalid; expected one of "
            f"{', '.join(sorted(ALLOWED_DECISIONS))}"
        )
    reviewer_text = _required_text("reviewer", reviewer)
    rationale_text = _required_text("rationale", rationale)
    inspection = inspect_calibration_baseline(baseline, baseline_path=baseline_path)
    template = _decision_template(inspection)
    allowed_decisions = [
        str(item) for item in template.get("allowed_decisions", []) if isinstance(item, str)
    ]
    if normalized_decision not in allowed_decisions:
        raise ValueError(
            f"Decision '{normalized_decision}' is not allowed for this baseline; "
            f"allowed decisions: {', '.join(allowed_decisions) or 'none'}"
        )

    fingerprint = artifact_fingerprint(baseline_path)
    env_assignment = template.get("env_assignment") if normalized_decision == "arm_gate" else None
    return {
        "decision_format": DECISION_RECORD_FORMAT,
        "decision": normalized_decision,
        "reviewed_at_utc": reviewed_at_utc or _utc_now(),
        "reviewer": reviewer_text,
        "rationale": rationale_text,
        "notes": _normalized_notes(notes),
        "applied": False,
        "automatic_gate_arming_allowed": False,
        "manual_action_required": _manual_action(normalized_decision, env_assignment),
        "environment_variable": template.get("environment_variable"),
        "env_assignment": env_assignment,
        "baseline": {
            "path": str(baseline_path),
            "inspection_format": inspection.get("inspection_format"),
            "ready": bool(inspection.get("ready")),
            "status": inspection.get("status"),
            "content_hash": fingerprint["content_hash"],
            "size_bytes": fingerprint["size_bytes"],
        },
        "decision_template": {
            "template_format": template.get("template_format"),
            "decision_status": template.get("decision_status"),
            "recommended_decision": template.get("recommended_decision"),
            "recommended_workflow": template.get("recommended_workflow"),
            "allowed_decisions": allowed_decisions,
            "required_review_items": template.get("required_review_items", []),
            "gate_status": template.get("gate_status"),
            "gate_reason": template.get("gate_reason"),
            "hard_gate_action": template.get("hard_gate_action"),
            "measurement_status": template.get("measurement_status"),
        },
        "evidence": template.get("evidence", {}),
        "policy": (
            "This record documents an explicit operator decision only. Primr did not "
            "set, export, or persist any environment variable."
        ),
    }


def _decision_template(inspection: dict[str, Any]) -> dict[str, Any]:
    template = inspection.get("operator_decision_template")
    if not isinstance(template, dict):
        raise ValueError("Baseline inspection does not include an operator decision template")
    return template


def _required_text(field: str, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _normalized_notes(notes: list[str] | tuple[str, ...]) -> list[str]:
    return [str(note).strip() for note in notes if str(note).strip()]


def _manual_action(decision: str, env_assignment: Any) -> str:
    if decision == "arm_gate":
        if not isinstance(env_assignment, str) or not env_assignment:
            raise ValueError("arm_gate decisions require a validated environment assignment")
        return (
            "Set PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY outside Primr only after "
            "reviewing this record."
        )
    return "Leave PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY unset."


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _same_path(left: Path, right: Path) -> bool:
    return left.resolve(strict=False) == right.resolve(strict=False)
