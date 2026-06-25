"""MCP tool registrations for the skill_pack pipeline.

Exposes two synchronous tools (the pipeline is short enough — ~30-90s
— that the job-store async pattern isn't worth its complexity here):

  - estimate_skill_pack: cost-and-time estimate, called before
    generate_skill_pack to satisfy the standard estimate-first gate.
  - generate_skill_pack: runs the full pipeline and returns artifact
    paths + the pack report markdown inline so the agent client doesn't
    need filesystem access to consume results.

Both honor `max_estimated_cost_usd` and the
PRIMR_ENFORCE_MCP_COST_CAPS server-side enforcement when set.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent, Tool

from primr.data.hiring_career_urls import normalize_career_urls
from primr.mcp_server.approval_tokens import (
    enforce_approval_token,
    issue_approval_token,
    skill_pack_approval_args,
)
from primr.skill_pack.config import (
    DEFAULT_MAX_COST_PER_ROLE_USD,
    DEFAULT_MAX_REFINE_ITERATIONS,
    DEFAULT_ROLES,
    DEFAULT_SKILLS_PER_ROLE,
    MAX_ROLES,
    MAX_SKILLS_PER_ROLE,
    MIN_ROLES,
    MIN_SKILLS_PER_ROLE,
    SkillPackConfig,
    SkillPackFormat,
)

if TYPE_CHECKING:
    from mcp.server import Server

    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def register_skill_pack_tools(server: Server, mcp_server: PrimrMCPServer) -> list[Tool]:
    """Return the Tool definitions for inclusion in list_tools().

    Does not register handlers itself — handlers run via handle_skill_pack_tool
    which is dispatched from the central call_tool in tools.py.
    """
    return [
        Tool(
            name="estimate_skill_pack",
            description=(
                "Estimate cost and time to produce a skill pack for a "
                "company. Call this BEFORE generate_skill_pack to satisfy "
                "the standard estimate-first gate. ~$0.20-0.35, 30-120s."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "company_url": {"type": "string"},
                    "report_path": {
                        "type": "string",
                        "description": (
                            "Optional path to an existing primr report or "
                            "working directory. When provided, the standalone "
                            "evidence-collection step is skipped (cheaper)."
                        ),
                    },
                    "from_jd_path": {
                        "type": "string",
                        "description": (
                            "Optional path to a local job description or role "
                            "brief to add to the hiring evidence layer."
                        ),
                    },
                    "career_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional exact career / ATS URLs to use as hiring "
                            "evidence. Repeat entries for segmented career sites."
                        ),
                    },
                    "roles_count": {
                        "type": "integer",
                        "minimum": MIN_ROLES,
                        "maximum": MAX_ROLES,
                        "default": DEFAULT_ROLES,
                    },
                    "skills_per_role": {
                        "type": "integer",
                        "minimum": MIN_SKILLS_PER_ROLE,
                        "maximum": MAX_SKILLS_PER_ROLE,
                        "default": DEFAULT_SKILLS_PER_ROLE,
                    },
                },
                "required": ["company_name"],
            },
        ),
        Tool(
            name="generate_skill_pack",
            description=(
                "Generate a QA-refined Agent Skills pack for a company. "
                "Produces both a Claude/Cursor/VS Code-ready unpacked tree "
                "AND a Microsoft 365 Copilot Cowork sideload .zip from one "
                "byte-identical set of SKILL.md files. Internal QA pipeline: "
                "role discovery, best-practices grounding, parallel authoring, "
                "deterministic validation, per-skill refinement (capped), "
                "pack-level coherence pass. Synchronous (~30-120s)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "company_url": {
                        "type": "string",
                        "description": (
                            "Required unless report_path, from_jd_path, or career_urls is provided."
                        ),
                    },
                    "report_path": {
                        "type": "string",
                        "description": (
                            "Optional path to an existing primr report or "
                            "working directory. When provided, the pipeline "
                            "reuses that directory's recon + hiring evidence."
                        ),
                    },
                    "from_jd_path": {
                        "type": "string",
                        "description": (
                            "Optional path to a local job description or role "
                            "brief. The server sanitizes it and materializes it "
                            "into the hiring evidence stream before planning "
                            "and authoring. Can be used as the sole evidence "
                            "source when company_url/report_path are absent."
                        ),
                    },
                    "career_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional exact career / ATS URLs to use as hiring "
                            "evidence. Multiple URLs are merged before planning."
                        ),
                    },
                    "roles_count": {
                        "type": "integer",
                        "minimum": MIN_ROLES,
                        "maximum": MAX_ROLES,
                        "default": DEFAULT_ROLES,
                    },
                    "skills_per_role": {
                        "type": "integer",
                        "minimum": MIN_SKILLS_PER_ROLE,
                        "maximum": MAX_SKILLS_PER_ROLE,
                        "default": DEFAULT_SKILLS_PER_ROLE,
                    },
                    "formats": {
                        "type": "string",
                        "enum": [f.value for f in SkillPackFormat],
                        "default": SkillPackFormat.BOTH.value,
                        "description": (
                            "claude = unpacked roles/ tree only; "
                            "cowork = sideload .zip only; "
                            "both (default) = emit both from one run."
                        ),
                    },
                    "max_refine_iterations": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 5,
                        "default": DEFAULT_MAX_REFINE_ITERATIONS,
                    },
                    "destination": {
                        "type": "string",
                        "description": ("Optional output directory. Defaults to ./output/."),
                    },
                    "max_estimated_cost_usd": {
                        "type": "number",
                        "minimum": 0,
                        "description": (
                            "Optional hard ceiling for estimated run cost. "
                            "The server rejects execution if the estimate "
                            "exceeds this cap."
                        ),
                    },
                    "approval_token": {
                        "type": "string",
                        "description": (
                            "Server-issued token returned by estimate_skill_pack. "
                            "Required when MCP cost-cap enforcement is enabled."
                        ),
                    },
                    "allow_recon_only": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When True, proceed even when no posting and "
                            "no research evidence are available. Default "
                            "fails closed."
                        ),
                    },
                    "emit_agent_metadata": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When True, add optional primr-namespaced "
                            "metadata to each SKILL.md frontmatter. Default "
                            "False keeps skills clean and portable."
                        ),
                    },
                    "plan_only": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When True, run the planning step, persist "
                            "role_plan.md / role_plan.json, and return "
                            "without authoring. Useful for inspecting "
                            "the planned roster before paying for skills."
                        ),
                    },
                    "from_plan_path": {
                        "type": "string",
                        "description": (
                            "Optional path to a previously-persisted "
                            "role_plan.json. Skips planning and authors "
                            "against the plan's final_roster verbatim."
                        ),
                    },
                    "roles_override": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of role labels that bypass "
                            "automatic planning. Mutually exclusive with "
                            "roles_add / roles_skip."
                        ),
                    },
                    "roles_add": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of role labels to ADD to the "
                            "planned roster (operator-supplied augmentation). "
                            "Composes with from_plan_path."
                        ),
                    },
                    "roles_skip": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of role labels or kebab-case "
                            "slugs to REMOVE from the planned roster. "
                            "Composes with from_plan_path."
                        ),
                    },
                },
                "required": ["company_name"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Estimation helpers
# ---------------------------------------------------------------------------


def _estimate_skill_pack_cost(
    roles_count: int,
    skills_per_role: int,
    has_report_path: bool,
) -> dict[str, float]:
    """Return {cost_usd, min_minutes, max_minutes}.

    Numbers are conservative and from the design plan's cost analysis,
    adjusted upward 15% for safety margin in the estimate-first gate.
    """
    cost = 0.0
    if not has_report_path:
        cost += 0.05  # standalone evidence collection
    cost += 0.02  # discovery
    cost += 0.03 * roles_count  # authoring (per role)
    cost += 0.015 * roles_count * skills_per_role * 0.3  # refinement (30% need it)
    cost += 0.02  # pack coherence pass
    cost = round(cost * 1.15, 3)  # 15% safety margin

    minutes_min = 0.5 if has_report_path else 1.5
    minutes_max = 1.5 + roles_count * 0.4
    if not has_report_path:
        minutes_max += 1.0
    return {
        "cost_usd": cost,
        "min_minutes": round(minutes_min, 1),
        "max_minutes": round(minutes_max, 1),
    }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _is_cost_cap_enforced() -> bool:
    from primr.mcp_server.cost_caps import is_cost_cap_enforced

    return is_cost_cap_enforced()


def _validate_from_jd_path(
    from_jd_path: str | None,
    mcp_server: PrimrMCPServer,
) -> tuple[str | None, TextContent | None]:
    """Validate and resolve the optional operator JD path for MCP calls."""
    if not from_jd_path:
        return None, None

    jd_result = mcp_server.path_validator.validate(from_jd_path)
    if not jd_result.valid or jd_result.resolved_path is None:
        return (
            None,
            _error_response(f"from_jd_path rejected: {jd_result.error_message or 'invalid path'}"),
        )
    if not jd_result.resolved_path.is_file():
        return (
            None,
            _error_response(f"from_jd_path does not exist: {jd_result.resolved_path}"),
        )
    return str(jd_result.resolved_path), None


def _pipeline_error_response(exc: Exception) -> TextContent:
    """Map expected skill-pack pipeline exceptions to user-facing MCP errors."""
    if isinstance(exc, FileNotFoundError):
        return _error_response(f"Evidence missing: {exc}")
    if isinstance(exc, ValueError):
        return _error_response(f"Invalid input: {exc}")
    if isinstance(exc, RuntimeError):
        return _error_response(f"Pipeline failed: {exc}")
    if isinstance(exc, OSError):
        return _error_response(f"Evidence IO failed: {exc}")
    return _error_response(f"Unexpected error: {exc}")


def _coerce_list(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if str(s).strip()]
    return []


async def handle_skill_pack_tool(
    name: str,
    arguments: dict[str, Any],
    mcp_server: PrimrMCPServer,
) -> list[TextContent] | None:
    """Dispatch for skill_pack MCP tools. Returns None when `name` is not ours."""
    if name == "estimate_skill_pack":
        return await _handle_estimate_skill_pack(arguments)
    if name == "generate_skill_pack":
        return await _handle_generate_skill_pack(arguments, mcp_server)
    return None


async def _handle_estimate_skill_pack(arguments: dict[str, Any]) -> list[TextContent]:
    company_name = str(arguments.get("company_name", "")).strip()
    if not company_name:
        return [_error_response("company_name is required")]

    roles_count = int(arguments.get("roles_count") or DEFAULT_ROLES)
    skills_per_role = int(arguments.get("skills_per_role") or DEFAULT_SKILLS_PER_ROLE)
    has_report_path = bool(arguments.get("report_path"))
    has_jd_path = bool(arguments.get("from_jd_path") or arguments.get("from_jd"))
    try:
        career_urls = normalize_career_urls(_coerce_list(arguments.get("career_urls")))
    except ValueError as exc:
        return [_error_response(f"Invalid career_urls: {exc}")]

    cost_uses_existing_evidence = bool(
        has_report_path or (has_jd_path and not arguments.get("company_url") and not career_urls)
    )
    estimate = _estimate_skill_pack_cost(
        roles_count,
        skills_per_role,
        has_report_path=cost_uses_existing_evidence,
    )
    payload = {
        "company_name": company_name,
        "roles_count": roles_count,
        "skills_per_role": skills_per_role,
        "uses_existing_report": has_report_path,
        "uses_operator_role_brief": has_jd_path,
        "uses_career_urls": bool(career_urls),
        **estimate,
        "notes": (
            "Includes role discovery, parallel authoring, validation, "
            "refinement (capped), and pack-level coherence pass. "
            "Evidence collection (recon + hiring) excluded when "
            "report_path is provided, or when from_jd_path is the sole "
            "evidence source. career_urls are treated as standalone "
            "hiring evidence and included in the collection estimate."
        ),
    }
    payload.update(
        issue_approval_token(
            tool_name="generate_skill_pack",
            approval_args=skill_pack_approval_args(
                effective_roles=roles_count,
                skills_per_role=skills_per_role,
                has_report_path=cost_uses_existing_evidence,
                has_operator_role_brief=has_jd_path,
                has_career_urls=bool(career_urls),
            ),
            max_cost_usd=float(estimate["cost_usd"]),
        )
    )
    return [TextContent(type="text", text=json.dumps(payload, indent=2))]


async def _handle_generate_skill_pack(
    arguments: dict[str, Any],
    mcp_server: PrimrMCPServer,
) -> list[TextContent]:
    company_name = str(arguments.get("company_name", "")).strip()
    company_url = str(arguments.get("company_url", "")).strip() or None
    report_path = str(arguments.get("report_path", "")).strip() or None
    from_jd_path = (
        str(arguments.get("from_jd_path") or arguments.get("from_jd") or "").strip() or None
    )

    career_urls_raw = _coerce_list(arguments.get("career_urls") or arguments.get("career_url"))
    try:
        career_urls = normalize_career_urls(career_urls_raw)
    except ValueError as exc:
        return [_error_response(f"Invalid career_urls: {exc}")]

    if not company_name:
        return [_error_response("company_name is required")]
    if not company_url and not report_path and not from_jd_path and not career_urls:
        return [
            _error_response(
                "Either company_url, report_path, from_jd_path, or career_urls must be provided "
                "(company_url runs a standalone evidence collection; "
                "report_path reuses an existing primr run's evidence; "
                "from_jd_path adds a local job description / role brief as "
                "the evidence source; career_urls provide exact hiring boards "
                "for segmented career sites)."
            )
        ]

    roles_count = int(arguments.get("roles_count") or DEFAULT_ROLES)
    skills_per_role = int(arguments.get("skills_per_role") or DEFAULT_SKILLS_PER_ROLE)
    formats_value = str(arguments.get("formats") or SkillPackFormat.BOTH.value)
    max_refine = int(arguments.get("max_refine_iterations") or DEFAULT_MAX_REFINE_ITERATIONS)
    destination = arguments.get("destination") or "output"
    max_cost = arguments.get("max_estimated_cost_usd")
    allow_recon_only = bool(arguments.get("allow_recon_only") or False)
    emit_agent_metadata = bool(arguments.get("emit_agent_metadata") or False)
    plan_only = bool(arguments.get("plan_only") or False)
    from_plan_path = arguments.get("from_plan_path") or None

    roles_override = _coerce_list(arguments.get("roles_override"))
    roles_add = _coerce_list(arguments.get("roles_add"))
    roles_skip = _coerce_list(arguments.get("roles_skip"))

    from_jd_path, from_jd_error = _validate_from_jd_path(from_jd_path, mcp_server)
    if from_jd_error is not None:
        return [from_jd_error]

    # Cost gate. Estimate on the EFFECTIVE roster size that will actually be
    # authored, not the raw roles_count: roles_override replaces the count and
    # roles_add augments it, so estimating on roles_count alone let a caller
    # pass roles_count=1 with 15 overrides and slip past a cap sized for one
    # role. Capped at MAX_ROLES (the pipeline's hard ceiling).
    effective_roles = len(roles_override) if roles_override else roles_count
    effective_roles = min(effective_roles + len(roles_add), MAX_ROLES)
    cost_uses_existing_evidence = bool(
        report_path or (from_jd_path and not company_url and not career_urls)
    )
    estimate = _estimate_skill_pack_cost(
        effective_roles,
        skills_per_role,
        has_report_path=cost_uses_existing_evidence,
    )
    if _is_cost_cap_enforced():
        # Fail closed: when server-side caps are enforced, a cost-incurring run
        # MUST carry an explicit cap. Other MCP tools behave the same way; this
        # path previously only checked the cap when the caller chose to supply
        # one, which silently defeated the enforcement toggle.
        if max_cost is None:
            return [
                _error_response(
                    "max_estimated_cost_usd is required when cost-cap "
                    "enforcement is enabled (PRIMR_ENFORCE_MCP_COST_CAPS). "
                    f"Estimated cost for this run is ${estimate['cost_usd']:.2f}; "
                    "re-call with max_estimated_cost_usd at or above it."
                )
            ]
        try:
            cap = float(max_cost)
        except (TypeError, ValueError):
            return [_error_response("max_estimated_cost_usd must be a number")]
        if estimate["cost_usd"] > cap:
            return [
                _error_response(
                    f"Estimated cost ${estimate['cost_usd']:.2f} exceeds cap "
                    f"${cap:.2f}. Increase max_estimated_cost_usd, reduce "
                    f"roles_count/skills_per_role, or supply a report_path "
                    f"to skip evidence collection."
                )
            ]
        approval_error = enforce_approval_token(
            tool_name="generate_skill_pack",
            approval_args=skill_pack_approval_args(
                effective_roles=effective_roles,
                skills_per_role=skills_per_role,
                has_report_path=cost_uses_existing_evidence,
                has_operator_role_brief=bool(from_jd_path),
                has_career_urls=bool(career_urls),
            ),
            estimated_cost_usd=float(estimate["cost_usd"]),
            approval_token=arguments.get("approval_token"),
        )
        if approval_error is not None:
            return [TextContent(type="text", text=json.dumps(approval_error))]

    try:
        config = SkillPackConfig(
            roles_count=(len(roles_override) if roles_override else roles_count),
            skills_per_role=skills_per_role,
            formats=SkillPackFormat(formats_value),
            max_refine_iterations=max_refine,
            run_pack_coherence_pass=True,
            reuse_existing_evidence=bool(report_path),
            max_cost_per_role_usd=DEFAULT_MAX_COST_PER_ROLE_USD,
            max_total_cost_usd=float(max_cost) if max_cost is not None else None,
            allow_recon_only=allow_recon_only,
            emit_agent_metadata=emit_agent_metadata,
            roles_override=roles_override,
            roles_add=roles_add,
            roles_skip=roles_skip,
            plan_only=plan_only,
            from_plan_path=from_plan_path,
            from_jd_path=from_jd_path,
            career_urls=career_urls,
        )
        config.validate()
    except ValueError as exc:
        return [_error_response(f"Invalid config: {exc}")]

    # Working directory: existing report path or fresh temp dir + standalone evidence.
    if report_path:
        # Validate through the shared MCP PathValidator (allowed roots only,
        # traversal/symlink/null-byte/system-dir checks) — same containment
        # every other path-taking MCP tool uses. Previously report_path was
        # resolved straight from caller input, letting an authenticated client
        # point the run at any server-side directory.
        path_result = mcp_server.path_validator.validate(report_path)
        if not path_result.valid or path_result.resolved_path is None:
            return [
                _error_response(
                    f"report_path rejected: {path_result.error_message or 'invalid path'}"
                )
            ]
        working_dir = path_result.resolved_path
        if not working_dir.exists():
            return [_error_response(f"report_path does not exist: {working_dir}")]
        cleanup_tempdir: Path | None = None
    else:
        from primr.skill_pack.evidence import collect_evidence

        tmp = Path(tempfile.mkdtemp(prefix="primr-skill-pack-mcp-"))
        working_dir = tmp
        cleanup_tempdir = tmp
        if company_url or config.career_urls:
            outcome = collect_evidence(
                company_name=company_name,
                company_url=company_url,
                working_dir=working_dir,
                career_urls=config.career_urls,
            )
            if not outcome.get("recon") and not outcome.get("hiring") and not from_jd_path:
                return [
                    _error_response(
                        "Could not collect any evidence (recon and hiring both "
                        "failed). Supply report_path, supply from_jd_path with "
                        "a role brief, add exact career_urls for segmented "
                        "career sites, or check that the URL is reachable."
                    )
                ]

    # Destination is caller-controlled too — contain it to allowed roots before
    # creating directories and writing the SKILL.md tree / Cowork zip / report.
    dest_result = mcp_server.path_validator.validate(destination)
    if not dest_result.valid or dest_result.resolved_path is None:
        return [
            _error_response(f"destination rejected: {dest_result.error_message or 'invalid path'}")
        ]
    output_dir = dest_result.resolved_path
    output_dir.mkdir(parents=True, exist_ok=True)

    from primr.skill_pack.pipeline import run_skill_pack_pipeline

    try:
        pack, artifacts = run_skill_pack_pipeline(
            company_name=company_name,
            company_url=company_url,
            working_dir=working_dir,
            config=config,
            output_dir=output_dir,
        )
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        return [_pipeline_error_response(exc)]
    except Exception as exc:
        logger.exception("generate_skill_pack failed")
        return [_error_response(f"Unexpected error: {exc}")]
    finally:
        # Don't delete the temp evidence dir — useful for debugging. The OS
        # will reap it on reboot. Tradeoff: extra disk vs forensic visibility.
        _ = cleanup_tempdir

    pack_report_md = ""
    if artifacts.report_md_path:
        try:
            pack_report_md = Path(artifacts.report_md_path).read_text(encoding="utf-8")
        except OSError:
            pack_report_md = ""

    response = {
        "company_name": pack.company_name,
        "roles_count": len(pack.roles),
        "total_skills": pack.total_skills,
        "validation": pack.validation.to_dict(),
        "dropped_roles": [{"name": name, "reason": reason} for name, reason in pack.dropped_roles],
        "refinement_iterations_used": dict(pack.refinement_iterations_used),
        "artifacts": artifacts.to_dict(),
        "estimated_cost_usd": estimate["cost_usd"],
        "pack_report_md": pack_report_md,
        "sideload_instructions": (
            "Open M365 Admin Center > Manage Apps > Upload custom app, "
            "and upload the Cowork .zip from artifacts.cowork_zip_path. "
            "For Claude/Cursor/VS Code, the unpacked tree at "
            "artifacts.claude_tree_root is drop-in: copy individual "
            "<slug>/SKILL.md folders into ~/.claude/skills/ or your "
            "editor's plugin skills directory."
        ),
    }
    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ---------------------------------------------------------------------------


def _error_response(message: str) -> TextContent:
    return TextContent(
        type="text",
        text=json.dumps({"error": True, "message": message}),
    )


__all__ = ["handle_skill_pack_tool", "register_skill_pack_tools"]
