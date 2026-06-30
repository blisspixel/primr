"""Tests for MCP tool invocation audit logging."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import UUID

import pytest
from mcp.server.auth.provider import AccessToken
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    ReadResourceRequest,
    ReadResourceRequestParams,
)

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


async def _call(server, name: str, arguments: dict) -> dict:
    handler = server.server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=name, arguments=arguments),
        )
    )
    return json.loads(result.root.content[0].text)


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
async def test_recent_audit_resource_is_local_or_admin_only(server):
    await _call(server, "estimate_run", {"company_url": "https://example.com"})
    await _call(server, "doctor", {})

    local_data = await _read_resource(server, "primr://agent/audit/recent?limit=1")

    assert local_data["schema_version"] == "1.0"
    assert local_data["event_count"] == 1
    assert local_data["events"][0]["tool_name"] == "doctor"

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
