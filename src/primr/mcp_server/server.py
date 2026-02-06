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

        # Initialize components
        self.job_store = SingleJobStore(journal_path=journal_path)
        self.path_validator = PathValidator()
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
        shutdown_start = asyncio.get_event_loop().time()

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
                    remaining_time = SHUTDOWN_TOTAL_TIMEOUT - (asyncio.get_event_loop().time() - shutdown_start)
                    if remaining_time > 0:
                        await asyncio.wait(pending, timeout=min(remaining_time, 2.0))

            except Exception:
                logger.exception("Error during task shutdown")

        # Phase 2: Mark active job as failed
        self.job_store.mark_shutdown()

        # Check total timeout
        elapsed = asyncio.get_event_loop().time() - shutdown_start
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

        # Check plaintext security
        if not self.allow_plaintext and self.host != "127.0.0.1":
            logger.warning(
                "Non-localhost HTTP without --allow-plaintext is insecure. "
                "Use a TLS-terminating reverse proxy in production."
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

        # Build app with optional auth middleware
        app = Starlette(
            routes=[Mount("/mcp", app=handle_mcp)],
            on_startup=[lambda: logger.info("MCP HTTP server started")],
            on_shutdown=[self._graceful_shutdown],
        )

        # Add auth middleware if required
        if self.require_auth:
            from primr.mcp_server.auth import AuthConfig, PrimrTokenVerifier, create_auth_middleware

            config = AuthConfig.from_env()
            verifier = PrimrTokenVerifier(config)
            auth_middleware = create_auth_middleware(verifier)
            app = auth_middleware(app)

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
