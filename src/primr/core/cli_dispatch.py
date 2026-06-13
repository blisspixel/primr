"""Early subcommand routing for the ``primr`` CLI.

A small set of subcommands (``mcp``, ``skills``, ``update``) are *delegated*
to their own entry points before the main argparse parser runs, rather than
being parsed as research arguments. This module holds the matching
predicate/runner pairs so the routing boilerplate lives in one place instead
of bloating ``cli.py`` (which is a pinned monster under the file-size ratchet).

Each pair is ``is_<x>_command(args)`` (does this argv select the subcommand?)
and its runner (``run_<x>(args)``), and ``cli.main`` consults them in order.
Imports of the target entry points stay lazy so importing ``cli`` does not
pull in the MCP server, skill_pack, or update machinery.
"""

from __future__ import annotations

import sys


def is_mcp_command(args: list[str] | None) -> bool:
    """Check if the command line is a ``primr mcp ...`` invocation."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] == "mcp"


def run_mcp(args: list[str] | None) -> int:
    """Delegate ``primr mcp ...`` to the MCP server entry point.

    With no additional args, defaults to ``--stdio`` since that's the
    canonical mode for AI-host integration (Claude Code, Cursor, etc.).
    Pass-through args allow ``primr mcp --http --port 8000`` to still work.
    """
    from primr.mcp_server.cli import main as mcp_main

    argv = args if args is not None else sys.argv[1:]
    mcp_argv = argv[1:]  # strip the "mcp" token
    if not mcp_argv:
        mcp_argv = ["--stdio"]

    saved_argv = sys.argv
    try:
        sys.argv = ["primr-mcp", *list(mcp_argv)]
        mcp_main()
        return 0
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    finally:
        sys.argv = saved_argv


def is_skills_command(args: list[str] | None) -> bool:
    """Check if the command line is a ``primr skills ...`` invocation."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] == "skills"


def run_skills(args: list[str] | None) -> int:
    """Delegate to the skill_pack CLI handler."""
    try:
        from primr.skill_pack.cli import run_skills_cli
    except ImportError as exc:
        print(f"Error: skill_pack module unavailable: {exc}", file=sys.stderr)
        return 1
    return run_skills_cli(args)


def is_update_command(args: list[str] | None) -> bool:
    """Check if the command line is a ``primr update ...`` invocation."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] in {"update", "upgrade", "self-update"}


def run_update_cli(args: list[str] | None) -> int:
    """Delegate ``primr update`` to the self-upgrade handler."""
    from primr.core.cli_update import run_update

    argv = args if args is not None else sys.argv[1:]
    rest = argv[1:]  # strip the "update" token
    check_only = "--check" in rest or "--check-only" in rest
    yes = "-y" in rest or "--yes" in rest
    return run_update(check_only=check_only, yes=yes)
