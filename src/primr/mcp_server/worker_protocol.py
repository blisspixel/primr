"""Versioned JSONL protocol for supervised MCP research workers.

The protocol is intentionally small. A parent sends one ``start`` command,
may later send one ``cancel`` command, and receives ``ready``, ``state``, and
``terminal`` events. Pipeline logs never belong on this channel.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, BinaryIO

PROTOCOL_NAME = "primr.mcp.worker"
PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 1024 * 1024

START_KIND = "start"
CANCEL_KIND = "cancel"
EVENT_KINDS = frozenset({"ready", "state", "terminal"})
TERMINAL_STAGES = frozenset({"completed", "failed", "cancelled"})
_RESEARCH_STAGES = frozenset(
    {
        "idle",
        "accepted",
        "scraping",
        "extracting",
        "deep_research",
        "writing",
        "qa",
        *TERMINAL_STAGES,
    }
)

_BASE_FIELDS = frozenset({"protocol", "version", "kind", "job_id"})
_START_FIELDS = _BASE_FIELDS | {
    "job",
    "company_url",
    "mode",
    "platform",
    "skip_qa",
    "verify",
    "destination",
    "budget_usd",
}
_CANCEL_FIELDS = _BASE_FIELDS | {"reason"}
_EVENT_FIELDS = _BASE_FIELDS | {"seq", "ts", "state", "exit_reason"}
_JOB_JOURNAL_FIELDS = frozenset(
    {
        "job_id",
        "company_name",
        "mode",
        "start_time",
        "owner_client_id",
        "current_stage",
        "stage_progress_percent",
        "stage_started_at",
        "last_heartbeat_time",
        "completion_time",
        "output_paths",
        "error_type",
        "error_message",
        "deep_research_job_id",
        "qa_score",
        "actual_cost_usd",
        "governance_audit",
    }
)
_MODES = frozenset({"scrape", "deep", "full", "premium"})


class WorkerProtocolError(ValueError):
    """Raised when a worker protocol message is malformed or unexpected."""


def encode_message(message: dict[str, Any]) -> bytes:
    """Encode one protocol message as bounded UTF-8 JSONL."""
    if not isinstance(message, dict):
        raise WorkerProtocolError("Protocol message must be an object")
    try:
        encoded = (
            json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WorkerProtocolError("Protocol message is not JSON serializable") from exc
    if len(encoded) > MAX_LINE_BYTES:
        raise WorkerProtocolError(f"Protocol message exceeds the {MAX_LINE_BYTES}-byte line limit")
    return encoded


def decode_message(line: bytes) -> dict[str, Any]:
    """Decode one bounded UTF-8 JSONL protocol message."""
    if not isinstance(line, bytes):
        raise WorkerProtocolError("Protocol line must be bytes")
    if not line:
        raise WorkerProtocolError("Protocol line is empty")
    if len(line) > MAX_LINE_BYTES:
        raise WorkerProtocolError(f"Protocol line exceeds the {MAX_LINE_BYTES}-byte limit")
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkerProtocolError("Protocol line is not valid UTF-8") from exc
    if not text.endswith("\n"):
        raise WorkerProtocolError("Protocol line must end with a newline")
    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorkerProtocolError("Protocol line is not valid JSON") from exc
    if not isinstance(message, dict):
        raise WorkerProtocolError("Protocol message must be an object")
    return message


def build_start_command(
    *,
    job: dict[str, Any],
    company_url: str,
    mode: str,
    platform: str | None = None,
    skip_qa: bool = False,
    verify: bool = False,
    destination: str | None = None,
    budget_usd: float | None = None,
) -> dict[str, Any]:
    """Build and validate the only command that may start a worker."""
    job_id = job.get("job_id") if isinstance(job, dict) else None
    command = {
        "protocol": PROTOCOL_NAME,
        "version": PROTOCOL_VERSION,
        "kind": START_KIND,
        "job_id": job_id,
        "job": job,
        "company_url": company_url,
        "mode": mode,
        "platform": platform,
        "skip_qa": skip_qa,
        "verify": verify,
        "destination": destination,
        "budget_usd": budget_usd,
    }
    return validate_start_command(command)


def build_cancel_command(job_id: str, *, reason: str = "user_cancelled") -> dict[str, Any]:
    """Build and validate a cooperative cancellation command."""
    command = {
        "protocol": PROTOCOL_NAME,
        "version": PROTOCOL_VERSION,
        "kind": CANCEL_KIND,
        "job_id": job_id,
        "reason": reason,
    }
    return validate_cancel_command(command, expected_job_id=job_id)


def validate_start_command(command: dict[str, Any]) -> dict[str, Any]:
    """Validate a start command and return a shallow normalized copy."""
    _validate_envelope(command, expected_kind=START_KIND, allowed_fields=_START_FIELDS)

    job = command.get("job")
    if not isinstance(job, dict):
        raise WorkerProtocolError("Start command job must be an object")
    validate_job_snapshot(job, label="job snapshot")

    job_id = _required_string(command, "job_id")
    if job.get("job_id") != job_id:
        raise WorkerProtocolError("Start command job_id does not match the job snapshot")

    company_url = _required_string(command, "company_url")
    if not company_url.strip():
        raise WorkerProtocolError("Start command company_url must not be blank")

    mode = _required_string(command, "mode")
    if mode not in _MODES:
        raise WorkerProtocolError(f"Unsupported worker mode: {mode}")
    if job.get("mode") != mode:
        raise WorkerProtocolError("Start command mode does not match the job snapshot")

    _optional_string(command, "platform")
    _optional_string(command, "destination")
    for field_name in ("skip_qa", "verify"):
        if not isinstance(command.get(field_name), bool):
            raise WorkerProtocolError(f"Start command {field_name} must be a boolean")

    budget = command.get("budget_usd")
    if budget is not None:
        if isinstance(budget, bool) or not isinstance(budget, (int, float)):
            raise WorkerProtocolError("Start command budget_usd must be a finite number or null")
        if not math.isfinite(float(budget)) or float(budget) < 0:
            raise WorkerProtocolError("Start command budget_usd must be finite and non-negative")

    return dict(command)


def validate_cancel_command(
    command: dict[str, Any],
    *,
    expected_job_id: str,
) -> dict[str, Any]:
    """Validate a cancel command for one known worker job."""
    _validate_envelope(command, expected_kind=CANCEL_KIND, allowed_fields=_CANCEL_FIELDS)
    if command.get("job_id") != expected_job_id:
        raise WorkerProtocolError("Cancel command targets a different job")
    reason = _required_string(command, "reason")
    if len(reason) > 128:
        raise WorkerProtocolError("Cancel command reason is too long")
    return dict(command)


def validate_event(
    event: dict[str, Any],
    expected_job_id: str,
    expected_seq: int,
) -> dict[str, Any]:
    """Strictly validate one child event for job identity and sequence."""
    if not isinstance(expected_seq, int) or isinstance(expected_seq, bool) or expected_seq < 1:
        raise WorkerProtocolError("Expected sequence must be a positive integer")
    _validate_envelope(
        event,
        allowed_fields=_EVENT_FIELDS,
        required_fields=_BASE_FIELDS | {"seq", "ts"},
    )

    kind = event.get("kind")
    if kind not in EVENT_KINDS:
        raise WorkerProtocolError(f"Unsupported worker event kind: {kind}")
    if event.get("job_id") != expected_job_id:
        raise WorkerProtocolError("Worker event targets a different job")

    sequence = event.get("seq")
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise WorkerProtocolError("Worker event seq must be an integer")
    if sequence != expected_seq:
        raise WorkerProtocolError(
            f"Worker event sequence mismatch: expected {expected_seq}, received {sequence}"
        )

    timestamp = _required_string(event, "ts")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkerProtocolError("Worker event ts must be an ISO-8601 timestamp") from exc
    if parsed_timestamp.tzinfo is None:
        raise WorkerProtocolError("Worker event ts must include a timezone")

    state = event.get("state")
    exit_reason = event.get("exit_reason")
    if kind == "ready":
        if state is not None or exit_reason is not None:
            raise WorkerProtocolError("Ready events cannot contain state or exit_reason")
    else:
        if not isinstance(state, dict):
            raise WorkerProtocolError(f"{kind.capitalize()} events require a state object")
        validate_job_snapshot(state, label="worker state")
        if state.get("job_id") != expected_job_id:
            raise WorkerProtocolError("Worker state job_id does not match its event")
        if kind == "state" and exit_reason is not None:
            raise WorkerProtocolError("State events cannot contain exit_reason")
        if kind == "terminal":
            if state.get("current_stage") not in TERMINAL_STAGES:
                raise WorkerProtocolError("Terminal event state is not terminal")
            _required_string(event, "exit_reason")

    return dict(event)


def read_message(stream: BinaryIO) -> dict[str, Any]:
    """Read one bounded message without allowing an unbounded ``readline``."""
    line = stream.readline(MAX_LINE_BYTES + 1)
    return decode_message(line)


def make_event(
    *,
    kind: str,
    job_id: str,
    seq: int,
    state: dict[str, Any] | None = None,
    exit_reason: str | None = None,
) -> dict[str, Any]:
    """Build a worker event. Callers still validate it before consumption."""
    event: dict[str, Any] = {
        "protocol": PROTOCOL_NAME,
        "version": PROTOCOL_VERSION,
        "kind": kind,
        "job_id": job_id,
        "seq": seq,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if state is not None:
        event["state"] = state
    if exit_reason is not None:
        event["exit_reason"] = exit_reason
    return validate_event(event, expected_job_id=job_id, expected_seq=seq)


def _validate_envelope(
    message: dict[str, Any],
    *,
    expected_kind: str | None = None,
    allowed_fields: frozenset[str] | set[str],
    required_fields: frozenset[str] | set[str] | None = None,
) -> None:
    if not isinstance(message, dict):
        raise WorkerProtocolError("Protocol message must be an object")
    _validate_exact_fields(
        message,
        allowed_fields,
        label="protocol message",
        required_fields=required_fields,
    )
    if message.get("protocol") != PROTOCOL_NAME:
        raise WorkerProtocolError("Unsupported worker protocol")
    version = message.get("version")
    if isinstance(version, bool) or version != PROTOCOL_VERSION:
        raise WorkerProtocolError("Unsupported worker protocol version")
    if expected_kind is not None and message.get("kind") != expected_kind:
        raise WorkerProtocolError(f"Expected a {expected_kind} command")
    _required_string(message, "job_id")


def _validate_exact_fields(
    value: dict[str, Any],
    allowed_fields: frozenset[str] | set[str],
    *,
    label: str,
    required_fields: frozenset[str] | set[str] | None = None,
) -> None:
    unexpected = set(value) - set(allowed_fields)
    if unexpected:
        names = ", ".join(sorted(unexpected))
        raise WorkerProtocolError(f"Unexpected {label} field(s): {names}")
    required = set(allowed_fields) if required_fields is None else set(required_fields)
    missing = required - set(value)
    if missing:
        names = ", ".join(sorted(missing))
        raise WorkerProtocolError(f"Missing {label} field(s): {names}")


def validate_job_snapshot(snapshot: dict[str, Any], *, label: str = "job snapshot") -> None:
    """Validate the complete serialized job schema at the trust boundary."""
    _validate_exact_fields(snapshot, _JOB_JOURNAL_FIELDS, label=label)
    for field_name in ("job_id", "company_name", "mode", "start_time", "current_stage"):
        _required_string(snapshot, field_name)
    if snapshot["mode"] not in _MODES:
        raise WorkerProtocolError(f"{label} mode is unsupported")
    if snapshot["current_stage"] not in _RESEARCH_STAGES:
        raise WorkerProtocolError(f"{label} current_stage is unsupported")

    owner = snapshot.get("owner_client_id")
    if owner is not None and (not isinstance(owner, str) or not owner):
        raise WorkerProtocolError(f"{label} owner_client_id must be a non-empty string or null")

    progress = snapshot.get("stage_progress_percent")
    if isinstance(progress, bool) or not isinstance(progress, int) or not 0 <= progress <= 100:
        raise WorkerProtocolError(
            f"{label} stage_progress_percent must be an integer from 0 to 100"
        )

    for field_name in (
        "start_time",
        "stage_started_at",
        "last_heartbeat_time",
        "completion_time",
    ):
        _optional_timestamp(snapshot, field_name, required=field_name == "start_time")

    paths = snapshot.get("output_paths")
    if not isinstance(paths, list) or any(not isinstance(path, str) or not path for path in paths):
        raise WorkerProtocolError(f"{label} output_paths must be a list of non-empty strings")

    for field_name in ("error_type", "error_message", "deep_research_job_id"):
        field_value = snapshot.get(field_name)
        if field_value is not None and not isinstance(field_value, str):
            raise WorkerProtocolError(f"{label} {field_name} must be a string or null")

    score = snapshot.get("qa_score")
    if score is not None and (
        isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100
    ):
        raise WorkerProtocolError(f"{label} qa_score must be an integer from 0 to 100 or null")

    actual_cost = snapshot.get("actual_cost_usd")
    if actual_cost is not None and (
        isinstance(actual_cost, bool)
        or not isinstance(actual_cost, int | float)
        or not math.isfinite(float(actual_cost))
        or actual_cost < 0
    ):
        raise WorkerProtocolError(
            f"{label} actual_cost_usd must be a finite non-negative number or null"
        )

    audit = snapshot.get("governance_audit")
    if audit is not None and not isinstance(audit, dict):
        raise WorkerProtocolError(f"{label} governance_audit must be an object or null")


def _optional_timestamp(value: dict[str, Any], field_name: str, *, required: bool = False) -> None:
    field_value = value.get(field_name)
    if field_value is None and not required:
        return
    if not isinstance(field_value, str) or not field_value:
        raise WorkerProtocolError(f"Protocol field {field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(field_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkerProtocolError(
            f"Protocol field {field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise WorkerProtocolError(f"Protocol field {field_name} must include a timezone")


def _required_string(value: dict[str, Any], field_name: str) -> str:
    field_value = value.get(field_name)
    if not isinstance(field_value, str) or not field_value:
        raise WorkerProtocolError(f"Protocol field {field_name} must be a non-empty string")
    return field_value


def _optional_string(value: dict[str, Any], field_name: str) -> str | None:
    field_value = value.get(field_name)
    if field_value is not None and not isinstance(field_value, str):
        raise WorkerProtocolError(f"Protocol field {field_name} must be a string or null")
    return field_value
