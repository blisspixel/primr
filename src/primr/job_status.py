"""Versioned, transport-neutral job status snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA = "primr.job-status"
SCHEMA_VERSION = "1.0"

_STATE_ALIASES = {
    "idle": "idle",
    "pending": "queued",
    "queued": "queued",
    "accepted": "queued",
    "pending_approval": "pending_approval",
    "running": "in_progress",
    "in_progress": "in_progress",
    "requires_action": "requires_action",
    "cancel_requested": "cancel_requested",
    "cancellation_requested": "cancel_requested",
    "succeeded": "completed",
    "complete": "completed",
    "completed": "completed",
    "failed": "failed",
    "error": "failed",
    "expired": "failed",
    "canceled": "cancelled",
    "cancelled": "cancelled",
}


def normalize_lifecycle_state(status: object) -> str:
    """Map transport-specific states to the stable v1 lifecycle vocabulary."""
    value = str(getattr(status, "value", status) or "").strip().lower()
    if value == "check_error":
        return "unknown"
    return _STATE_ALIASES.get(value, "unknown")


def _rfc3339(value: object) -> str | None:
    if value is None:
        return None
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_job_status(
    *,
    job_id: object = None,
    source: str,
    status: object,
    company_name: object = None,
    mode: object = None,
    stage: object = None,
    percent: object = None,
    possibly_stuck: bool | None = None,
    submitted_at: object = None,
    started_at: object = None,
    updated_at: object = None,
    completed_at: object = None,
    artifacts_available: bool | None = None,
    error_message: object = None,
    error_code: object = None,
    error_source: object = None,
) -> dict[str, Any]:
    """Build an allowlisted v1 status snapshot with no report or path fields."""
    raw_status = str(getattr(status, "value", status) or "").strip().lower()
    message = str(error_message).strip()[:1000] if error_message else ""
    error = None
    if message:
        error = {
            "kind": "observation" if raw_status == "check_error" else "job",
            "code": str(error_code).strip()[:100] if error_code else None,
            "message": message,
            "source": str(error_source).strip()[:100] if error_source else None,
        }
    numeric_percent = percent if isinstance(percent, (int, float)) else None
    if numeric_percent is not None:
        numeric_percent = min(100, max(0, numeric_percent))
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "job_id": str(job_id) if job_id else None,
        "source": source,
        "lifecycle_state": normalize_lifecycle_state(raw_status),
        "company_name": str(company_name) if company_name else None,
        "mode": str(getattr(mode, "value", mode)) if mode else None,
        "progress": {
            "stage": str(getattr(stage, "value", stage)) if stage else None,
            "percent": numeric_percent,
            "possibly_stuck": possibly_stuck,
        },
        "timestamps": {
            "submitted_at": _rfc3339(submitted_at),
            "started_at": _rfc3339(started_at),
            "updated_at": _rfc3339(updated_at),
            "completed_at": _rfc3339(completed_at),
        },
        "artifacts_available": artifacts_available,
        "error": error,
    }


def build_job_status_list(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the v1 CLI collection envelope."""
    return {
        "schema": "primr.job-status-list",
        "schema_version": SCHEMA_VERSION,
        "jobs": jobs,
    }
