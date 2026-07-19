"""Tests for MCP tool invocation audit logging."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from mcp.server.auth.provider import AccessToken
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    ReadResourceRequest,
    ReadResourceRequestParams,
)

from primr.mcp_server import audit_log as audit_log_module
from primr.mcp_server.audit_log import _optional_float
from primr.mcp_server.auth import AuthContext
from primr.mcp_server.server import create_mcp_server


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        s = create_mcp_server(
            journal_path=str(root / "test_journal.json"),
            audit_log_path=str(root / "audit.jsonl"),
            skip_background_tasks=True,
        )
        s.rate_limiter.reset()
        yield s


def _context(scopes: list[str], client_id: str = "client-a") -> AuthContext:
    return AuthContext(
        AccessToken(
            token="test-token",
            client_id=client_id,
            scopes=scopes,
        )
    )


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", float("nan")])
def test_optional_float_rejects_non_finite_values(value) -> None:
    assert _optional_float(value) is None


async def _call_text(server, name: str, arguments: dict) -> str:
    handler = server.server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=name, arguments=arguments),
        )
    )
    return result.root.content[0].text


async def _call(server, name: str, arguments: dict) -> dict:
    return json.loads(await _call_text(server, name, arguments))


async def _read_resource(server, uri: str) -> dict:
    handler = server.server.request_handlers[ReadResourceRequest]
    result = await handler(
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri=uri),
        )
    )
    return json.loads(result.root.contents[0].text)


def _events(server) -> list[dict]:
    return [
        json.loads(line) for line in server.audit_log.path.read_text(encoding="utf-8").splitlines()
    ]


def _valid_event(**overrides) -> dict:
    event = {
        "schema_version": "1.0",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "request_id": "00000000-0000-4000-8000-000000000001",
        "timestamp": "2026-07-17T00:00:00Z",
        "event_type": "tool_call",
        "tool_name": "doctor",
        "status": "success",
        "transport": "stdio",
        "duration_ms": 1,
        "actor": "stdio",
        "client_id_hash": None,
        "authenticated": False,
        "auth_scopes": [],
        "args_hash": "sha256:" + "0" * 64,
    }
    event.update(overrides)
    return event


def _append_valid_event(server) -> None:
    server.audit_log._append(
        audit_log_module.MCPAuditEvent(
            schema_version="1.0",
            event_id="00000000-0000-4000-8000-000000000001",
            request_id="00000000-0000-4000-8000-000000000001",
            timestamp="2026-07-17T00:00:00Z",
            transport="stdio",
            tool_name="doctor",
            status="success",
            duration_ms=1,
            actor="stdio",
            client_id_hash=None,
            authenticated=False,
            auth_scopes=[],
            args_hash="sha256:" + "0" * 64,
        )
    )


def _assert_otel_projection(event: dict, *, expected_name: str) -> None:
    UUID(event["request_id"])
    assert event["event_id"] == event["request_id"]
    span = event["otel_span"]
    assert span["name"] == expected_name
    attrs = span["attributes"]
    assert attrs["primr.request_id"] == event["request_id"]
    assert attrs["primr.event_type"] == event["event_type"]
    assert attrs["primr.transport"] == event["transport"]
    assert attrs["primr.tool_name"] == event["tool_name"]
    assert attrs["primr.status"] == event["status"]
    assert attrs["primr.duration_ms"] == event["duration_ms"]


@pytest.mark.asyncio
async def test_successful_tool_call_writes_hashed_audit_event(server):
    data = await _call(
        server,
        "estimate_run",
        {"company_url": "https://example.com/private?token=secret", "mode": "full"},
    )

    audit_text = server.audit_log.path.read_text(encoding="utf-8")
    assert "example.com" not in audit_text
    assert "private" not in audit_text
    assert data["approval_token"] not in audit_text

    event = _events(server)[0]
    assert event["tool_name"] == "estimate_run"
    assert event["status"] == "success"
    assert event["actor"] == "stdio"
    assert event["args_hash"].startswith("sha256:")
    assert event["result_hash"].startswith("sha256:")
    assert event["approval_token_id"] == data["approval_token_id"]
    assert event["estimated_cost_usd"] == data["estimated_cost_usd"]
    _assert_otel_projection(event, expected_name="primr.stdio.tool_call.estimate_run")
    assert event["otel_span"]["attributes"]["primr.approval_token_id"] == data["approval_token_id"]
    assert (
        event["otel_span"]["attributes"]["primr.estimated_cost_usd"] == data["estimated_cost_usd"]
    )


@pytest.mark.asyncio
async def test_cost_cap_approval_failure_is_audited(server, monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")

    data = await _call(
        server,
        "research_company",
        {
            "company_name": "Acme Corp",
            "company_url": "https://example.com",
            "max_estimated_cost_usd": 100.0,
        },
    )

    assert data["error"] is True
    event = _events(server)[0]
    assert event["tool_name"] == "research_company"
    assert event["status"] == "error"
    assert event["error_type"] == "approval_token_required"
    assert event["max_estimated_cost_usd"] == 100.0


@pytest.mark.asyncio
async def test_scope_denial_is_audited_without_raw_client_id(server):
    server._auth_context = _context(["read"], client_id="sensitive-client")

    data = await _call(
        server,
        "research_company",
        {"company_name": "Acme Corp", "company_url": "https://example.com"},
    )

    assert data["error"] is True
    event = _events(server)[0]
    audit_text = server.audit_log.path.read_text(encoding="utf-8")
    assert "sensitive-client" not in audit_text
    assert event["status"] == "scope_denied"
    assert event["error_type"] == "insufficient_scope"
    assert event["actor"] is None
    assert event["client_id_hash"].startswith("sha256:")
    assert event["auth_scopes"] == ["read"]


@pytest.mark.asyncio
async def test_caller_controlled_audit_metadata_is_normalized_and_bounded(server):
    marker = "private-marker-in-protocol-metadata"
    server._auth_context = _context(["read", marker + "x" * (1024 * 1024)])

    await _call_text(server, marker, {})
    with pytest.raises(ValueError, match="Unknown resource"):
        await _read_resource(server, f"primr://unexpected/{marker}")

    audit_text = server.audit_log.path.read_text(encoding="utf-8")
    assert marker not in audit_text
    assert server.audit_log.path.stat().st_size < 16 * 1024
    events = _events(server)
    assert events[0]["tool_name"] == "unknown_tool"
    assert events[0]["auth_scopes"] == ["read", "unknown"]
    assert events[1]["resource_kind"] == "unknown_resource"
    assert events[1]["resource_uri_hash"].startswith("sha256:")


@pytest.mark.asyncio
async def test_unknown_tool_names_share_one_rate_limit_bucket(server):
    responses = [await _call_text(server, f"unknown-{index}", {}) for index in range(11)]

    assert json.loads(responses[-1])["error_type"] == "rate_limit_exceeded"
    assert {event["tool_name"] for event in _events(server)} == {"unknown_tool"}


@pytest.mark.asyncio
async def test_successful_resource_read_writes_hashed_audit_event(server):
    await _read_resource(
        server,
        "primr://research/status?company_url=https://example.com/private&token=secret",
    )

    audit_text = server.audit_log.path.read_text(encoding="utf-8")
    assert "example.com" not in audit_text
    assert "private" not in audit_text
    assert "secret" not in audit_text

    event = _events(server)[0]
    assert event["event_type"] == "resource_read"
    assert event["tool_name"] == "resources/read"
    assert event["resource_kind"] == "primr://research/status"
    assert event["resource_uri_hash"].startswith("sha256:")
    assert event["status"] == "success"
    assert event["actor"] == "stdio"
    assert event["args_hash"].startswith("sha256:")
    assert event["result_hash"].startswith("sha256:")
    _assert_otel_projection(event, expected_name="primr.stdio.resource_read.resources.read")
    assert event["otel_span"]["attributes"]["primr.resource_kind"] == "primr://research/status"


@pytest.mark.asyncio
async def test_resource_scope_denial_is_audited_without_raw_client_id(server):
    server._auth_context = _context(["read"], client_id="sensitive-client")

    data = await _read_resource(server, "primr://agent/audit/recent")

    assert data["error"] == "insufficient_scope"
    event = _events(server)[0]
    audit_text = server.audit_log.path.read_text(encoding="utf-8")
    assert "sensitive-client" not in audit_text
    assert event["event_type"] == "resource_read"
    assert event["status"] == "scope_denied"
    assert event["error_type"] == "insufficient_scope"
    assert event["client_id_hash"].startswith("sha256:")
    assert event["auth_scopes"] == ["read"]


@pytest.mark.asyncio
async def test_http_subject_named_stdio_gets_no_local_audit_access(server):
    server.transport = "streamable-http"
    server._auth_context = _context(["read"], client_id="stdio")

    data = await _read_resource(server, "primr://agent/audit/recent")

    assert data["error"] == "insufficient_scope"
    event = _events(server)[0]
    assert event["actor"] is None
    assert event["client_id_hash"].startswith("sha256:")


@pytest.mark.asyncio
async def test_recent_audit_resource_is_local_or_admin_only(server):
    await _call(server, "estimate_run", {"company_url": "https://example.com"})
    await _call(server, "doctor", {})

    local_data = await _read_resource(server, "primr://agent/audit/recent?limit=1")

    assert local_data["schema_version"] == "1.0"
    assert local_data["event_count"] == 1
    assert local_data["events"][0]["tool_name"] == "doctor"
    assert local_data["audit_sink"]["status"] == "ok"

    server._auth_context = _context(["read"])
    denied = await _read_resource(server, "primr://agent/audit/recent")
    assert denied["error"] == "insufficient_scope"
    assert denied["required_scopes"] == ["admin"]

    server._auth_context = _context(["admin"])
    admin_data = await _read_resource(server, "primr://agent/audit/recent?limit=10")
    assert admin_data["event_count"] >= 4
    event_types = [event["event_type"] for event in admin_data["events"]]
    assert "tool_call" in event_types
    assert "resource_read" in event_types
    assert any(event["status"] == "scope_denied" for event in admin_data["events"])


@pytest.mark.asyncio
async def test_doctor_surfaces_audit_write_failure_and_recovery(server, tmp_path):
    blocked = tmp_path / "blocked-audit"
    blocked.mkdir()
    server.audit_log.path = blocked

    await _call(server, "estimate_run", {"company_url": "https://example.com"})
    degraded = await _call(server, "doctor", {})

    assert degraded["audit_log"]["status"] == "degraded"
    assert degraded["audit_log"]["last_write_succeeded"] is False
    assert degraded["audit_log"]["consecutive_write_failures"] >= 1
    assert degraded["status"] == "degraded"
    serialized = json.dumps(degraded)
    assert str(blocked) not in serialized
    assert "example.com" not in serialized

    server.audit_log.path = tmp_path / "recovered-audit.jsonl"
    await _call(server, "estimate_run", {"company_url": "https://example.com"})
    recovered = await _call(server, "doctor", {})

    assert recovered["audit_log"]["status"] == "ok"
    assert recovered["audit_log"]["last_write_succeeded"] is True
    assert recovered["audit_log"]["consecutive_write_failures"] == 0


def test_unreadable_audit_sink_is_degraded(server, tmp_path):
    unreadable = tmp_path / "audit-directory"
    unreadable.mkdir()
    server.audit_log.path = unreadable

    assert server.audit_log.recent(limit=10) == []

    health = server.audit_log.health_snapshot()
    assert health["status"] == "degraded"
    assert health["last_read_succeeded"] is False
    assert (
        health["last_read_error_type"] == "PermissionError"
        or health["last_read_error_type"] == "IsADirectoryError"
        or health["last_read_error_type"] == "_UnsafeAuditSinkError"
    )
    assert str(unreadable) not in json.dumps(health)


def test_preflight_opens_and_reads_the_actual_empty_sink(server):
    assert not server.audit_log.path.exists()

    assert server.audit_log.preflight() is True

    assert server.audit_log.path.read_bytes() == b""
    assert server.audit_log.health_snapshot()["status"] == "ok"


def test_preflight_rejects_a_hard_linked_sink(server, tmp_path):
    target = tmp_path / "shared-audit.jsonl"
    original = b"do-not-modify\n"
    target.write_bytes(original)
    link = tmp_path / "audit-hardlink.jsonl"
    try:
        link.hardlink_to(target)
    except OSError:
        pytest.skip("hard links are unavailable")
    server.audit_log.path = link

    assert server.audit_log.preflight() is False

    assert target.read_bytes() == original
    assert server.audit_log.health_snapshot()["status"] == "degraded"


def test_missing_sink_after_success_is_degraded(server):
    server.audit_log.path.parent.mkdir(parents=True, exist_ok=True)
    event = _valid_event()
    server.audit_log.path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    expected = audit_log_module._project_safe_audit_event(event)
    assert server.audit_log.recent(limit=1) == [expected]
    server.audit_log._record_write_result(succeeded=True)
    server.audit_log.path.unlink()

    assert server.audit_log.recent(limit=1) == []

    health = server.audit_log.health_snapshot()
    assert health["status"] == "degraded"
    assert health["file_observed"] is False


def test_health_snapshot_detects_external_deletion_without_recent_read(server):
    _append_valid_event(server)
    server.audit_log.path.unlink()

    health = server.audit_log.health_snapshot()
    assert health["status"] == "degraded"
    assert health["file_observed"] is False


def test_health_snapshot_metadata_probe_failure_is_degraded(server):
    _append_valid_event(server)

    with patch.object(Path, "lstat", side_effect=PermissionError("blocked")):
        health = server.audit_log.health_snapshot()

    assert health["status"] == "degraded"
    assert health["file_observed"] is False
    assert health["read_attempted"] is True
    assert health["last_read_succeeded"] is False
    assert health["last_read_error_type"] == "PermissionError"
    assert "blocked" not in json.dumps(health)


def test_recent_never_follows_audit_symlink(server, tmp_path):
    target = tmp_path / "private-target.jsonl"
    target.write_text(json.dumps(_valid_event()) + "\n", encoding="utf-8")
    link = tmp_path / "audit-link.jsonl"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks are unavailable")
    server.audit_log.path = link

    assert server.audit_log.recent(limit=10) == []
    assert server.audit_log.health_snapshot()["status"] == "degraded"


def test_append_never_follows_or_modifies_audit_symlink(server, tmp_path):
    target = tmp_path / "private-target.jsonl"
    original = b"do-not-modify\n"
    target.write_bytes(original)
    link = tmp_path / "audit-link.jsonl"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks are unavailable")
    server.audit_log.path = link

    with pytest.raises(audit_log_module._UnsafeAuditSinkError):
        _append_valid_event(server)

    assert target.read_bytes() == original
    health = server.audit_log.health_snapshot()
    assert health["status"] == "degraded"
    assert health["last_write_succeeded"] is False


def test_health_snapshot_detects_external_truncation(server):
    _append_valid_event(server)
    server.audit_log.path.write_text("", encoding="utf-8")

    health = server.audit_log.health_snapshot()

    assert health["status"] == "degraded"
    assert health["file_truncated_after_successful_write"] is True
    assert health["file_replaced_after_successful_write"] is False


def test_health_snapshot_detects_external_replacement(server, tmp_path):
    _append_valid_event(server)
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_text(json.dumps(_valid_event()) + "\n", encoding="utf-8")
    replacement.replace(server.audit_log.path)

    health = server.audit_log.health_snapshot()

    assert health["status"] == "degraded"
    assert health["file_replaced_after_successful_write"] is True


def test_replaced_sink_cannot_be_laundered_by_a_later_append(server, tmp_path):
    _append_valid_event(server)
    pinned_identity = server.audit_log._last_write_identity
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_text(json.dumps(_valid_event()) + "\n", encoding="utf-8")
    replacement.replace(server.audit_log.path)

    with pytest.raises(audit_log_module._UnsafeAuditSinkError, match="continuity"):
        _append_valid_event(server)

    assert server.audit_log._last_write_identity == pinned_identity
    assert server.audit_log.health_snapshot()["status"] == "degraded"


def test_truncated_sink_cannot_be_laundered_by_a_later_append(server):
    _append_valid_event(server)
    pinned_size = server.audit_log._last_write_size
    server.audit_log.path.write_text("", encoding="utf-8")

    with pytest.raises(audit_log_module._UnsafeAuditSinkError, match="continuity"):
        _append_valid_event(server)

    assert server.audit_log._last_write_size == pinned_size
    assert server.audit_log.health_snapshot()["status"] == "degraded"


def test_encoded_event_size_limit_marks_sink_degraded(server, monkeypatch):
    monkeypatch.setattr(audit_log_module, "_MAX_AUDIT_EVENT_BYTES", 64)

    server.audit_log.record_tool_call(
        tool_name="doctor",
        arguments={},
        result=None,
        auth_context=None,
        client_id="stdio",
        transport="stdio",
        started_at=0,
    )

    health = server.audit_log.health_snapshot()
    assert health["status"] == "degraded"
    assert health["last_write_succeeded"] is False
    assert health["last_write_error_type"] == "ValueError"


def test_missing_never_written_sink_is_not_observed(server):
    assert server.audit_log.recent(limit=1) == []

    health = server.audit_log.health_snapshot()
    assert health["status"] == "not_observed"
    assert health["read_attempted"] is True
    assert health["file_observed"] is False


def test_malformed_complete_event_is_counted_without_exposing_content(server):
    valid_event = _valid_event()
    server.audit_log.path.write_text(
        json.dumps(valid_event) + "\n" + "malformed secret event\n",
        encoding="utf-8",
    )

    events = server.audit_log.recent(limit=10)
    health = server.audit_log.health_snapshot()

    assert events == [audit_log_module._project_safe_audit_event(valid_event)]
    assert health["status"] == "degraded"
    assert health["malformed_event_count"] == 1
    assert "malformed secret event" not in json.dumps(health)


def test_recent_read_uses_bounded_tail(server, monkeypatch):
    monkeypatch.setattr(audit_log_module, "_MAX_RECENT_READ_BYTES", 512)
    oversized_prefix = json.dumps({"padding": "x" * 1024}) + "\n"
    final_event = _valid_event(event_id="event-final")
    server.audit_log.path.write_text(
        oversized_prefix + json.dumps(final_event) + "\n",
        encoding="utf-8",
    )

    expected = audit_log_module._project_safe_audit_event(final_event)
    assert server.audit_log.recent(limit=1) == [expected]
    health = server.audit_log.health_snapshot()
    assert health["status"] == "ok"
    assert health["read_truncated"] is True
    assert health["malformed_event_count"] == 0


def test_schema_invalid_json_object_is_not_returned(server):
    server.audit_log.path.write_text(
        json.dumps({"secret": "private audit body"}) + "\n",
        encoding="utf-8",
    )

    assert server.audit_log.recent(limit=10) == []
    health = server.audit_log.health_snapshot()
    assert health["status"] == "degraded"
    assert health["malformed_event_count"] == 1
    assert "private audit body" not in json.dumps(health)


def test_safe_projection_drops_additive_and_unsafe_fields(server):
    marker = "private-historical-field-marker"
    event = _valid_event(raw_secret=marker, job_id=marker)
    server.audit_log.path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    events = server.audit_log.recent(limit=10)

    assert len(events) == 1
    assert "raw_secret" not in events[0]
    assert marker not in json.dumps(events)
    assert events[0]["job_id"].startswith("sha256:")


def test_oversized_complete_event_is_not_returned(server):
    event = _valid_event(raw_secret="x" * (audit_log_module._MAX_AUDIT_EVENT_BYTES + 1))
    server.audit_log.path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    assert server.audit_log.recent(limit=10) == []
    health = server.audit_log.health_snapshot()
    assert health["status"] == "degraded"
    assert health["malformed_event_count"] == 1


def test_oversized_incomplete_tail_is_degraded(server, monkeypatch):
    monkeypatch.setattr(audit_log_module, "_MAX_RECENT_READ_BYTES", 128)
    server.audit_log.path.write_text(
        json.dumps({"padding": "private-marker-" + "x" * 1024}),
        encoding="utf-8",
    )

    assert server.audit_log.recent(limit=10) == []
    health = server.audit_log.health_snapshot()
    assert health["status"] == "degraded"
    assert health["read_truncated"] is True
    assert health["incomplete_tail"] is True
    assert "private-marker" not in json.dumps(health)


def test_deep_malformed_json_is_counted_without_escaping(server):
    nested = "[" * 2_000 + "]" * 2_000
    server.audit_log.path.write_text(nested + "\n", encoding="utf-8")

    assert server.audit_log.recent(limit=10) == []
    health = server.audit_log.health_snapshot()
    assert health["status"] == "degraded"
    assert health["malformed_event_count"] == 1
