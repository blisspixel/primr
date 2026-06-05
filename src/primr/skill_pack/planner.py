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

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from primr.skill_pack.archetypes import load_archetypes, match_archetype
from primr.skill_pack.config import MAX_ROLES
from primr.skill_pack.discovery import (
    EmptyHiringEvidenceError,
    hiring_evidence_is_empty,
    load_full_evidence,
    research_evidence_is_empty,
)
from primr.skill_pack.industry import classify_industry
from primr.skill_pack.prompts_loader import extract_json, load_skill_pack_prompt
from primr.skill_pack.schema import (
    IndustryClassification,
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
# Operator curation (--roles-add, --roles-skip)
# =============================================================================


_CURATION_NAME_RE = re.compile(r"[^a-z0-9]+")


def _normalize_curation_key(label: str) -> str:
    """Lowercase + collapse non-alphanumerics into hyphens. Matches the
    same shape used to generate role slugs so add/skip input is robust to
    variations like ``"Marketing Manager"`` vs ``"marketing-manager"``."""
    return _CURATION_NAME_RE.sub("-", label.lower()).strip("-")


def _materialize_added_role(label: str) -> Role:
    """Turn one --roles-add label into a Role with provenance=override.

    Archetype matching runs against the label so authoring picks up the
    closest scaffolding. Mirrors `_materialize_override_roles` in
    pipeline.py but is called here because curation runs inside the
    planner — keeping the override path in pipeline.py for the
    "bypass planning entirely" case.
    """
    slug = _normalize_curation_key(label) or "operator-role"
    match = match_archetype(label)
    archetype_slug = match.archetype.slug if match.archetype is not None else None
    return Role(
        name=slug,
        display_name=label,
        confidence="Operator",
        summary=f"Operator-supplied role: {label}.",
        evidence=RoleEvidence(
            sources=["override"],
            dns_signals=[],
            posting_count=0,
            archetype=archetype_slug,
            provenance=RoleProvenance.OVERRIDE,
            citations=["operator override"],
        ),
    )


def _match_skip_target(role: Role, skip_keys: set[str]) -> bool:
    """True when this role should be dropped per --roles-skip.

    Matches against role.name (the kebab-case slug) and role.display_name,
    both normalized through `_normalize_curation_key` so operator input
    is robust. Exact match only — no substring magic.
    """
    candidates = {
        _normalize_curation_key(role.name),
        _normalize_curation_key(role.display_name),
    }
    return bool(candidates & skip_keys)


def _drop_excess_to_cap(roster: list[Role], cap: int) -> tuple[list[Role], list[Role]]:
    """Enforce the MAX_ROLES cap with operator-priority trim order.

    Trim order (head of trim list is the first to go):
      1. plausible roles (research / industry provenance)
      2. observed roles (posting provenance)
      3. operator-supplied roles (override provenance) — never trimmed

    Returns (kept, trimmed) so the trimmed entries can flow to
    gap_flagged for plan-artifact transparency.
    """
    if len(roster) <= cap:
        return list(roster), []

    overflow = len(roster) - cap
    # Mark each role with a priority key: lower number = trim first.
    priority: dict[int, int] = {}
    for idx, role in enumerate(roster):
        prov = role.evidence.provenance
        if prov in (RoleProvenance.RESEARCH, RoleProvenance.INDUSTRY):
            priority[idx] = 0
        elif prov == RoleProvenance.POSTING:
            priority[idx] = 1
        else:
            priority[idx] = 2

    # Sort indices by (trim-priority ASC, original index DESC) so we drop
    # the LAST low-priority entries first — preserves the natural order
    # the planner produced for the survivors.
    trim_order = sorted(
        range(len(roster)),
        key=lambda i: (priority[i], -i),
    )
    drop_indices = set(trim_order[:overflow])

    kept = [r for i, r in enumerate(roster) if i not in drop_indices]
    trimmed = [r for i, r in enumerate(roster) if i in drop_indices]
    return kept, trimmed


def apply_curation(
    plan: RolePlan,
    *,
    roles_add: list[str],
    roles_skip: list[str],
    cap: int = MAX_ROLES,
) -> None:
    """Apply operator curation in place: skip first, then add.

    Order is significant: skip-then-add means an operator can swap a
    role with `--roles-skip "Marketing Manager" --roles-add
    "Demand Generation Manager"` and have the swap behave as expected
    even when both names normalize to similar archetypes.

    Updates the plan's `final_roster`, `gap_flagged`, `operator_added`,
    and `operator_skipped` fields. Raises RuntimeError when curation
    leaves an empty roster — the check runs as a preflight against the
    intended post-curation state BEFORE any plan mutation so the input
    plan is preserved on the error path.

    Returns nothing — the plan is mutated when validation passes.
    """
    # --- Preflight: validate the curation BEFORE mutating the plan ------
    # Compute the post-skip survivor count and combine with the projected
    # add count to know the final roster size. If that count is zero we
    # raise without touching plan state.
    skip_keys = {_normalize_curation_key(s) for s in roles_skip if s.strip()}
    survivors_after_skip = (
        [r for r in plan.final_roster if not _match_skip_target(r, skip_keys)]
        if skip_keys
        else list(plan.final_roster)
    )
    # roles_add itself might be entirely deduped — but the operator must
    # supply at least one effective recovery role for the preflight to
    # pass when skip empties the roster. Conservative count: assume every
    # entry survives. The actual add pass below applies real dedup.
    projected_total = len(survivors_after_skip) + len(roles_add)
    if projected_total == 0:
        raise RuntimeError(
            "Curation would leave an empty roster — every role was "
            "skipped and no replacements were added. Re-run with fewer "
            "--roles-skip entries or supply --roles-add to fill the "
            "roster. (Plan unchanged.)"
        )

    # --- Skip pass -------------------------------------------------------
    if skip_keys:
        existing_keys: set[str] = set()
        for role in plan.final_roster:
            existing_keys.add(_normalize_curation_key(role.name))
            existing_keys.add(_normalize_curation_key(role.display_name))
        unmatched = skip_keys - existing_keys
        for key in sorted(unmatched):
            logger.warning("--roles-skip %r did not match any role in the plan", key)

        plan.final_roster = survivors_after_skip
        plan.operator_skipped = sorted(skip_keys)

    # --- Add pass --------------------------------------------------------
    added: list[Role] = []
    if roles_add:
        existing_name_keys = {_normalize_curation_key(r.name) for r in plan.final_roster}
        existing_display_keys = {_normalize_curation_key(r.display_name) for r in plan.final_roster}
        # Archetype dedup is scoped to DISCOVERED roles only. Operator
        # additions that target the same archetype as a planner-produced
        # role are dropped (existing role keeps its citations), but two
        # operator additions that happen to map to the same archetype
        # are BOTH kept — the operator typed two distinct labels for a
        # reason. Name dedup still catches identical labels within the
        # add list.
        discovered_archetypes = {
            r.evidence.archetype for r in plan.final_roster if r.evidence.archetype is not None
        }

        for label in roles_add:
            candidate = _materialize_added_role(label)
            cand_name_key = _normalize_curation_key(candidate.name)
            cand_display_key = _normalize_curation_key(candidate.display_name)

            if cand_name_key in existing_name_keys or cand_display_key in existing_display_keys:
                logger.warning(
                    "--roles-add %r — already in roster; skipping duplicate",
                    label,
                )
                continue

            if (
                candidate.evidence.archetype is not None
                and candidate.evidence.archetype in discovered_archetypes
            ):
                logger.warning(
                    "--roles-add %r — archetype %s already covered by a "
                    "discovered role; skipping duplicate. Pair with "
                    "--roles-skip if you want to force this label.",
                    label,
                    candidate.evidence.archetype,
                )
                continue

            added.append(candidate)
            # Only name-key tracking updates as adds accumulate; archetype
            # dedup intentionally does NOT grow with operator additions.
            existing_name_keys.add(cand_name_key)
            existing_display_keys.add(cand_display_key)

        plan.operator_added = added
        plan.final_roster = plan.final_roster + added

    # --- Cap pass --------------------------------------------------------
    kept, trimmed = _drop_excess_to_cap(plan.final_roster, cap)
    if trimmed:
        plan.gap_flagged = plan.gap_flagged + trimmed
        logger.info(
            "Curation cap trimmed %d role(s) to gap_flagged "
            "(operator-priority order: plausible -> observed -> never override)",
            len(trimmed),
        )
    plan.final_roster = kept

    # Refresh evidence_summary counters so the plan_md / report reflect
    # the post-curation reality.
    plan.evidence_summary["operator_added_count"] = len(plan.operator_added)
    plan.evidence_summary["operator_skipped_count"] = len(plan.operator_skipped)
    plan.evidence_summary["final_roster_count"] = len(plan.final_roster)
    plan.evidence_summary["gap_flagged_count"] = len(plan.gap_flagged)

    # Defensive empty-roster guard. The preflight above catches the
    # planned-empty case, but if every --roles-add entry was deduped
    # against the discovered set we can still land here. Raise rather
    # than ship an empty pack.
    if not plan.final_roster:
        raise RuntimeError(
            "Curation left an empty roster — every --roles-add entry "
            "deduped against the discovered roster and all discovered "
            "roles were skipped. Use distinct labels for --roles-add."
        )


# =============================================================================
# Plan artifact rendering
# =============================================================================


def _format_role_block(role: Role) -> str:
    lines: list[str] = []
    lines.append(f"### {role.display_name} (`{role.name}`)")
    lines.append("")
    lines.append(f"- Confidence: **{role.confidence}**")
    lines.append(f"- Provenance: `{role.evidence.provenance.value}`")
    if role.evidence.archetype:
        lines.append(f"- Archetype: `{role.evidence.archetype}`")
    if role.evidence.posting_count > 0:
        lines.append(f"- Posting count: {role.evidence.posting_count}")
    if role.summary:
        lines.append("")
        lines.append(role.summary)
    if role.evidence.citations:
        lines.append("")
        lines.append("Citations:")
        for citation in role.evidence.citations[:6]:
            trimmed = citation if len(citation) <= 220 else citation[:217] + "..."
            lines.append(f"- {trimmed}")
    return "\n".join(lines)


def _render_plan_md(
    company_name: str,
    plan: RolePlan,
    generated_at: str,
    roles_count: int,
) -> str:
    lines: list[str] = []
    lines.append(f"# Role Plan — {company_name}")
    lines.append("")
    lines.append(f"_Generated {generated_at} by primr._")
    lines.append("")

    lines.append("## Industry Classification")
    industry = plan.industry
    lines.append(f"- Business model: **{industry.business_model}**")
    lines.append(f"- Industry vertical: **{industry.industry_vertical}**")
    lines.append(f"- Company stage: **{industry.company_stage}**")
    lines.append(f"- Employee estimate: **{industry.employee_estimate}**")
    lines.append(
        f"- Classification confidence: **{industry.confidence}** (source: `{industry.source}`)"
    )
    if industry.cited_evidence:
        lines.append("- Cited evidence:")
        for citation in industry.cited_evidence[:5]:
            trimmed = citation if len(citation) <= 180 else citation[:177] + "..."
            lines.append(f"  - {trimmed}")
    lines.append("")

    lines.append("## Evidence Summary")
    for key, value in plan.evidence_summary.items():
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append(f"## Observed Roles — {len(plan.observed)} (from postings)")
    lines.append("")
    if plan.observed:
        for role in plan.observed:
            lines.append(_format_role_block(role))
            lines.append("")
    else:
        lines.append("_No observed roles — no posting evidence available._")
        lines.append("")

    lines.append(f"## Plausible Roles — {len(plan.plausible)} (from research + industry)")
    lines.append("")
    if plan.plausible:
        for role in plan.plausible:
            lines.append(_format_role_block(role))
            lines.append("")
    else:
        lines.append("_No plausible roles inferred — research signal was insufficient._")
        lines.append("")

    if plan.operator_added:
        lines.append(
            f"## Operator-Added Roles — {len(plan.operator_added)} (supplied via --roles-add)"
        )
        lines.append("")
        lines.append(
            "These roles were injected by the operator after planning. "
            "They bypass posting / research grounding and are authored "
            "with the operator-override provenance branch."
        )
        lines.append("")
        for role in plan.operator_added:
            lines.append(_format_role_block(role))
            lines.append("")

    if plan.operator_skipped:
        lines.append(
            f"## Operator-Skipped Roles — {len(plan.operator_skipped)} (dropped via --roles-skip)"
        )
        lines.append("")
        lines.append(
            "The operator asked to drop these roles from the planned "
            "roster. Names are normalized (kebab-case, lowercase) so "
            "either the display label or the slug can match."
        )
        lines.append("")
        for key in plan.operator_skipped:
            lines.append(f"- `{key}`")
        lines.append("")

    if plan.gap_flagged:
        lines.append(f"## Gap-flagged Roles — {len(plan.gap_flagged)} (excluded from this pack)")
        lines.append("")
        lines.append(
            "These plausible roles were dropped because the requested "
            f"`{roles_count}`-role cap was hit. Re-run with "
            "`--roles-override` to include them explicitly."
        )
        lines.append("")
        for role in plan.gap_flagged:
            lines.append(_format_role_block(role))
            lines.append("")

    lines.append("## Final Roster")
    lines.append("")
    for idx, role in enumerate(plan.final_roster, start=1):
        provenance = role.evidence.provenance.value
        lines.append(
            f"{idx}. **{role.display_name}** — `{role.name}` ({provenance}, {role.confidence})"
        )
    lines.append("")

    lines.append("## How to act on this plan")
    lines.append("")
    lines.append("- **Proceed as-is**: nothing to do; authoring follows next.")
    lines.append(
        "- **Inspect only**: re-run with `--plan-only` to write this plan without authoring."
    )
    lines.append(
        "- **Pin the roster**: re-run with "
        "`--from-plan <path/to/role_plan.json>` to author exactly the "
        "roles in this plan."
    )
    lines.append(
        "- **Override entirely**: re-run with "
        '`--roles-override "Role A, Role B, ..."` to bypass discovery.'
    )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _persist_plan(
    plan: RolePlan,
    working_dir: Path,
    company_name: str,
    generated_at: str,
    roles_count: int,
) -> None:
    """Write role_plan.md and role_plan.json into the working dir."""
    try:
        working_dir.mkdir(parents=True, exist_ok=True)
        md_path = working_dir / "role_plan.md"
        json_path = working_dir / "role_plan.json"
        md_text = _render_plan_md(company_name, plan, generated_at, roles_count)
        md_path.write_text(md_text, encoding="utf-8")
        plan.plan_md_path = str(md_path)
        json_text = json.dumps(plan.to_dict(), indent=2, ensure_ascii=False)
        json_path.write_text(json_text, encoding="utf-8")
        plan.plan_json_path = str(json_path)
        logger.info("Wrote role plan to %s and %s", md_path, json_path)
    except OSError as exc:
        logger.warning("Failed to persist role plan: %s", exc)


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
                + (f" — archetype: `{r.evidence.archetype}`" if r.evidence.archetype else "")
                for r in observed
            )
            or "(none — no observed roles found)"
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

    evidence_summary: dict[str, Any] = {
        "recon_chars": 0 if recon.startswith("(no recon") else len(recon),
        "hiring_chars": 0 if hiring_evidence_is_empty(hiring) else len(hiring),
        "research_chars": 0 if research_evidence_is_empty(research) else len(research),
        "observed_count": len(observed),
        "plausible_count": len(plausible),
        "final_roster_count": len(final_roster),
        "gap_flagged_count": len(gap_flagged),
    }

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
    _persist_plan(plan, working_dir, company_name, generated_at, roles_count)

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


