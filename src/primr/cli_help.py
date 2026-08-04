"""Focused help surfaces for onboarding and diagnostics commands."""

from __future__ import annotations

import argparse
import sys

ROOT_HELP = """usage: primr [COMPANY] [WEBSITE] [OPTIONS]

Build evidence-grounded company research, from a zero-API-spend host handoff
to a provider-backed strategic dossier.

Agent host, $0 Primr model API spend
  In an agent chat, say: primr ExampleCo https://example.co
  Primr-aware agents default to Primr Zero when no paid run is requested.
  Terminal collection: primr prep "ExampleCo" https://example.co --dry-run
  Then collect:        primr prep "ExampleCo" https://example.co

Provider-backed dossier
  primr init
  primr doctor
  primr "ExampleCo" https://example.co --dry-run
  primr "ExampleCo" https://example.co
  Always review the fresh estimate before launching a billable run.

Recovery and outputs
  primr --check-jobs          Read pending cloud and latest local state
  primr --resume-latest       Finalize completed provider jobs
  primr "ExampleCo" https://example.co --resume-local
                              Continue the latest local interrupted run
  primr --list-recent         List recent deliverables and diagnostics
  primr --clear-jobs          Confirm removal of pending recovery records
  primr --clear-jobs --yes    Non-interactive destructive confirmation

Other keyless and agent workflows
  primr recon example.co      Run standalone DNS intelligence
  primr render report.md      Markdown to DOCX/TXT at $0
  primr skills "ExampleCo" https://example.co --dry-run
  primr mcp                   Start the MCP server

Common research options
  --mode {scrape,deep,full,premium,parallel}
  --platform {azure,aws,gcp,private,agnostic,ms}
  --budget N                  Refuse to start above N USD
  --no-ai-strategy
  --output-dir DIRECTORY
  --json
  --verbose

Focused help
  primr init --help
  primr doctor --help
  primr prep --help
  primr recon --help
  primr update --help

Reference
  primr --help-all            Show every command and advanced option
  primr --version
"""

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

UPDATE_COMMAND_ALIASES = frozenset({"update", "upgrade", "self-update"})


def create_update_parser(command: str = "update") -> argparse.ArgumentParser:
    """Create the strict, side-effect-free parser shared by update aliases."""
    if command not in UPDATE_COMMAND_ALIASES:
        raise ValueError(f"Unsupported update command: {command}")
    parser = argparse.ArgumentParser(
        prog=f"primr {command}",
        description="Check for or install the latest published Primr release.",
        epilog=(
            f"Examples:\n  primr {command} --check\n  primr {command}\n  primr {command} --yes"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check",
        "--check-only",
        dest="check_only",
        action="store_true",
        help="Report whether an update is available without installing it",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Confirm installation without an interactive prompt",
    )
    return parser


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
                if "--yes" in flags:
                    help_text = (
                        "With 'init', accept safe defaults; with destructive commands, "
                        "confirm the requested action"
                    )
                else:
                    help_text = f"With '{command_name}', {description}"
            else:
                help_text = description[0].upper() + description[1:]
            parser.add_argument(*flags, action="store_true", help=help_text)


def _create_scoped_help_parser(command: str) -> argparse.ArgumentParser:
    """Create the concise help surface for an existing positional command."""
    if command in UPDATE_COMMAND_ALIASES:
        return create_update_parser(command)
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
    """Exit through argparse with concise help for focused commands."""
    argv = list(args) if args is not None else sys.argv[1:]
    if not argv or argv[0] not in {"init", "doctor", *UPDATE_COMMAND_ALIASES}:
        return
    if not any(argument in {"-h", "--help"} for argument in argv[1:]):
        return
    _create_scoped_help_parser(argv[0]).parse_args(["--help"])


def maybe_print_root_help(args: list[str] | None) -> None:
    """Exit with a concise root workflow when root help is requested."""
    argv = list(args) if args is not None else sys.argv[1:]
    if argv not in (["-h"], ["--help"]):
        return
    print(ROOT_HELP)
    raise SystemExit(0)
