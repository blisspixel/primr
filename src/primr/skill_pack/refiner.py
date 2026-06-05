"""Phase 5: per-skill refinement loop + pack-level coherence pass.

Two refinement stages:

  1. **Per-skill refinement** — for each Skill with HARD validator
     findings, send the draft + structured findings back through an LLM
     and let it fix the issues. Iteration cap from config. Diminishing
     returns stop if findings don't drop by ≥50% per iteration.

  2. **Pack-level coherence pass** — one LLM call sees a summary of
     every skill in the pack and identifies trigger collisions,
     semantic overlaps, voice drift, and strategic inconsistencies.
     If the verdict is "refine", a single pack-level refinement round
     follows (typically updating descriptions / trigger phrasing rather
     than rewriting bodies).

Refinement runs inside the shared ContinuousReasoningSession when one is
provided — the validator's view of the whole pack is more useful when
the model already has the role drafts in context.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import Any

from primr.skill_pack.config import SkillPackConfig
from primr.skill_pack.prompts_loader import extract_json, load_skill_pack_prompt
from primr.skill_pack.schema import (
    IssueSeverity,
    Role,
    Skill,
    SkillIssue,
    SkillPack,
    ValidationReport,
)
from primr.skill_pack.validator import is_body_too_short, validate_skill

logger = logging.getLogger(__name__)


def _actionable_findings(skill: Skill, role_name: str) -> list[SkillIssue]:
    """Findings worth a refinement turn: all HARD findings, plus the
    too-short-body SOFT (a thin body is cheaply fixable and materially
    improves the skill). Other SOFT findings (e.g. DESC-PUSHY, gerund
    hints) are advisory and intentionally NOT auto-refined here — they are
    handled by the description-optimization loop, not per-skill rewrites.
    """
    findings = validate_skill(skill, role_name)
    actionable: list[SkillIssue] = []
    for f in findings:
        if f.severity == IssueSeverity.HARD or (
            f.code == "BODY-LEN" and is_body_too_short(skill.body)
        ):
            actionable.append(f)
    return actionable


# ---------------------------------------------------------------------------
# Per-skill refinement
# ---------------------------------------------------------------------------


def _findings_table(findings: Iterable[SkillIssue]) -> str:
    """Render validator findings as a markdown table for the LLM."""
    lines = ["| Severity | Code | Field | Message |", "|----------|------|-------|---------|"]
    for f in findings:
        msg = f.message.replace("|", "\\|")
        lines.append(f"| {f.severity.value.upper()} | {f.code} | {f.field or '-'} | {msg} |")
    return "\n".join(lines)


def _skill_to_json(skill: Skill) -> str:
    return json.dumps(
        {
            "name": skill.name,
            "display_name": skill.display_name,
            "description": skill.description,
            "body": skill.body,
            "canonical_skill_basis": skill.canonical_skill_basis,
        },
        ensure_ascii=False,
        indent=2,
    )


def _apply_refined(skill: Skill, parsed: dict) -> Skill:
    """Return a new Skill with refined fields, falling back to originals."""
    return Skill(
        name=str(parsed.get("name") or skill.name).strip(),
        display_name=str(parsed.get("display_name") or skill.display_name).strip(),
        description=str(parsed.get("description") or skill.description).strip(),
        body=str(parsed.get("body") or skill.body).replace("\\n", "\n").strip(),
        canonical_skill_basis=(
            str(parsed.get("canonical_skill_basis"))
            if parsed.get("canonical_skill_basis")
            else skill.canonical_skill_basis
        ),
        references=list(skill.references),
        bundled_files=list(skill.bundled_files),
    )


def refine_skill(
    skill: Skill,
    findings: list[SkillIssue],
    company_context: str,
    *,
    reasoning_session: Any | None = None,
) -> Skill:
    """One refinement turn for one skill."""
    prompt = load_skill_pack_prompt("refine_skill")
    user_msg = prompt.render(
        findings_table=_findings_table(findings),
        current_draft_json=_skill_to_json(skill),
        company_context=company_context,
    )

    if reasoning_session is not None and hasattr(reasoning_session, "send"):
        response = reasoning_session.send(
            f"{prompt.system_prompt}\n\n{user_msg}",
            temperature=0.3,
            max_tokens=12_000,
        )
    else:
        from primr.ai.grok_client import grok_llm

        response = grok_llm(
            user_msg,
            system_prompt=prompt.system_prompt,
            temperature=0.3,
            max_tokens=12_000,
        )

    try:
        parsed = extract_json(response)
    except ValueError as exc:
        logger.warning("Refinement returned unparseable JSON for %s: %s", skill.name, exc)
        return skill

    return _apply_refined(skill, parsed)


def refine_role(
    role: Role,
    config: SkillPackConfig,
    company_context: str,
    *,
    reasoning_session: Any | None = None,
) -> dict[str, int]:
    """Refine every failing skill on a role until clean or cap reached.

    Returns a dict mapping skill name → iterations used (for the pack report).
    """
    iterations_per_skill: dict[str, int] = {}

    for idx, skill in enumerate(role.skills):
        findings = _actionable_findings(skill, role.name)
        if not findings:
            continue

        last_count = len(findings)
        for iteration in range(1, config.max_refine_iterations + 1):
            refined = refine_skill(
                skill,
                findings,
                company_context,
                reasoning_session=reasoning_session,
            )
            role.skills[idx] = refined
            skill = refined

            new_findings = _actionable_findings(skill, role.name)
            iterations_per_skill[skill.name] = iteration

            if not new_findings:
                logger.info(
                    "Skill %s/%s cleared actionable findings after %d iteration(s)",
                    role.name,
                    skill.name,
                    iteration,
                )
                break

            # Diminishing returns: if fewer than half of the actionable
            # findings were resolved, further iterations rarely converge.
            reduction = (last_count - len(new_findings)) / max(1, last_count)
            if reduction < 0.5:
                logger.info(
                    "Skill %s/%s diminishing returns at iteration %d "
                    "(reduction=%.2f), stopping refinement",
                    role.name,
                    skill.name,
                    iteration,
                    reduction,
                )
                break

            last_count = len(new_findings)
            findings = new_findings

    return iterations_per_skill


# ---------------------------------------------------------------------------
# Pack-level coherence
# ---------------------------------------------------------------------------


def _pack_summary(pack: SkillPack) -> str:
    lines: list[str] = []
    for role in pack.roles:
        for skill in role.skills:
            lines.append(f"- `{role.name}/{skill.name}` — {skill.description}")
    return "\n".join(lines)


def run_pack_coherence_pass(
    pack: SkillPack,
    *,
    reasoning_session: Any | None = None,
) -> dict:
    """Run the pack-level coherence check. Returns the parsed JSON verdict.

    Note: we don't auto-apply coherence fixes inline — the verdict is
    appended to the pack report so a human can decide whether the
    overlaps/collisions matter for their use case. (Auto-fixing risks
    rewriting good skills based on noisy similarity signals.)
    """
    prompt = load_skill_pack_prompt("pack_coherence")
    user_msg = prompt.render(
        company_name=pack.company_name,
        pack_summary=_pack_summary(pack),
    )

    if reasoning_session is not None and hasattr(reasoning_session, "send"):
        response = reasoning_session.send(
            f"{prompt.system_prompt}\n\n{user_msg}",
            temperature=0.2,
            max_tokens=4_000,
        )
    else:
        from primr.ai.grok_client import grok_llm

        response = grok_llm(
            user_msg,
            system_prompt=prompt.system_prompt,
            temperature=0.2,
            max_tokens=4_000,
        )

    try:
        return extract_json(response)
    except ValueError as exc:
        logger.warning("Pack coherence pass returned unparseable JSON: %s", exc)
        return {"verdict": "ship", "_error": str(exc)}


def _locate_skill(pack: SkillPack, key: str | None) -> tuple[Role, int, Skill] | None:
    """Find a skill by its `role-name/skill-name` key. Returns
    (role, index_in_role, skill) or None. Tolerant of a bare skill name
    (no role prefix) by falling back to a name search across the pack.
    """
    if not key:
        return None
    role_part, _, skill_part = key.partition("/")
    skill_name = skill_part or role_part
    for role in pack.roles:
        if skill_part and role.name != role_part:
            continue
        for idx, skill in enumerate(role.skills):
            if skill.name == skill_name:
                return role, idx, skill
    return None


def auto_resolve_overlaps(
    pack: SkillPack,
    coherence: dict,
    company_context: str,
    *,
    reasoning_session: Any | None = None,
) -> list[str]:
    """Re-scope ONE skill of each overlapping / colliding pair so the two
    stop overlapping, instead of merely flagging them.

    Conservative by design (the coherence signal is LLM-derived, not
    deterministic):
      - Only the SECOND skill of a pair (`skill_b`) is touched; `skill_a`
        is left as the owner of the shared ground.
      - A re-scope that introduces a NEW hard finding is reverted.
      - Resolved entries are POPPED from `coherence` so a later
        `attach_coherence_findings_as_issues` reflects only what remains
        unresolved.

    Returns human-readable descriptions of the pairs it resolved.
    """
    resolved: list[str] = []

    plans: list[tuple[str, str, dict]] = []
    for entry in coherence.get("semantic_overlaps") or []:
        plans.append(("PACK-OVERLAP-LLM", entry.get("overlap_summary") or "", entry))
    for entry in coherence.get("trigger_collisions") or []:
        plans.append(("PACK-TRIGGER", entry.get("fix") or "", entry))

    for code, detail, entry in plans:
        a_key = entry.get("skill_a")
        b_key = entry.get("skill_b")
        located = _locate_skill(pack, b_key)
        if located is None:
            continue
        role, idx, skill = located

        issue = SkillIssue(
            code=code,
            severity=IssueSeverity.SOFT,
            message=(
                f"This skill overlaps with `{a_key}`. Narrow THIS skill's scope, "
                f"workflow, and trigger phrasing so it no longer overlaps with "
                f"`{a_key}` — treat `{a_key}` as the owner of the shared ground and "
                f"move this skill to the distinct part of the work. Do NOT broaden. "
                f"Overlap detail: {detail}"
            ),
            role_name=role.name,
            field="description",
        )

        before_hard = sum(
            1 for f in validate_skill(skill, role.name) if f.severity == IssueSeverity.HARD
        )
        refined = refine_skill(skill, [issue], company_context, reasoning_session=reasoning_session)
        after_hard = sum(
            1 for f in validate_skill(refined, role.name) if f.severity == IssueSeverity.HARD
        )
        if after_hard > before_hard:
            logger.info("Auto-resolve of %s introduced a HARD finding; reverting", b_key)
            continue

        role.skills[idx] = refined
        resolved.append(f"{b_key} re-scoped to not overlap {a_key}")
        # Drop the resolved entry so the attached report reflects reality.
        try:
            if code == "PACK-OVERLAP-LLM":
                coherence["semantic_overlaps"].remove(entry)
            else:
                coherence["trigger_collisions"].remove(entry)
        except (KeyError, ValueError):
            pass

    if resolved:
        logger.info("Auto-resolved %d overlap/collision pair(s)", len(resolved))
    return resolved


def attach_coherence_findings_as_issues(pack: SkillPack, coherence: dict) -> ValidationReport:
    """Convert pack coherence verdict into SkillIssue objects for the
    validation report shown in the pack report markdown.
    """
    issues: list[SkillIssue] = []

    for entry in coherence.get("trigger_collisions") or []:
        issues.append(
            SkillIssue(
                code="PACK-TRIGGER",
                severity=IssueSeverity.SOFT,
                message=(
                    f"Trigger collision between {entry.get('skill_a')} and "
                    f"{entry.get('skill_b')}: {entry.get('fix') or 'differentiate triggers'}"
                ),
            )
        )
    for entry in coherence.get("semantic_overlaps") or []:
        issues.append(
            SkillIssue(
                code="PACK-OVERLAP-LLM",
                severity=IssueSeverity.SOFT,
                message=(
                    f"Semantic overlap between {entry.get('skill_a')} and "
                    f"{entry.get('skill_b')}: {entry.get('overlap_summary')}"
                ),
            )
        )
    if coherence.get("voice_drift"):
        issues.append(
            SkillIssue(
                code="PACK-VOICE",
                severity=IssueSeverity.SOFT,
                message=str(coherence["voice_drift"]),
            )
        )
    for entry in coherence.get("strategic_inconsistencies") or []:
        issues.append(
            SkillIssue(
                code="PACK-STRAT",
                severity=IssueSeverity.HARD,  # contradictions are ship-blocking
                message=(
                    f"Strategic inconsistency in {entry.get('skills')}: {entry.get('description')}"
                ),
            )
        )
    return ValidationReport(issues=pack.validation.issues + issues)


__all__ = [
    "attach_coherence_findings_as_issues",
    "auto_resolve_overlaps",
    "refine_role",
    "refine_skill",
    "run_pack_coherence_pass",
]
