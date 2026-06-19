"""Cowork plugin packaging and unpacked-tree emission.

Two artifact paths produced from one in-memory SkillPack:

  1. Unpacked Claude/Cursor/VS Code tree at <output_dir>/roles/<slug>/SKILL.md
  2. Cowork .zip at <output_dir>/<Company>_Cowork_Pack.zip containing:
       - manifest.json    (M365 Unified App Manifest v1.28)
       - color.png        (192x192)
       - outline.png      (32x32)
       - skills/<slug>/SKILL.md   (byte-identical to the Claude tree above)

Plus a human-readable <Company>_Skills_Pack_Report.md summarizing what was
produced, what was dropped, and the validation scorecard.

The UUID v5 for the manifest is deterministic on (namespace + company name),
matching the Microsoft conversion script's behavior — re-running the
pipeline against the same company replaces the existing Cowork plugin on
sideload rather than creating a parallel install.
"""

from __future__ import annotations

import io
import json
import logging
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from primr.skill_pack.config import SkillPackConfig
from primr.skill_pack.icons import pillow_available
from primr.skill_pack.image_generation import generate_icons
from primr.skill_pack.schema import (
    BundledFile,
    Role,
    Skill,
    SkillPack,
    SkillPackArtifacts,
)
from primr.skill_pack.validator import scan_bundled_content, validate_bundled_path

logger = logging.getLogger(__name__)

# ASCII control characters (except the ones str handles via .replace below);
# stripped from SKILL.md frontmatter metadata values so an injected CR/ESC/etc.
# can't forge a log line or break the YAML.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MANIFEST_SCHEMA_URL = (
    "https://developer.microsoft.com/json-schemas/teams/v1.28/MicrosoftTeams.schema.json"
)
MANIFEST_VERSION = "1.28"
PACKAGE_VERSION = "1.0.0"

# Stable namespace for UUID v5. Picking our own UUID-namespace constant gives
# us a deterministic GUID across runs and across machines for the same input
# without polluting any registered namespace. This is the documented pattern
# the Microsoft Convert-ClaudePluginToMOS3 script uses.
PRIMR_SKILL_PACK_NAMESPACE = uuid.UUID("64a4d3ab-2cdb-5e8a-9b51-7ad11e3c4a6e")

# Cowork accent color (sane default). Could be derived from company branding
# in the future — see plan's "Out of Scope (v1)".
DEFAULT_ACCENT_COLOR = "#2B579A"


def _safe_filename_token(text: str) -> str:
    """Sanitize a company name into a safe filename token."""
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    token = token.strip("._-")
    return token or "Company"


def _today_yyyymmdd() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d")


# How a consuming agent reaches primr to refresh or extend a generated skill.
# primr exposes `generate_skill_pack` over MCP (mcp__primr__*) and an A2A
# surface — this is the capability declaration, not a claim that the skill
# itself calls those tools. Stable string so SKILL.md output stays deterministic.
_PRIMR_REFRESH_VIA = "mcp:primr/generate_skill_pack, a2a:primr"


def _agent_metadata(skill: Skill, role: Role) -> dict[str, str]:
    """Build the primr-namespaced SKILL.md frontmatter metadata for one skill.

    Grounded entirely in data primr already has — no fabrication:
    - primr-role / primr-provenance / primr-confidence: how the role was
      discovered and how strongly it is grounded;
    - primr-context-tokens: an approximate context-load budget for the skill
      (4-chars-per-token heuristic over the loadable content);
    - primr-refresh-via: the MCP/A2A capability hint for regenerating it.
    """
    # Approximate the context cost of loading this skill (name + trigger +
    # body). Stable regardless of the metadata block itself, so re-rendering
    # is deterministic.
    loadable = f"{skill.name}{skill.description}{skill.body}"
    context_tokens = len(loadable) // 4
    return {
        "primr-role": role.display_name,
        "primr-provenance": role.evidence.provenance.value,
        "primr-confidence": role.confidence,
        "primr-context-tokens": str(context_tokens),
        "primr-refresh-via": _PRIMR_REFRESH_VIA,
    }


