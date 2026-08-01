"""
Coverage tests for spike.py.

Exercises the trailing-slash resource read, the run_stdio wiring (mocked
transport), and the main() CLI entry point branches.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.mcp_server import spike
from primr.mcp_server.spike import create_spike_server, main, run_stdio
from tests.mcp_server.sdk_compat import read_resource_handler


class TestResourceTrailingSlash:
    @pytest.mark.asyncio
    async def test_read_test_resource_trailing_slash(self):
        server = create_spike_server()
        result = await read_resource_handler(server, "primr://test/")
        assert "Test resource content @" in result.contents[0].text


class TestRunStdio:
    @pytest.mark.asyncio
    async def test_run_stdio_invokes_server_run(self):
        fake_server = MagicMock()
        fake_server.run = AsyncMock()
        fake_server.create_initialization_options = MagicMock(return_value={})

        # stdio_server is an async context manager yielding (read, write)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=("read", "write"))
        cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(spike, "create_spike_server", return_value=fake_server),
            patch.object(spike, "stdio_server", return_value=cm),
        ):
            await run_stdio()

        fake_server.run.assert_awaited_once()


class TestMain:
    def test_main_stdio_default(self):
        # asyncio.run is replaced with a stub that closes the coroutine handed
        # to it, so no "coroutine never awaited" warning is emitted.
        calls = []

        def fake_run(coro):
            calls.append(coro)
            coro.close()

        with (
            patch.object(sys, "argv", ["spike"]),
            patch.object(spike.asyncio, "run", side_effect=fake_run),
        ):
            main()
        assert len(calls) == 1

    def test_main_http_exits(self):
        with (
            patch.object(sys, "argv", ["spike", "--http"]),
            pytest.raises(SystemExit) as exc,
        ):
            main()
        assert exc.value.code == 1
