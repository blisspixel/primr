"""Per-skill authorization policy for Primr's A2A surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from primr.mcp_server.tool_authz import (
    READ_SCOPE,
    RESEARCH_SCOPE,
    scope_granted,
)
from primr.mcp_server.types import MCPErrorCode

A2A_READ_SKILLS = frozenset(
    {
        "estimate_research",
        "check_jobs",
        "system_health",
        "read_artifacts_by_job",
        "read_qa_summary_by_job",
        "read_usage_summary_by_job",
        "read_source_summary_by_job",
        "read_stage_scorecard",
    }
)
A2A_RESEARCH_SKILLS = frozenset({"research_company", "run_qa", "cancel_task"})

A2A_SKILL_REQUIRED_SCOPES: dict[str, tuple[str, ...]] = {
    **dict.fromkeys(A2A_READ_SKILLS, (READ_SCOPE,)),
    **dict.fromkeys(A2A_RESEARCH_SKILLS, (RESEARCH_SCOPE,)),
}


@dataclass(frozen=True)
class A2ASkillAuthorizationDecision:
    """Decision returned by the A2A skill authorization policy."""

    allowed: bool
    skill_id: str | None
    required_scopes: tuple[str, ...] = ()
    granted_scopes: tuple[str, ...] = ()
    missing_scopes: tuple[str, ...] = ()
    reason: str = ""


def authorize_a2a_skill(
    skill_id: str | None,
    auth_context: Any,
) -> A2ASkillAuthorizationDecision:
    """Return whether *auth_context* may invoke an A2A skill."""
    required = A2A_SKILL_REQUIRED_SCOPES.get(skill_id or "")
    if required is None:
        return A2ASkillAuthorizationDecision(
            allowed=True,
            skill_id=skill_id,
            reason="unknown_skill_deferred_to_dispatch",
        )

    if auth_context is None or not getattr(auth_context, "is_authenticated", False):
        return A2ASkillAuthorizationDecision(
            allowed=True,
            skill_id=skill_id,
            required_scopes=required,
            reason="stdio_or_unauthenticated_local_context",
        )

    granted = tuple(str(scope) for scope in getattr(auth_context, "scopes", []) or [])
    missing = tuple(scope for scope in required if not scope_granted(scope, granted))
    return A2ASkillAuthorizationDecision(
        allowed=not missing,
        skill_id=skill_id,
        required_scopes=required,
        granted_scopes=granted,
        missing_scopes=missing,
        reason="allowed" if not missing else "insufficient_scope",
    )


def a2a_scope_denied_text(
    skill_id: str | None,
    decision: A2ASkillAuthorizationDecision,
) -> str:
    """Build a structured A2A text payload for insufficient-scope denials."""
    return json.dumps(
        {
            "error": True,
            "error_type": "insufficient_scope",
            "error_code": MCPErrorCode.INSUFFICIENT_SCOPE,
            "message": (
                f"A2A skill {skill_id!r} requires scope {', '.join(decision.required_scopes)!r}"
            ),
            "required_scopes": list(decision.required_scopes),
            "granted_scopes": list(decision.granted_scopes),
            "missing_scopes": list(decision.missing_scopes),
        }
    )
