"""Server-side cost-cap enforcement policy for MCP tools.

Single source of truth for whether cost-incurring MCP tools require
``max_estimated_cost_usd``. Safe-by-default policy:

- ``PRIMR_ENFORCE_MCP_COST_CAPS`` explicitly truthy  -> enforced
- ``PRIMR_ENFORCE_MCP_COST_CAPS`` explicitly falsy   -> unsafe compatibility opt-out
- unset -> enforced on every transport

Stdio clients can be automated and configured provider keys are not approval
to spend. Requiring the estimate-bound cap and approval token on every MCP
transport keeps the execution boundary consistent. Operators that knowingly
need legacy behavior can set ``PRIMR_ENFORCE_MCP_COST_CAPS=0`` explicitly.

``PrimrMCPServer`` publishes its transport at serve time for audit context and
future transport-specific policy without weakening the default gate.
"""

from __future__ import annotations

import os

_FALSY = {"0", "false", "no", "off"}

# Set by PrimrMCPServer at construction; None until a server exists in this
# process. Kept as a module global (not an env mutation) so constructing a
# server never leaks state into the process environment.
_active_transport: str | None = None


def set_active_transport(transport: str | None) -> None:
    """Record the transport the in-process MCP server is serving."""
    global _active_transport
    _active_transport = transport


def is_cost_cap_enforced() -> bool:
    """Resolve the cost-cap enforcement policy (see module docstring)."""
    explicit = os.getenv("PRIMR_ENFORCE_MCP_COST_CAPS", "").strip().lower()
    return explicit not in _FALSY
