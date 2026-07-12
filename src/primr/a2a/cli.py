"""CLI entry point for the primr-a2a command.

Starts the A2A server, optionally co-hosted with the MCP server.

Requires: pip install primr[a2a]
"""

import argparse
import sys


def main() -> None:
    """Entry point for the primr-a2a command."""
    parser = argparse.ArgumentParser(
        description="Primr A2A Server — Agent-to-Agent protocol interface for company research",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  primr-a2a                         Start A2A server on port 9000
  primr-a2a --port 9001             Start on custom port
  primr-a2a --no-auth               Disable authentication (dev only)
  primr-a2a --no-mcp                A2A only (no MCP co-hosting)

Agent Card:
  curl http://localhost:9000/.well-known/agent.json

Health Check:
  curl http://localhost:9000/ping
""",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="A2A server port (default: 9000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        # Default is loopback so that a stray --no-auth on a multi-user or
        # cloud host doesn't expose research_company / check_jobs / run_qa
        # to the open internet. Operators who want a public listener must
        # opt in explicitly with --host 0.0.0.0 and configure real auth.
        help="Host to bind to (default: 127.0.0.1; use 0.0.0.0 for external access)",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help=(
            "Disable authentication. ONLY safe with --host 127.0.0.1; "
            "combining --no-auth with a non-loopback host exposes the A2A "
            "skill set (research_company, check_jobs, run_qa) to anyone "
            "who can reach the port."
        ),
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Run A2A server only, without co-hosting MCP",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--journal-path",
        type=str,
        default=None,
        help="Path to job journal file (default: output/.mcp_job_journal.json)",
    )

    args = parser.parse_args()

    # Fail-closed guard: --no-auth + public bind is a misconfiguration we
    # refuse to start. The previous CLI accepted this combination and was
    # documented as such in README/ROADMAP, which produced an
    # unauthenticated A2A service exposing research_company on 0.0.0.0:9000
    # whenever someone followed the docs literally.
    if args.no_auth and args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            (
                f"Error: --no-auth requires --host 127.0.0.1 (got {args.host!r}). "
                "Exposing the A2A skills without authentication on a non-loopback "
                "interface lets any reachable client start research jobs and read "
                "job state. Either keep auth on, or bind to loopback."
            ),
            file=sys.stderr,
        )
        sys.exit(2)

    # Check a2a-sdk availability
    try:
        import a2a  # noqa: F401
    except ImportError:
        print(
            "Error: a2a-sdk is not installed. Install with: pip install primr[a2a]",
            file=sys.stderr,
        )
        sys.exit(1)

    import logging

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Create shared MCP server instance (provides job store, security, etc.)
    from primr.mcp_server.server import PrimrMCPServer

    mcp_server = PrimrMCPServer(
        transport="streamable-http",
        port=args.port,
        host=args.host,
        journal_path=args.journal_path,
        require_auth=not args.no_auth,
    )

    # Create A2A server
    from primr.a2a.server import PrimrA2AServer

    a2a_server = PrimrA2AServer(
        mcp_server=mcp_server,
        host=args.host,
        port=args.port,
        require_auth=not args.no_auth,
    )

    try:
        from primr.utils.async_utils import run_sync

        run_sync(a2a_server.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
