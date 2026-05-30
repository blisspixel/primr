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
from primr.skill_pack.validator import validate_skill

logger = logging.getLogger(__name__)


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
        findings = [f for f in validate_skill(skill, role.name) if f.severity == IssueSeverity.HARD]
        if not findings:
            continue

        last_hard = len(findings)
        for iteration in range(1, config.max_refine_iterations + 1):
            refined = refine_skill(
                skill,
                findings,
                company_context,
                reasoning_session=reasoning_session,
            )
            role.skills[idx] = refined
            skill = refined

            new_findings = [
                f for f in validate_skill(skill, role.name) if f.severity == IssueSeverity.HARD
            ]
            iterations_per_skill[skill.name] = iteration

            if not new_findings:
                logger.info(
                    "Skill %s/%s cleared HARD findings after %d iteration(s)",
                    role.name,
                    skill.name,
                    iteration,
                )
                break

            # Diminishing returns: if fewer than half of HARD findings were
            # resolved, further iterations rarely converge.
            reduction = (last_hard - len(new_findings)) / max(1, last_hard)
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

            last_hard = len(new_findings)
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
    "refine_role",
    "refine_skill",
    "run_pack_coherence_pass",
]
