"""Process-tree cleanup ownership contracts."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.mcp_server import worker_process_control


@pytest.mark.asyncio
async def test_windows_close_failure_preserves_job_object(monkeypatch) -> None:
    """Kill-on-close ownership remains retained until CloseHandle succeeds."""
    monkeypatch.setattr(worker_process_control, "os", SimpleNamespace(name="nt"))
    process = MagicMock()
    windows_job = MagicMock()
    windows_job.close.side_effect = OSError("close failed")

    retained, error = await worker_process_control.cleanup_process_tree(
        process,
        windows_job,
    )

    assert retained is windows_job
    assert error is not None
    assert "cleanup failed" in error
