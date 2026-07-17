"""Phase 1 — role planning.

Replaces the single-call ``discover_roles`` with a structured two-call
plan:

  Call A (observed): roles drawn from actual job postings, each backed
    by verbatim posting citations. Provenance = posting, confidence =
    Confirmed.
  Call B (plausible): roles inferred from research + industry
    classification, each backed by either a verbatim research citation
    OR a business-model + stage rationale. Provenance = research or
    industry, confidence = Inferred or Speculated.

The two calls run in parallel. The merge step dedupes by archetype
(observed wins) and applies a signal-driven cap up to ``roles_count``.
The resulting plan is persisted to the working directory as
``role_plan.md`` (human view) and ``role_plan.json`` (machine view) so
operators can inspect before the pack is authored, or re-author from a
saved plan via ``--from-plan``.

Job postings are the primary input; research and recon are supporting
context. See feedback_skill_pack_primary_input memory for the design
invariant.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from primr.skill_pack.archetypes import load_archetypes, match_archetype
from primr.skill_pack.curation import (
    apply_curation,
)
from primr.skill_pack.discovery import (
    EmptyHiringEvidenceError,
    hiring_evidence_is_empty,
    load_full_evidence,
    research_evidence_is_empty,
)
from primr.skill_pack.industry import classify_industry
from primr.skill_pack.plan_artifacts import persist_plan
from primr.skill_pack.posting_coverage import assess_posting_coverage
from primr.skill_pack.prompts_loader import extract_json, load_skill_pack_prompt
from primr.skill_pack.saved_plan import (
    SavedPlanValidationError,
    load_plan,
    prepare_saved_plan,
    saved_plan_approval_basis,
)
from primr.skill_pack.schema import (
    Role,
    RoleEvidence,
    RolePlan,
    RoleProvenance,
)

logger = logging.getLogger(__name__)

# Fraction of the roster reserved for plausible (research / industry / org-shape)
# roles so a posting set dominated by one function can't crowd out the universal
# business functions (sales, marketing, HR, operations, finance, IT, leadership).
# Observed roles still take the leading slots and win on ties; this only caps how
# many observed slots are filled when eligible plausible roles are waiting. At
# cap=5 this reserves up to 2 slots; at cap=10, up to 4.
PLAUSIBLE_RESERVE_FRACTION = 0.4


# =============================================================================
# LLM call helpers
# =============================================================================


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    reasoning_session: Any | None,
    *,
    max_tokens: int = 8_000,
) -> str:
    """Route a planning LLM call through the shared session if provided,
    otherwise use a fresh grok_llm() call. Matches discovery._call_llm so
    the two stay in lockstep on temperature / max_tokens."""
    if reasoning_session is not None and hasattr(reasoning_session, "send"):
        return reasoning_session.send(  # type: ignore[no-any-return]
            f"{system_prompt}\n\n{user_prompt}",
            temperature=0.3,
            max_tokens=max_tokens,
        )

    from primr.ai.grok_client import grok_llm

    return grok_llm(
        user_prompt,
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=max_tokens,
    )


# =============================================================================
# Response parsing
# =============================================================================


def _parse_observed_response(raw: str, roles_count: int) -> list[Role]:
    """Parse Call A output into Role objects.

    Roles without at least one posting citation are dropped — observed
    roles must be grounded in actual postings or they don't belong here.
    """
    parsed = extract_json(raw)
    entries = parsed.get("roles") or []
    if not isinstance(entries, list):
        return []

    out: list[Role] = []
    for entry in entries[:roles_count]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        citations_raw = entry.get("posting_citations") or []
        citations = [str(c).strip() for c in citations_raw if str(c).strip()][:8]
        if not citations:
            # Observed roles MUST cite postings.
            logger.debug("Dropping observed role %r — no posting citations", name)
            continue
        archetype = str(entry["archetype"]).strip() if entry.get("archetype") else None
        try:
            posting_count = int(entry.get("posting_count") or len(citations))
        except (TypeError, ValueError):
            posting_count = len(citations)
        out.append(
            Role(
                name=name,
                display_name=str(entry.get("display_name", name)).strip(),
                confidence="Confirmed",
                summary=str(entry.get("summary", "")).strip(),
                evidence=RoleEvidence(
                    sources=[f"hiring:{c[:80]}" for c in citations[:3]],
                    dns_signals=[],
                    posting_count=posting_count,
                    archetype=archetype or None,
                    provenance=RoleProvenance.POSTING,
                    citations=citations,
                ),
            )
        )
    return out


def _parse_plausible_response(
    raw: str,
    roles_count: int,
    observed_archetypes: set[str],
) -> list[Role]:
    """Parse Call B output into Role objects.

    Roles without citations are dropped. Roles whose archetype already
    appears in `observed_archetypes` are dropped to prevent duplication.
    """
    parsed = extract_json(raw)
    entries = parsed.get("roles") or []
    if not isinstance(entries, list):
        return []

    out: list[Role] = []
    for entry in entries[:roles_count]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        citations_raw = entry.get("research_citations") or []
        citations = [str(c).strip() for c in citations_raw if str(c).strip()][:8]
        if not citations:
            logger.debug("Dropping plausible role %r — no citations", name)
            continue
        archetype = str(entry["archetype"]).strip() if entry.get("archetype") else None
        if archetype and archetype in observed_archetypes:
            logger.debug(
                "Dropping plausible role %r — archetype %s already observed",
                name,
                archetype,
            )
            continue
        provenance_label = str(entry.get("provenance") or "research").strip().lower()
        if provenance_label == "industry":
            provenance = RoleProvenance.INDUSTRY
        else:
            provenance = RoleProvenance.RESEARCH
        confidence = str(entry.get("confidence") or "Inferred").strip() or "Inferred"
        out.append(
            Role(
                name=name,
                display_name=str(entry.get("display_name", name)).strip(),
                confidence=confidence,
                summary=str(entry.get("summary", "")).strip(),
                evidence=RoleEvidence(
                    sources=[f"research:{c[:80]}" for c in citations[:3]],
                    dns_signals=[],
                    posting_count=0,
                    archetype=archetype or None,
                    provenance=provenance,
                    citations=citations,
                ),
            )
        )
    return out


# =============================================================================
# Merge + cap
# =============================================================================


def _resolve_archetype(role: Role) -> str | None:
    """Return the archetype slug for a role, computing a fallback match
    when the LLM didn't supply one."""
    if role.evidence.archetype:
        return role.evidence.archetype
    match = match_archetype(role.display_name or role.name)
    if match.archetype is not None and match.confidence >= 0.55:
        return match.archetype.slug
    return None


