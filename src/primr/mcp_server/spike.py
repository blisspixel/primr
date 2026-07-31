"""
Protocol Spike - Minimal MCP server to validate SDK assumptions.

This module creates a minimal MCP server with:
- One dummy tool (ping)
- One dummy resource (primr://test)

Used to validate:
- SDK installation and basic server creation
- JSON-RPC framing
- Tool/resource listing
- Stdio and HTTP transport
- Resource subscription negotiation
- Stdout purity in stdio mode

Run with: python -m primr.mcp_server.spike [--stdio | --http]
Test with: npx @modelcontextprotocol/inspector
"""

import asyncio
import sys
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListResourcesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)


def create_spike_server() -> Server:
    """Create a minimal MCP server for protocol validation."""

    async def list_tools(_ctx: object, _params: PaginatedRequestParams | None) -> ListToolsResult:
        """List available tools."""
        return ListToolsResult(
            tools=[
                Tool(
                    name="ping",
                    description="Simple ping tool that returns pong with timestamp",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Optional message to echo back",
                            }
                        },
                        "required": [],
                    },
                )
            ]
        )

    async def call_tool(_ctx: object, params: CallToolRequestParams) -> CallToolResult:
        """Handle tool calls."""
        arguments: dict[str, Any] = params.arguments or {}
        if params.name == "ping":
            message = arguments.get("message", "")
            timestamp = datetime.now().isoformat()
            response = f"pong @ {timestamp}"
            if message:
                response += f" - echo: {message}"
            return CallToolResult(content=[TextContent(type="text", text=response)])

        raise MCPError(INVALID_PARAMS, f"Unknown tool: {params.name}")

    async def list_resources(
        _ctx: object, _params: PaginatedRequestParams | None
    ) -> ListResourcesResult:
        """List available resources."""
        return ListResourcesResult(
            resources=[
                Resource(
                    uri="primr://test",
                    name="Test Resource",
                    description="A simple test resource for protocol validation",
                    mime_type="text/plain",
                )
            ]
        )

    async def read_resource(_ctx: object, params: ReadResourceRequestParams) -> ReadResourceResult:
        """Read a resource by URI."""
        if params.uri in ("primr://test", "primr://test/"):
            return ReadResourceResult(
                contents=[
                    TextResourceContents(
                        uri=params.uri,
                        text=f"Test resource content @ {datetime.now().isoformat()}",
                        mime_type="text/plain",
                    )
                ]
            )

        raise MCPError(INVALID_PARAMS, f"Unknown resource: {params.uri}")

    return Server(
        "primr-spike",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
    )


async def run_stdio() -> None:
    """Run the spike server with stdio transport."""
    server = create_spike_server()

    # Redirect all logging to stderr to preserve stdout for JSON-RPC
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Entry point for the spike server."""
    import argparse

    parser = argparse.ArgumentParser(description="Primr MCP Protocol Spike")
    parser.add_argument(
        "--stdio",
        action="store_true",
        default=True,
        help="Use stdio transport (default)",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Use HTTP transport",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP port (default: 8000)",
    )

    args = parser.parse_args()

    if args.http:
        print("HTTP transport not yet implemented in spike", file=sys.stderr)
        sys.exit(1)
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
