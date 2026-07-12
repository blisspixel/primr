"""Import-order regressions across the A2A and MCP composition boundary."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("primr.a2a.server", "primr.mcp_server.server"),
        ("primr.mcp_server.server", "primr.a2a.server"),
        ("primr.a2a.executor", "primr.mcp_server.server"),
        ("primr.mcp_server.server", "primr.a2a.executor"),
    ],
)
def test_a2a_and_mcp_modules_import_in_either_order(first: str, second: str) -> None:
    """Each transport order starts in a fresh interpreter without partial modules."""
    completed = subprocess.run(
        [sys.executable, "-c", f"import {first}\nimport {second}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
