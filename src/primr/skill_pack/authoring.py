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
from primr.skill_pack.script_safety import (
    scan_authored_executable_instructions,
)
from primr.skill_pack.validator import validate_bundled_path, validate_kebab_case
from primr.skill_pack.verifier_asset import (
    VERIFY_ARTIFACT_SCRIPT,
    VERIFY_ARTIFACT_SCRIPT_PATH,
    has_registered_verifier_invocation,
    insert_registered_verifier_invocation,
    is_verification_skill_name,
    registered_verifier_path_count,
)
from primr.utils.content_sanitizer import fence_untrusted

logger = logging.getLogger(__name__)

# Parallelism cap matches the section-writing pattern in research_agent.py.
# Going higher hits provider rate limits without much wallclock gain.
_MAX_PARALLEL_AUTHORS = 4


def _fenced_prompt_value(label: str, value: str | None, *, empty: str) -> str:
    """Return untrusted authoring context as sanitized, explicitly fenced data."""
    if not value or not value.strip():
        return empty
    return fence_untrusted(label, value)


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
        rendered = _fenced_prompt_value(
            "ROLE_CITATIONS",
            "\n".join(citation[:200] for citation in citations[:5]),
            empty="(none)",
        )
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
    if not validate_kebab_case(role.name):
        raise ValueError(f"author_role_skills: invalid role name {role.name!r}")

    match, archetype_grounding = _resolve_archetype_grounding(role)
    if match.archetype is not None:
        # Mutate the role's evidence so the packager report can show what
        # the pipeline actually grounded against.
        role.evidence.archetype = match.archetype.slug

    prompt = load_skill_pack_prompt("author_skill")
    user_msg = prompt.render(
        role_name=role.name,
        role_name_context=_fenced_prompt_value("ROLE_NAME", role.name, empty="(unknown)"),
        role_display_name=_fenced_prompt_value(
            "ROLE_DISPLAY_NAME", role.display_name, empty="(unknown)"
        ),
        role_archetype=_fenced_prompt_value(
            "ROLE_ARCHETYPE", role.evidence.archetype, empty="(none)"
        ),
        role_confidence=_fenced_prompt_value("ROLE_CONFIDENCE", role.confidence, empty="(unknown)"),
        role_summary=_fenced_prompt_value("ROLE_SUMMARY", role.summary, empty="(none)"),
        role_sources=_fenced_prompt_value(
            "ROLE_SOURCES", ", ".join(role.evidence.sources), empty="(none)"
        ),
        company_name=_fenced_prompt_value("COMPANY_NAME", company_name, empty="(unknown)"),
        company_url=_fenced_prompt_value("COMPANY_URL", company_url, empty="(not provided)"),
        industry_context=_fenced_prompt_value(
            "INDUSTRY_CONTEXT", industry_context, empty="(unknown)"
        ),
        recon_signals=_fenced_prompt_value("RECON_EVIDENCE", recon_evidence, empty="(none)"),
        hiring_signals=_fenced_prompt_value("HIRING_EVIDENCE", hiring_evidence, empty="(none)"),
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
        display_name = str(entry.get("display_name", name)).strip()
        description = str(entry.get("description", "")).strip()
        body = str(entry.get("body", "")).strip()
        # Normalize \n escape sequences that may leak in from JSON literals.
        body = body.replace("\\n", "\n")
        for field_name, content in (
            ("display_name", display_name),
            ("description", description),
            ("body", body),
        ):
            executable_instruction = scan_authored_executable_instructions(content)
            if executable_instruction is not None:
                raise ValueError(
                    "author_role_skills: rejected executable instruction in "
                    f"{field_name}: {executable_instruction}"
                )
        skills.append(
            Skill(
                name=name,
                display_name=display_name,
                description=description,
                body=body,
                canonical_skill_basis=(
                    str(entry.get("canonical_skill_basis"))
                    if entry.get("canonical_skill_basis")
                    else None
                ),
                bundled_files=_parse_bundled_files(entry.get("bundled_files")),
            )
        )

    verifiers = [skill for skill in skills if is_verification_skill_name(skill.name)]
    if len(verifiers) != 1:
        raise ValueError(
            f"author_role_skills: expected exactly one verification skill, got {len(verifiers)}"
        )
    verifier = verifiers[0]

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

    # Attach the reviewed verifier and its invocation to the one verification
    # skill required above. No model-authored executable survives this phase.
    verifier.bundled_files = [
        bundled_file
        for bundled_file in verifier.bundled_files
        if not bundled_file.relpath.startswith("scripts/")
    ]
    verifier.bundled_files.append(
        BundledFile(
            relpath=VERIFY_ARTIFACT_SCRIPT_PATH,
            content=VERIFY_ARTIFACT_SCRIPT,
        )
    )
    verifier.body = insert_registered_verifier_invocation(verifier.body)
    if not has_registered_verifier_invocation(verifier.body):
        raise ValueError("author_role_skills: verification body is missing required sections")

    for skill in skills:
        for field_name, content in (
            ("display_name", skill.display_name),
            ("description", skill.description),
            ("body", skill.body),
        ):
            if registered_verifier_path_count(content) and not (
                skill is verifier and field_name == "body"
            ):
                raise ValueError(
                    "author_role_skills: registered verifier path is allowed only in "
                    "the verification workflow"
                )
        if any(
            bundled_file.relpath.endswith(".md")
            and registered_verifier_path_count(bundled_file.content)
            for bundled_file in skill.bundled_files
        ):
            raise ValueError(
                "author_role_skills: registered verifier path is not allowed in reference prose"
            )

    return skills


def _parse_bundled_files(raw: object) -> list[BundledFile]:
    """Parse the optional bundled_files array from an authored skill.

    Only reference markdown may cross this untrusted model-output boundary.
    Executable scripts and evaluation data are generated by first-party code,
    never accepted from authored output. Downstream path and content gates are
    retained as defense in depth for reference prose and programmatic callers.
    """
    if not isinstance(raw, list):
        return []
    out: list[BundledFile] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        relpath = str(item.get("path") or item.get("relpath") or "")
        content = str(item.get("content") or "")
        if not relpath.startswith("references/") or validate_bundled_path(relpath) is not None:
            continue
        content = content.replace("\\n", "\n")
        if scan_authored_executable_instructions(content) is not None:
            continue
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
        raise RuntimeError(f"All {len(errors)} authoring calls failed")


__all__ = ["author_all_roles", "author_role_skills"]