def _merge_and_cap(
    observed: list[Role],
    plausible: list[Role],
    cap: int,
) -> tuple[list[Role], list[Role]]:
    """Merge observed and plausible roles into a final roster, capped at
    `cap`. Returns (final_roster, gap_flagged).

    Rules:
      - Observed (posting-grounded) roles take the LEADING slots and win on
        ties / archetype collisions — postings stay the primary input.
      - But observed roles do NOT get to consume the *entire* roster when
        plausible org-shape roles are waiting. A fraction of the roster
        (``PLAUSIBLE_RESERVE_FRACTION``) is reserved so the universal
        business functions (sales, marketing, HR, operations, finance, IT,
        leadership) still appear even when a company's postings are
        dominated by one technical function (e.g. an infra-heavy reseller
        whose every posting is a cloud-engineer role).
      - When the reserve bumps observed roles out of the roster, those
        bumped observed roles flow to ``gap_flagged`` (a contiguous suffix
        of ``observed``) so they stay visible and promotable via
        ``--roles-override``.
      - Archetype-level dedupe applies to PLAUSIBLE roles only (a plausible
        role is dropped if its archetype already appears among observed or
        an earlier-kept plausible role). Two distinct observed postings may
        share an archetype — both deserve representation.
    """
    # Backfill every observed role's archetype for downstream rendering.
    for role in observed:
        archetype = _resolve_archetype(role)
        if archetype is not None and not role.evidence.archetype:
            role.evidence.archetype = archetype

    observed_names: set[str] = {r.name for r in observed}

    # Reserve up to `reserve` slots for plausible org-shape roles. Bound it by
    # the count of plausible roles that could plausibly fill a slot (name-unique
    # vs observed) — NOT by archetype-eligibility, which depends on which
    # observed roles are kept (computed next). Basing the reserve on archetype-
    # eligibility-vs-all-observed was the bug: a plausible role colliding with
    # an observed role that the reserve then BUMPS would shrink the reserve and
    # then be dropped, even though its archetype isn't in the final roster.
    fillable_plausible = sum(1 for c in plausible if c.name not in observed_names)
    reserve = min(fillable_plausible, int(cap * PLAUSIBLE_RESERVE_FRACTION))

    # How many observed roles would fit WITHOUT the reserve (historical cap
    # behavior) vs WITH it. The difference is the set displaced *by the reserve*
    # — only those flow to gap_flagged. Observed beyond the cap entirely (plain
    # overflow, no plausible competing) is truncated silently as before.
    observed_keep_naive = min(len(observed), cap)
    observed_keep = min(len(observed), max(1, cap - reserve)) if observed else 0
    kept_observed = observed[:observed_keep]

    # Dedupe plausible against the archetypes of the KEPT observed roles only,
    # so a bumped observed role's archetype never suppresses a reserved
    # plausible role.
    seen_names: set[str] = set(observed_names)
    seen_archetypes: set[str] = {
        a for r in kept_observed if (a := _resolve_archetype(r)) is not None
    }
    eligible_plausible: list[Role] = []
    for candidate in plausible:
        archetype = _resolve_archetype(candidate)
        if archetype is not None and not candidate.evidence.archetype:
            candidate.evidence.archetype = archetype
        if candidate.name in seen_names:
            continue
        if archetype is not None and archetype in seen_archetypes:
            continue
        eligible_plausible.append(candidate)
        seen_names.add(candidate.name)
        if archetype is not None:
            seen_archetypes.add(archetype)

    final: list[Role] = list(kept_observed)
    # Observed roles the reserve bumped out (a suffix of the would-have-fit
    # observed) are gap-flagged so they stay visible / promotable.
    gap: list[Role] = list(observed[observed_keep:observed_keep_naive])

    for candidate in eligible_plausible:
        if len(final) >= cap:
            gap.append(candidate)
        else:
            final.append(candidate)

    return final, gap


