"""Body-free operator decision records for calibration baselines."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from primr.qa.artifact_fingerprints import artifact_fingerprint
from primr.qa.calibration_baseline import inspect_calibration_baseline, read_calibration_baseline

DECISION_RECORD_FORMAT = "primr.calibration_gate_decision_record.v1"
DECISION_INSPECTION_FORMAT = "primr.calibration_gate_decision_inspection.v1"
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


def read_operator_decision_record(path: Path) -> dict[str, Any]:
    """Read a body-free operator decision record from disk."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid operator decision record JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Operator decision record must be a JSON object")
    if payload.get("decision_format") != DECISION_RECORD_FORMAT:
        raise ValueError(
            f"Unsupported operator decision record format: {payload.get('decision_format')!r}"
        )
    return payload


def inspect_operator_decision_record(
    record: dict[str, Any],
    *,
    decision_path: Path | None = None,
    baseline: dict[str, Any] | None = None,
    baseline_path: Path | None = None,
) -> dict[str, Any]:
    """Return a body-free readback inspection for an operator decision record."""
    blockers: list[str] = []
    decision_format = record.get("decision_format")
    decision = str(record.get("decision") or "").strip()
    if decision_format != DECISION_RECORD_FORMAT:
        blockers.append("invalid_decision_record_format")
    if decision not in ALLOWED_DECISIONS:
        blockers.append("invalid_decision")
    if bool(record.get("applied")):
        blockers.append("record_claims_automatic_application")
    if bool(record.get("automatic_gate_arming_allowed")):
        blockers.append("record_allows_automatic_gate_arming")
    reviewer_present = _required_record_text_present(record, "reviewer", blockers)
    rationale_present = _required_record_text_present(record, "rationale", blockers)
    reviewed_at_present = _required_record_text_present(record, "reviewed_at_utc", blockers)
    manual_action_present = _required_record_text_present(
        record, "manual_action_required", blockers
    )

    recorded_baseline = _recorded_baseline(record)
    effective_baseline_path = baseline_path or _recorded_baseline_path(recorded_baseline)
    current_fingerprint = _current_fingerprint(effective_baseline_path, blockers)
    if baseline is None and effective_baseline_path is not None:
        baseline = _read_baseline_for_inspection(effective_baseline_path, blockers)

    baseline_section = _baseline_section(
        recorded_baseline=recorded_baseline,
        baseline_path=effective_baseline_path,
        current_fingerprint=current_fingerprint,
        blockers=blockers,
    )
    template_section = _template_section(
        baseline=baseline,
        baseline_path=effective_baseline_path,
        decision=decision,
        record=record,
        blockers=blockers,
    )
    status = _inspection_status(blockers)
    return {
        "inspection_format": DECISION_INSPECTION_FORMAT,
        "decision_path": str(decision_path) if decision_path is not None else None,
        "decision_format": decision_format,
        "decision": decision or None,
        "ready_to_trust": status == "current",
        "status": status,
        "applied": False,
        "automatic_gate_arming_allowed": False,
        "record": {
            "reviewed_at_present": reviewed_at_present,
            "reviewer_present": reviewer_present,
            "rationale_present": rationale_present,
            "notes_count": len(record.get("notes", []))
            if isinstance(record.get("notes"), list)
            else 0,
            "manual_action_present": manual_action_present,
            "env_assignment_present": bool(str(record.get("env_assignment") or "").strip()),
        },
        "baseline": baseline_section,
        "decision_template": template_section,
        "blockers": blockers,
        "policy": (
            "This inspection validates a recorded decision against body-free baseline "
            "metadata only. Primr did not set, export, or persist any environment variable."
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


def _recorded_baseline(record: dict[str, Any]) -> dict[str, Any]:
    baseline = record.get("baseline")
    return baseline if isinstance(baseline, dict) else {}


def _recorded_baseline_path(recorded_baseline: dict[str, Any]) -> Path | None:
    baseline_path = str(recorded_baseline.get("path") or "").strip()
    return Path(baseline_path) if baseline_path else None


def _current_fingerprint(
    baseline_path: Path | None,
    blockers: list[str],
) -> dict[str, Any] | None:
    if baseline_path is None:
        blockers.append("baseline_path_unavailable")
        return None
    fingerprint = artifact_fingerprint(baseline_path)
    if fingerprint.get("content_hash") is None or fingerprint.get("size_bytes") is None:
        blockers.append("baseline_unavailable")
        return None
    return fingerprint


def _read_baseline_for_inspection(
    baseline_path: Path,
    blockers: list[str],
) -> dict[str, Any] | None:
    try:
        return read_calibration_baseline(baseline_path)
    except (OSError, ValueError):
        if "baseline_unavailable" not in blockers:
            blockers.append("baseline_unavailable")
        return None


def _baseline_section(
    *,
    recorded_baseline: dict[str, Any],
    baseline_path: Path | None,
    current_fingerprint: dict[str, Any] | None,
    blockers: list[str],
) -> dict[str, Any]:
    recorded_hash = _recorded_content_hash(recorded_baseline, blockers)
    recorded_size = _recorded_size_bytes(recorded_baseline, blockers)
    current_hash = _optional_text(
        current_fingerprint.get("content_hash") if current_fingerprint else None
    )
    current_size = current_fingerprint.get("size_bytes") if current_fingerprint else None
    hash_matches = _matches(recorded_hash, current_hash, "baseline_content_hash_changed", blockers)
    size_matches = _matches(recorded_size, current_size, "baseline_size_changed", blockers)
    return {
        "path_present": baseline_path is not None,
        "recorded_content_hash_present": recorded_baseline.get("content_hash") is not None,
        "recorded_content_hash_valid": recorded_hash is not None,
        "current_content_hash": current_hash,
        "content_hash_matches": hash_matches,
        "recorded_size_bytes_present": recorded_baseline.get("size_bytes") is not None,
        "recorded_size_bytes_valid": recorded_size is not None,
        "current_size_bytes": current_size,
        "size_bytes_matches": size_matches,
    }


def _template_section(
    *,
    baseline: dict[str, Any] | None,
    baseline_path: Path | None,
    decision: str,
    record: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any] | None:
    if baseline is None:
        return None
    try:
        template = _decision_template(
            inspect_calibration_baseline(baseline, baseline_path=baseline_path)
        )
    except ValueError:
        blockers.append("decision_template_unavailable")
        return None
    allowed_decisions = [
        str(item) for item in template.get("allowed_decisions", []) if isinstance(item, str)
    ]
    if decision in ALLOWED_DECISIONS and decision not in allowed_decisions:
        blockers.append("decision_not_allowed_for_current_baseline")
    current_env_assignment = template.get("env_assignment") if decision == "arm_gate" else None
    if decision == "arm_gate" and record.get("env_assignment") != current_env_assignment:
        blockers.append("gate_assignment_changed")
    return {
        "template_format": template.get("template_format"),
        "decision_status": template.get("decision_status"),
        "recommended_decision": template.get("recommended_decision"),
        "recommended_workflow": template.get("recommended_workflow"),
        "allowed_decisions": allowed_decisions,
        "gate_status": template.get("gate_status"),
        "gate_reason": template.get("gate_reason"),
        "hard_gate_action": template.get("hard_gate_action"),
        "measurement_status": template.get("measurement_status"),
        "env_assignment": current_env_assignment,
        "evidence": template.get("evidence", {}),
    }


def _matches(
    recorded: Any,
    current: Any,
    blocker: str,
    blockers: list[str],
) -> bool:
    if recorded is None or current is None:
        return False
    matches = recorded == current
    if not matches:
        blockers.append(blocker)
    return matches


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _inspection_status(blockers: list[str]) -> str:
    if not blockers:
        return "current"
    if any(blocker.startswith(("invalid_", "missing_")) for blocker in blockers):
        return "invalid_record"
    if "record_claims_automatic_application" in blockers:
        return "unsafe_record"
    if "record_allows_automatic_gate_arming" in blockers:
        return "unsafe_record"
    if "baseline_unavailable" in blockers or "baseline_path_unavailable" in blockers:
        return "baseline_unavailable"
    if "decision_not_allowed_for_current_baseline" in blockers:
        return "decision_not_allowed"
    if any(blocker.endswith("_changed") for blocker in blockers):
        return "baseline_changed"
    return "not_current"


def _required_record_text_present(
    record: dict[str, Any],
    field: str,
    blockers: list[str],
) -> bool:
    present = bool(str(record.get(field) or "").strip())
    if not present:
        blockers.append(f"missing_{field}")
    return present


def _recorded_content_hash(
    recorded_baseline: dict[str, Any],
    blockers: list[str],
) -> str | None:
    value = _optional_text(recorded_baseline.get("content_hash"))
    if value is None:
        blockers.append("missing_baseline_content_hash")
        return None
    if not _valid_sha256(value):
        blockers.append("invalid_baseline_content_hash")
        return None
    return value


def _recorded_size_bytes(
    recorded_baseline: dict[str, Any],
    blockers: list[str],
) -> int | None:
    value = recorded_baseline.get("size_bytes")
    if value is None:
        blockers.append("missing_baseline_size_bytes")
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        blockers.append("invalid_baseline_size_bytes")
        return None
    return value


def _valid_sha256(value: str) -> bool:
    digest = value.removeprefix("sha256:")
    return (
        value.startswith("sha256:")
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest)
    )
