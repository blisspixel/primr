"""Skill pack pipeline orchestrator.

Coordinates phases 1-6 end-to-end:

  Phase 1: discover_roles
  Phase 2: archetype grounding (resolved per role during authoring)
  Phase 3: author_all_roles  (parallel SKILL.md drafts)
  Phase 4: validate          (deterministic, no LLM)
  Phase 5: refine_role       (per-skill refinement, capped)
  Phase 5b: run_pack_coherence_pass + auto_resolve_overlaps (pack-level)
  Phase 5c: optimize_pack_triggers   (opt-in, --optimize-triggers)
  Phase 5d: run_pack_behavioral_evals (opt-in, --with-evals)
  Phase 6: package_skill_pack (write artifacts)

The shared ContinuousReasoningSession is wired through refinement only —
authoring runs in parallel so it cannot share a single session. That's the
right trade: parallel authoring saves wallclock; shared-session refinement
gives the refiner full pack context for free.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from primr.skill_pack.archetypes import match_archetype
from primr.skill_pack.authoring import author_all_roles
from primr.skill_pack.behavioral_eval import run_pack_behavioral_evals
from primr.skill_pack.config import MAX_ROLES, SkillPackConfig
from primr.skill_pack.packager import package_skill_pack
from primr.skill_pack.planner import apply_curation, load_plan, plan_roles
from primr.skill_pack.refiner import (
    attach_coherence_findings_as_issues,
    auto_resolve_overlaps,
    refine_role,
    run_pack_coherence_pass,
)
from primr.skill_pack.schema import (
    IssueSeverity,
    Role,
    RoleEvidence,
    RolePlan,
    SkillPack,
    SkillPackArtifacts,
)
from primr.skill_pack.trigger_eval import optimize_pack_triggers
from primr.skill_pack.validator import validate_pack

logger = logging.getLogger(__name__)


_NAME_SAFE_RE = re.compile(r"[^a-z0-9]+")


def _slugify_role_name(label: str) -> str:
    slug = _NAME_SAFE_RE.sub("-", label.lower()).strip("-")
    return slug or "role"


def _materialize_override_roles(labels: list[str]) -> list[Role]:
    """Turn operator-supplied role labels into Role objects.

    The label is used verbatim as `display_name`; `name` is the slugified
    form; archetype matching runs against the label so authoring picks up
    the right grounding fragment when a known archetype is close enough.
    Confidence is 'Operator' to make clear these roles bypassed automatic
    discovery and were supplied by the caller.
    """
    out: list[Role] = []
    for label in labels:
        slug = _slugify_role_name(label)
        match = match_archetype(label)
        archetype_slug = match.archetype.slug if match.archetype is not None else None
        out.append(
            Role(
                name=slug,
                display_name=label,
                confidence="Operator",
                summary=f"Operator-supplied role: {label}.",
                evidence=RoleEvidence(
                    sources=["override"],
                    dns_signals=[],
                    posting_count=0,
                    archetype=archetype_slug,
                ),
            )
        )
    return out


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
        working_dir: Directory containing recon + hiring evidence (and
            optionally research artifacts like insights.txt / report.md).
        config: Tuning knobs.
        output_dir: Directory where the dated output folder is written.
        industry_context: Optional one-paragraph industry summary to
            improve authoring grounding. Used when no plan industry
            classification is available.
        reasoning_session: Optional ContinuousReasoningSession.

    Raises ValueError on config out-of-bounds, FileNotFoundError on
    missing evidence, RuntimeError if no roles survive refinement, and
    EmptyHiringEvidenceError when both posting and research evidence
    are empty (unless allow_recon_only is set).
    """
    config.validate()
    company_url = company_url or None

    plan: RolePlan | None = None
    roles: list[Role]

    # -- Phase 1 -----------------------------------------------------------
    if config.roles_override:
        if config.roles_add or config.roles_skip:
            logger.warning(
                "[skill_pack] roles_override is mutually exclusive with "
                "roles_add/roles_skip — curation flags ignored."
            )
        logger.info(
            "[skill_pack] Phase 1: roles_override supplied (%d names) — "
            "skipping automatic discovery",
            len(config.roles_override),
        )
        roles = _materialize_override_roles(config.roles_override)
    elif config.from_plan_path:
        logger.info(
            "[skill_pack] Phase 1: loading saved plan from %s",
            config.from_plan_path,
        )
        plan = load_plan(Path(config.from_plan_path))
        if config.roles_add or config.roles_skip:
            # When --from-plan is in use, honor the saved plan size + adds
            # rather than the user's --roles flag, but never exceed the
            # global MAX_ROLES ceiling. _drop_excess_to_cap trims plausible
            # first, then observed, never operator-added.
            curation_cap = min(
                MAX_ROLES,
                max(
                    config.roles_count,
                    len(plan.final_roster) + len(config.roles_add),
                ),
            )
            apply_curation(
                plan,
                roles_add=list(config.roles_add),
                roles_skip=list(config.roles_skip),
                cap=curation_cap,
            )
        roles = list(plan.final_roster)
        if not roles:
            raise RuntimeError(
                f"Saved plan at {config.from_plan_path} has an empty "
                "final_roster — nothing to author."
            )
    else:
        logger.info("[skill_pack] Phase 1: planning roles for %s", company_name)
        plan = plan_roles(
            company_name=company_name,
            company_url=company_url,
            working_dir=working_dir,
            roles_count=config.roles_count,
            reasoning_session=reasoning_session,
            allow_recon_only=config.allow_recon_only,
            roles_add=list(config.roles_add),
            roles_skip=list(config.roles_skip),
        )
        roles = list(plan.final_roster)

    if config.plan_only:
        logger.info("[skill_pack] --plan-only set; skipping authoring + packaging")
        empty_pack = SkillPack(
            company_name=company_name,
            company_url=company_url,
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            roles=[],
            plan=plan,
        )
        return empty_pack, SkillPackArtifacts(output_dir=str(output_dir))

    # When an industry classification was computed during planning, prefer
    # it over the caller-supplied industry_context so authoring grounds
    # against the same context the plan was built on.
    if plan is not None and plan.industry.business_model != "Unknown":
        industry_context = (
            f"Business model: {plan.industry.business_model}; "
            f"vertical: {plan.industry.industry_vertical}; "
            f"stage: {plan.industry.company_stage}; "
            f"headcount: {plan.industry.employee_estimate}."
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
        plan=plan,
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
            # Auto-resolve overlapping/colliding pairs (mutates coherence to
            # drop resolved entries) before recording the remaining findings.
            if config.auto_resolve_overlaps:
                resolved = auto_resolve_overlaps(
                    pack,
                    coherence,
                    _build_company_context(company_name, company_url, roles),
                    reasoning_session=reasoning_session,
                )
                if resolved:
                    logger.info(
                        "[skill_pack] Phase 5b: auto-resolved %d overlap pair(s)",
                        len(resolved),
                    )
            pack.validation = attach_coherence_findings_as_issues(pack, coherence)
        except Exception as exc:
            logger.warning("Pack coherence pass failed (non-fatal): %s", exc)

    # -- Phase 5c: trigger-description optimization (opt-in) ---------------
    if config.optimize_triggers and pack.roles:
        logger.info("[skill_pack] Phase 5c: trigger-description optimization")
        try:
            trigger_results = optimize_pack_triggers(
                pack,
                _build_company_context(company_name, company_url, roles),
                threshold=config.trigger_accuracy_threshold,
                reasoning_session=reasoning_session,
            )
            pack.trigger_results = trigger_results
            # Descriptions changed — re-validate, then re-attach coherence
            # findings so the report reflects the optimized descriptions.
            coherence_issues = [
                i
                for i in pack.validation.issues
                if i.code in ("PACK-OVERLAP-LLM", "PACK-TRIGGER", "PACK-VOICE", "PACK-STRAT")
            ]
            pack.validation = validate_pack(pack)
            pack.validation.issues.extend(coherence_issues)
        except Exception as exc:
            logger.warning("Trigger optimization failed (non-fatal): %s", exc)

    # -- Phase 5d: behavioral evaluation (opt-in, expensive) --------------
    if config.with_evals and pack.roles:
        logger.info("[skill_pack] Phase 5d: behavioral eval (with-skill vs baseline)")
        try:
            pack.behavioral_results = run_pack_behavioral_evals(
                pack,
                _build_company_context(company_name, company_url, roles),
                n_cases=config.eval_cases_per_skill,
                reasoning_session=reasoning_session,
            )
        except Exception as exc:
            logger.warning("Behavioral eval failed (non-fatal): %s", exc)

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
