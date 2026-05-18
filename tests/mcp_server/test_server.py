"""
Tests for MCP server core.

Task 6: MCP server core with transport support
"""

import tempfile
from pathlib import Path

import pytest

from primr.mcp_server.server import PrimrMCPServer, create_mcp_server


class TestServerCreation:
    """Tests for server creation and configuration."""

    @pytest.fixture
    def temp_journal(self):
        """Create a temporary journal file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield str(Path(tmpdir) / "test_journal.json")

    def test_create_server(self, temp_journal):
        """Server can be created."""
        server = create_mcp_server(journal_path=temp_journal)

        assert server is not None
        assert isinstance(server, PrimrMCPServer)

    def test_server_has_components(self, temp_journal):
        """Server has all required components."""
        server = create_mcp_server(journal_path=temp_journal)

        assert server.job_store is not None
        assert server.path_validator is not None
        assert server.url_validator is not None
        assert server.rate_limiter is not None
        assert server.server is not None

    def test_server_name(self, temp_journal):
        """Server has correct name."""
        server = create_mcp_server(journal_path=temp_journal)

        assert server.server.name == "primr"

    def test_server_transport_default(self, temp_journal):
        """Server defaults to stdio transport."""
        server = create_mcp_server(journal_path=temp_journal)

        assert server.transport == "stdio"

    def test_server_transport_http(self, temp_journal):
        """Server can be configured for HTTP transport."""
        server = create_mcp_server(
            transport="streamable-http",
            port=9000,
            journal_path=temp_journal,
        )

        assert server.transport == "streamable-http"
        assert server.port == 9000


class TestServerHandlers:
    """Tests for handler registration."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path)

    def test_tools_registered(self, server):
        """Tools are registered with the server."""
        from mcp.types import ListToolsRequest

        assert ListToolsRequest in server.server.request_handlers

    def test_resources_registered(self, server):
        """Resources are registered with the server."""
        from mcp.types import ListResourcesRequest, ReadResourceRequest

        assert ListResourcesRequest in server.server.request_handlers
        assert ReadResourceRequest in server.server.request_handlers

    def test_prompts_registered(self, server):
        """Prompts are registered with the server."""
        from mcp.types import GetPromptRequest, ListPromptsRequest

        assert ListPromptsRequest in server.server.request_handlers
        assert GetPromptRequest in server.server.request_handlers
