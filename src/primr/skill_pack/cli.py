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
        help=(f"Number of roles to generate ({MIN_ROLES}-{MAX_ROLES}, default {DEFAULT_ROLES})."),
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
        "--from-jd",
        type=str,
        default=None,
        help=(
            "Path to a local job description or role brief. The file is "
            "sanitized and added to the hiring evidence layer before planning "
            "and authoring. Can be used with --roles-override for a single "
            "well-specified role, or as the sole evidence source when no URL "
            "or report directory is available."
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
        "--optimize-triggers",
        action="store_true",
        help=(
            "Measure and optimize each skill's trigger description: generate "
            "should/should-not-trigger queries, score the description against "
            "a discovery simulator, and improve it when below threshold (kept "
            "only if it beats the original on a held-out split). Adds LLM "
            "calls per skill; off by default."
        ),
    )
    parser.add_argument(
        "--with-evals",
        action="store_true",
        help=(
            "Behavioral evaluation: for each skill, run task cases WITH the "
            "skill vs WITHOUT it, grade both, and report the pass-rate delta "
            "(proves the skill changes output). Also writes evals/evals.json "
            "per skill. Expensive (~3 LLM calls per case per skill); off by "
            "default."
        ),
    )
    parser.add_argument(
        "--emit-agent-metadata",
        action="store_true",
        help=(
            "Add optional primr-namespaced metadata to each SKILL.md "
            "frontmatter. Off by default so skills stay clean and portable."
        ),
    )
    parser.add_argument(
        "--allow-recon-only",
        action="store_true",
        help=(
            "Proceed even when no job-posting evidence was gathered. By "
            "default the pipeline fails closed in this state because "
            "DNS-only role discovery is structurally incomplete for "
            "services / reseller / consultancy companies."
        ),
    )
    parser.add_argument(
        "--roles-override",
        type=str,
        default=None,
        help=(
            'Comma-separated list of role labels (e.g. "Account Executive,'
            'Cloud Migration Consultant") that bypasses automatic planning. '
            "Up to MAX_ROLES labels accepted. Each label feeds straight to "
            "authoring with archetype matching applied. Mutually exclusive "
            "with --roles-add / --roles-skip."
        ),
    )
    parser.add_argument(
        "--roles-add",
        type=str,
        default=None,
        help=(
            "Comma-separated list of role labels to ADD to the discovered "
            'roster (e.g. "Account Executive,Procurement Manager"). '
            "Composes with --from-plan to augment a saved plan. Added "
            "roles are marked with provenance=override and authored "
            "alongside discovered roles. Subject to the MAX_ROLES cap "
            "with operator-priority (plausible roles trim first)."
        ),
    )
    parser.add_argument(
        "--roles-skip",
        type=str,
        default=None,
        help=(
            "Comma-separated list of role labels or kebab-case slugs to "
            'REMOVE from the discovered roster (e.g. "Marketing Manager,'
            'devops-engineer"). Composes with --from-plan to prune a '
            "saved plan. Unmatched names log a warning. Hard error if "
            "curation leaves an empty roster."
        ),
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Run through the planning step, persist role_plan.md + "
            "role_plan.json in the working directory, then exit before "
            "authoring. Useful for inspecting the planned roster before "
            "paying for skill authoring."
        ),
    )
    parser.add_argument(
        "--from-plan",
        type=str,
        default=None,
        help=(
            "Path to a previously-persisted role_plan.json. Skips the "
            "planning LLM calls and authors against the plan's "
            "final_roster verbatim. Supports the plan -> inspect -> "
            "author workflow."
        ),
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


def _estimate(config: SkillPackConfig, *, will_collect_evidence: bool) -> tuple[float, int]:
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
    if will_collect_evidence:
        cost += 0.04
        minutes += 1.0
    cost += 0.02  # discovery
    cost += 0.03 * config.roles_count  # authoring
    # Assume 30% of skills need refinement (conservative).
    cost += 0.015 * config.roles_count * config.skills_per_role * 0.3
    if config.run_pack_coherence_pass:
        cost += 0.02
    if config.optimize_triggers:
        # ~3-4 LLM calls per skill (generate evals, score, optimize, re-score).
        cost += 0.02 * config.roles_count * config.skills_per_role
        minutes += 0.25 * config.roles_count
    if config.with_evals:
        # ~1 gen + 3 calls per case (with/baseline/grade x2) per skill.
        calls_per_skill = 1 + config.eval_cases_per_skill * 3
        cost += 0.006 * calls_per_skill * config.roles_count * config.skills_per_role
        minutes += 0.5 * config.roles_count
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
    from_jd = parsed.from_jd

    if not from_report and not company_url and not from_jd:
        print(
            "Error: company_url is required unless --from-report or --from-jd is provided.",
            file=sys.stderr,
        )
        return 2

    def _split_role_labels(raw: str | None) -> list[str]:
        if not raw:
            return []
        return [label.strip() for label in raw.split(",") if label.strip()]

    override_labels = _split_role_labels(parsed.roles_override)
    add_labels = _split_role_labels(parsed.roles_add)
    skip_labels = _split_role_labels(parsed.roles_skip)

    if override_labels and (add_labels or skip_labels):
        print(
            "Warning: --roles-override is mutually exclusive with "
            "--roles-add / --roles-skip. Curation flags ignored.",
            file=sys.stderr,
        )
        add_labels = []
        skip_labels = []

    from_plan_path: str | None = parsed.from_plan
    if from_plan_path:
        plan_path_obj = Path(from_plan_path).expanduser().resolve()
        if not plan_path_obj.exists():
            print(
                f"Error: --from-plan path does not exist: {plan_path_obj}",
                file=sys.stderr,
            )
            return 2
        from_plan_path = str(plan_path_obj)

    from_jd_path: str | None = from_jd
    if from_jd_path:
        jd_path_obj = Path(from_jd_path).expanduser().resolve()
        if not jd_path_obj.is_file():
            print(
                f"Error: --from-jd path does not exist or is not a file: {jd_path_obj}",
                file=sys.stderr,
            )
            return 2
        from_jd_path = str(jd_path_obj)

    try:
        config = SkillPackConfig(
            roles_count=(len(override_labels) if override_labels else parsed.roles),
            skills_per_role=parsed.skills_per_role,
            formats=SkillPackFormat(parsed.formats),
            max_refine_iterations=parsed.max_refine_iterations,
            run_pack_coherence_pass=not parsed.no_coherence_pass,
            optimize_triggers=parsed.optimize_triggers,
            with_evals=parsed.with_evals,
            emit_agent_metadata=parsed.emit_agent_metadata,
            reuse_existing_evidence=bool(from_report),
            allow_recon_only=parsed.allow_recon_only,
            roles_override=override_labels,
            roles_add=add_labels,
            roles_skip=skip_labels,
            plan_only=parsed.plan_only,
            from_plan_path=from_plan_path,
            from_jd_path=from_jd_path,
        )
        config.validate()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if parsed.dry_run:
        cost, minutes = _estimate(
            config,
            will_collect_evidence=bool(company_url and not from_report),
        )
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
        # Standalone: create a temp working dir and collect evidence when a
        # URL is available. A role brief can also be the sole evidence source.
        tmp = Path(tempfile.mkdtemp(prefix="primr-skill-pack-"))
        working_dir = tmp
        if company_url:
            print(f"Collecting recon + hiring evidence for {company_name}...")
            outcome = collect_evidence(
                company_name=company_name,
                company_url=company_url,
                working_dir=working_dir,
            )
            recon_path = outcome.get("recon")
            hiring_path = outcome.get("hiring")
            if not recon_path and not hiring_path and not config.from_jd_path:
                print(
                    "Error: Could not collect any evidence (recon and hiring both "
                    "failed). Try --from-report against an existing primr run, "
                    "or supply --from-jd with a job description / role brief.",
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
    except ValueError as exc:
        print(f"Input invalid: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Evidence IO failed: {exc}", file=sys.stderr)
        return 1

    print()

    def _format_roster_breakdown(
        plan_roster: int, obs: int, plaus: int, added: int, skipped: int
    ) -> str:
        parts = [f"{obs} observed", f"{plaus} plausible"]
        if added:
            parts.append(f"{added} added")
        if skipped:
            parts.append(f"{skipped} skipped")
        return f"{plan_roster} ({', '.join(parts)})"

    if config.plan_only:
        print(f"Role plan complete for {pack.company_name}")
        if pack.plan is not None:
            plan = pack.plan
            print(
                "  Roster: "
                + _format_roster_breakdown(
                    plan.total_planned,
                    len(plan.observed),
                    len(plan.plausible),
                    len(plan.operator_added),
                    len(plan.operator_skipped),
                )
            )
            if plan.plan_md_path:
                print(f"  Plan (markdown): {plan.plan_md_path}")
            if plan.plan_json_path:
                print(f"  Plan (json): {plan.plan_json_path}")
                print(
                    "  To author against this plan: "
                    f'primr skills "{pack.company_name}" '
                    f"--from-plan {plan.plan_json_path}"
                )
            else:
                # Persistence failed (plan_md_path is also None in this
                # path) — surface clearly rather than printing
                # "--from-plan None" or pointing at a phantom file.
                print(
                    "  Plan artifacts could not be persisted; check the "
                    "logger output above for the underlying filesystem error."
                )
        else:
            # --plan-only combined with --roles-override skips planning
            # entirely, so there's no RolePlan to render. Surface the
            # would-be roster explicitly and explain why no plan file
            # was written.
            print(
                "  --roles-override was supplied, so no role plan was "
                "produced (planning was bypassed)."
            )
            if override_labels:
                print(f"  Override roster ({len(override_labels)}): " + ", ".join(override_labels))
            print("  Drop --plan-only or drop --roles-override to choose one of the two flows.")
        return 0

    print(f"Skill pack complete for {pack.company_name}")
    observed = pack.observed_role_count
    plausible = pack.plausible_role_count
    added = pack.operator_added_role_count
    if observed or plausible or added:
        target_segment = "" if config.from_plan_path else f"; target {config.roles_count}"
        print(
            "  Roles: "
            + _format_roster_breakdown(
                len(pack.roles),
                observed,
                plausible,
                added,
                len(pack.plan.operator_skipped) if pack.plan is not None else 0,
            ).rstrip(")")
            + f"{target_segment})"
        )
    else:
        print(f"  Roles: {len(pack.roles)} (target {config.roles_count})")
    print(f"  Total skills: {pack.total_skills}")
    if pack.plan is not None and pack.plan.plan_md_path:
        print(f"  Role plan: {pack.plan.plan_md_path}")
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
