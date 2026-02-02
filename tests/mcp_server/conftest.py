"""
Shared fixtures for MCP server tests.
"""

import tempfile
from pathlib import Path

import pytest

from primr.mcp_server.server import create_mcp_server


@pytest.fixture
def mcp_server():
    """
    Create a test MCP server with background tasks disabled.
    
    This fixture provides a clean server instance for each test,
    with background task execution disabled to prevent actual
    pipeline runs during testing.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        server = create_mcp_server(
            journal_path=journal_path,
            skip_background_tasks=True,
        )
        server.rate_limiter.reset()
        yield server


@pytest.fixture
def mcp_server_with_tasks():
    """
    Create a test MCP server with background tasks enabled.
    
    Use this fixture only for tests that need to verify
    actual pipeline execution.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        server = create_mcp_server(
            journal_path=journal_path,
            skip_background_tasks=False,
        )
        server.rate_limiter.reset()
        yield server
