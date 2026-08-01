"""
MCP Server instance and configuration.

This module provides the main MCPServer creation and configuration,
including transport setup and handler registration.

Requirements: 1.1-1.10, 15.1-15.5, 16.1-16.10, 20.1-20.5
"""

import asyncio
import contextlib
import contextvars
import importlib.metadata
import ipaddress
import logging
import signal
import sys
from typing import Literal

from mcp.server import Server
from mcp.server.caching import CacheHint
from mcp.server.stdio import stdio_server

from primr.mcp_server.audit_log import MCPAuditLog
from primr.mcp_server.job_process import LocalJobSupervisor
from primr.mcp_server.job_process_types import await_task_uninterruptibly
from primr.mcp_server.job_store import ControllerLease, SingleJobStore
from primr.mcp_server.logging_config import configure_http_logging, configure_stdio_logging
from primr.mcp_server.readiness import (
    PersistencePreflightError,
    build_readiness_payload,
    probe_local_persistence,
    validate_local_persistence_paths,
)
from primr.mcp_server.security import PathValidator, RateLimiter, URLValidator

logger = logging.getLogger(__name__)

TransportType = Literal["stdio", "streamable-http"]

# Shutdown timeouts (seconds)
SHUTDOWN_WORK_COMPLETION_TIMEOUT = 5  # Max time to wait for current work
SHUTDOWN_TOTAL_TIMEOUT = 10  # Total shutdown timeout


def _primr_version() -> str:
    """Installed distribution version for MCP server identity.

    Read from package metadata rather than ``primr.__version__`` so this
    module does not import the ``primr`` package root (which would join the
    core CLI import cycle pinned by tests/test_architecture.py).
    """
    try:
        return importlib.metadata.version("primr")
    except importlib.metadata.PackageNotFoundError:
        return ""


def _is_loopback_host(host: str) -> bool:
    """Return whether a listener host is explicitly confined to loopback."""
    normalized = host.casefold()
    if normalized == "localhost":
        return True
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


