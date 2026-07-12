"""Shared authorization helpers for MCP resources."""

from __future__ import annotations

from typing import Any

from primr.mcp_server.auth import RESERVED_CLIENT_IDS
from primr.mcp_server.tool_authz import ADMIN_SCOPE, REPORT_SCOPE, scope_granted

LOCAL_A2A_CLIENT_ID = "a2a"


class _TrustedLocalA2AAuthContext:
    """Internal identity for a loopback A2A server with auth disabled."""

    client_id = LOCAL_A2A_CLIENT_ID
    is_authenticated = False
    is_admin = False
    scopes: tuple[str, ...] = ()


TRUSTED_LOCAL_A2A_AUTH_CONTEXT = _TrustedLocalA2AAuthContext()


def is_trusted_local_a2a_context(auth_context: Any) -> bool:
    """Return whether the server installed the local A2A context singleton."""
    return auth_context is TRUSTED_LOCAL_A2A_AUTH_CONTEXT


def is_local_stdio_context(transport: object, auth_context: Any) -> bool:
    """Identify an unauthenticated local call from trusted transport state."""
    return transport == "stdio" and auth_context is None


def caller_is_local_stdio(mcp_server: Any) -> bool:
    """Return whether this call is the unauthenticated local stdio surface.

    Transport is trusted server configuration. Client ids are caller-controlled
    JWT claims and must never select local privileges. An explicit auth context
    disables the compatibility shortcut, which also lets tests model HTTP
    requests without starting a listener.
    """
    return is_local_stdio_context(
        getattr(mcp_server, "transport", None),
        getattr(mcp_server, "_auth_context", None),
    )


def caller_client_id(mcp_server: Any) -> str:
    """Resolve the calling client_id from the active auth context.

    Stdio callers have implicit single-user access. HTTP requests carry an
    auth_context.client_id set by middleware. Only a real non-empty string is
    treated as authenticated context so MagicMock placeholders in tests do not
    look like HTTP callers.
    """
    if caller_is_local_stdio(mcp_server):
        return "stdio"

    ctx = getattr(mcp_server, "_auth_context", None)
    if ctx is not None:
        client_id = getattr(ctx, "client_id", None)
        if isinstance(client_id, str) and client_id:
            return client_id
    return "anonymous"


def caller_can_read_audit(mcp_server: Any) -> bool:
    """Audit events are local-only by default and admin-only over HTTP."""
    if caller_is_local_stdio(mcp_server):
        return True
    return scope_granted(ADMIN_SCOPE, caller_granted_scopes(mcp_server))


def caller_granted_scopes(mcp_server: Any) -> tuple[str, ...]:
    """Return normalized scopes from the active auth context."""
    ctx = getattr(mcp_server, "_auth_context", None)
    scopes = getattr(ctx, "scopes", []) if ctx is not None else []
    return tuple(str(scope) for scope in scopes)


def caller_can_read_report(mcp_server: Any) -> bool:
    """Report bodies are local-only by default and report-scoped over HTTP."""
    if caller_is_local_stdio(mcp_server):
        return True
    if is_trusted_local_a2a_context(getattr(mcp_server, "_auth_context", None)):
        return True
    return scope_granted(REPORT_SCOPE, caller_granted_scopes(mcp_server))


def caller_can_inline_legacy_report_content(mcp_server: Any) -> bool:
    """Return whether legacy compact endpoints may inline report content."""
    return caller_is_local_stdio(mcp_server) and caller_can_read_report(mcp_server)


def caller_owns_job_resource(mcp_server: Any, job: Any, client_id: str) -> bool:
    """Return whether a caller may read a job-scoped resource."""
    if caller_is_local_stdio(mcp_server):
        return True
    if is_trusted_local_a2a_context(getattr(mcp_server, "_auth_context", None)):
        return client_id == LOCAL_A2A_CLIENT_ID and job.owner_client_id == LOCAL_A2A_CLIENT_ID
    if not isinstance(client_id, str) or client_id.casefold() in RESERVED_CLIENT_IDS:
        return False
    return job.owner_client_id is not None and job.owner_client_id == client_id


def caller_can_manage_job(mcp_server: Any, job: Any, client_id: str) -> bool:
    """Allow local stdio, an authenticated admin, or the exact job owner."""
    if caller_is_local_stdio(mcp_server):
        return True
    context = getattr(mcp_server, "_auth_context", None)
    if context is not None and getattr(context, "is_authenticated", False) is True:
        if getattr(context, "is_admin", False) is True:
            return True
    return caller_owns_job_resource(mcp_server, job, client_id)
