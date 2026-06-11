"""Server-side cost-cap enforcement policy for MCP tools.

Single source of truth for whether cost-incurring MCP tools require
``max_estimated_cost_usd``. Tri-state policy:

- ``PRIMR_ENFORCE_MCP_COST_CAPS`` explicitly truthy  -> enforced
- ``PRIMR_ENFORCE_MCP_COST_CAPS`` explicitly falsy   -> not enforced
- unset -> enforced when the server is running the HTTP transport,
  not enforced on stdio

Rationale: HTTP mode is the networked, potentially multi-client surface —
the one an unattended agent platform talks to — so safe-by-default applies
there. stdio is a locally-launched single-host transport where the host
(Claude Desktop, Claude Code) already mediates the user's approval, and
defaulting to hard enforcement would break existing host configs.

``PrimrMCPServer`` publishes its transport via ``PRIMR_MCP_TRANSPORT`` at
construction time so this check works at tool-call time regardless of which
entry point launched the server.
"""

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def is_cost_cap_enforced() -> bool:
    """Resolve the cost-cap enforcement policy (see module docstring)."""
    explicit = os.getenv("PRIMR_ENFORCE_MCP_COST_CAPS", "").strip().lower()
    if explicit in _TRUTHY:
        return True
    if explicit in _FALSY:
        return False
    return os.getenv("PRIMR_MCP_TRANSPORT", "").strip().lower() == "streamable-http"