# =============================================================================
# Public entry point
# =============================================================================


def plan_roles(
    company_name: str,
    company_url: str | None,
    working_dir: Path,
    roles_count: int,
    *,
    reasoning_session: Any | None = None,
    allow_recon_only: bool = False,
    roles_add: list[str] | None = None,
    roles_skip: list[str] | None = None,
) -> RolePlan:
    """Run the two-call planning step.

    Args:
        company_name: Display name.
        company_url: Optional URL.
        working_dir: Directory containing evidence files (recon, hiring,
            optionally research).
        roles_count: Target size of the final roster.
        reasoning_session: Optional ContinuousReasoningSession.
        allow_recon_only: When False (default), refuse to plan when both
            posting evidence AND research evidence are empty. Set True
            to opt in to the degraded recon-only path.

    Returns:
        A RolePlan with observed, plausible, gap_flagged, and
        final_roster populated, and a persisted role_plan.md /
        role_plan.json in `working_dir`.

    Raises:
        EmptyHiringEvidenceError: when both hiring and research evidence
            are empty and `allow_recon_only` is False.
    """
    recon, hiring, research = load_full_evidence(working_dir)

    # The empty-evidence guard fires when both posting and research
    # evidence are empty AND the operator has not provided any explicit
    # recovery signal: --allow-recon-only (proceed with DNS-only) or
    # --roles-add (operator supplied the roles themselves). Without one
    # of those, planning would have nothing to ground roles in and we
    # fail closed rather than ship a hollow pack.
    has_operator_roles = bool(roles_add)
    if (
        hiring_evidence_is_empty(hiring)
        and research_evidence_is_empty(research)
        and not allow_recon_only
        and not has_operator_roles
    ):
        raise EmptyHiringEvidenceError(
            "Role planning refused: no job-posting evidence and no "
            "research evidence are available. Skill packs need either "
            "actual postings (primary) or strategic research (for "
            "plausible-role inference). Options: pass --allow-recon-only "
            "to proceed with DNS-only, or pass --roles-add to supply "
            "roles explicitly."
        )

    industry = classify_industry(
        company_name=company_name,
        recon_text=recon,
        hiring_text=hiring,
        research_text=research,
        report_text=research,
    )

    archetype_slugs = ", ".join(sorted(load_archetypes().keys())) or "(none bundled)"

    observed_prompt = load_skill_pack_prompt("plan_observed_roles")
    plausible_prompt = load_skill_pack_prompt("plan_plausible_roles")

    observed: list[Role] = []
    plausible: list[Role] = []

    # Call A: observed roles. Skipped when hiring evidence is empty (no
    # postings to ground against).
    if not hiring_evidence_is_empty(hiring):
        observed_user_msg = observed_prompt.render(
            company_name=company_name,
            company_url=company_url or "(not provided)",
            max_roles=roles_count,
            archetype_slugs=archetype_slugs,
            hiring_evidence=hiring,
        )
        try:
            raw_observed = _call_llm(
                observed_prompt.system_prompt,
                observed_user_msg,
                reasoning_session,
            )
            observed = _parse_observed_response(raw_observed, roles_count)
        except Exception as exc:
            logger.warning("Observed-roles call failed: %s", exc)
            observed = []
    else:
        logger.info("Skipping observed-roles call: hiring evidence empty")

    observed_archetypes: set[str] = set()
    for role in observed:
        archetype = _resolve_archetype(role)
        if archetype is not None:
            observed_archetypes.add(archetype)

    # Call B: plausible roles. Runs when there is room left in the
    # roster (or no observed roles were found) AND there is either
    # research signal to ground against OR observed roles to gap-fill.
    if not research_evidence_is_empty(research) or observed:
        observed_block = (
            "\n".join(
                f"- {r.display_name} (`{r.name}`)"
                + (f" - archetype: `{r.evidence.archetype}`" if r.evidence.archetype else "")
                for r in observed
            )
            or "(none - no observed roles found)"
        )
        remaining = max(roles_count - len(observed), 1)
        plausible_user_msg = plausible_prompt.render(
            company_name=company_name,
            company_url=company_url or "(not provided)",
            max_roles=remaining + 3,  # ask for a little headroom for dedupe drops
            business_model=industry.business_model,
            industry_vertical=industry.industry_vertical,
            company_stage=industry.company_stage,
            employee_estimate=industry.employee_estimate,
            classification_confidence=industry.confidence,
            observed_roles_block=observed_block,
            recon_evidence=recon,
            research_evidence=research,
            archetype_slugs=archetype_slugs,
        )
        try:
            raw_plausible = _call_llm(
                plausible_prompt.system_prompt,
                plausible_user_msg,
                reasoning_session,
            )
            plausible = _parse_plausible_response(
                raw_plausible,
                remaining + 3,
                observed_archetypes,
            )
        except Exception as exc:
            logger.warning("Plausible-roles call failed: %s", exc)
            plausible = []

    final_roster, gap_flagged = _merge_and_cap(observed, plausible, roles_count)
    coverage = assess_posting_coverage(observed, industry)

    evidence_summary: dict[str, Any] = {
        "recon_chars": 0 if recon.startswith("(no recon") else len(recon),
        "hiring_chars": 0 if hiring_evidence_is_empty(hiring) else len(hiring),
        "research_chars": 0 if research_evidence_is_empty(research) else len(research),
        "observed_count": len(observed),
        "plausible_count": len(plausible),
        "final_roster_count": len(final_roster),
        "gap_flagged_count": len(gap_flagged),
    }
    evidence_summary.update(coverage.to_evidence_summary())

    plan = RolePlan(
        observed=observed,
        plausible=plausible,
        gap_flagged=gap_flagged,
        final_roster=final_roster,
        industry=industry,
        evidence_summary=evidence_summary,
    )

    # Apply operator curation (--roles-add / --roles-skip) before
    # persistence so the saved plan reflects the curated roster.
    if roles_add or roles_skip:
        apply_curation(
            plan,
            roles_add=list(roles_add or []),
            roles_skip=list(roles_skip or []),
            cap=roles_count,
        )

    generated_at = datetime.now(tz=timezone.utc).isoformat()
    persist_plan(plan, working_dir, company_name, generated_at, roles_count)

    logger.info(
        "Plan: %d observed + %d plausible -> %d in roster (cap %d), "
        "%d gap-flagged, %d operator-added, %d operator-skipped",
        len(observed),
        len(plausible),
        len(plan.final_roster),
        roles_count,
        len(plan.gap_flagged),
        len(plan.operator_added),
        len(plan.operator_skipped),
    )

    if not plan.final_roster:
        raise RuntimeError(
            f"plan_roles returned no usable roles for {company_name}. "
            "Both posting and research signals are too thin to ground "
            "even an inferred role. Inspect the evidence files in "
            f"{working_dir} or pass --roles-override to specify roles "
            "explicitly."
        )

    return plan


__all__ = [
    "SavedPlanValidationError",
    "load_plan",
    "plan_roles",
    "prepare_saved_plan",
    "saved_plan_approval_basis",
]