def load_plan(json_path: Path) -> RolePlan:
    """Load a previously-persisted RolePlan from its JSON sidecar.

    Used by --from-plan to author against an approved or hand-edited
    plan without re-running the planning LLM calls. Wraps OS-level and
    JSON parse errors in RuntimeError with a helpful message so the
    pipeline's existing error path renders cleanly.
    """
    try:
        raw = json_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Could not read role plan at {json_path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Role plan at {json_path} is not valid JSON: {exc}. "
            "If you hand-edited it, re-run --plan-only to regenerate."
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Role plan at {json_path} is not a JSON object (got {type(data).__name__})."
        )

    def _hydrate_role(entry: dict[str, Any]) -> Role:
        evidence = entry.get("evidence") or {}
        provenance_val = str(evidence.get("provenance") or "posting").strip().lower()
        try:
            provenance = RoleProvenance(provenance_val)
        except ValueError:
            provenance = RoleProvenance.POSTING
        return Role(
            name=str(entry.get("name", "")).strip(),
            display_name=str(entry.get("display_name", "")).strip(),
            confidence=str(entry.get("confidence", "Inferred")).strip(),
            summary=str(entry.get("summary", "")).strip(),
            evidence=RoleEvidence(
                sources=[str(s) for s in evidence.get("sources", [])],
                dns_signals=[str(s) for s in evidence.get("dns_signals", [])],
                posting_count=int(evidence.get("posting_count") or 0),
                archetype=evidence.get("archetype"),
                provenance=provenance,
                citations=[str(c) for c in evidence.get("citations", [])],
            ),
        )

    industry_raw = data.get("industry") or {}
    industry = IndustryClassification(
        business_model=str(industry_raw.get("business_model") or "Unknown"),
        industry_vertical=str(industry_raw.get("industry_vertical") or "Unknown"),
        company_stage=str(industry_raw.get("company_stage") or "Unknown"),
        employee_estimate=str(industry_raw.get("employee_estimate") or "Unknown"),
        confidence=str(industry_raw.get("confidence") or "Low"),
        cited_evidence=[str(c) for c in industry_raw.get("cited_evidence", [])],
        source=str(industry_raw.get("source") or "loaded"),
    )

    return RolePlan(
        observed=[_hydrate_role(r) for r in data.get("observed", [])],
        plausible=[_hydrate_role(r) for r in data.get("plausible", [])],
        gap_flagged=[_hydrate_role(r) for r in data.get("gap_flagged", [])],
        operator_added=[_hydrate_role(r) for r in data.get("operator_added", [])],
        operator_skipped=[str(s) for s in data.get("operator_skipped", [])],
        final_roster=[_hydrate_role(r) for r in data.get("final_roster", [])],
        industry=industry,
        evidence_summary=dict(data.get("evidence_summary") or {}),
        plan_md_path=data.get("plan_md_path"),
        plan_json_path=str(json_path),
    )


__all__ = ["load_plan", "plan_roles"]