def _format_skill_md(skill: Skill, metadata: dict[str, str] | None = None) -> str:
    """Serialize a Skill into the SKILL.md on-disk format.

    YAML frontmatter (name + description, plus an optional primr-namespaced
    `metadata` block) followed by the body. The body is expected to already
    contain the required H2 sections — validator enforces that upstream. We
    escape double quotes in the YAML scalar values.
    """
    safe_name = skill.name.replace('"', '\\"')
    safe_desc = skill.description.replace('"', '\\"').replace("\n", " ").strip()
    lines = [
        "---",
        f'name: "{safe_name}"',
        f'description: "{safe_desc}"',
    ]
    if metadata:
        lines.append("metadata:")
        for key, value in metadata.items():
            # Defense-in-depth: strip control chars and escape quotes/newlines so
            # a role field (display_name/confidence) that reaches frontmatter
            # can't break the YAML or inject a line. The validator's role-level
            # SEC-INJECT is the primary gate (drops the role); this keeps the
            # emitted document well-formed even if a value slips through.
            safe_value = _CONTROL_CHARS_RE.sub("", str(value))
            safe_value = safe_value.replace('"', '\\"').replace("\n", " ").strip()
            lines.append(f'  {key}: "{safe_value}"')
    lines.extend(
        [
            "---",
            "",
            skill.body.rstrip(),
            "",
        ]
    )
    return "\n".join(lines)


def _build_manifest(
    company_name: str,
    company_short_name: str,
    pack_uuid: uuid.UUID,
    skill_folders: list[str],
) -> dict[str, Any]:
    """Build the M365 manifest.json dict (v1.28).

    Schema reference: ASKILL-M001-M003 plus the v1.28 unified app manifest
    spec. We populate only the fields required for a skills-only package;
    `agentConnectors` is intentionally absent (plan §Out of Scope: connectors
    are v2).
    """
    safe_short = company_short_name[:30]
    safe_full = f"{company_name} Skills for Copilot Cowork"[:100]
    package_name = (
        "com.primr.skill-pack."
        + re.sub(r"[^a-z0-9.-]+", "-", company_name.lower()).strip("-.")[:60]
    )

    manifest: dict[str, Any] = {
        "$schema": MANIFEST_SCHEMA_URL,
        "manifestVersion": MANIFEST_VERSION,
        "version": PACKAGE_VERSION,
        "id": str(pack_uuid),
        "packageName": package_name,
        "developer": {
            "name": "Custom Skill Pack",
            "websiteUrl": "https://github.com/blisspixel/primr",
            "privacyUrl": "https://github.com/blisspixel/primr",
            "termsOfUseUrl": "https://github.com/blisspixel/primr",
        },
        "name": {
            "short": safe_short,
            "full": safe_full,
        },
        "description": {
            "short": (f"Skill pack for {safe_short}: top roles and AI-augmented skills.")[:80],
            "full": (
                f"A skill pack for {company_name}, covering "
                f"{len(skill_folders)} role-specific skills grounded in DNS "
                "recon and hiring signals. Each skill is sideload-ready for "
                "Microsoft 365 Copilot Cowork and byte-identical to the "
                "Agent Skills format used by Claude Code, Cursor, and VS "
                "Code Copilot."
            )[:4000],
        },
        "icons": {
            "color": "color.png",
            "outline": "outline.png",
        },
        "accentColor": DEFAULT_ACCENT_COLOR,
        "agentSkills": [{"folder": f"./skills/{slug}"} for slug in skill_folders],
    }
    return manifest


