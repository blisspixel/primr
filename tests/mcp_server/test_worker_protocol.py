"""Tests for the bounded MCP worker JSONL protocol."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from primr.mcp_server.job_store import ResearchJobState
from primr.mcp_server.types import ResearchStage
from primr.mcp_server.worker_protocol import (
    MAX_LINE_BYTES,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    WorkerProtocolError,
    build_cancel_command,
    build_start_command,
    decode_message,
    encode_message,
    make_event,
    validate_cancel_command,
    validate_event,
    validate_start_command,
)


@pytest.fixture
def job_snapshot() -> dict:
    job = ResearchJobState(
        job_id="job-123",
        company_name="Acme Corp",
        mode="full",
        start_time=datetime(2026, 7, 11, tzinfo=timezone.utc),
        owner_client_id="stdio",
        current_stage=ResearchStage.ACCEPTED,
    )
    return job.to_journal_dict()


@pytest.fixture
def start_command(job_snapshot) -> dict:
    return build_start_command(
        job=job_snapshot,
        company_url="https://acme.example",
        mode="full",
        platform="aws",
        skip_qa=True,
        verify=True,
        destination="output/acme",
        budget_usd=2.5,
    )


def test_protocol_identity_is_stable():
    assert PROTOCOL_NAME == "primr.mcp.worker"
    assert PROTOCOL_VERSION == 1
    assert MAX_LINE_BYTES == 1024 * 1024


def test_encode_decode_round_trip_uses_jsonl(start_command):
    encoded = encode_message(start_command)

    assert encoded.endswith(b"\n")
    assert decode_message(encoded) == start_command


def test_encode_supports_utf8_without_ascii_expansion(start_command):
    start_command["job"]["company_name"] = "Société Exemple"

    encoded = encode_message(start_command)

    assert "Société Exemple" in encoded.decode("utf-8")


def test_encode_rejects_oversized_message():
    with pytest.raises(WorkerProtocolError, match="exceeds"):
        encode_message({"value": "x" * MAX_LINE_BYTES})


@pytest.mark.parametrize(
    "line,match",
    [
        (b"", "empty"),
        (b"{}", "newline"),
        (b"not-json\n", "valid JSON"),
        (b"[]\n", "object"),
        (b"\xff\n", "UTF-8"),
    ],
)
def test_decode_rejects_invalid_lines(line, match):
    with pytest.raises(WorkerProtocolError, match=match):
        decode_message(line)


def test_decode_rejects_oversized_line_before_parsing():
    with pytest.raises(WorkerProtocolError, match="exceeds"):
        decode_message(b"x" * (MAX_LINE_BYTES + 1))


def test_start_command_contains_only_bounded_execution_fields(start_command):
    assert set(start_command) == {
        "protocol",
        "version",
        "kind",
        "job_id",
        "job",
        "company_url",
        "mode",
        "platform",
        "skip_qa",
        "verify",
        "destination",
        "budget_usd",
    }
    assert not any("key" in field or "token" in field for field in start_command)
    assert start_command["platform"] == "aws"
    assert "platforms" not in start_command
    assert "strategy_type" not in start_command


def test_start_rejects_unknown_secret_field(start_command):
    start_command["api_key"] = "not-allowed"

    with pytest.raises(WorkerProtocolError, match="api_key"):
        validate_start_command(start_command)


def test_start_rejects_unknown_job_snapshot_field(start_command):
    start_command["job"]["approval_token"] = "not-allowed"

    with pytest.raises(WorkerProtocolError, match="approval_token"):
        validate_start_command(start_command)


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("stage_progress_percent", "bad", "stage_progress_percent"),
        ("stage_progress_percent", 101, "stage_progress_percent"),
        ("output_paths", "output/report.md", "output_paths"),
        ("output_paths", [""], "output_paths"),
        ("qa_score", True, "qa_score"),
        ("qa_score", 101, "qa_score"),
        ("actual_cost_usd", -0.01, "actual_cost_usd"),
        ("actual_cost_usd", float("nan"), "actual_cost_usd"),
        ("actual_cost_usd", True, "actual_cost_usd"),
        ("last_heartbeat_time", "tomorrow", "last_heartbeat_time"),
    ],
)
def test_start_rejects_malformed_job_snapshot_values(start_command, field, value, match):
    start_command["job"][field] = value

    with pytest.raises(WorkerProtocolError, match=match):
        validate_start_command(start_command)


def test_start_rejects_job_identity_or_mode_drift(start_command):
    start_command["job_id"] = "different"
    with pytest.raises(WorkerProtocolError, match="job_id"):
        validate_start_command(start_command)

    start_command["job_id"] = "job-123"
    start_command["mode"] = "deep"
    with pytest.raises(WorkerProtocolError, match="mode"):
        validate_start_command(start_command)


@pytest.mark.parametrize("field", ["skip_qa", "verify"])
def test_start_requires_real_booleans(start_command, field):
    start_command[field] = 1

    with pytest.raises(WorkerProtocolError, match=field):
        validate_start_command(start_command)


@pytest.mark.parametrize("budget", [-1, float("inf"), float("nan"), True, "2.5"])
def test_start_rejects_invalid_budget(start_command, budget):
    start_command["budget_usd"] = budget

    with pytest.raises(WorkerProtocolError, match="budget_usd"):
        validate_start_command(start_command)


def test_cancel_command_is_job_bound():
    command = build_cancel_command("job-123", reason="user_cancelled")

    assert validate_cancel_command(command, expected_job_id="job-123") == command
    with pytest.raises(WorkerProtocolError, match="different job"):
        validate_cancel_command(command, expected_job_id="job-456")


def test_ready_event_validates_exact_job_and_sequence():
    event = make_event(kind="ready", job_id="job-123", seq=1)

    assert validate_event(event, "job-123", 1) == event
    with pytest.raises(WorkerProtocolError, match="different job"):
        validate_event(event, "job-456", 1)
    with pytest.raises(WorkerProtocolError, match="sequence mismatch"):
        validate_event(event, "job-123", 2)


def test_state_and_terminal_events_reuse_job_journal(job_snapshot):
    state_event = make_event(kind="state", job_id="job-123", seq=2, state=job_snapshot)
    assert validate_event(state_event, "job-123", 2) == state_event

    job_snapshot["current_stage"] = "completed"
    terminal = make_event(
        kind="terminal",
        job_id="job-123",
        seq=3,
        state=job_snapshot,
        exit_reason="completed",
    )
    assert validate_event(terminal, "job-123", 3) == terminal


def test_terminal_event_requires_terminal_state(job_snapshot):
    with pytest.raises(WorkerProtocolError, match="not terminal"):
        make_event(
            kind="terminal",
            job_id="job-123",
            seq=1,
            state=job_snapshot,
            exit_reason="completed",
        )


def test_event_rejects_unknown_kind_or_field(job_snapshot):
    with pytest.raises(WorkerProtocolError, match="Unsupported worker event kind"):
        make_event(kind="log", job_id="job-123", seq=1)

    event = make_event(kind="state", job_id="job-123", seq=1, state=job_snapshot)
    event["api_key"] = "not-allowed"
    with pytest.raises(WorkerProtocolError, match="api_key"):
        validate_event(event, "job-123", 1)
