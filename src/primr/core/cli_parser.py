"""CLI strategy discovery + command-dispatch helpers.

Extracted from `primr.core.cli` for isolated unit testing.

These are the small pure helpers that surround the (still in-place)
`_create_parser` + `parse_args` functions: YAML-driven strategy choice
discovery and the `_determine_command` dispatcher that maps a parsed
argparse Namespace to the right `Command` enum value.

The bulk parser (`_create_parser`, `parse_args`) is intentionally left
in cli.py for now because it threads through 60+ argparse options and would
not gain meaningful test coverage from extraction.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TypeVar

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)
_CommandT = TypeVar("_CommandT")


# The argparse help epilog (examples + mode reference). Kept here rather than
# inline in cli._create_parser so cli.py stays under its file-size ceiling.
CLI_EPILOG = """
Research Modes:
  full     Scrape + standard research + one AI strategy (~34-53 min, ~$0.89 with XAI+Gemini) [DEFAULT]
  scrape   Scrape website + extract insights only (~5-10 min, ~$0.10)
  deep     Autonomous AI web research + hiring signals (~11-17 min, ~$2.50)
  parallel Both engines in parallel (legacy, ~25 min)

Common first-run path:
  primr init                                         # Guided first-run setup
  primr doctor                                       # System diagnostics
  primr keys set xai                                 # Store xAI/Grok key in user config
  primr keys set gemini                              # Store Gemini key in user config
  primr "Acme Corp" https://acme.example --dry-run  # Estimate cost and time only
  primr "Acme Corp" https://acme.example             # Launch after you accept the estimate
  primr --check-jobs                                 # Read-only status (cloud + latest local)
  primr --list-recent                                # Recent deliverables vs diagnostics
  primr --resume-latest                              # Finalize completed interrupted cloud jobs

Examples:
  primr prep "Acme Corp" https://acme.example       # $0 API evidence bundle for a host agent
  primr skills "Acme Corp" https://acme.example     # Agent Skills pack (~$0.30 default)
  primr "Acme Corp" acme.example --mode deep
  primr "Acme Corp" acme.example --mode scrape       # Build Site Corpus + Extract Insights
  primr keys list                                    # Show configured provider keys
  primr doctor --fix                                 # Diagnose, then launch guided fixes
  primr update                                       # Upgrade primr to the latest release
  primr update --check                               # Check for a newer version without installing
  primr --qa "Acme Corp"                             # Show detailed QA analysis
  primr --qa-recent 5                                # Show QA summary for recent reports
  primr improve "output/Company_Strategic_Overview_03-06-2026.md"   # Improve one output
  primr improve "output/Company_AI_Strategy_AZURE_03-06-2026.md" --improve-agentic
  primr refine "Acme Corp"                           # QA loop: regenerate weak sections until grade >= 90
  primr refine "Acme Corp" --target-grade 85 --in-place
  primr calibrate "Acme Corp"                        # Audit confidence-label traceability (writes sidecar JSON)
  primr calibrate --calibrate-recent 10 --dry-run    # Preview judge-call count/cost, no spend
  primr --banner                                     # Show startup banner only

AI Strategy recovery:
  primr "Acme Corp" https://acme.example --resume-local
  primr --resume-latest                               # Recover + finalize completed cloud jobs
  Do not use --ai-strategy-only until its in-command estimate and approval gate is available.

Versioned Eval (offline-first, no API spend by default):
  primr --eval --eval-id eval-2026-02-r1
  primr --eval --eval-id eval-2026-02-r1 --eval-profiles full lite fast
  primr --eval --eval-id eval-2026-02-r1 --eval-company "ExampleCo"
  primr --eval --eval-id eval-2026-02-r1 --eval-llm-judge --eval-judge-max-cost 0.25
  primr --eval --eval-id eval-2026-02-r1 --eval-run-missing --eval-manifest eval_companies.csv --eval-max-new-runs 2 --eval-max-estimated-cost 12
  primr --eval --eval-id eval-2026-02-r1 --eval-stage-scorecard --eval-stage-quality quality.json

Company profiles and research memory:
  primr company track "Acme Corp" https://acme.com  # Track a company profile locally
  primr company list                                # List tracked company profiles
  primr company show "Acme Corp"                    # Show one tracked company profile
  primr company export "Acme Corp"                  # Export local profile + hypotheses bundle
  primr memory "Acme Corp"                           # View hypotheses for a company
  primr --memory-list                                # List all companies with memory
  primr orchestrate "Acme Corp" https://acme.com    # Run orchestrated research
  primr --orchestrate --max-cost 5.0                 # With cost budget
  primr roadmap                                      # Show roadmap overview
  primr --roadmap-version v1.7.0                     # Show version details

Domain Intelligence (Recon):
  primr recon acme.com                               # DNS intelligence lookup
  primr recon acme.com --json                        # Structured JSON output
  primr recon acme.com --md                          # Markdown report
  primr recon acme.com --services                    # M365 vs tech stack split
  primr recon acme.com --full                        # Everything
  primr recon batch domains.txt                      # Batch mode
  primr recon batch domains.txt -c 10                # Batch with concurrency
  primr recon doctor                                 # Connectivity check

"""


def enable_shell_completion(parser: argparse.ArgumentParser) -> None:
    """Enable argcomplete tab completion if argcomplete is installed.

    Soft and opt-in: with argcomplete absent this is a no-op, so completion adds
    no hard dependency. To use it, install argcomplete and run
    ``activate-global-python-argcomplete`` once (or eval
    ``register-python-argcomplete primr`` in your shell rc). The
    ``# PYTHON_ARGCOMPLETE_OK`` marker near the top of cli.py lets the global
    completion script recognize primr.
    """
    try:
        import argcomplete
    except ImportError:
        return
    argcomplete.autocomplete(parser)


def add_inference_arguments(parser: argparse.ArgumentParser) -> None:
    """Register capability-routing options and the host-billing safety gate."""

    parser.add_argument(
        "--inference",
        choices=["cloud", "hybrid"],
        default="cloud",
        dest="inference_profile",
        help="Inference profile for routed experimental stages",
    )
    parser.add_argument(
        "--acknowledge-host-agent-may-bill",
        action="store_true",
        help=(
            "Allow the unpromoted hybrid Codex pilot after acknowledging that its "
            "session may use metered billing outside Primr's estimate (single runs only)"
        ),
    )


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
            "description": "Business-first AI portfolio, economics, operating model, architecture, and governance",
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


def _determine_command(
    args: argparse.Namespace,
    command_factory: Callable[[str], _CommandT],
    positional_commands: Mapping[str, _CommandT],
    flag_commands: Sequence[tuple[str, _CommandT]],
) -> _CommandT:
    """Determine which command to run based on parsed args."""
    if args.company:
        cmd = positional_commands.get(args.company.lower())
        if cmd is not None:
            return cmd

    for attr, cmd in flag_commands:
        if getattr(args, attr, None):
            return cmd

    if getattr(args, "qa_recent", None) is not None:
        return command_factory("qa-recent")

    if getattr(args, "enrich", False) and getattr(args, "batch", None):
        return command_factory("enrich")

    if getattr(args, "batch", None):
        return command_factory("batch")

    if args.csv:
        return command_factory("batch")

    return command_factory("research")
