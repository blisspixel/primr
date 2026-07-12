"""A2A server for Primr — exposes research capabilities via Agent-to-Agent protocol.

Builds a Starlette app with A2A routes. Shares the PrimrMCPServer instance
for unified job store, rate limiter, and security middleware.

Requires: pip install primr[a2a]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler

from primr.a2a.agent_card import build_agent_card
from primr.a2a.call_context import PrimrA2ACallContextBuilder
from primr.a2a.executor import PrimrAgentExecutor
from primr.a2a.task_store import PrimrTaskStore
from primr.mcp_server.resource_auth import TRUSTED_LOCAL_A2A_AUTH_CONTEXT

if TYPE_CHECKING:
    from starlette.applications import Starlette

    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)


class PrimrA2AServer:
    """A2A server wrapping Primr's research pipeline.

    Can run standalone or be co-hosted with the MCP server.
    """

    def __init__(
        self,
        mcp_server: PrimrMCPServer,
        host: str = "127.0.0.1",
        port: int = 9000,
        require_auth: bool = True,
        public_path: str = "/",
    ):
        """
        Args:
            public_path: The URL path the A2A app is reachable at. Must
                match the actual mount: "/" when running standalone (the
                A2A app owns the uvicorn server), "/a2a/" when co-hosted
                under the MCP Starlette app. The AgentCard URL is built
                from (host, port, public_path) so clients that follow
                AgentCard.url land on a real listener instead of an
                unused port.
        """
        self._mcp = mcp_server
        self.host = host
        self.port = port
        self.require_auth = require_auth
        self.public_path = public_path
        self._trusted_local_unauthenticated = not require_auth and _is_loopback_host(host)
        if not require_auth and not self._trusted_local_unauthenticated:
            raise ValueError("Unauthenticated A2A requires a loopback host")

        # A2A components
        self._task_store = PrimrTaskStore(mcp_server.job_store)
        self._executor = PrimrAgentExecutor(mcp_server, self._task_store)
        self._agent_card = build_agent_card(host=host, port=port, path=public_path)

    @property
    def task_store(self) -> PrimrTaskStore:
        return self._task_store

    @property
    def agent_card(self):
        return self._agent_card

    def build_app(self) -> Starlette:
        """Build the Starlette ASGI application with A2A routes.

        Returns:
            Configured Starlette application.
        """
        request_handler = DefaultRequestHandler(
            agent_executor=self._executor,
            task_store=self._task_store,
        )

        a2a_app_builder = A2AStarletteApplication(
            agent_card=self._agent_card,
            http_handler=request_handler,
            context_builder=PrimrA2ACallContextBuilder(
                trusted_local_unauthenticated=self._trusted_local_unauthenticated,
            ),
        )

        app = a2a_app_builder.build()
        app = self._with_auth_context(app)

        # Add auth middleware if required. Fail CLOSED: if auth setup raises
        # (e.g. AuthConfig.from_env() rejects a short/placeholder MCP_JWT_SECRET
        # in cloud mode), let the exception abort startup rather than silently
        # serving the agent unauthenticated. This matches the MCP server, which
        # also does not swallow auth-setup failures.
        if self.require_auth:
            from primr.mcp_server.auth import (
                AuthConfig,
                PrimrTokenVerifier,
                create_auth_middleware,
            )

            config = AuthConfig.from_env()
            verifier = PrimrTokenVerifier(config)
            auth_middleware = create_auth_middleware(verifier)
            app = auth_middleware(app)
            logger.info("A2A server: authentication enabled")

        return app

    def _with_auth_context(self, app: Any) -> Any:
        """Bridge authenticated A2A HTTP requests into shared tool context."""

        async def _app(scope, receive, send):
            auth_context = self._mcp._auth_context_from_scope(scope)
            if auth_context is None and self._trusted_local_unauthenticated:
                auth_context = TRUSTED_LOCAL_A2A_AUTH_CONTEXT
            token = self._mcp._auth_context_var.set(auth_context)
            try:
                await app(scope, receive, send)
            finally:
                self._mcp._auth_context_var.reset(token)

        return _app

    async def run(self) -> None:
        """Run the A2A server standalone with uvicorn."""
        import uvicorn

        app = self.build_app()

        logger.info(
            "Starting Primr A2A server on %s:%d",
            self.host,
            self.port,
        )

        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        async with self._mcp.controller_lifecycle():
            await server.serve()


def _is_loopback_host(host: str) -> bool:
    """Return whether a listener host is explicitly loopback-only."""
    return host.casefold() in {"127.0.0.1", "localhost", "::1"}
