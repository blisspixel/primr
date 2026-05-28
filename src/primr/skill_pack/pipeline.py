"""Skill pack pipeline orchestrator.

Coordinates phases 1-6 end-to-end:

  Phase 1: discover_roles
  Phase 2: archetype grounding (resolved per role during authoring)
  Phase 3: author_all_roles  (parallel SKILL.md drafts)
  Phase 4: validate          (deterministic, no LLM)
  Phase 5: refine_role       (per-skill refinement, capped)
  Phase 5b: run_pack_coherence_pass (pack-level checks)
  Phase 6: package_skill_pack (write artifacts)

The shared ContinuousReasoningSession is wired through refinement only —
authoring runs in parallel so it cannot share a single session. That's the
right trade: parallel authoring saves wallclock; shared-session refinement
gives the refiner full pack context for free.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from primr.skill_pack.authoring import author_all_roles
from primr.skill_pack.config import SkillPackConfig
from primr.skill_pack.discovery import discover_roles
from primr.skill_pack.packager import package_skill_pack
from primr.skill_pack.refiner import (
    attach_coherence_findings_as_issues,
    refine_role,
    run_pack_coherence_pass,
)
from primr.skill_pack.schema import (
    IssueSeverity,
    Role,
    SkillPack,
    SkillPackArtifacts,
)
from primr.skill_pack.validator import validate_pack

logger = logging.getLogger(__name__)


def _build_company_context(company_name: str, company_url: str | None, roles: list[Role]) -> str:
    """Short string passed to the refiner so it doesn't lose company anchoring."""
    parts = [f"Company: {company_name}"]
    if company_url:
        parts.append(f"URL: {company_url}")
    dns_summary: list[str] = []
    archetypes: list[str] = []
    for role in roles:
        if role.evidence.dns_signals:
            dns_summary.extend(role.evidence.dns_signals[:3])
        if role.evidence.archetype:
            archetypes.append(role.evidence.archetype)
    if dns_summary:
        parts.append("DNS-confirmed signals: " + ", ".join(sorted(set(dns_summary))[:8]))
    if archetypes:
        parts.append("Role archetypes in this pack: " + ", ".join(sorted(set(archetypes))))
    return "\n".join(parts)


def _drop_failing_roles(pack: SkillPack) -> None:
    """After refinement, drop any role still carrying HARD findings.

    Safer than shipping a failing skill — Cowork's manifest validator
    would reject the package anyway. Dropped roles are recorded on the
    pack so the report markdown surfaces them.
    """
    surviving: list[Role] = []
    for role in pack.roles:
        role_findings = [
            i
            for i in pack.validation.issues
            if i.role_name == role.name and i.severity == IssueSeverity.HARD
        ]
        if role_findings:
            reasons = "; ".join({i.code for i in role_findings})
            pack.dropped_roles.append((role.name, reasons))
            logger.warning(
                "Dropping role %s — unrecovered HARD findings: %s",
                role.name,
                reasons,
            )
            continue
        surviving.append(role)
    pack.roles = surviving


def run_skill_pack_pipeline(
    company_name: str,
    company_url: str | None,
    working_dir: Path,
    config: SkillPackConfig,
    output_dir: Path,
    *,
    industry_context: str = "(unknown)",
    reasoning_session: Any | None = None,
) -> tuple[SkillPack, SkillPackArtifacts]:
    """Run the full pipeline. Returns (pack, artifacts).

    Args:
        company_name: Display name.
        company_url: Optional URL.
        working_dir: Directory containing recon + hiring evidence.
        config: Tuning knobs.
        output_dir: Directory where the dated output folder is written.
        industry_context: Optional one-paragraph industry summary to
            improve authoring grounding. The CLI standalone path passes
            "(unknown)"; --from-report can extract this from the report.
        reasoning_session: Optional ContinuousReasoningSession.

    Raises ValueError on config out-of-bounds, FileNotFoundError on
    missing evidence, RuntimeError if no roles survive refinement.
    """
    config.validate()
    company_url = company_url or None

    # -- Phase 1 -----------------------------------------------------------
    logger.info("[skill_pack] Phase 1: discovering roles for %s", company_name)
    roles = discover_roles(
        company_name=company_name,
        company_url=company_url,
        working_dir=working_dir,
        roles_count=config.roles_count,
        reasoning_session=reasoning_session,
    )

    # -- Phase 3 (Phase 2 resolved per-role inside authoring) --------------
    logger.info("[skill_pack] Phase 3: authoring %d roles in parallel", len(roles))
    author_all_roles(
        roles=roles,
        company_name=company_name,
        company_url=company_url,
        skills_per_role=config.skills_per_role,
        working_dir=working_dir,
        industry_context=industry_context,
    )

    pack = SkillPack(
        company_name=company_name,
        company_url=company_url,
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        roles=roles,
    )

    # -- Phase 4: deterministic validation --------------------------------
    pack.validation = validate_pack(pack)
    logger.info(
        "[skill_pack] Phase 4: validation found %d HARD / %d SOFT issues",
        len(pack.validation.hard_issues),
        len(pack.validation.soft_issues),
    )

    # -- Phase 5: per-skill refinement ------------------------------------
    if pack.validation.hard_issues and config.max_refine_iterations > 0:
        logger.info("[skill_pack] Phase 5: refining failing skills")
        company_context = _build_company_context(company_name, company_url, roles)
        for role in pack.roles:
            iterations = refine_role(
                role,
                config,
                company_context,
                reasoning_session=reasoning_session,
            )
            for skill_name, count in iterations.items():
                pack.refinement_iterations_used[f"{role.name}/{skill_name}"] = count

        # Re-run validation after refinement.
        pack.validation = validate_pack(pack)
        logger.info(
            "[skill_pack] Post-refinement: %d HARD / %d SOFT issues",
            len(pack.validation.hard_issues),
            len(pack.validation.soft_issues),
        )

    # -- Phase 5b: pack-level coherence -----------------------------------
    if config.run_pack_coherence_pass and pack.roles:
        logger.info("[skill_pack] Phase 5b: pack coherence pass")
        try:
            coherence = run_pack_coherence_pass(pack, reasoning_session=reasoning_session)
            pack.validation = attach_coherence_findings_as_issues(pack, coherence)
        except Exception as exc:
            logger.warning("Pack coherence pass failed (non-fatal): %s", exc)

    # Drop any role that still has HARD findings — Cowork won't accept it
    # and downstream consumers shouldn't see a half-broken skill.
    _drop_failing_roles(pack)

    if not pack.roles:
        raise RuntimeError(
            "Pipeline produced no valid roles after refinement and pack-level review. "
            "Inspect the validation report for HARD findings; consider lowering "
            "roles_count or supplying richer evidence."
        )

    # -- Phase 6: packaging ----------------------------------------------
    logger.info(
        "[skill_pack] Phase 6: packaging %d roles / %d skills",
        len(pack.roles),
        pack.total_skills,
    )
    artifacts = package_skill_pack(pack, config, output_dir)
    return pack, artifacts


__all__ = ["run_skill_pack_pipeline"]
