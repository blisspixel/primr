"""Render and persist skill-pack role-plan artifacts."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from primr.skill_pack.schema import Role, RolePlan
from primr.utils.security import mask_sensitive_data

logger = logging.getLogger(__name__)


def persist_plan(
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
        md_text = mask_sensitive_data(render_plan_md(company_name, plan, generated_at, roles_count))
        md_path.write_text(md_text, encoding="utf-8")
        plan.plan_md_path = str(md_path)
        json_text = mask_sensitive_data(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
        json_path.write_text(json_text, encoding="utf-8")
        plan.plan_json_path = str(json_path)
        logger.info("Wrote role plan to %s and %s", md_path, json_path)
    except OSError as exc:
        logger.warning("Failed to persist role plan: %s", exc)


def render_plan_md(
    company_name: str,
    plan: RolePlan,
    generated_at: str,
    roles_count: int,
) -> str:
    lines: list[str] = []
    lines.append(f"# Role Plan - {company_name}")
    lines.append("")
    lines.append(f"_Created {generated_at}._")
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

    _append_posting_coverage(lines, plan.evidence_summary)

    lines.append(f"## Observed Roles - {len(plan.observed)} (from postings)")
    lines.append("")
    if plan.observed:
        for role in plan.observed:
            lines.append(_format_role_block(role))
            lines.append("")
    else:
        lines.append("_No observed roles - no posting evidence available._")
        lines.append("")

    lines.append(f"## Plausible Roles - {len(plan.plausible)} (from research + industry)")
    lines.append("")
    if plan.plausible:
        for role in plan.plausible:
            lines.append(_format_role_block(role))
            lines.append("")
    else:
        lines.append("_No plausible roles inferred - research signal was insufficient._")
        lines.append("")

    if plan.operator_added:
        lines.append(
            f"## Operator-Added Roles - {len(plan.operator_added)} (supplied via --roles-add)"
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
            f"## Operator-Skipped Roles - {len(plan.operator_skipped)} (dropped via --roles-skip)"
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
        lines.append(f"## Gap-flagged Roles - {len(plan.gap_flagged)} (excluded from this pack)")
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
            f"{idx}. **{role.display_name}** - `{role.name}` ({provenance}, {role.confidence})"
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


def _append_posting_coverage(lines: list[str], summary: dict[str, Any]) -> None:
    status = str(summary.get("posting_coverage_status") or "")
    if not status:
        return
    lines.append("## Posting Coverage")
    lines.append("")
    lines.append(f"- Status: **{status}**")
    dominant = str(summary.get("posting_coverage_dominant_bucket") or "")
    if dominant:
        share = float(summary.get("posting_coverage_dominant_share") or 0.0)
        lines.append(f"- Dominant observed band: `{dominant}` ({share:.0%})")
    reason = str(summary.get("posting_coverage_reason") or "")
    if reason:
        lines.append(f"- Reason: {reason}")
    recommendation = str(summary.get("posting_coverage_recommendation") or "")
    if recommendation:
        lines.append(f"- Recommended operator action: {recommendation}")
    lines.append("")


__all__ = ["persist_plan", "render_plan_md"]
