"""Import-order regressions for the acyclic MCP controller boundary."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("primr.mcp_server.audit_log", "primr.mcp_server.server"),
        ("primr.mcp_server.server", "primr.mcp_server.audit_log"),
        ("primr.mcp_server.tools", "primr.mcp_server.server"),
        ("primr.mcp_server.server", "primr.mcp_server.tools"),
    ],
)
def test_mcp_modules_import_in_either_order(first: str, second: str) -> None:
    """Each import order starts in a fresh interpreter without partial modules."""
    completed = subprocess.run(
        [sys.executable, "-c", f"import {first}\nimport {second}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
