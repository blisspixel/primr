"""Tests for A2A server."""

import pytest

a2a = pytest.importorskip("a2a")

from primr.a2a.server import PrimrA2AServer
from primr.mcp_server.server import create_mcp_server


class TestPrimrA2AServer:
    """Tests for PrimrA2AServer."""

    @pytest.fixture
    def mcp_server(self, tmp_path):
        journal_path = str(tmp_path / "journal.json")
        return create_mcp_server(
            journal_path=journal_path,
            skip_background_tasks=True,
        )

    @pytest.fixture
    def a2a_server(self, mcp_server):
        return PrimrA2AServer(
            mcp_server=mcp_server,
            host="localhost",
            port=9000,
            require_auth=False,
        )

    def test_creates_task_store(self, a2a_server):
        assert a2a_server.task_store is not None

    def test_creates_agent_card(self, a2a_server):
        card = a2a_server.agent_card
        assert card.name == "Primr Research Agent"

    def test_build_app_returns_starlette(self, a2a_server):
        app = a2a_server.build_app()
        assert app is not None

    def test_build_app_with_auth(self, mcp_server):
        """Auth middleware is applied when require_auth=True."""
        import os
        # Set a token so auth middleware can initialize
        os.environ.setdefault("MCP_ADMIN_TOKENS", "test-token")
        try:
            server = PrimrA2AServer(
                mcp_server=mcp_server,
                host="localhost",
                port=9000,
                require_auth=True,
            )
            app = server.build_app()
            assert app is not None
        finally:
            if os.environ.get("MCP_ADMIN_TOKENS") == "test-token":
                del os.environ["MCP_ADMIN_TOKENS"]

    def test_shared_job_store(self, a2a_server, mcp_server):
        """A2A and MCP share the same job store."""
        assert a2a_server.task_store._job_store is mcp_server.job_store
