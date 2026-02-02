"""
CLI entry point for MCP server.

This module provides the `primr-mcp` command for running the MCP server.

Requirements: 1.1, 1.2, 14.1-14.3
"""

import argparse
import asyncio
import sys

from primr.mcp_server.server import create_mcp_server


def main() -> None:
    """Entry point for the primr-mcp command."""
    parser = argparse.ArgumentParser(
        description="Primr MCP Server - AI agent interface for company research",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  primr-mcp --stdio              Run with stdio transport (for Claude Desktop)
  primr-mcp --http --port 8000   Run with HTTP transport on port 8000
  primr-mcp --http --no-auth     Run HTTP without authentication (dev only)

For Claude Desktop integration, add to claude_desktop_config.json:
  {
    "mcpServers": {
      "primr": {
        "command": "primr-mcp",
        "args": ["--stdio"]
      }
    }
  }

Authentication (HTTP mode):
  Set MCP_ADMIN_TOKENS environment variable with comma-separated admin tokens.
  Or use JWT tokens with 'sub' claim for client_id and 'role=admin' for admin access.
""",
    )
    
    # Transport options
    transport_group = parser.add_mutually_exclusive_group()
    transport_group.add_argument(
        "--stdio",
        action="store_true",
        default=True,
        help="Use stdio transport (default)",
    )
    transport_group.add_argument(
        "--http",
        action="store_true",
        help="Use streamable HTTP transport",
    )
    
    # HTTP options
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP port (default: 8000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="HTTP host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--allow-plaintext",
        action="store_true",
        help="Allow plaintext HTTP (for local development only)",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication (for local development only)",
    )
    
    # Logging options
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    
    # Other options
    parser.add_argument(
        "--journal-path",
        type=str,
        default=None,
        help="Path to job journal file (default: output/.mcp_job_journal.json)",
    )
    
    args = parser.parse_args()
    
    # Determine transport
    transport = "streamable-http" if args.http else "stdio"
    
    # Create and run server
    server = create_mcp_server(
        transport=transport,
        port=args.port,
        host=args.host,
        log_level=args.log_level,
        journal_path=args.journal_path,
        allow_plaintext=args.allow_plaintext,
        require_auth=not args.no_auth,
    )
    
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
