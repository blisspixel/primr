"""
MCP Server instance and configuration.

This module provides the main MCPServer creation and configuration,
including transport setup and handler registration.

Requirements: 1.1-1.10, 15.1-15.5, 16.1-16.10, 20.1-20.5
"""

import asyncio
import contextlib
import logging
import signal
import sys
from typing import Literal

from mcp.server import Server
from mcp.server.stdio import stdio_server

from primr.mcp_server.job_store import SingleJobStore
from primr.mcp_server.logging_config import configure_http_logging, configure_stdio_logging
from primr.mcp_server.security import PathValidator, RateLimiter, URLValidator

logger = logging.getLogger(__name__)

TransportType = Literal["stdio", "streamable-http"]

# Shutdown timeouts (seconds)
SHUTDOWN_WORK_COMPLETION_TIMEOUT = 5  # Max time to wait for current work
SHUTDOWN_TOTAL_TIMEOUT = 10  # Total shutdown timeout


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
            allow_plaintext: Allow plaintext HTTP (for local dev only)
            require_auth: Require authentication for HTTP transport
        """
        self.transport = transport
        self.port = port
        self.host = host
        self.log_level = log_level
        self.allow_plaintext = allow_plaintext
        self.require_auth = require_auth

        # Publish the transport so tool-call-time policy checks (cost-cap
        # enforcement defaults on for HTTP — see mcp_server.cost_caps) know
        # which surface they are serving, regardless of entry point.
        import os as _os

        _os.environ["PRIMR_MCP_TRANSPORT"] = transport

        # Initialize components
        self.job_store = SingleJobStore(journal_path=journal_path)
        # "working" is primr's own run/scratch root: report_path reuse
        # (e.g. skill packs authored from `working/<run>` evidence) must be
        # allowed alongside the deliverable roots, while still blocking
        # traversal / symlinks / system dirs / arbitrary server paths.
        self.path_validator = PathValidator(allowed_roots=["output", "logs", "working"])
        self.url_validator = URLValidator()
        self.rate_limiter = RateLimiter()

        # Auth context for current request (set during HTTP handling)
        self._auth_context = None

        # Create MCP server
        self.server = Server("primr")

        # Register handlers
        self._register_handlers()

        # Shutdown flag
        self._shutdown_event = asyncio.Event()

        # Track running background tasks for graceful shutdown
        self._background_tasks: set[asyncio.Task] = set()

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

    async def _graceful_shutdown(self) -> None:
        """
        Perform graceful shutdown with timeouts.

        Requirements: 20.1-20.5

        Shutdown sequence:
        1. Signal shutdown to all components
        2. Wait up to SHUTDOWN_WORK_COMPLETION_TIMEOUT (5s) for current work
        3. Force-cancel any remaining tasks
        4. Mark active job as failed with error_type "server_shutdown"
        5. Flush journal to disk
        6. Total timeout: SHUTDOWN_TOTAL_TIMEOUT (10s)
        """
        logger.info("Starting graceful shutdown")
        shutdown_start = asyncio.get_running_loop().time()

        # Phase 1: Wait for background tasks to complete (max 5s)
        if self._background_tasks:
            logger.info(
                "Waiting for %d background task(s) to complete...",
                len(self._background_tasks),
            )
            try:
                # Give tasks a chance to complete gracefully
                done, pending = await asyncio.wait(
                    self._background_tasks,
                    timeout=SHUTDOWN_WORK_COMPLETION_TIMEOUT,
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

        # Phase 2: Mark active job as failed
        self.job_store.mark_shutdown()

        # Check total timeout
        elapsed = asyncio.get_running_loop().time() - shutdown_start
        if elapsed >= SHUTDOWN_TOTAL_TIMEOUT:
            logger.warning("Shutdown timeout (%ds) exceeded", SHUTDOWN_TOTAL_TIMEOUT)

        logger.info("Graceful shutdown complete in %.2fs", elapsed)

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

            # Perform graceful shutdown
            await self._graceful_shutdown()

    async def run_http(self) -> None:
        """
        Run the server with streamable HTTP transport.

        Requirements: 1.2, 1.7, 1.8, 13.1-13.10
        """
        import uvicorn
        from mcp.server.streamable_http import StreamableHTTPServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount

        configure_http_logging(self.log_level)
        self._setup_signal_handlers()

        logger.info(
            "Starting Primr MCP server (HTTP transport on %s:%d)",
            self.host,
            self.port,
        )

        # Check plaintext security. We refuse to bind to a non-loopback
        # address without explicit opt-in: the previous behavior was a
        # warning-only check, which silently exposed plaintext MCP on
        # whichever interface the operator typed (including 0.0.0.0)
        # while the warning scrolled off the boot log. Operators who
        # terminate TLS in front (Azure Container Apps ingress, an nginx
        # reverse proxy, etc.) must pass --allow-plaintext to acknowledge
        # the container speaks HTTP.
        if not self.allow_plaintext and self.host not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError(
                f"Refusing to bind MCP HTTP to non-loopback host {self.host!r} "
                "without --allow-plaintext. Pass --allow-plaintext only when "
                "TLS is terminated upstream (reverse proxy, cloud ingress)."
            )

        # Create transport
        transport = StreamableHTTPServerTransport(
            mcp_session_id=None,  # Will be assigned per-connection
            is_json_response_enabled=False,
        )

        # Create ASGI app
        async def handle_mcp(scope, receive, send):
            """Handle MCP requests via streamable HTTP."""
            if scope["type"] == "lifespan":
                # Handle lifespan events
                while True:
                    message = await receive()
                    if message["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif message["type"] == "lifespan.shutdown":
                        await self._graceful_shutdown()
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            else:
                # Handle HTTP requests
                await transport.handle_request(scope, receive, send)

        from starlette.responses import JSONResponse
        from starlette.routing import Route

        # Wrap the MCP ASGI app with auth when required. Auth is applied to the
        # mounted /mcp app rather than the whole server so (a) /healthz stays
        # public for liveness probes and (b) lifespan events never reach the
        # auth middleware — RequireAuthMiddleware does not guard the scope type
        # and would try to 401 a lifespan scope, breaking startup/shutdown.
        mcp_app = handle_mcp
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
            return JSONResponse({"status": "ok"})

        # Build routes — /healthz is intentionally unauthenticated.
        routes = [
            Route("/healthz", _healthz, methods=["GET"]),
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
        # A2A app applies its own in build_app); /healthz remains public.
        app = Starlette(
            routes=routes,
            on_startup=[lambda: logger.info("MCP HTTP server started")],
            on_shutdown=[self._graceful_shutdown],
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

    async def run(self) -> None:
        """Run the server with configured transport."""
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
        allow_plaintext=allow_plaintext,
        require_auth=require_auth,
    )
    server._skip_background_tasks = skip_background_tasks
    return server
