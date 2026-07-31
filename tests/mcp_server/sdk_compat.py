"""Shared MCP SDK v2 handler-invocation helpers for server tests.

The v2 SDK keys handlers by method string (``get_request_handler``) and
handlers receive ``(ctx, params)`` and return typed results directly (no
``ServerResult`` wrapper). Tests exercise Primr's registered handlers through
these helpers so the SDK coupling lives in exactly one module.

Primr's handlers take auth state from the server's own context variable, not
from the SDK request context, so ``ctx=None`` is deliberate here.
"""

from __future__ import annotations

from typing import Any

import mcp.types as mcp_types


def _sdk_server(server: Any) -> Any:
    """Accept either a PrimrMCPServer wrapper or a bare SDK Server."""
    return getattr(server, "server", server)


def _handler(server: Any, method: str) -> Any:
    entry = _sdk_server(server).get_request_handler(method)
    assert entry is not None, f"no handler registered for {method}"
    return entry.handler


async def list_tools_handler(server: Any) -> mcp_types.ListToolsResult:
    return await _handler(server, "tools/list")(None, mcp_types.PaginatedRequestParams())


async def server_discover_handler(server: Any) -> mcp_types.DiscoverResult:
    """Invoke the 2026-07-28 server/discover handler with a minimal context.

    The SDK discover path reads ``ctx.protocol_version``; a bare ``None``
    context is not valid even though list handlers tolerate it.
    """
    from types import SimpleNamespace

    from mcp.server.context import ServerRequestContext

    ctx = ServerRequestContext(
        session=SimpleNamespace(),
        lifespan_context=None,
        protocol_version="2026-07-28",
        method="server/discover",
    )
    return await _handler(server, "server/discover")(ctx, None)


async def call_tool_handler(
    server: Any, name: str, arguments: dict[str, Any] | None = None
) -> mcp_types.CallToolResult:
    params = mcp_types.CallToolRequestParams(name=name, arguments=arguments or {})
    return await _handler(server, "tools/call")(None, params)


async def list_resources_handler(server: Any) -> mcp_types.ListResourcesResult:
    return await _handler(server, "resources/list")(None, mcp_types.PaginatedRequestParams())


async def list_resource_templates_handler(
    server: Any,
) -> mcp_types.ListResourceTemplatesResult:
    return await _handler(server, "resources/templates/list")(
        None, mcp_types.PaginatedRequestParams()
    )


async def read_resource_handler(server: Any, uri: str) -> mcp_types.ReadResourceResult:
    params = mcp_types.ReadResourceRequestParams(uri=uri)
    return await _handler(server, "resources/read")(None, params)


async def list_prompts_handler(server: Any) -> mcp_types.ListPromptsResult:
    return await _handler(server, "prompts/list")(None, mcp_types.PaginatedRequestParams())


async def get_prompt_handler(
    server: Any, name: str, arguments: dict[str, str] | None = None
) -> mcp_types.GetPromptResult:
    params = mcp_types.GetPromptRequestParams(name=name, arguments=arguments)
    return await _handler(server, "prompts/get")(None, params)
