"""CLI strategy discovery + command-dispatch helpers.

Extracted from `primr.core.cli` for isolated unit testing.

These are the small pure helpers that surround the (still in-place)
`_create_parser` + `parse_args` functions: YAML-driven strategy choice
discovery and the `_determine_command` dispatcher that maps a parsed
argparse Namespace to the right `Command` enum value.

The bulk parser (`_create_parser`, `parse_args`) is intentionally left
in cli.py for now — it threads through 60+ argparse options and would
not gain meaningful test coverage from extraction.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml  # type: ignore[import-untyped]

if TYPE_CHECKING:
    import argparse

    from primr.core.cli import Command

logger = logging.getLogger(__name__)


def _discover_strategies() -> list[dict[str, str]]:
    """Discover available strategy types from YAML configs.

    Returns list of dicts with 'name', 'display_name', 'description',
    'status'. Results are cached after first call.
    """
    if hasattr(_discover_strategies, "_cache"):
        return _discover_strategies._cache  # type: ignore[attr-defined]

    strategies_dir = Path(__file__).parent.parent / "prompts" / "strategies"
    results: list[dict[str, str]] = [
        {
            "name": "ai",
            "display_name": "AI Strategy",
            "description": "AI transformation roadmap with vendor-specific recommendations",
            "status": "active",
        },
    ]

    if strategies_dir.exists():
        for yaml_path in sorted(strategies_dir.glob("*.yaml")):
            stem = yaml_path.stem
            if stem in ("ai_strategy", "ai_first_transformation"):
                continue
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                meta = data.get("meta", {})
                status = meta.get("status", "active")
                if status == "placeholder":
                    continue
                desc = meta.get("cli_description") or meta.get("description", "")
                display = meta.get("name", stem.replace("_", " ").title())
                results.append(
                    {
                        "name": stem,
                        "display_name": display,
                        "description": desc,
                        "status": status,
                    }
                )
            except Exception as e:
                logger.warning("Failed to load strategy %s: %s", yaml_path.name, e)
                continue

    _discover_strategies._cache = results  # type: ignore[attr-defined]
    return results


def _get_strategy_choices() -> list[str]:
    """Get valid --strategy-type choices from YAML discovery."""
    return [s["name"] for s in _discover_strategies()]


def _get_strategy_help() -> str:
    """Build --strategy-type help text from YAML descriptions."""
    strategies = _discover_strategies()
    parts = ["Strategy type. Options:"]
    for s in strategies:
        short_desc = s["description"]
        if len(short_desc) > 80:
            short_desc = short_desc[:77] + "..."
        parts.append(f"  {s['name']}: {short_desc}")
    parts.append("Use --list-strategies for details.")
    return " ".join(parts)


def add_research_input_arguments(parser: argparse.ArgumentParser) -> None:
    """Register research-input and framing arguments on the parser.

    Grouped here rather than inline in ``cli._create_parser`` so the framing
    surface can grow without bloating ``cli.py`` (pinned by the file-size
    ratchet). Covers operator-supplied context (discovery notes, context files,
    strategy type) and the tradecraft framing facets (purpose, audience,
    decision, core question) that resolve into a ``ResearchFraming``.
    """
    from primr.core.research_framing import ResearchPurpose

    parser.add_argument(
        "--discovery-notes",
        type=str,
        help="Path to discovery notes file (freeform meeting insights)",
    )
    parser.add_argument("--context", type=str, nargs="+", help="Context files for deep mode")
    parser.add_argument("--context-folder", type=str, help="Use working folder as context")
    parser.add_argument(
        "--strategy-type",
        type=str,
        choices=_get_strategy_choices(),
        default="ai",
        help=_get_strategy_help(),
    )
    # Research framing (tradecraft Step 1): operator intent threaded into the
    # analytical stages. See core/research_framing.py.
    parser.add_argument(
        "--purpose",
        type=str,
        choices=[p.value for p in ResearchPurpose],
        help="What the research is for; orients the analysis (default: general).",
    )
    parser.add_argument(
        "--audience",
        type=str,
        help="Who the brief is for (e.g. 'VP Sales, first meeting').",
    )
    parser.add_argument(
        "--decision",
        type=str,
        help="The decision this research informs.",
    )
    parser.add_argument(
        "--question",
        type=str,
        help="The single most important question the brief should answer.",
    )


def _determine_command(args: argparse.Namespace) -> Command:
    """Determine which command to run based on parsed args."""
    # Import here to avoid a circular dependency (cli imports from this module).
    from primr.core.cli import _FLAG_COMMANDS, _POSITIONAL_COMMANDS, Command

    if args.company:
        cmd = _POSITIONAL_COMMANDS.get(args.company.lower())
        if cmd is not None:
            return cmd

    for attr, cmd in _FLAG_COMMANDS:
        if getattr(args, attr, None):
            return cmd

    if getattr(args, "qa_recent", None) is not None:
        return Command.QA_RECENT

    if getattr(args, "enrich", False) and getattr(args, "batch", None):
        return Command.ENRICH

    if getattr(args, "batch", None):
        return Command.BATCH

    if args.csv:
        return Command.BATCH

    return Command.RESEARCH