class PrimrMCPServer:
    """
    Primr MCP Server wrapper.

    Manages the MCP server instance, job store, and security middleware.
    """

    def __init__(
        self,
        transport: TransportType = "stdio",
        port: int = 8000,
        host: str = "127.0.0.1",
        log_level: str = "INFO",
        journal_path: str | None = None,
        audit_log_path: str | None = None,
        allow_plaintext: bool = False,
        require_auth: bool = True,
    ):
        """
        Initialize the Primr MCP server.

        Args:
            transport: Transport type ("stdio" or "streamable-http")
            port: HTTP port for streamable-http transport
            host: HTTP host to bind to (default: 127.0.0.1 for localhost only)
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            journal_path: Path to job journal file
            audit_log_path: Path to MCP audit JSONL file
            allow_plaintext: Allow plaintext HTTP (for local dev only)
            require_auth: Require authentication for HTTP transport
        """
        self.transport = transport
        self.port = port
        self.host = host
        self.log_level = log_level
        self.allow_plaintext = allow_plaintext
        self.require_auth = require_auth

        # Initialize components
        # Construction must not read controller state before this process owns
        # the journal lease and the persistence boundary passes preflight.
        self.job_store = SingleJobStore(journal_path=journal_path, defer_initial_load=True)
        self._controller_lease = ControllerLease(self.job_store.journal_path)
        self.audit_log = MCPAuditLog(audit_log_path=audit_log_path, journal_path=journal_path)
        # "working" is primr's own run/scratch root: report_path reuse
        # (e.g. skill packs authored from `working/<run>` evidence) must be
        # allowed alongside the deliverable roots, while still blocking
        # traversal / symlinks / system dirs / arbitrary server paths.
        self.path_validator = PathValidator(allowed_roots=["output", "logs", "working"])
        self.url_validator = URLValidator()
        self.rate_limiter = RateLimiter()

        # Auth context for current request. HTTP transport can handle
        # concurrent requests, so request auth lives in a context variable.
        # Tests may still set _auth_context directly through the property
        # below to exercise ownership and scope checks.
        self._auth_context_var = contextvars.ContextVar("primr_mcp_auth_context", default=None)
        self._auth_context_override = None

        # Create MCP server. Identity fields surface in initialize and
        # server/discover responses; cache hints are the 2026-07-28
        # `ttlMs`/`cacheScope` freshness metadata. Every hint is private:
        # responses are auth-scoped and must never be reused across callers
        # by a shared intermediary. Listings are stable per-process; reads
        # cover live job state, so they are always revalidated.
        self.server = Server(
            "primr",
            version=_primr_version(),
            title="Primr",
            description="Company research: URL in, sourced strategic brief out.",
            website_url="https://github.com/blisspixel/primr",
            instructions=(
                "Primr runs cost real money. Call estimate_run before any "
                "cost-incurring tool, surface the estimate, and get explicit "
                "user approval before research_company or generate_strategy. "
                "Research is a long-running async job: launch once, then poll "
                "primr://research/status or use wait_for_status_change. Read "
                "primr://agent/governance for the full contract."
            ),
            cache_hints={
                "tools/list": CacheHint(ttl_ms=300_000, scope="private"),
                "prompts/list": CacheHint(ttl_ms=300_000, scope="private"),
                "resources/list": CacheHint(ttl_ms=10_000, scope="private"),
                "resources/templates/list": CacheHint(ttl_ms=300_000, scope="private"),
                "resources/read": CacheHint(ttl_ms=0, scope="private"),
                "server/discover": CacheHint(ttl_ms=300_000, scope="private"),
            },
        )

        # Register handlers
        self._register_handlers()

        # Shutdown flag
        self._shutdown_event = asyncio.Event()

        # Track running background tasks for graceful shutdown
        self._background_tasks: set[asyncio.Task] = set()

        # A shared controller lifecycle may be entered by MCP and standalone
        # A2A concurrently. The final entrant owns shutdown and lease release.
        self._controller_lifecycle_lock = asyncio.Lock()
        self._controller_lifecycle_users = 0
        self._controller_phase = "inactive"
        self._persistence_ready = {
            "journal": False,
            "audit": False,
            "output": False,
        }

        # Own long research work outside the controller process. The
        # supervisor is shared by MCP and A2A so both surfaces have identical
        # cancellation and shutdown semantics.
        self.job_supervisor = LocalJobSupervisor(self.job_store)

    @contextlib.asynccontextmanager
    async def controller_lifecycle(self):
        """Own the journal lease and workers across one or more co-hosted servers."""
        async with self._controller_lifecycle_lock:
            if self._controller_lifecycle_users == 0:
                self._controller_phase = "starting"
                if self.job_supervisor.shutdown_started:
                    self._controller_phase = "failed"
                    raise RuntimeError(
                        "This controller has already shut down; create a new server instance"
                    )
                if getattr(self._controller_lease, "acquired", False) is True:
                    self._controller_phase = "failed"
                    raise RuntimeError(
                        "Prior controller shutdown is incomplete; refusing journal reconciliation"
                    )
                acquired_here = False
                try:
                    validate_local_persistence_paths(
                        journal_path=self.job_store.journal_path,
                        audit_path=self.audit_log.path,
                        output_root=self.job_supervisor.output_root,
                        controller_lock_path=self._controller_lease.lock_path,
                    )
                    self._controller_lease.acquire()
                    acquired_here = True
                    self._persistence_ready = probe_local_persistence(
                        journal_path=self.job_store.journal_path,
                        audit_path=self.audit_log.path,
                        output_root=self.job_supervisor.output_root,
                        controller_lock_path=self._controller_lease.lock_path,
                    )
                    if not self.audit_log.preflight():
                        raise PersistencePreflightError("audit")
                    self.job_supervisor.mark_output_preflight_succeeded()
                    self.job_store.reload_from_journal()
                    reconciled_job_id = self.job_store.reconcile_interrupted_job()
                except BaseException:
                    self._controller_phase = "failed"
                    self._persistence_ready = {
                        "journal": False,
                        "audit": False,
                        "output": False,
                    }
                    if acquired_here:
                        self._controller_lease.close()
                    raise
                if reconciled_job_id is not None:
                    logger.warning(
                        "Reconciled interrupted job %s after server restart",
                        reconciled_job_id,
                    )
                self._shutdown_event.clear()
                self._controller_phase = "ready"
            self._controller_lifecycle_users += 1

        try:
            yield
        finally:
            cleanup_task = asyncio.create_task(self._leave_controller_lifecycle())
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                await await_task_uninterruptibly(cleanup_task)
                raise

    async def _leave_controller_lifecycle(self) -> None:
        async with self._controller_lifecycle_lock:
            self._controller_lifecycle_users -= 1
            if self._controller_lifecycle_users > 0:
                return
            self._controller_phase = "stopping"
            try:
                workers_reaped = await self._graceful_shutdown()
            except BaseException:
                self._controller_phase = "failed"
                raise
            remaining = self.job_supervisor.running_job_ids
            if not workers_reaped or remaining:
                self._controller_phase = "failed"
                raise RuntimeError(
                    "Controller shutdown could not reap all workers; retaining the journal lease"
                )
            self._controller_lease.close()
            self._persistence_ready = {
                "journal": False,
                "audit": False,
                "output": False,
            }
            self._controller_phase = "inactive"

    def readiness_snapshot(self) -> tuple[bool, dict[str, object]]:
        """Return body-safe local controller readiness without remote checks."""
        audit_status = str(self.audit_log.health_snapshot().get("status", "degraded"))
        persistence = {
            **self._persistence_ready,
            "journal": self._persistence_ready["journal"] and self.job_store.persistence_healthy,
            "output": self._persistence_ready["output"]
            and self.job_supervisor.output_persistence_healthy,
        }
        return build_readiness_payload(
            phase=self._controller_phase,
            lease_acquired=bool(getattr(self._controller_lease, "acquired", False)),
            lifecycle_users=self._controller_lifecycle_users,
            shutdown_requested=self._shutdown_event.is_set(),
            admission_open=not self.job_supervisor.shutdown_started,
            persistence=persistence,
            audit_status=audit_status,
        )

    @property
    def _auth_context(self):
        """Return the current request auth context, if any."""
        if self._auth_context_override is not None:
            return self._auth_context_override
        return self._auth_context_var.get()

    @_auth_context.setter
    def _auth_context(self, value) -> None:
        """Set a test override for the auth context."""
        self._auth_context_override = value

    def _track_task(self, task: asyncio.Task) -> None:
        """Track a background task for shutdown coordination."""
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _register_handlers(self) -> None:
        """Register all tool, resource, and prompt handlers."""
        from primr.mcp_server.prompts import register_prompts
        from primr.mcp_server.resources import register_resources
        from primr.mcp_server.tools import register_tools

        register_resources(self.server, self)
        register_tools(self.server, self)
        register_prompts(self.server)

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def handle_shutdown(signum, _frame):
            logger.info("Received signal %s, initiating shutdown", signum)
            self._shutdown_event.set()

        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, handle_shutdown)
            signal.signal(signal.SIGINT, handle_shutdown)
        else:
            # Windows doesn't support SIGTERM the same way
            signal.signal(signal.SIGINT, handle_shutdown)

    async def _graceful_shutdown(self) -> bool:
        """
        Perform graceful shutdown with timeouts.

        Requirements: 20.1-20.5

        Shutdown sequence:
        1. Refuse new supervised worker starts.
        2. Request cooperative worker stop, then terminate and reap as needed.
        3. Wait within the remaining total budget for controller tasks.
        4. Cancel controller tasks that remain.
        5. Mark any active job without an owned worker as server_shutdown.
        6. Keep the total controller shutdown budget at 10 seconds.
        """
        logger.info("Starting graceful shutdown")
        shutdown_start = asyncio.get_running_loop().time()
        workers_reaped = False

        # Phase 1: stop and reap owned worker processes before cancelling the
        # controller tasks that monitor them.
        try:
            shutdown_result = await self.job_supervisor.shutdown(
                timeout=SHUTDOWN_WORK_COMPLETION_TIMEOUT
            )
            workers_reaped = (
                shutdown_result is not False and not self.job_supervisor.running_job_ids
            )
        except Exception:
            logger.exception("Error while stopping supervised research workers")

        # Phase 2: Wait for remaining background tasks to complete (max 5s)
        if self._background_tasks:
            logger.info(
                "Waiting for %d background task(s) to complete...",
                len(self._background_tasks),
            )
            try:
                # Give tasks a chance to complete gracefully
                remaining_budget = max(
                    0.0,
                    SHUTDOWN_TOTAL_TIMEOUT - (asyncio.get_running_loop().time() - shutdown_start),
                )
                done, pending = await asyncio.wait(
                    self._background_tasks,
                    timeout=min(SHUTDOWN_WORK_COMPLETION_TIMEOUT, remaining_budget),
                    return_when=asyncio.ALL_COMPLETED,
                )

                if pending:
                    logger.warning(
                        "Force-cancelling %d task(s) after %ds timeout",
                        len(pending),
                        SHUTDOWN_WORK_COMPLETION_TIMEOUT,
                    )
                    for task in pending:
                        task.cancel()

                    # Wait briefly for cancellation to complete
                    remaining_time = SHUTDOWN_TOTAL_TIMEOUT - (
                        asyncio.get_running_loop().time() - shutdown_start
                    )
                    if remaining_time > 0:
                        await asyncio.wait(pending, timeout=min(remaining_time, 2.0))

            except Exception:
                logger.exception("Error during task shutdown")

        # Phase 3: only reconcile state after every retained process exited.
        if workers_reaped:
            self.job_store.mark_shutdown()

        # Check total timeout
        elapsed = asyncio.get_running_loop().time() - shutdown_start
        if elapsed >= SHUTDOWN_TOTAL_TIMEOUT:
            logger.warning("Shutdown timeout (%ds) exceeded", SHUTDOWN_TOTAL_TIMEOUT)

        logger.info("Graceful shutdown complete in %.2fs", elapsed)
        return workers_reaped

    async def run_stdio(self) -> None:
        """
        Run the server with stdio transport.

        Requirements: 1.1, 1.4, 14.1
        """
        configure_stdio_logging(self.log_level)
        self._setup_signal_handlers()

        logger.info("Starting Primr MCP server (stdio transport)")

        async with stdio_server() as (read_stream, write_stream):
            # Create shutdown task
            shutdown_task = asyncio.create_task(self._shutdown_event.wait())

            # Create server task
            server_task = asyncio.create_task(
                self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options(),
                )
            )

            # Wait for either shutdown or server completion
            done, pending = await asyncio.wait(
                [shutdown_task, server_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            if server_task in done:
                server_task.result()
            else:
                shutdown_task.result()

    async def run_http(self) -> None:
        """
        Run the server with streamable HTTP transport.

        Requirements: 1.2, 1.7, 1.8, 13.1-13.10
        """
        import uvicorn
        from mcp.server.streamable_http_manager import (
            StreamableHTTPASGIApp,
            StreamableHTTPSessionManager,
        )
        from starlette.applications import Starlette
        from starlette.routing import Mount

        configure_http_logging(self.log_level)
        self._setup_signal_handlers()

        logger.info(
            "Starting Primr MCP server (HTTP transport on %s:%d)",
            self.host,
            self.port,
        )

        is_loopback = _is_loopback_host(self.host)

        # Disabling authentication is a local-development convenience only.
        # Plaintext opt-in acknowledges upstream TLS termination; it must not
        # also become an implicit opt-out from identity and scope enforcement.
        if not self.require_auth and not is_loopback:
            raise RuntimeError(
                f"Refusing to bind unauthenticated MCP HTTP to non-loopback "
                f"host {self.host!r}. Authentication may only be disabled on "
                "an explicit loopback listener."
            )

        # Check plaintext security. We refuse to bind to a non-loopback
        # address without explicit opt-in: the previous behavior was a
        # warning-only check, which silently exposed plaintext MCP on
        # whichever interface the operator typed (including 0.0.0.0)
        # while the warning scrolled off the boot log. Operators who
        # terminate TLS in front (Azure Container Apps ingress, an nginx
        # reverse proxy, etc.) must pass --allow-plaintext to acknowledge
        # the container speaks HTTP.
        if not self.allow_plaintext and not is_loopback:
            raise RuntimeError(
                f"Refusing to bind MCP HTTP to non-loopback host {self.host!r} "
                "without --allow-plaintext. Pass --allow-plaintext only when "
                "TLS is terminated upstream (reverse proxy, cloud ingress)."
            )

        # The session manager serves both protocol eras from one endpoint:
        # 2026-07-28 clients speak statelessly per-request, legacy clients
        # get the initialize handshake and a session. Its run() context owns
        # per-session task lifecycles, entered from the app lifespan below.
        session_manager = StreamableHTTPSessionManager(
            app=self.server,
            json_response=False,
        )
        transport_asgi = StreamableHTTPASGIApp(session_manager)

        # Create ASGI app
        async def handle_mcp(scope, receive, send):
            """Handle MCP requests via streamable HTTP."""
            if scope["type"] == "lifespan":
                # Mounted raw ASGI apps can still receive lifespan scopes
                # from some servers; answer them so startup never wedges.
                while True:
                    message = await receive()
                    if message["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif message["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            else:
                # Handle HTTP requests
                await transport_asgi(scope, receive, send)

        async def handle_mcp_with_auth_context(scope, receive, send):
            """Bridge SDK-authenticated HTTP users into tool dispatch."""
            auth_context = self._auth_context_from_scope(scope)
            token = self._auth_context_var.set(auth_context)
            try:
                await handle_mcp(scope, receive, send)
            finally:
                self._auth_context_var.reset(token)

        from starlette.responses import JSONResponse
        from starlette.routing import Route

        # Wrap the MCP ASGI app with auth when required. Auth is applied to the
        # mounted /mcp app rather than the whole server so (a) /healthz stays
        # public for liveness probes and (b) lifespan events never reach the
        # auth middleware — RequireAuthMiddleware does not guard the scope type
        # and would try to 401 a lifespan scope, breaking startup/shutdown.
        mcp_app = handle_mcp_with_auth_context
        if self.require_auth:
            from primr.mcp_server.auth import (
                AuthConfig,
                PrimrTokenVerifier,
                create_auth_middleware,
            )

            config = AuthConfig.from_env()
            verifier = PrimrTokenVerifier(config)
            mcp_app = create_auth_middleware(verifier)(mcp_app)

        async def _healthz(_request: object) -> JSONResponse:
            return JSONResponse(
                {"status": "ok"},
                headers={"Cache-Control": "no-store"},
            )

        async def _readyz(_request: object) -> JSONResponse:
            ready, payload = self.readiness_snapshot()
            return JSONResponse(
                payload,
                status_code=200 if ready else 503,
                headers={"Cache-Control": "no-store"},
            )

        # Probe routes are intentionally unauthenticated and body-safe.
        routes = [
            Route("/healthz", _healthz, methods=["GET"]),
            Route("/readyz", _readyz, methods=["GET"]),
            Mount("/mcp", app=mcp_app),
        ]

        # Co-host A2A server if available and enabled
        if getattr(self, "_a2a_enabled", False):
            try:
                from primr.a2a.server import PrimrA2AServer

                # In co-hosted mode there is exactly one uvicorn listener —
                # the MCP one on self.port — and the A2A app is mounted under
                # /a2a. The AgentCard URL must reflect that real listener,
                # not the historical --a2a-port (which was advertised but
                # never bound, sending clients toward an unrelated port).
                a2a_server = PrimrA2AServer(
                    mcp_server=self,
                    host=self.host,
                    port=self.port,
                    require_auth=self.require_auth,
                    public_path="/a2a/",
                )
                a2a_app = a2a_server.build_app()
                routes.append(Mount("/a2a", app=a2a_app))
                logger.info("A2A server co-hosted at /a2a/")
            except ImportError:
                logger.warning("A2A co-hosting requested but a2a-sdk not installed")
            except Exception:
                logger.exception("Failed to initialize A2A co-hosting")

        # Build app. Auth is already applied per-mount above (and the co-hosted
        # A2A app applies its own in build_app); probe routes remain public.
        # The lifespan owns the session manager's task group: requests fail
        # cleanly before startup and drain on shutdown.
        @contextlib.asynccontextmanager
        async def _lifespan(_app):
            async with session_manager.run():
                logger.info("MCP HTTP server started")
                yield

        app = Starlette(
            routes=routes,
            lifespan=_lifespan,
        )

        # Run with uvicorn
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level=self.log_level.lower(),
        )
        server = uvicorn.Server(config)

        # Run server with shutdown handling
        await server.serve()

    def _auth_context_from_scope(self, scope):
        """Build an AuthContext from Starlette/MCP auth scope state."""
        access_token = getattr(scope.get("user"), "access_token", None)
        if access_token is None:
            return None

        from primr.mcp_server.auth import AuthContext

        return AuthContext(access_token)

    async def run(self) -> None:
        """Run the server with configured transport."""
        # Publish the transport at serve time (not construction) so
        # tool-call-time policy checks — cost-cap enforcement defaults on
        # for HTTP, see mcp_server.cost_caps — know which surface they are
        # serving. Constructing a server (tests do this freely) must not
        # change process-wide policy.
        from primr.mcp_server.cost_caps import set_active_transport

        async with self.controller_lifecycle():
            set_active_transport(self.transport)
            if self.transport == "stdio":
                await self.run_stdio()
            else:
                await self.run_http()


def create_mcp_server(
    transport: TransportType = "stdio",
    port: int = 8000,
    host: str = "127.0.0.1",
    log_level: str = "INFO",
    journal_path: str | None = None,
    audit_log_path: str | None = None,
    allow_plaintext: bool = False,
    require_auth: bool = True,
    skip_background_tasks: bool = False,
) -> PrimrMCPServer:
    """
    Create and configure the Primr MCP server.

    Args:
        transport: Transport type ("stdio" or "streamable-http")
        port: HTTP port for streamable-http transport
        host: HTTP host to bind to (default: 127.0.0.1 for localhost only)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        journal_path: Path to job journal file
        audit_log_path: Path to MCP audit JSONL file
        allow_plaintext: Allow plaintext HTTP (for local dev only)
        require_auth: Require authentication for HTTP transport
        skip_background_tasks: Skip background task creation (for testing)

    Returns:
        Configured PrimrMCPServer instance
    """
    server = PrimrMCPServer(
        transport=transport,
        port=port,
        host=host,
        log_level=log_level,
        journal_path=journal_path,
        audit_log_path=audit_log_path,
        allow_plaintext=allow_plaintext,
        require_auth=require_auth,
    )
    server._skip_background_tasks = skip_background_tasks
    return server
