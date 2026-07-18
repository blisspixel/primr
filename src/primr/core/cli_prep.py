"""CLI for keyless evidence collection and host-agent handoff."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from primr.core.evidence_bundle import (
    DEFAULT_MAX_PAGES,
    collect_evidence_bundle,
    install_bundled_skill,
)


def _create_prep_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="primr prep",
        description=(
            "Collect a keyless Primr evidence bundle for a capable agent host "
            "to analyze using existing plan capacity."
        ),
    )
    parser.add_argument("company_name", nargs="?", help="Display name for the company.")
    parser.add_argument("company_url", nargs="?", help="Public company website URL.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Maximum first-party pages to collect (1-50, default {DEFAULT_MAX_PAGES}).",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Root directory for the evidence bundle (default: output).",
    )
    parser.add_argument("--skip-recon", action="store_true", help="Skip DNS reconnaissance.")
    parser.add_argument(
        "--skip-hiring",
        action="store_true",
        help="Skip public ATS and careers-page collection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the zero-API-spend collection plan without collecting evidence.",
    )
    parser.add_argument(
        "--install-skill",
        metavar="DIRECTORY",
        help="Install the packaged primr-zero skill at an explicit host skill directory.",
    )
    return parser


def is_prep_command(args: list[str] | None) -> bool:
    """Return whether argv selects the prep subcommand."""

    argv = args if args is not None else sys.argv[1:]
    return bool(argv) and argv[0] == "prep"


def run_prep_cli(args: list[str] | None) -> int:
    """Run ``primr prep`` and return a process exit code."""

    argv = args if args is not None else sys.argv[1:]
    parser = _create_prep_parser()
    parsed = parser.parse_args(argv[1:])
    if parsed.install_skill:
        if parsed.company_name or parsed.company_url:
            print("Error: --install-skill cannot be combined with a company.", file=sys.stderr)
            return 2
        if parsed.dry_run:
            print("Primr Zero skill installation plan:")
            print(f"  Requested destination: {Path(parsed.install_skill).expanduser()}")
            print("  Incremental API spend: $0.00")
            print("  Model calls: 0")
            print("  Network requests: 0")
            print("  Files written: 0 (dry run)")
            return 0
        try:
            installed = install_bundled_skill(Path(parsed.install_skill))
        except (OSError, ValueError) as exc:
            print(f"Primr Zero skill installation failed: {exc}", file=sys.stderr)
            return 1
        print(f"Primr Zero skill installed: {installed}")
        return 0
    if not parsed.company_name or not parsed.company_url:
        parser.print_usage(sys.stderr)
        print("Error: company_name and company_url are required.", file=sys.stderr)
        return 2
    if not 1 <= parsed.max_pages <= 50:
        print("Error: --max-pages must be between 1 and 50.", file=sys.stderr)
        return 2

    if parsed.dry_run:
        print(f"Primr prep plan for {parsed.company_name}:")
        print("  Incremental API spend: $0.00")
        print("  Model calls during collection: 0")
        print("  Host plan usage during collection: none")
        print("  Network requests: 0 (dry run)")
        print("  Files written: 0 (dry run)")
        print(f"  First-party page cap: {parsed.max_pages}")
        print(f"  DNS recon: {'off' if parsed.skip_recon else 'on'}")
        print(f"  Hiring signals: {'off' if parsed.skip_hiring else 'on'}")
        print("  Typical collection time: 5-15 min")
        print("  Synthesis later consumes the chosen host's plan allowance.")
        return 0

    try:
        result = collect_evidence_bundle(
            parsed.company_name,
            parsed.company_url,
            output_root=Path(parsed.output_dir),
            max_pages=parsed.max_pages,
            include_recon=not parsed.skip_recon,
            include_hiring=not parsed.skip_hiring,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Primr prep failed: {exc}", file=sys.stderr)
        return 1

    if result.status == "completed":
        print(f"Primr prep complete for {parsed.company_name}")
    else:
        print(f"Primr prep partial for {parsed.company_name}")
        print("  The bundle is usable, but coverage is incomplete.")
    print("  Incremental API spend: $0.00")
    print(f"  Pages: {result.pages_collected}")
    hiring_status = (
        "skipped" if parsed.skip_hiring else f"{result.hiring_postings} postings indexed"
    )
    recon_status = (
        "skipped"
        if parsed.skip_recon
        else ("collected" if result.recon_collected else "not collected")
    )
    print(f"  Hiring signals: {hiring_status}")
    print(f"  DNS recon: {recon_status}")
    if result.coverage_warnings:
        print("  Coverage notes:")
        for warning in result.coverage_warnings:
            print(f"    - {warning}")
    print(f"  Source index: {result.source_index_path}")
    print(f"  Evidence packet: {result.host_packet_path}")
    print(f"  Host workflow: {result.workflow_path}")
    print(f"  Portable skill: {result.bundle_dir / 'primr-zero'}")
    print(f"  Manifest: {result.manifest_path}")
    print(f"  Bundle: {result.bundle_dir}")
    print(
        "  Next: give the bundle to a research-capable host and have it read the "
        "manifest, source index, evidence packet, host workflow, and primr-zero skill."
    )
    return 0


__all__ = ["is_prep_command", "run_prep_cli"]
