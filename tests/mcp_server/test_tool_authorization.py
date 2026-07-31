"""Tests for MCP per-tool scope authorization."""

import json
import tempfile
from pathlib import Path

import pytest
from mcp.server.auth.provider import AccessToken

from primr.mcp_server.auth import AuthContext
from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.tool_authz import ADMIN_SCOPE, REPORT_SCOPE, scope_granted
from tests.mcp_server.sdk_compat import call_tool_handler


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
        s.rate_limiter.reset()
        yield s


def _context(scopes: list[str], client_id: str = "test-client") -> AuthContext:
    return AuthContext(
        AccessToken(
            token="test-token",
            client_id=client_id,
            scopes=scopes,
        )
    )


async def _call(server, name: str, arguments: dict) -> dict:
    result = await call_tool_handler(server, name, arguments)
    return json.loads(result.content[0].text)


class TestToolScopeAuthorization:
    @pytest.mark.asyncio
    async def test_read_scope_can_call_read_tool(self, server):
        server._auth_context = _context(["read"])

        data = await _call(
            server,
            "estimate_run",
            {"company_url": "https://example.com", "mode": "full"},
        )

        assert "estimated_cost_usd" in data
        assert data["mode"] == "full"

    @pytest.mark.asyncio
    async def test_read_scope_cannot_start_research(self, server):
        server._auth_context = _context(["read"])

        data = await _call(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
            },
        )

        assert data["error"] is True
        assert data["error_type"] == "insufficient_scope"
        assert data["required_scopes"] == ["research"]
        assert data["missing_scopes"] == ["research"]
        assert server.job_store.get_active() is None

    @pytest.mark.asyncio
    async def test_legacy_write_scope_allows_research_tool(self, server):
        server._auth_context = _context(["read", "write"], client_id="legacy-client")

        data = await _call(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
            },
        )

        assert data["accepted"] is True
        assert "job_id" in data

    @pytest.mark.asyncio
    async def test_research_scope_does_not_allow_delegate_tool(self, server):
        server._auth_context = _context(["read", "research"])

        data = await _call(
            server,
            "delegate_to_agent",
            {
                "agent_url": "https://agent.example.com",
                "message": "summarize current job",
            },
        )

        assert data["error"] is True
        assert data["error_type"] == "insufficient_scope"
        assert data["required_scopes"] == ["delegate"]

    @pytest.mark.asyncio
    async def test_clear_jobs_requires_admin_scope(self, server):
        server._auth_context = _context(["read", "write"])

        data = await _call(server, "clear_jobs", {})

        assert data["error"] is True
        assert data["error_type"] == "insufficient_scope"
        assert data["required_scopes"] == ["admin"]


class TestScopeGrantPolicy:
    def test_report_scope_is_not_satisfied_by_legacy_write(self):
        assert scope_granted(REPORT_SCOPE, (REPORT_SCOPE,))
        assert scope_granted(REPORT_SCOPE, (ADMIN_SCOPE,))
        assert not scope_granted(REPORT_SCOPE, ("write",))
