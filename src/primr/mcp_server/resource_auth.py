"""Shared authorization helpers for MCP resources."""

from __future__ import annotations

from typing import Any

from primr.mcp_server.tool_authz import ADMIN_SCOPE, REPORT_SCOPE, scope_granted


def caller_client_id(mcp_server: Any) -> str:
    """Resolve the calling client_id from the active auth context.

    Stdio callers have implicit single-user access. HTTP requests carry an
    auth_context.client_id set by middleware. Only a real non-empty string is
    treated as authenticated context so MagicMock placeholders in tests do not
    look like HTTP callers.
    """
    ctx = getattr(mcp_server, "_auth_context", None)
    if ctx is not None:
        client_id = getattr(ctx, "client_id", None)
        if isinstance(client_id, str) and client_id:
            return client_id
    return "stdio"


def caller_can_read_audit(mcp_server: Any) -> bool:
    """Audit events are local-only by default and admin-only over HTTP."""
    if caller_client_id(mcp_server) == "stdio":
        return True
    return scope_granted(ADMIN_SCOPE, caller_granted_scopes(mcp_server))


def caller_granted_scopes(mcp_server: Any) -> tuple[str, ...]:
    """Return normalized scopes from the active auth context."""
    ctx = getattr(mcp_server, "_auth_context", None)
    scopes = getattr(ctx, "scopes", []) if ctx is not None else []
    return tuple(str(scope) for scope in scopes)


def caller_can_read_report(mcp_server: Any) -> bool:
    """Report bodies are local-only by default and report-scoped over HTTP."""
    if caller_client_id(mcp_server) == "stdio":
        return True
    return scope_granted(REPORT_SCOPE, caller_granted_scopes(mcp_server))


def caller_owns_job_resource(job: Any, client_id: str) -> bool:
    """Return whether a caller may read a job-scoped resource."""
    if client_id == "stdio":
        return True
    return job.owner_client_id is not None and job.owner_client_id == client_id
