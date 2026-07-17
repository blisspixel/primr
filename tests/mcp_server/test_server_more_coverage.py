"""
Additional coverage-focused tests for primr.mcp_server.server.

Targets branches not exercised by test_server.py / test_server_coverage.py:

- handle_shutdown callback body (sets the shutdown event).
- run_stdio: drives the stdio transport with a mocked stdio_server +
  server.run, asserting graceful shutdown runs.
- run_http: plaintext refusal on non-loopback host, healthz handler,
  auth-middleware wiring, A2A co-hosting (success + ImportError), and the
  uvicorn serve call — all with the MCP/Starlette/uvicorn boundary mocked.
- _graceful_shutdown: exception during task wait is swallowed.

No real sockets are bound and no transport actually serves traffic.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import primr.mcp_server.server as server_module
from primr.mcp_server.server import create_mcp_server


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)


# ---------------------------------------------------------------------------
# Signal handler callback body
# ---------------------------------------------------------------------------


class TestSignalHandlerCallback:
    def test_handle_shutdown_sets_event(self, server):
        """The registered handler sets _shutdown_event when invoked."""
        captured = {}

        def fake_signal(signum, handler):
            captured[signum] = handler

        with patch("signal.signal", side_effect=fake_signal):
            server._setup_signal_handlers()

        assert not server._shutdown_event.is_set()
        # Invoke whichever handler was registered (SIGINT is wired on all platforms).
        handler = next(iter(captured.values()))
        handler(2, None)
        assert server._shutdown_event.is_set()


# ---------------------------------------------------------------------------
# run_stdio
# ---------------------------------------------------------------------------


class TestRunStdio:
    @pytest.mark.asyncio
    async def test_run_stdio_graceful_shutdown(self, server):
        """run_stdio wires the stdio transport and finishes via graceful shutdown."""

        @asynccontextmanager
        async def fake_stdio():
            yield (MagicMock(), MagicMock())

        # server.server.run completes immediately so the wait() returns.
        server.server.run = AsyncMock(return_value=None)
        server.server.create_initialization_options = MagicMock(return_value={})

        with (
            patch("primr.mcp_server.server.stdio_server", fake_stdio),
            patch("primr.mcp_server.server.configure_stdio_logging"),
            patch.object(server, "_setup_signal_handlers"),
            patch.object(server, "_graceful_shutdown", new=AsyncMock()) as mock_shutdown,
        ):
            await server.run_stdio()

        assert server.server.run.await_count == 1
        mock_shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_stdio_shutdown_event_cancels_server(self, server):
        """If the shutdown event fires first, the server task is cancelled."""

        @asynccontextmanager
        async def fake_stdio():
            yield (MagicMock(), MagicMock())

        async def never_returns(*args, **kwargs):
            await asyncio.sleep(60)

        server.server.run = never_returns
        server.server.create_initialization_options = MagicMock(return_value={})

        # Pre-set the shutdown event so the shutdown task wins the race.
        server._shutdown_event.set()

        with (
            patch("primr.mcp_server.server.stdio_server", fake_stdio),
            patch("primr.mcp_server.server.configure_stdio_logging"),
            patch.object(server, "_setup_signal_handlers"),
            patch.object(server, "_graceful_shutdown", new=AsyncMock()) as mock_shutdown,
        ):
            await server.run_stdio()

        mock_shutdown.assert_awaited_once()


# ---------------------------------------------------------------------------
# run_http
# ---------------------------------------------------------------------------


def _http_server(**kwargs):
    tmpdir = tempfile.mkdtemp()
    journal_path = str(Path(tmpdir) / "j.json")
    return create_mcp_server(
        transport="streamable-http",
        journal_path=journal_path,
        skip_background_tasks=True,
        **kwargs,
    )


class TestRunHttp:
    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("localhost", True),
            ("LOCALHOST", True),
            ("127.0.0.1", True),
            ("127.255.255.254", True),
            ("::1", True),
            ("[::1]", True),
            ("0.0.0.0", False),
            ("::", False),
            ("192.0.2.1", False),
            ("example.test", False),
        ],
    )
    def test_loopback_host_classification(self, host, expected):
        """Only explicit loopback names and addresses are treated as local."""
        assert server_module._is_loopback_host(host) is expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.0.2.1", "example.test"])
    async def test_run_http_refuses_unauthenticated_non_loopback(self, host):
        """Authentication cannot be disabled on a remotely reachable listener."""
        s = _http_server(host=host, allow_plaintext=True, require_auth=False)
        with (
            patch("primr.mcp_server.server.configure_http_logging"),
            patch.object(s, "_setup_signal_handlers"),
            pytest.raises(RuntimeError, match=r"unauthenticated.*non-loopback"),
        ):
            await s.run_http()

    @pytest.mark.asyncio
    async def test_run_http_refuses_plaintext_non_loopback(self):
        """Binding a non-loopback host without --allow-plaintext is refused."""
        s = _http_server(host="0.0.0.0", allow_plaintext=False, require_auth=False)
        with (
            patch("primr.mcp_server.server.configure_http_logging"),
            patch.object(s, "_setup_signal_handlers"),
            pytest.raises(RuntimeError, match="non-loopback"),
        ):
            await s.run_http()

    @pytest.mark.asyncio
    async def test_run_http_serves_with_auth_and_healthz(self):
        """run_http builds the app, applies auth, and serves via uvicorn."""
        s = _http_server(host="127.0.0.1", require_auth=True)

        captured = {}

        fake_uvicorn = MagicMock()
        fake_uvicorn.Config.return_value = MagicMock()
        served = MagicMock()
        served.serve = AsyncMock()
        fake_uvicorn.Server.return_value = served

        def fake_starlette(routes, on_startup, on_shutdown):
            captured["routes"] = routes
            return MagicMock()

        fake_auth_mod = MagicMock()
        # create_auth_middleware(verifier) -> wrapper(app) -> wrapped_app
        fake_auth_mod.create_auth_middleware.return_value = lambda app: ("wrapped", app)

        with (
            patch("primr.mcp_server.server.configure_http_logging"),
            patch.object(s, "_setup_signal_handlers"),
            patch.dict(
                "sys.modules",
                {
                    "uvicorn": fake_uvicorn,
                    "mcp.server.streamable_http": MagicMock(),
                    "starlette.applications": MagicMock(Starlette=fake_starlette),
                    "starlette.routing": _make_routing_module(),
                    "starlette.responses": MagicMock(JSONResponse=MagicMock()),
                    "primr.mcp_server.auth": fake_auth_mod,
                },
            ),
        ):
            await s.run_http()

        assert served.serve.await_count == 1
        assert fake_auth_mod.create_auth_middleware.called
        # Two routes: /healthz + /mcp mount (no A2A by default).
        assert len(captured["routes"]) == 2

    @pytest.mark.asyncio
    async def test_run_http_cohosts_a2a(self):
        """When _a2a_enabled, an /a2a mount is appended."""
        s = _http_server(host="127.0.0.1", require_auth=False)
        s._a2a_enabled = True

        fake_uvicorn = MagicMock()
        fake_uvicorn.Config.return_value = MagicMock()
        served = MagicMock()
        served.serve = AsyncMock()
        fake_uvicorn.Server.return_value = served

        captured = {}

        def fake_starlette(routes, on_startup, on_shutdown):
            captured["routes"] = routes
            return MagicMock()

        a2a_server = MagicMock()
        a2a_server.build_app.return_value = MagicMock()
        fake_a2a_mod = MagicMock()
        fake_a2a_mod.PrimrA2AServer.return_value = a2a_server

        with (
            patch("primr.mcp_server.server.configure_http_logging"),
            patch.object(s, "_setup_signal_handlers"),
            patch.dict(
                "sys.modules",
                {
                    "uvicorn": fake_uvicorn,
                    "mcp.server.streamable_http": MagicMock(),
                    "starlette.applications": MagicMock(Starlette=fake_starlette),
                    "starlette.routing": _make_routing_module(),
                    "starlette.responses": MagicMock(JSONResponse=MagicMock()),
                    "primr.a2a.server": fake_a2a_mod,
                },
            ),
        ):
            await s.run_http()

        assert served.serve.await_count == 1
        assert fake_a2a_mod.PrimrA2AServer.called
        # /healthz + /mcp + /a2a == 3 routes.
        assert len(captured["routes"]) == 3

    @pytest.mark.asyncio
    async def test_run_http_handle_mcp_lifespan_and_request(self):
        """Exercise the inner handle_mcp ASGI app: lifespan + request scopes."""
        s = _http_server(host="127.0.0.1", require_auth=False)

        fake_uvicorn = MagicMock()
        fake_uvicorn.Config.return_value = MagicMock()
        served = MagicMock()
        served.serve = AsyncMock()
        fake_uvicorn.Server.return_value = served

        transport = MagicMock()
        transport.handle_request = AsyncMock()
        fake_streamable = MagicMock()
        fake_streamable.StreamableHTTPServerTransport.return_value = transport

        captured = {}

        def fake_starlette(routes, on_startup, on_shutdown):
            captured["routes"] = routes
            return MagicMock()

        with (
            patch("primr.mcp_server.server.configure_http_logging"),
            patch.object(s, "_setup_signal_handlers"),
            patch.object(s, "_graceful_shutdown", new=AsyncMock()) as mock_shutdown,
            patch.dict(
                "sys.modules",
                {
                    "uvicorn": fake_uvicorn,
                    "mcp.server.streamable_http": fake_streamable,
                    "starlette.applications": MagicMock(Starlette=fake_starlette),
                    "starlette.routing": _make_routing_module(),
                    "starlette.responses": MagicMock(JSONResponse=MagicMock()),
                },
            ),
        ):
            await s.run_http()

            # require_auth False -> /mcp mount app is the raw handle_mcp closure.
            mcp_mount = next(r for r in captured["routes"] if r.path == "/mcp")
            handle_mcp = mcp_mount.app

            # 1) Lifespan scope: startup then shutdown.
            messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
            sent = []

            async def receive():
                return next(messages)

            async def send(msg):
                sent.append(msg["type"])

            await handle_mcp({"type": "lifespan"}, receive, send)
            assert "lifespan.startup.complete" in sent
            assert "lifespan.shutdown.complete" in sent
            assert mock_shutdown.await_count >= 1

            # 2) Plain HTTP request scope routes to transport.handle_request.
            await handle_mcp({"type": "http"}, AsyncMock(), AsyncMock())
            assert transport.handle_request.await_count == 1

            # 3) The /healthz endpoint returns a JSONResponse (line 297).
            healthz = next(r for r in captured["routes"] if r.path == "/healthz")
            await healthz.endpoint(object())

    @pytest.mark.asyncio
    async def test_run_http_bridges_authenticated_user_to_request_context(self):
        """Authenticated HTTP scope state is visible during tool dispatch."""
        from types import SimpleNamespace

        from mcp.server.auth.provider import AccessToken

        s = _http_server(host="127.0.0.1", require_auth=True)

        fake_uvicorn = MagicMock()
        fake_uvicorn.Config.return_value = MagicMock()
        served = MagicMock()
        served.serve = AsyncMock()
        fake_uvicorn.Server.return_value = served

        captured = {}

        async def capture_request(_scope, _receive, _send):
            ctx = s._auth_context
            captured["client_id"] = ctx.client_id if ctx else None
            captured["scopes"] = ctx.scopes if ctx else []

        transport = MagicMock()
        transport.handle_request = AsyncMock(side_effect=capture_request)
        fake_streamable = MagicMock()
        fake_streamable.StreamableHTTPServerTransport.return_value = transport

        def fake_starlette(routes, on_startup, on_shutdown):
            captured["routes"] = routes
            return MagicMock()

        access_token = AccessToken(
            token="scoped-token",
            client_id="scoped-client",
            scopes=["read", "research"],
        )

        def fake_auth_middleware(_verifier):
            def wrap(app):
                async def wrapped(scope, receive, send):
                    scoped = dict(scope)
                    scoped["user"] = SimpleNamespace(access_token=access_token)
                    await app(scoped, receive, send)

                return wrapped

            return wrap

        with (
            patch("primr.mcp_server.server.configure_http_logging"),
            patch.object(s, "_setup_signal_handlers"),
            patch("primr.mcp_server.auth.create_auth_middleware", fake_auth_middleware),
            patch.dict(
                "sys.modules",
                {
                    "uvicorn": fake_uvicorn,
                    "mcp.server.streamable_http": fake_streamable,
                    "starlette.applications": MagicMock(Starlette=fake_starlette),
                    "starlette.routing": _make_routing_module(),
                    "starlette.responses": MagicMock(JSONResponse=MagicMock()),
                },
            ),
        ):
            await s.run_http()

        mcp_mount = next(r for r in captured["routes"] if r.path == "/mcp")
        await mcp_mount.app({"type": "http"}, AsyncMock(), AsyncMock())

        assert captured["client_id"] == "scoped-client"
        assert captured["scopes"] == ["read", "research"]
        assert s._auth_context is None

    @pytest.mark.asyncio
    async def test_run_http_a2a_generic_exception_is_tolerated(self):
        """A non-ImportError failure building A2A is logged and tolerated (327-328)."""
        s = _http_server(host="127.0.0.1", require_auth=False)
        s._a2a_enabled = True

        fake_uvicorn = MagicMock()
        fake_uvicorn.Config.return_value = MagicMock()
        served = MagicMock()
        served.serve = AsyncMock()
        fake_uvicorn.Server.return_value = served

        captured = {}

        def fake_starlette(routes, on_startup, on_shutdown):
            captured["routes"] = routes
            return MagicMock()

        fake_a2a_mod = MagicMock()
        fake_a2a_mod.PrimrA2AServer.side_effect = RuntimeError("a2a boom")

        with (
            patch("primr.mcp_server.server.configure_http_logging"),
            patch.object(s, "_setup_signal_handlers"),
            patch.dict(
                "sys.modules",
                {
                    "uvicorn": fake_uvicorn,
                    "mcp.server.streamable_http": MagicMock(),
                    "starlette.applications": MagicMock(Starlette=fake_starlette),
                    "starlette.routing": _make_routing_module(),
                    "starlette.responses": MagicMock(JSONResponse=MagicMock()),
                    "primr.a2a.server": fake_a2a_mod,
                },
            ),
        ):
            await s.run_http()

        assert served.serve.await_count == 1
        # A2A failed -> only /healthz + /mcp.
        assert len(captured["routes"]) == 2

    @pytest.mark.asyncio
    async def test_run_http_a2a_import_error_is_tolerated(self):
        """A2A co-hosting requested but SDK missing -> warn and continue serving."""
        s = _http_server(host="127.0.0.1", require_auth=False)
        s._a2a_enabled = True

        fake_uvicorn = MagicMock()
        fake_uvicorn.Config.return_value = MagicMock()
        served = MagicMock()
        served.serve = AsyncMock()
        fake_uvicorn.Server.return_value = served

        captured = {}

        def fake_starlette(routes, on_startup, on_shutdown):
            captured["routes"] = routes
            return MagicMock()

        # Force ImportError when the server tries to import primr.a2a.server.
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "primr.a2a.server":
                raise ImportError("a2a-sdk not installed")
            return real_import(name, *args, **kwargs)

        with (
            patch("primr.mcp_server.server.configure_http_logging"),
            patch.object(s, "_setup_signal_handlers"),
            patch("builtins.__import__", side_effect=fake_import),
            patch.dict(
                "sys.modules",
                {
                    "uvicorn": fake_uvicorn,
                    "mcp.server.streamable_http": MagicMock(),
                    "starlette.applications": MagicMock(Starlette=fake_starlette),
                    "starlette.routing": _make_routing_module(),
                    "starlette.responses": MagicMock(JSONResponse=MagicMock()),
                },
            ),
        ):
            await s.run_http()

        assert served.serve.await_count == 1
        # A2A failed to mount, so only /healthz + /mcp remain.
        assert len(captured["routes"]) == 2


def _make_routing_module():
    """Build a fake starlette.routing with Route/Mount that record their args."""

    class _Route:
        def __init__(self, path, endpoint, methods=None):
            self.path = path
            self.endpoint = endpoint
            self.methods = methods

    class _Mount:
        def __init__(self, path, app=None):
            self.path = path
            self.app = app

    mod = MagicMock()
    mod.Route = _Route
    mod.Mount = _Mount
    return mod


# ---------------------------------------------------------------------------
# _graceful_shutdown: exception during task wait is swallowed
# ---------------------------------------------------------------------------


class TestGracefulShutdownErrors:
    @pytest.mark.asyncio
    async def test_shutdown_swallows_wait_exception(self, server):
        """An exception during asyncio.wait must not propagate (lines 166-167)."""

        async def quick():
            return 1

        task = asyncio.create_task(quick())
        server._track_task(task)

        with patch(
            "primr.mcp_server.server.asyncio.wait",
            new=AsyncMock(side_effect=RuntimeError("wait failed")),
        ):
            # Should complete without raising; job store still marked.
            await server._graceful_shutdown()

        await task

    @pytest.mark.asyncio
    async def test_shutdown_logs_when_total_timeout_exceeded(self, server, monkeypatch):
        """Elapsed >= total timeout hits the warning branch (lines 174-175)."""
        monkeypatch.setattr("primr.mcp_server.server.SHUTDOWN_TOTAL_TIMEOUT", 0)
        # No tasks -> skips the wait block, then elapsed >= 0 triggers the warn.
        await server._graceful_shutdown()


# ---------------------------------------------------------------------------
# run() dispatch for an explicit http instance (complements existing test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_dispatches_http_via_create():
    s = _http_server(require_auth=False)
    with patch.object(s, "run_http", new=AsyncMock()) as mock_http:
        await s.run()
    mock_http.assert_awaited_once()


def test_module_constants_present():
    """Sanity: shutdown timeout constants are importable (cheap import guard)."""
    from primr.mcp_server import server as srv

    assert srv.SHUTDOWN_TOTAL_TIMEOUT >= srv.SHUTDOWN_WORK_COMPLETION_TIMEOUT
    assert "win32" in sys.platform or sys.platform  # platform string exists
