"""Tests for delegate_to_agent MCP tool handler."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest
from primr.mcp_server.server import create_mcp_server


class TestDelegateToolListing:
    """Tests for delegate_to_agent tool visibility."""

    @pytest.fixture
    def server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_delegate_tool_listed_when_a2a_available(self, server):
        """delegate_to_agent appears in tool list when a2a client is importable."""
        handler = server.server.request_handlers[ListToolsRequest]
        result = await handler(ListToolsRequest(method="tools/list"))
        tool_names = [t.name for t in result.root.tools]
        # Will be present since primr.a2a.client exists (even without a2a-sdk)
        assert "delegate_to_agent" in tool_names

    @pytest.mark.asyncio
    async def test_delegate_tool_schema(self, server):
        """delegate_to_agent has correct input schema."""
        handler = server.server.request_handlers[ListToolsRequest]
        result = await handler(ListToolsRequest(method="tools/list"))
        delegate_tool = next(t for t in result.root.tools if t.name == "delegate_to_agent")
        schema = delegate_tool.inputSchema
        assert "agent_url" in schema["properties"]
        assert "message" in schema["properties"]
        assert "skill_id" in schema["properties"]
        assert "agent_url" in schema["required"]
        assert "message" in schema["required"]


class TestDelegateToolExecution:
    """Tests for delegate_to_agent tool execution."""

    @pytest.fixture
    def server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_blocks_ssrf_url(self, server):
        """Private IPs are blocked by SSRF validation."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="delegate_to_agent",
                arguments={
                    "agent_url": "http://169.254.169.254/latest/meta-data/",
                    "message": "test",
                },
            ),
        ))
        text = result.root.content[0].text
        data = json.loads(text)
        assert data["error"] is True

    @pytest.mark.asyncio
    async def test_blocks_localhost(self, server):
        """Localhost URLs are blocked."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="delegate_to_agent",
                arguments={
                    "agent_url": "http://127.0.0.1:9000",
                    "message": "test",
                },
            ),
        ))
        text = result.root.content[0].text
        data = json.loads(text)
        assert data["error"] is True

    @pytest.mark.asyncio
    async def test_successful_delegation(self, server):
        """Successful delegation returns remote agent response."""
        mock_result = {"status": {"state": "completed"}, "artifacts": []}

        with patch("primr.a2a.client.A2AClient") as MockClient:
            instance = AsyncMock()
            instance.send_message = AsyncMock(return_value=mock_result)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = instance

            # Also mock URL validator to allow the URL
            with patch.object(server.url_validator, "validate") as mock_validate:
                mock_validate.return_value = MagicMock(valid=True)

                handler = server.server.request_handlers[CallToolRequest]
                result = await handler(CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="delegate_to_agent",
                        arguments={
                            "agent_url": "https://remote-agent.example.com",
                            "message": "Research Acme Corp",
                            "skill_id": "research_company",
                        },
                    ),
                ))

        text = result.root.content[0].text
        data = json.loads(text)
        assert not data.get("error")
        assert data.get("status", {}).get("state") == "completed"

    @pytest.mark.asyncio
    async def test_delegation_error_handling(self, server):
        """Network errors during delegation return error response."""
        with patch("primr.a2a.client.A2AClient") as MockClient:
            instance = AsyncMock()
            instance.send_message = AsyncMock(side_effect=ConnectionError("unreachable"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = instance

            with patch.object(server.url_validator, "validate") as mock_validate:
                mock_validate.return_value = MagicMock(valid=True)

                handler = server.server.request_handlers[CallToolRequest]
                result = await handler(CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="delegate_to_agent",
                        arguments={
                            "agent_url": "https://broken-agent.example.com",
                            "message": "test",
                        },
                    ),
                ))

        text = result.root.content[0].text
        data = json.loads(text)
        assert data["error"] is True
        assert data["error_type"] == "a2a_delegation_failed"
