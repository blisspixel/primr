"""
Per-tool authorization policy for the MCP server.

The HTTP transport authenticates the caller before requests reach tool
dispatch. This module keeps the second layer small and explicit: map each
tool to the minimum scope needed to run it, while preserving stdio and legacy
``write`` behavior for existing local clients.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mcp.types import TextContent

from primr.mcp_server.types import MCPErrorCode

READ_SCOPE = "read"
RESEARCH_SCOPE = "research"
DELEGATE_SCOPE = "delegate"
ADMIN_SCOPE = "admin"
LEGACY_WRITE_SCOPE = "write"


READ_TOOLS = frozenset(
    {
        "estimate_run",
        "estimate_strategy",
        "estimate_skill_pack",
        "check_jobs",
        "wait_for_status_change",
        "doctor",
        "show_usage",
        "query_roadmap",
        "get_hypotheses",
    }
)

RESEARCH_TOOLS = frozenset(
    {
        "research_company",
        "generate_strategy",
        "generate_skill_pack",
        "run_qa",
        "cancel_job",
        "save_hypothesis",
    }
)

DELEGATE_TOOLS = frozenset({"delegate_to_agent"})
ADMIN_TOOLS = frozenset({"clear_jobs"})

TOOL_REQUIRED_SCOPES: dict[str, tuple[str, ...]] = {
    **dict.fromkeys(READ_TOOLS, (READ_SCOPE,)),
    **dict.fromkeys(RESEARCH_TOOLS, (RESEARCH_SCOPE,)),
    **dict.fromkeys(DELEGATE_TOOLS, (DELEGATE_SCOPE,)),
    **dict.fromkeys(ADMIN_TOOLS, (ADMIN_SCOPE,)),
}


@dataclass(frozen=True)
class ToolAuthorizationDecision:
    """Decision returned by the tool authorization policy."""

    allowed: bool
    tool_name: str
    required_scopes: tuple[str, ...] = ()
    granted_scopes: tuple[str, ...] = ()
    missing_scopes: tuple[str, ...] = ()
    reason: str = ""


def authorize_tool_call(tool_name: str, auth_context: Any) -> ToolAuthorizationDecision:
    """
    Return whether *auth_context* may call *tool_name*.

    Stdio and unauthenticated local contexts remain permissive. HTTP requests
    with a verified token are checked against the per-tool scope table.
    Unknown tools pass through so the existing unknown-tool error remains the
    single source of truth for typos and unregistered tool names.
    """
    required = TOOL_REQUIRED_SCOPES.get(tool_name)
    if required is None:
        return ToolAuthorizationDecision(
            allowed=True,
            tool_name=tool_name,
            reason="unknown_tool_deferred_to_dispatch",
        )

    if auth_context is None or not getattr(auth_context, "is_authenticated", False):
        return ToolAuthorizationDecision(
            allowed=True,
            tool_name=tool_name,
            required_scopes=required,
            reason="stdio_or_unauthenticated_local_context",
        )

    granted = tuple(str(scope) for scope in getattr(auth_context, "scopes", []) or [])
    missing = tuple(scope for scope in required if not scope_granted(scope, granted))
    return ToolAuthorizationDecision(
        allowed=not missing,
        tool_name=tool_name,
        required_scopes=required,
        granted_scopes=granted,
        missing_scopes=missing,
        reason="allowed" if not missing else "insufficient_scope",
    )


def scope_denied_response(
    tool_name: str,
    decision: ToolAuthorizationDecision,
) -> list[TextContent]:
    """Build a structured MCP tool response for an insufficient-scope decision."""
    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "error": True,
                    "error_type": "insufficient_scope",
                    "error_code": MCPErrorCode.INSUFFICIENT_SCOPE,
                    "message": (
                        f"Tool {tool_name!r} requires scope {', '.join(decision.required_scopes)!r}"
                    ),
                    "required_scopes": list(decision.required_scopes),
                    "granted_scopes": list(decision.granted_scopes),
                    "missing_scopes": list(decision.missing_scopes),
                }
            ),
        )
    ]


def scope_granted(required_scope: str, granted_scopes: tuple[str, ...]) -> bool:
    """Return True when the granted scope set satisfies *required_scope*."""
    if ADMIN_SCOPE in granted_scopes:
        return True
    if required_scope in granted_scopes:
        return True

    # Backwards compatibility: older primr JWTs only had read/write. Treat
    # write as the old broad mutating/delegating permission, but do not let it
    # satisfy admin-only operations.
    return (
        required_scope in {RESEARCH_SCOPE, DELEGATE_SCOPE} and LEGACY_WRITE_SCOPE in granted_scopes
    )


def _scope_granted(required_scope: str, granted_scopes: tuple[str, ...]) -> bool:
    """Backward-compatible private alias for older internal imports."""
    return scope_granted(required_scope, granted_scopes)