def _build_pack_report_md(
    pack: SkillPack,
    artifacts: SkillPackArtifacts,
    config: SkillPackConfig,
) -> str:
    """Human-readable summary of what the pipeline produced."""
    lines: list[str] = [
        f"# Skills Pack - {pack.company_name}",
        "",
        f"_Created {pack.generated_at}._",
        "",
        "## Configuration",
        "",
        f"- Target roles: {config.roles_count} (got {len(pack.roles)})",
        f"- Skills per role: {config.skills_per_role}",
        f"- Output formats: {config.formats.value}",
        f"- Pack-level coherence pass: {'yes' if config.run_pack_coherence_pass else 'no'}",
        f"- Pillow available: {'yes' if pillow_available() else 'no (using solid PNG fallback)'}",
        "",
    ]

    if pack.plan is not None:
        plan = pack.plan
        lines.extend(
            [
                "## Role Composition",
                "",
                f"- Observed (from job postings): **{pack.observed_role_count}**",
                f"- Plausible (from research / industry): **{pack.plausible_role_count}**",
                f"- Operator-added (via --roles-add): **{pack.operator_added_role_count}**",
                f"- Final roster size: **{len(pack.roles)}**",
                f"- Industry: **{plan.industry.business_model}** / "
                f"**{plan.industry.industry_vertical}** / "
                f"**{plan.industry.company_stage}** "
                f"(source: `{plan.industry.source}`, "
                f"confidence: {plan.industry.confidence})",
            ]
        )
        if plan.operator_skipped:
            lines.append(
                f"- Operator-skipped (via --roles-skip): "
                f"{len(plan.operator_skipped)} "
                f"({', '.join(plan.operator_skipped[:6])}"
                f"{'...' if len(plan.operator_skipped) > 6 else ''})"
            )
        if plan.plan_md_path:
            lines.append(f"- Full role plan: `{plan.plan_md_path}`")
        if plan.gap_flagged:
            lines.append(
                f"- Gap-flagged roles not authored: {len(plan.gap_flagged)} "
                "(see role plan for details)"
            )
        lines.append("")

    lines.extend(
        [
            "## Roles and Skills",
            "",
        ]
    )
    for role in pack.roles:
        lines.append(f"### {role.display_name} (`{role.name}`)")
        lines.append("")
        lines.append(f"- Confidence: **{role.confidence}**")
        lines.append(f"- Provenance: `{role.evidence.provenance.value}`")
        if role.evidence.archetype:
            lines.append(f"- Archetype: `{role.evidence.archetype}`")
        if role.evidence.dns_signals:
            lines.append("- DNS signals: " + ", ".join(role.evidence.dns_signals))
        if role.evidence.posting_count:
            lines.append(f"- Hiring posting count: {role.evidence.posting_count}")
        if role.evidence.citations:
            top_citations = role.evidence.citations[:3]
            rendered = "; ".join(c if len(c) <= 100 else c[:97] + "..." for c in top_citations)
            lines.append(f"- Citations: {rendered}")
        if role.summary:
            lines.append("")
            lines.append(role.summary)
        lines.append("")
        lines.append("**Skills:**")
        lines.append("")
        for skill in role.skills:
            lines.append(f"- `{skill.name}`: {skill.display_name}")
        lines.append("")

    lines.append("## Validation Scorecard")
    lines.append("")
    v = pack.validation
    lines.append(f"- Result: **{'PASS' if v.passed else 'FAIL'}**")
    lines.append(f"- HARD findings: {len(v.hard_issues)}")
    lines.append(f"- SOFT findings: {len(v.soft_issues)}")
    if v.issues:
        lines.append("")
        lines.append("| Severity | Code | Role | Field | Message |")
        lines.append("|----------|------|------|-------|---------|")
        pipe_escape = "\\|"
        for issue in v.issues:
            safe_msg = issue.message.replace("|", pipe_escape)
            lines.append(
                f"| {issue.severity.value.upper()} | {issue.code} | "
                f"{issue.role_name or '-'} | {issue.field or '-'} | "
                f"{safe_msg} |"
            )
        lines.append("")

    if pack.refinement_iterations_used:
        lines.append("## Refinement Iterations")
        lines.append("")
        for role_name, count in pack.refinement_iterations_used.items():
            lines.append(f"- `{role_name}`: {count} iteration(s)")
        lines.append("")

    if pack.trigger_results:
        improved = [r for r in pack.trigger_results if getattr(r, "optimized", False)]
        lines.append("## Trigger Optimization")
        lines.append("")
        lines.append(
            f"- Skills measured: {len(pack.trigger_results)}; "
            f"descriptions improved: {len(improved)}"
        )
        for r in improved:
            lines.append(
                f"- `{r.skill_name}`: trigger accuracy "
                f"{r.baseline_accuracy:.0%} -> {r.final_accuracy:.0%}"
            )
        lines.append("")

    if pack.behavioral_results:
        helped = [b for b in pack.behavioral_results if getattr(b, "delta", 0) > 0]
        lines.append("## Behavioral Eval (with-skill vs baseline)")
        lines.append("")
        lines.append(
            f"- Skills benchmarked: {len(pack.behavioral_results)}; "
            f"improved output vs baseline: {len(helped)}"
        )
        for b in pack.behavioral_results:
            lines.append(
                f"- `{b.skill_name}`: with-skill {b.with_skill_pass_rate:.0%} vs "
                f"baseline {b.baseline_pass_rate:.0%} "
                f"(delta {b.delta:+.0%}, {b.n_cases} case(s))"
            )
        lines.append("")

    if pack.dropped_roles:
        lines.append("## Dropped Roles")
        lines.append("")
        for name, reason in pack.dropped_roles:
            lines.append(f"- `{name}`: {reason}")
        lines.append("")

    lines.append("## Artifacts")
    lines.append("")
    if artifacts.claude_tree_root:
        lines.append(f"- Claude / Cursor / VS Code tree: `{artifacts.claude_tree_root}`")
    if artifacts.cowork_zip_path:
        lines.append(f"- Cowork sideload .zip: `{artifacts.cowork_zip_path}`")
    if artifacts.manifest_uuid:
        lines.append(f"- Manifest UUID: `{artifacts.manifest_uuid}` (deterministic v5)")
    lines.append("")

    lines.append("## Sideload Instructions (M365 Cowork)")
    lines.append("")
    lines.append(
        "1. Open Microsoft 365 Admin Center > Manage Apps > Upload custom app.\n"
        "2. Upload the Cowork .zip file from the artifacts list above.\n"
        "3. Open Cowork > Sources & Skills - your skills will appear.\n"
        "\n"
        "Note: re-running the pipeline against the same company produces "
        "the same manifest UUID, so sideload will *replace* the previous "
        "install (Cowork update semantics)."
    )
    lines.append("")
    return "\n".join(lines)


