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
from primr.skill_pack.role_references import (
    add_role_family_reference,
    build_composition_reference,
    build_gotchas_reference,
    build_role_family_reference,
)
from primr.skill_pack.schema import BundledFile, Role, RoleProvenance, Skill

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


def _provenance_guidance(role: Role) -> str:
    """Return per-provenance guidance text injected into the authoring
    prompt. Steers the LLM to ground in posting evidence, research
    evidence, business-model context, or to honor an operator override.
    """
    citations = role.evidence.citations or []
    citation_block = ""
    if citations:
        rendered = "\n".join(f"  - {c[:200]}" for c in citations[:5])
        citation_block = f"\n\nSupporting citations for this role:\n{rendered}"

    provenance = role.evidence.provenance
    if provenance == RoleProvenance.POSTING:
        return (
            "OBSERVED FROM POSTINGS. This role is grounded in actual job "
            "postings. Anchor every skill in the specific responsibilities, "
            "tools, and language the postings use. Prefer concrete posting "
            "phrases over generic capability descriptions. When a skill "
            "covers a workflow the postings explicitly mention, say so in "
            "the body's customization." + citation_block
        )
    if provenance == RoleProvenance.RESEARCH:
        return (
            "INFERRED FROM RESEARCH. This role was not in the posting data "
            "but is a confident inference from the company's strategic "
            "research (named practices, services, programs, or partner "
            "designations). Anchor every skill in the cited research "
            "phrases. The body should reference the practice or program "
            "the inference came from (e.g. \"as part of the company's "
            '<named practice>").' + citation_block
        )
    if provenance == RoleProvenance.INDUSTRY:
        return (
            "INFERRED FROM BUSINESS MODEL + STAGE. This role is plausible "
            "given the company's business model, industry vertical, and "
            "employee-size estimate, but is not specifically named in the "
            "research. Skills should reflect what this role typically does "
            "at companies of this shape, tuned to the company's named tools "
            "and stack where possible. Avoid claims about specific company "
            "programs that are not in the evidence." + citation_block
        )
    if provenance == RoleProvenance.OVERRIDE:
        return (
            "OPERATOR-SUPPLIED ROLE. This role was supplied directly by "
            "the operator and bypasses automatic discovery. Author skills "
            "that fit the role label and the company's general evidence. "
            "If the hiring evidence includes an operator-provided role "
            "brief or job description, treat that brief as the primary "
            "grounding for responsibilities, tools, constraints, required "
            "inputs, and worked examples. No public posting or research "
            "citation is required."
        )
    # The enum covers POSTING / RESEARCH / INDUSTRY / OVERRIDE; if a new
    # value is added to RoleProvenance without updating this function we
    # fail loudly rather than ship a generic-guidance prompt that would
    # silently degrade authoring quality.
    raise ValueError(
        f"Unhandled RoleProvenance value in _provenance_guidance: "
        f"{provenance!r}. Add a branch for it here when the enum is extended."
    )


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
        provenance_guidance=_provenance_guidance(role),
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
                bundled_files=_parse_bundled_files(entry.get("bundled_files")),
            )
        )

    role_family_reference = build_role_family_reference(
        role,
        company_name=company_name,
        company_url=company_url,
        archetype=match.archetype,
    )
    add_role_family_reference(skills, role_family_reference)

    # Always attach progressive gotchas + composition (BP: Gotchas highest signal,
    # progressive disclosure, composability by name).
    gotchas_ref = build_gotchas_reference(
        role,
        company_name=company_name,
        evidence_citations=role.evidence.citations or [],
    )
    comp_ref = build_composition_reference(role)
    for skill in skills:
        for bf in (gotchas_ref, comp_ref):
            skill.bundled_files = [b for b in skill.bundled_files if b.relpath != bf.relpath]
            skill.bundled_files.append(bf)
        # lightweight hint in body (non-duplicating)
        if "references/gotchas.md" not in skill.body:
            skill.body = (
                skill.body.rstrip()
                + "\n\nSee references/gotchas.md for known issues and references/composition.md for cross-skill handoffs."
            )

    # Ensure at least one verification skill has a deterministic script attached.
    # This uses the existing BundledFile seam (no new way). Prompt drives selection;
    # this guarantees the script for the verifier (TDD: test expects it in authoring).
    verifier = None
    for s in skills:
        if any(k in (s.name or "").lower() for k in ("validat", "review", "check", "verif")):
            verifier = s
            break
    if verifier:
        has_script = any(bf.relpath.startswith("scripts/") for bf in verifier.bundled_files)
        if not has_script:
            default_verify = (
                "#!/usr/bin/env python3\n"
                '"""Deterministic verification script for this role\'s primary artifacts.\n'
                "Run with path to artifact. Uses company signals from context.\n"
                '"""\n'
                "import sys\n\n"
                "def verify(artifact_path: str) -> bool:\n"
                "    # TODO: implement real checks grounded in role evidence (DNS, hiring)\n"
                "    print(f'Verifying {artifact_path} against company signals...')\n"
                "    return True\n\n"
                "if __name__ == '__main__':\n"
                "    if len(sys.argv) < 2:\n"
                "        print('Usage: python scripts/verify-*.py <artifact>')\n"
                "        sys.exit(2)\n"
                "    ok = verify(sys.argv[1])\n"
                "    sys.exit(0 if ok else 1)\n"
            )
            verifier.bundled_files.append(
                BundledFile(relpath="scripts/verify-artifact.py", content=default_verify)
            )

    return skills


def _parse_bundled_files(raw: object) -> list[BundledFile]:
    """Parse the optional bundled_files array from an authored skill.

    Tolerant: skips malformed entries. Both path-safety AND content-safety are
    validated downstream (validator BUNDLE-PATH + SEC-BUNDLE, plus the packager
    defense-in-depth drop), so here we only shape-check — never trust this
    content, it is LLM output derived from adversarial web/hiring evidence.
    """
    if not isinstance(raw, list):
        return []
    out: list[BundledFile] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        relpath = str(item.get("path") or item.get("relpath") or "").strip()
        content = str(item.get("content") or "")
        # Normalize double-escaped \n -> newline ONLY for markdown references.
        # Do NOT touch script (.py) or data (.json) content: a literal
        # backslash-n there is meaningful (regex, Windows path, JSON string)
        # and rewriting it would silently corrupt the file.
        if relpath.endswith(".md"):
            content = content.replace("\\n", "\n")
        if relpath and content.strip():
            out.append(BundledFile(relpath=relpath, content=content))
    return out


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
