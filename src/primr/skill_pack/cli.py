"""CLI subcommand: `primr skills <Company> <url> [options]`.

Mirrors the `primr recon` and `primr keys` patterns — sniffed before
argparse in core/cli.py so we control the help message and option layout
ourselves.
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from primr.skill_pack.config import (
    DEFAULT_ROLES,
    DEFAULT_SKILLS_PER_ROLE,
    MAX_ROLES,
    MAX_SKILLS_PER_ROLE,
    MIN_ROLES,
    MIN_SKILLS_PER_ROLE,
    SkillPackConfig,
    SkillPackFormat,
)
from primr.skill_pack.evidence import collect_evidence
from primr.skill_pack.pipeline import run_skill_pack_pipeline

logger = logging.getLogger(__name__)


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="primr skills",
        description=(
            "Generate a QA-refined Agent Skills pack for a company. "
            "Produces a Claude/Cursor/VS Code-ready roles/ tree AND a "
            "Microsoft 365 Copilot Cowork sideload .zip from the same "
            "byte-identical SKILL.md files."
        ),
    )
    parser.add_argument(
        "company_name",
        help="Display name for the company (use quotes for multi-word names).",
    )
    parser.add_argument(
        "company_url",
        nargs="?",
        default=None,
        help="Company website URL (required unless --from-report is used).",
    )
    parser.add_argument(
        "--roles",
        type=int,
        default=DEFAULT_ROLES,
        help=(
            f"Number of roles to generate ({MIN_ROLES}-{MAX_ROLES}, "
            f"default {DEFAULT_ROLES})."
        ),
    )
    parser.add_argument(
        "--skills-per-role",
        type=int,
        default=DEFAULT_SKILLS_PER_ROLE,
        help=(
            f"Skills per role ({MIN_SKILLS_PER_ROLE}-{MAX_SKILLS_PER_ROLE}, "
            f"default {DEFAULT_SKILLS_PER_ROLE})."
        ),
    )
    parser.add_argument(
        "--formats",
        choices=[f.value for f in SkillPackFormat],
        default=SkillPackFormat.BOTH.value,
        help="Which artifact formats to emit (default: both).",
    )
    parser.add_argument(
        "--from-report",
        type=str,
        default=None,
        help=(
            "Path to an existing primr report directory (e.g. "
            "working/<company>/<timestamp>/) containing recon + hiring "
            "evidence. Skips the standalone evidence-collection step."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory where the dated pack folder is written (default: output/).",
    )
    parser.add_argument(
        "--max-refine-iterations",
        type=int,
        default=2,
        help="Cap on per-skill refinement turns (default: 2).",
    )
    parser.add_argument(
        "--no-coherence-pass",
        action="store_true",
        help="Skip the pack-level coherence LLM pass (saves ~$0.02).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Estimate cost and time, then exit without running the pipeline.",
    )
    return parser


def _is_skills_command(args: list[str] | None) -> bool:
    """True when sys.argv[1] == 'skills' (the top-level subcommand sniff)."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] == "skills"


def _estimate(config: SkillPackConfig, has_from_report: bool) -> tuple[float, int]:
    """Cheap cost / time estimate for the dry-run path.

    Numbers come from the budget plan in the design doc:
      - Evidence collection (recon + hiring): ~$0.02-0.05, 30-90s
      - Discovery: ~$0.02
      - Authoring: ~$0.03 per role
      - Refinement (only if HARD findings): ~$0.02 per failing skill
      - Pack coherence: ~$0.02
    """
    cost = 0.0
    minutes = 0.0
    if not has_from_report:
        cost += 0.04
        minutes += 1.0
    cost += 0.02  # discovery
    cost += 0.03 * config.roles_count  # authoring
    # Assume 30% of skills need refinement (conservative).
    cost += 0.015 * config.roles_count * config.skills_per_role * 0.3
    if config.run_pack_coherence_pass:
        cost += 0.02
    minutes += 0.5 * config.roles_count
    return cost, max(1, int(minutes))


def run_skills_cli(args: list[str] | None) -> int:
    """Entry point. Returns a CLI exit code."""
    argv = args if args is not None else sys.argv[1:]
    parser = _create_parser()
    parsed = parser.parse_args(argv[1:])  # strip leading 'skills'

    company_name = parsed.company_name
    company_url = parsed.company_url
    from_report = parsed.from_report

    if not from_report and not company_url:
        print(
            "Error: company_url is required when --from-report is not provided.",
            file=sys.stderr,
        )
        return 2

    try:
        config = SkillPackConfig(
            roles_count=parsed.roles,
            skills_per_role=parsed.skills_per_role,
            formats=SkillPackFormat(parsed.formats),
            max_refine_iterations=parsed.max_refine_iterations,
            run_pack_coherence_pass=not parsed.no_coherence_pass,
            reuse_existing_evidence=bool(from_report),
        )
        config.validate()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if parsed.dry_run:
        cost, minutes = _estimate(config, has_from_report=bool(from_report))
        print(f"Skill pack estimate for {company_name}:")
        print(f"  Roles: {config.roles_count} x {config.skills_per_role} skills")
        print(f"  Formats: {config.formats.value}")
        print(f"  Estimated cost: ~${cost:.2f}")
        print(f"  Estimated time: ~{minutes} min")
        return 0

    output_dir = Path(parsed.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Working directory: either the supplied --from-report path, or a fresh
    # temp dir that we fill with recon + hiring before the pipeline runs.
    if from_report:
        working_dir = Path(from_report).resolve()
        if not working_dir.exists():
            print(f"Error: --from-report path does not exist: {working_dir}", file=sys.stderr)
            return 2
        print(f"Using existing evidence from {working_dir}")
    else:
        # Standalone: create a temp working dir and collect evidence.
        assert company_url is not None
        tmp = Path(tempfile.mkdtemp(prefix="primr-skill-pack-"))
        working_dir = tmp
        print(f"Collecting recon + hiring evidence for {company_name}...")
        outcome = collect_evidence(
            company_name=company_name,
            company_url=company_url,
            working_dir=working_dir,
        )
        recon_path = outcome.get("recon")
        hiring_path = outcome.get("hiring")
        if not recon_path and not hiring_path:
            print(
                "Error: Could not collect any evidence (recon and hiring both "
                "failed). Try --from-report against an existing primr run.",
                file=sys.stderr,
            )
            return 1

    try:
        pack, artifacts = run_skill_pack_pipeline(
            company_name=company_name,
            company_url=company_url,
            working_dir=working_dir,
            config=config,
            output_dir=output_dir,
        )
    except FileNotFoundError as exc:
        print(f"Evidence missing: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1

    print()
    print(f"Skill pack complete for {pack.company_name}")
    print(f"  Roles: {len(pack.roles)} (target {config.roles_count})")
    print(f"  Total skills: {pack.total_skills}")
    if artifacts.claude_tree_root:
        print(f"  Claude/Cursor tree: {artifacts.claude_tree_root}")
    if artifacts.cowork_zip_path:
        print(f"  Cowork sideload zip: {artifacts.cowork_zip_path}")
    if artifacts.report_md_path:
        print(f"  Pack report: {artifacts.report_md_path}")
    if pack.dropped_roles:
        print(f"  Dropped roles: {len(pack.dropped_roles)} (see report)")
    return 0


__all__ = ["_is_skills_command", "run_skills_cli"]