# A folder slug must be a single safe path segment: lowercase alphanumerics,
# hyphens (incl. the `--` disambiguator), dots, underscores; no slash,
# backslash, traversal, or leading separator/dot.
_SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _is_safe_slug(slug: str) -> bool:
    if not slug or ".." in slug or "/" in slug or "\\" in slug:
        return False
    return bool(_SAFE_SLUG_RE.match(slug))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _flatten_skills(pack: SkillPack) -> list[tuple[Role, Skill]]:
    return [(role, skill) for role in pack.roles for skill in role.skills]


def _valid_bundled_files(skill: Skill) -> list[BundledFile]:
    """Filter a skill's bundled files to those that are safe to write, de-duped
    by relpath.

    Drops two classes of file defensively (the validator already recorded the
    matching finding upstream):
      - unsafe PATH (traversal / wrong subdir / wrong ext) — SOFT BUNDLE-PATH;
      - unsafe CONTENT (injection markers, hardcoded paths, or an executable
        Python helper that does process/network/eval/secret/destructive work)
        — HARD SEC-BUNDLE.

    This is defense-in-depth: even if a role somehow ships with a HARD finding
    unresolved, no unreviewed executable or injected content reaches the
    Claude tree or the Cowork zip.
    """
    out: list[BundledFile] = []
    seen: set[str] = set()
    for bf in skill.bundled_files:
        if validate_bundled_path(bf.relpath) is not None:
            continue
        if bf.relpath in seen:
            continue
        unsafe = scan_bundled_content(bf.relpath, bf.content)
        if unsafe is not None:
            logger.warning("Dropping unsafe bundled file %r: %s", bf.relpath, unsafe)
            continue
        seen.add(bf.relpath)
        out.append(bf)
    return out


def _ensure_unique_slugs(items: list[tuple[Role, Skill]]) -> list[tuple[str, Role, Skill]]:
    """Yield (folder_slug, role, skill) tuples with collision-free folder names.

    Within a pack two roles could legitimately produce skills with the same
    kebab-case name. We disambiguate by prefixing the role slug. Validator
    has already enforced kebab-case shape so we can safely concatenate.
    """
    seen: set[str] = set()
    result: list[tuple[str, Role, Skill]] = []
    for role, skill in items:
        slug = skill.name
        if slug in seen:
            slug = f"{role.name}--{skill.name}"
        seen.add(slug)
        result.append((slug, role, skill))
    return result


