"""Deterministic operator curation for skill-pack role plans."""

from __future__ import annotations

import logging
import re

from primr.skill_pack.archetypes import match_archetype
from primr.skill_pack.config import MAX_ROLES
from primr.skill_pack.schema import Role, RoleEvidence, RolePlan, RoleProvenance

logger = logging.getLogger(__name__)

_CURATION_NAME_RE = re.compile(r"[^a-z0-9]+")


def _normalize_curation_key(label: str) -> str:
    """Normalize an operator label to the same shape as a role slug."""
    return _CURATION_NAME_RE.sub("-", label.lower()).strip("-")


def _materialize_added_role(label: str) -> Role:
    """Turn one operator-provided label into an override-provenance role."""
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
    """Return whether an operator skip exactly matches a role label or slug."""
    candidates = {
        _normalize_curation_key(role.name),
        _normalize_curation_key(role.display_name),
    }
    return bool(candidates & skip_keys)


def _drop_excess_to_cap(roster: list[Role], cap: int) -> tuple[list[Role], list[Role]]:
    """Enforce the role cap while preserving operator roles preferentially."""
    if len(roster) <= cap:
        return list(roster), []

    overflow = len(roster) - cap
    priority: dict[int, int] = {}
    for idx, role in enumerate(roster):
        provenance = role.evidence.provenance
        if provenance in (RoleProvenance.RESEARCH, RoleProvenance.INDUSTRY):
            priority[idx] = 0
        elif provenance == RoleProvenance.POSTING:
            priority[idx] = 1
        else:
            priority[idx] = 2

    trim_order = sorted(
        range(len(roster)),
        key=lambda index: (priority[index], -index),
    )
    drop_indices = set(trim_order[:overflow])

    kept = [role for index, role in enumerate(roster) if index not in drop_indices]
    trimmed = [role for index, role in enumerate(roster) if index in drop_indices]
    return kept, trimmed


def apply_curation(
    plan: RolePlan,
    *,
    roles_add: list[str],
    roles_skip: list[str],
    cap: int = MAX_ROLES,
) -> None:
    """Atomically apply operator skips and additions to a role plan."""
    skip_keys = {_normalize_curation_key(value) for value in roles_skip if value.strip()}
    survivors_after_skip = (
        [role for role in plan.final_roster if not _match_skip_target(role, skip_keys)]
        if skip_keys
        else list(plan.final_roster)
    )
    projected_total = len(survivors_after_skip) + len(roles_add)
    if projected_total == 0:
        raise RuntimeError(
            "Curation would leave an empty roster; every role was "
            "skipped and no replacements were added. Re-run with fewer "
            "--roles-skip entries or supply --roles-add to fill the "
            "roster. (Plan unchanged.)"
        )

    operator_skipped = sorted(
        {
            *(_normalize_curation_key(value) for value in plan.operator_skipped),
            *skip_keys,
        }
    )

    if skip_keys:
        existing_keys: set[str] = set()
        for role in plan.final_roster:
            existing_keys.add(_normalize_curation_key(role.name))
            existing_keys.add(_normalize_curation_key(role.display_name))
        unmatched = skip_keys - existing_keys
        for key in sorted(unmatched):
            logger.warning("--roles-skip %r did not match any role in the plan", key)

    curated_roster = survivors_after_skip
    added: list[Role] = []
    if roles_add:
        existing_name_keys = {_normalize_curation_key(role.name) for role in curated_roster}
        existing_display_keys = {
            _normalize_curation_key(role.display_name) for role in curated_roster
        }
        discovered_archetypes = {
            role.evidence.archetype
            for role in curated_roster
            if role.evidence.provenance != RoleProvenance.OVERRIDE
            and role.evidence.archetype is not None
        }

        for label in roles_add:
            candidate = _materialize_added_role(label)
            candidate_name_key = _normalize_curation_key(candidate.name)
            candidate_display_key = _normalize_curation_key(candidate.display_name)

            if (
                candidate_name_key in existing_name_keys
                or candidate_display_key in existing_display_keys
            ):
                logger.warning(
                    "--roles-add %r; already in roster, skipping duplicate",
                    label,
                )
                continue

            if (
                candidate.evidence.archetype is not None
                and candidate.evidence.archetype in discovered_archetypes
            ):
                logger.warning(
                    "--roles-add %r; archetype %s already covered by a "
                    "discovered role, skipping duplicate. Pair with "
                    "--roles-skip to force this label.",
                    label,
                    candidate.evidence.archetype,
                )
                continue

            added.append(candidate)
            existing_name_keys.add(candidate_name_key)
            existing_display_keys.add(candidate_display_key)

        curated_roster = curated_roster + added

    overflow = max(0, len(curated_roster) - cap)
    discovered_count = sum(
        role.evidence.provenance != RoleProvenance.OVERRIDE for role in curated_roster
    )
    if overflow > discovered_count:
        raise RuntimeError(
            "Curation exceeds the role cap and cannot preserve every "
            "operator-supplied role. Remove an existing operator role or "
            "skip another role before adding a replacement."
        )
    kept, trimmed = _drop_excess_to_cap(curated_roster, cap)
    if not kept:
        raise RuntimeError(
            "Curation left an empty roster. Use fewer role removals or add "
            "at least one distinct replacement role."
        )

    operator_added = [role for role in kept if role.evidence.provenance == RoleProvenance.OVERRIDE]

    plan.final_roster = kept
    plan.operator_added = operator_added
    plan.operator_skipped = operator_skipped
    if trimmed:
        plan.gap_flagged = plan.gap_flagged + trimmed
        logger.info(
            "Curation cap trimmed %d role(s) to gap_flagged "
            "(operator-priority order: plausible -> observed -> never override)",
            len(trimmed),
        )
    plan.evidence_summary["operator_added_count"] = len(plan.operator_added)
    plan.evidence_summary["operator_skipped_count"] = len(plan.operator_skipped)
    plan.evidence_summary["final_roster_count"] = len(plan.final_roster)
    plan.evidence_summary["gap_flagged_count"] = len(plan.gap_flagged)


__all__ = ["apply_curation"]
