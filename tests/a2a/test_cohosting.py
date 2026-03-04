"""Tests for MCP + A2A co-hosting in server.py."""

import tempfile
from pathlib import Path

import pytest

from primr.mcp_server.server import create_mcp_server


class TestA2ACohosting:
    """Tests for A2A co-hosting via _a2a_enabled flag."""

    @pytest.fixture
    def server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(
                transport="streamable-http",
                journal_path=journal_path,
                skip_background_tasks=True,
                require_auth=False,
            )

    def test_a2a_disabled_by_default(self, server):
        """A2A co-hosting is disabled by default."""
        assert not getattr(server, "_a2a_enabled", False)

    def test_a2a_flag_can_be_set(self, server):
        """_a2a_enabled flag can be set."""
        server._a2a_enabled = True
        assert server._a2a_enabled is True

    def test_server_has_shared_job_store(self, server):
        """Server's job store is available for sharing with A2A."""
        assert server.job_store is not None

    def test_server_has_shared_url_validator(self, server):
        """Server's URL validator is available for sharing with A2A."""
        assert server.url_validator is not None

    def test_server_has_shared_rate_limiter(self, server):
        """Server's rate limiter is available for sharing with A2A."""
        assert server.rate_limiter is not None