def package_skill_pack(
    pack: SkillPack,
    config: SkillPackConfig,
    base_output_dir: Path,
) -> SkillPackArtifacts:
    """Write all artifacts for a SkillPack to disk.

    Returns an SkillPackArtifacts with paths populated for whatever formats
    were emitted. Always writes the pack report markdown.
    """
    company_token = _safe_filename_token(pack.company_name)
    date_token = _today_yyyymmdd()
    output_dir = base_output_dir / f"{company_token}_Skills_Pack_{date_token}"
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts = SkillPackArtifacts(output_dir=str(output_dir))

    flat_skills = _ensure_unique_slugs(_flatten_skills(pack))

    # Defense-in-depth: a folder slug is used verbatim as a path segment in
    # BOTH the Claude tree and the Cowork zip member path. Validation enforces
    # kebab-case (ASKILL-P007) upstream, but drop any slug that isn't a single
    # safe path segment here so a malformed/authored name can't write outside
    # the skill folder in either artifact.
    safe_flat_skills: list[tuple[str, Role, Skill]] = []
    for slug, role, skill in flat_skills:
        if _is_safe_slug(slug):
            safe_flat_skills.append((slug, role, skill))
        else:
            logger.warning("Dropping skill with unsafe folder slug %r", slug)
    flat_skills = safe_flat_skills

    # Precompute the agent-handoff metadata once per skill so the Claude tree
    # and the Cowork zip render byte-identical SKILL.md files (a pack invariant).
    agent_meta: dict[str, dict[str, str]] = (
        {slug: _agent_metadata(skill, role) for slug, role, skill in flat_skills}
        if config.emit_agent_metadata
        else {}
    )

    if config.emit_claude:
        roles_root = output_dir / "roles"
        roles_root.mkdir(parents=True, exist_ok=True)
        artifacts.claude_tree_root = str(roles_root)
        for slug, _role, skill in flat_skills:
            skill_dir = roles_root / slug
            # Defense-in-depth path-traversal check.
            resolved = skill_dir.resolve()
            if not _is_relative_to(resolved, roles_root.resolve()):
                logger.warning("Path traversal blocked for slug=%r", slug)
                continue
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_path = skill_dir / "SKILL.md"
            # newline="\n": write LF verbatim (no platform CRLF translation) so
            # the Claude-tree SKILL.md is byte-identical to the Cowork zip copy,
            # which zipfile.writestr emits with raw LF. Without this the
            # invariant silently breaks on Windows.
            skill_path.write_text(
                _format_skill_md(skill, agent_meta.get(slug)),
                encoding="utf-8",
                newline="\n",
            )
            artifacts.skill_md_paths.append(str(skill_path))
            # Progressive-disclosure resources (references/*.md, scripts/*.py).
            for bf in _valid_bundled_files(skill):
                bf_path = skill_dir / bf.relpath
                bf_resolved = bf_path.resolve()
                if not _is_relative_to(bf_resolved, skill_dir.resolve()):
                    logger.warning("Path traversal blocked for bundled file %r", bf.relpath)
                    continue
                bf_path.parent.mkdir(parents=True, exist_ok=True)
                bf_path.write_text(bf.content, encoding="utf-8", newline="\n")

    if config.emit_cowork:
        zip_path = output_dir / f"{company_token}_Cowork_Pack.zip"
        pack_uuid = uuid.uuid5(PRIMR_SKILL_PACK_NAMESPACE, pack.company_name)
        artifacts.manifest_uuid = str(pack_uuid)

        manifest = _build_manifest(
            pack.company_name,
            company_token,
            pack_uuid,
            [slug for slug, _, _ in flat_skills],
        )

        # Multi-provider image generation: tries Grok > Gemini > OpenAI image
        # APIs in order if their keys are present, then falls back to a
        # programmatic gradient+shape Pillow render, then to a solid PNG.
        # Adding Foundry / Bedrock / Anthropic later is a localized change
        # in image_generation.py.
        company_blurb = pack.roles[0].summary[:120] if pack.roles and pack.roles[0].summary else ""
        color_png, outline_png = generate_icons(
            pack.company_name,
            company_description=company_blurb or None,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.writestr("color.png", color_png)
            zf.writestr("outline.png", outline_png)
            for slug, _role, skill in flat_skills:
                zf.writestr(
                    f"skills/{slug}/SKILL.md",
                    _format_skill_md(skill, agent_meta.get(slug)),
                )
                for bf in _valid_bundled_files(skill):
                    zf.writestr(f"skills/{slug}/{bf.relpath}", bf.content)

        zip_path.write_bytes(buf.getvalue())
        artifacts.cowork_zip_path = str(zip_path)

    report_md = _build_pack_report_md(pack, artifacts, config)
    report_path = output_dir / f"{company_token}_Skills_Pack_Report.md"
    report_path.write_text(report_md, encoding="utf-8")
    artifacts.report_md_path = str(report_path)

    return artifacts


__all__ = ["MANIFEST_SCHEMA_URL", "PACKAGE_VERSION", "package_skill_pack"]
