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

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)

from mcp.server import Server


def create_spike_server() -> Server:
    """Create a minimal MCP server for protocol validation."""
    server = Server("primr-spike")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="ping",
                description="Simple ping tool that returns pong with timestamp",
                inputSchema={
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

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        if name == "ping":
            message = arguments.get("message", "")
            timestamp = datetime.now().isoformat()
            response = f"pong @ {timestamp}"
            if message:
                response += f" - echo: {message}"
            return [TextContent(type="text", text=response)]

        raise ValueError(f"Unknown tool: {name}")

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available resources."""
        return [
            Resource(
                uri="primr://test",
                name="Test Resource",
                description="A simple test resource for protocol validation",
                mimeType="text/plain",
            )
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> list[ReadResourceContents]:
        """Read a resource by URI."""
        # URI comes in as AnyUrl, convert to string for comparison
        uri_str = str(uri)
        if uri_str == "primr://test" or uri_str == "primr://test/":
            return [
                ReadResourceContents(
                    content=f"Test resource content @ {datetime.now().isoformat()}",
                    mime_type="text/plain",
                )
            ]

        raise ValueError(f"Unknown resource: {uri}")

    return server


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
