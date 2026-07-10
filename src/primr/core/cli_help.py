"""Focused help surfaces for onboarding and diagnostics commands."""

from __future__ import annotations

import argparse
import sys

_INIT_DOCTOR_OPTION_SPECS: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
    "doctor": (
        (
            ("--fix",),
            "launch guided setup for missing keys and browser dependencies",
        ),
        (
            ("--scraper-stats",),
            "show per-tier scrape success rate, latency p95, and content quality across recent runs",
        ),
    ),
    "init": (
        (
            ("--non-interactive",),
            "print missing setup steps without prompting",
        ),
        (
            ("--yes", "-y"),
            "accept safe defaults such as browser installation",
        ),
        (("--skip-browsers",), "skip Playwright browser installation"),
        (("--no-doctor",), "skip the final doctor verification"),
    ),
}


def add_init_doctor_arguments(
    parser: argparse.ArgumentParser,
    *,
    command: str | None = None,
) -> None:
    """Register init and doctor flags from one canonical definition."""
    commands = (command,) if command is not None else ("doctor", "init")
    for command_name in commands:
        try:
            specifications = _INIT_DOCTOR_OPTION_SPECS[command_name]
        except KeyError as exc:
            raise ValueError(f"Unsupported scoped command: {command_name}") from exc
        for flags, description in specifications:
            if command is None:
                help_text = f"With '{command_name}', {description}"
            else:
                help_text = description[0].upper() + description[1:]
            parser.add_argument(*flags, action="store_true", help=help_text)


def _create_scoped_help_parser(command: str) -> argparse.ArgumentParser:
    """Create the concise help surface for an existing positional command."""
    if command == "init":
        parser = argparse.ArgumentParser(
            prog="primr init",
            description=(
                "Configure provider keys and browser dependencies, then verify the installation."
            ),
            epilog=(
                "Examples:\n"
                "  primr init\n"
                "  primr init --non-interactive\n"
                "  primr init --yes --skip-browsers"
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        add_init_doctor_arguments(parser, command=command)
        return parser

    if command != "doctor":
        raise ValueError(f"Unsupported scoped command: {command}")
    parser = argparse.ArgumentParser(
        prog="primr doctor",
        description=(
            "Check the runtime, providers, dependencies, filesystem, connectivity, and updates."
        ),
        epilog=("Examples:\n  primr doctor\n  primr doctor --fix\n  primr doctor --scraper-stats"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_init_doctor_arguments(parser, command=command)
    return parser


def maybe_print_scoped_help(args: list[str] | None) -> None:
    """Exit through argparse with concise help for init and doctor."""
    argv = list(args) if args is not None else sys.argv[1:]
    if not argv or argv[0] not in {"init", "doctor"}:
        return
    if not any(argument in {"-h", "--help"} for argument in argv[1:]):
        return
    _create_scoped_help_parser(argv[0]).parse_args(["--help"])
