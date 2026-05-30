"""
Coverage tests for server.py.

Exercises configuration flags, task tracking, signal handler setup, and the
graceful shutdown path without binding any real transport.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from primr.mcp_server.server import PrimrMCPServer, create_mcp_server
from primr.mcp_server.types import ResearchStage


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)


class TestConfiguration:
    def test_create_skip_background_flag(self, server):
        assert server._skip_background_tasks is True

    def test_http_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "j.json")
            s = create_mcp_server(
                transport="streamable-http",
                port=9001,
                host="0.0.0.0",
                allow_plaintext=True,
                require_auth=False,
                journal_path=journal_path,
            )
        assert s.transport == "streamable-http"
        assert s.port == 9001
        assert s.host == "0.0.0.0"
        assert s.allow_plaintext is True
        assert s.require_auth is False

    def test_auth_context_initial_none(self, server):
        assert server._auth_context is None


class TestTrackTask:
    @pytest.mark.asyncio
    async def test_track_and_autoremove(self, server):
        async def noop():
            return 1

        task = asyncio.create_task(noop())
        server._track_task(task)
        assert task in server._background_tasks
        await task
        # done callback should remove it from the set
        await asyncio.sleep(0)
        assert task not in server._background_tasks


class TestSignalHandlers:
    def test_setup_signal_handlers(self, server):
        # Should not raise; on Windows only SIGINT is wired.
        with patch("signal.signal") as mock_signal:
            server._setup_signal_handlers()
        assert mock_signal.called


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_no_tasks(self, server):
        # No background tasks; should still mark shutdown and complete.
        await server._graceful_shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_marks_active_job_failed(self, server):
        job = server.job_store.create("Acme Corp", "full")
        await server._graceful_shutdown()
        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.FAILED
        assert updated.error_type == "server_shutdown"

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_completed_task(self, server):
        async def quick():
            return "done"

        task = asyncio.create_task(quick())
        server._track_task(task)
        await server._graceful_shutdown()
        assert task.done()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending_task(self, server, monkeypatch):
        # A long-running task should be force-cancelled. Shorten the timeouts
        # so the test stays fast.
        monkeypatch.setattr("primr.mcp_server.server.SHUTDOWN_WORK_COMPLETION_TIMEOUT", 0.05)
        monkeypatch.setattr("primr.mcp_server.server.SHUTDOWN_TOTAL_TIMEOUT", 0.2)

        async def slow():
            await asyncio.sleep(10)

        task = asyncio.create_task(slow())
        server._track_task(task)
        await server._graceful_shutdown()
        assert task.cancelled() or task.done()


class TestRunDispatch:
    @pytest.mark.asyncio
    async def test_run_dispatches_stdio(self, server):
        with patch.object(server, "run_stdio", new=AsyncMock()) as mock_stdio:
            await server.run()
        mock_stdio.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_dispatches_http(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "j.json")
            s = PrimrMCPServer(transport="streamable-http", journal_path=journal_path)
        with patch.object(s, "run_http", new=AsyncMock()) as mock_http:
            await s.run()
        mock_http.assert_awaited_once()
