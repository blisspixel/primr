"""Lightweight composition boundary for the public ``primr`` command."""

from __future__ import annotations

import sys

from primr import __version__
from primr.cli_help import maybe_print_root_help, maybe_print_scoped_help


def main(args: list[str] | None = None) -> int:
    """Handle deterministic fast paths before loading the operational CLI."""
    argv = list(args) if args is not None else sys.argv[1:]

    maybe_print_root_help(argv)
    maybe_print_scoped_help(argv)

    if argv == ["--version"]:
        print(f"primr {__version__}")
        return 0

    if argv and argv[0] == "prep":
        from primr.cli_prep import run_prep_cli

        return run_prep_cli(argv)

    from primr.core.cli import main as run_operational_cli

    return run_operational_cli(argv)


__all__ = ["main"]
