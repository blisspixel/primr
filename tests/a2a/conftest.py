"""Shared fixtures for A2A tests."""


import pytest


@pytest.fixture
def tmp_journal(tmp_path):
    """Provide a temporary journal path."""
    return str(tmp_path / "test_journal.json")


@pytest.fixture
def mcp_server(tmp_journal):
    """Create a PrimrMCPServer with temp journal."""
    from primr.mcp_server.server import create_mcp_server

    return create_mcp_server(
        journal_path=tmp_journal,
        skip_background_tasks=True,
    )
