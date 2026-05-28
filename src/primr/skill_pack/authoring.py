"""Phase 3: author SKILL.md content for each role.

Runs in parallel (ThreadPoolExecutor) per role. Each call produces a list
of skills heavily customized to the company's specific signals — the
archetype is treated as a territory hint, not a template.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from primr.skill_pack.archetypes import (
    ArchetypeMatch,
    grounding_prompt_fragment,
    load_archetypes,
    match_archetype,
)
from primr.skill_pack.discovery import load_evidence
from primr.skill_pack.prompts_loader import extract_json, load_skill_pack_prompt
from primr.skill_pack.schema import Role, Skill

logger = logging.getLogger(__name__)

# Parallelism cap matches the section-writing pattern in research_agent.py.
# Going higher hits provider rate limits without much wallclock gain.
_MAX_PARALLEL_AUTHORS = 4


def _resolve_archetype_grounding(role: Role) -> tuple[ArchetypeMatch, str]:
    """Pick an archetype (if any) and render its grounding fragment."""
    hints = [role.evidence.archetype] if role.evidence.archetype else None
    match = match_archetype(role.display_name, hints=hints)
    if match.archetype is None:
        return match, "(no bundled archetype matched — author from company evidence only)"
    grounding = grounding_prompt_fragment(match.archetype, max_skills=8)
    return match, grounding


def author_role_skills(
    role: Role,
    company_name: str,
    company_url: str | None,
    skills_per_role: int,
    recon_evidence: str,
    hiring_evidence: str,
    industry_context: str = "(unknown)",
) -> list[Skill]:
    """Produce the skills for one role. Synchronous (call from a worker).

    Authoring runs fresh per-role (NOT inside the shared reasoning session)
    so the ThreadPoolExecutor doesn't serialize through one session. The
    pack-level coherence pass downstream picks up cross-role consistency.
    """
    match, archetype_grounding = _resolve_archetype_grounding(role)
    if match.archetype is not None:
        # Mutate the role's evidence so the packager report can show what
        # the pipeline actually grounded against.
        role.evidence.archetype = match.archetype.slug

    prompt = load_skill_pack_prompt("author_skill")
    user_msg = prompt.render(
        role_name=role.name,
        role_display_name=role.display_name,
        role_archetype=role.evidence.archetype or "(none)",
        role_confidence=role.confidence,
        role_summary=role.summary or "(none)",
        role_sources=", ".join(role.evidence.sources) or "(none)",
        company_name=company_name,
        company_url=company_url or "(not provided)",
        industry_context=industry_context,
        recon_signals=recon_evidence,
        hiring_signals=hiring_evidence,
        archetype_grounding=archetype_grounding,
        skills_per_role=skills_per_role,
    )

    from primr.ai.grok_client import grok_llm

    response_text = grok_llm(
        user_msg,
        system_prompt=prompt.system_prompt,
        temperature=0.4,
        max_tokens=16_000,
    )
    parsed = extract_json(response_text)

    skills_raw = parsed.get("skills") or []
    if not isinstance(skills_raw, list):
        raise ValueError(f"author_role_skills: expected list, got {type(skills_raw).__name__}")

    skills: list[Skill] = []
    for entry in skills_raw[:skills_per_role]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        body = str(entry.get("body", "")).strip()
        # Normalize \n escape sequences that may leak in from JSON literals.
        body = body.replace("\\n", "\n")
        skills.append(
            Skill(
                name=name,
                display_name=str(entry.get("display_name", name)).strip(),
                description=str(entry.get("description", "")).strip(),
                body=body,
                canonical_skill_basis=(
                    str(entry.get("canonical_skill_basis"))
                    if entry.get("canonical_skill_basis")
                    else None
                ),
            )
        )

    return skills


def author_all_roles(
    roles: list[Role],
    company_name: str,
    company_url: str | None,
    skills_per_role: int,
    working_dir: Path,
    industry_context: str = "(unknown)",
) -> None:
    """Author skills for every role in parallel. Mutates roles in place."""
    # Reuse the evidence load — discover_roles already validated they exist.
    recon, hiring = load_evidence(working_dir)
    # Trim more aggressively for authoring (the model only needs the
    # role-specific signals, not the full hiring corpus).
    recon_trim = recon[:5_000]
    hiring_trim = hiring[:8_000]

    # Ensure archetype data is loaded once before workers fan out.
    load_archetypes()

    errors: dict[str, Exception] = {}

    def _worker(role: Role) -> tuple[Role, list[Skill]]:
        skills = author_role_skills(
            role,
            company_name,
            company_url,
            skills_per_role,
            recon_trim,
            hiring_trim,
            industry_context=industry_context,
        )
        return role, skills

    workers = min(_MAX_PARALLEL_AUTHORS, max(1, len(roles)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_worker, role): role for role in roles}
        for future in as_completed(futures):
            role = futures[future]
            try:
                _, skills = future.result()
                role.skills = skills
                logger.info("Authored %d skills for role %s", len(skills), role.name)
            except Exception as exc:
                logger.warning("Authoring failed for role %s: %s", role.name, exc)
                errors[role.name] = exc

    if errors and len(errors) == len(roles):
        raise RuntimeError(f"All authoring calls failed: {list(errors.keys())}")


__all__ = ["author_all_roles", "author_role_skills"]
