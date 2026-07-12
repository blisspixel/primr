"""A2A server call-context ownership helpers."""

from __future__ import annotations

from typing import Any

from a2a.auth.user import User
from a2a.server.apps.jsonrpc.jsonrpc_app import (
    DefaultCallContextBuilder,
)

from primr.mcp_server.auth import RESERVED_CLIENT_IDS

LOCAL_A2A_CLIENT_ID = "a2a"


class _TrustedLocalA2AUser(User):
    """SDK user marker created only for a loopback no-auth listener."""

    @property
    def is_authenticated(self) -> bool:
        return False

    @property
    def user_name(self) -> str:
        return LOCAL_A2A_CLIENT_ID


TRUSTED_LOCAL_A2A_USER = _TrustedLocalA2AUser()


class PrimrA2ACallContextBuilder(DefaultCallContextBuilder):
    """Build SDK contexts while preserving trusted loopback identity."""

    def __init__(self, *, trusted_local_unauthenticated: bool) -> None:
        self._trusted_local_unauthenticated = trusted_local_unauthenticated

    def build(self, request: Any):
        """Build a request context with a server-derived local marker."""
        context = super().build(request)
        if self._trusted_local_unauthenticated and not context.user.is_authenticated:
            context.user = TRUSTED_LOCAL_A2A_USER
        return context


def context_client_id(context: Any) -> str | None:
    """Resolve an owned-task client id from an SDK server call context."""
    if context is None:
        return None

    user = getattr(context, "user", None)
    if user is TRUSTED_LOCAL_A2A_USER:
        return LOCAL_A2A_CLIENT_ID
    if user is None or getattr(user, "is_authenticated", False) is not True:
        return None

    user_name = getattr(user, "user_name", None)
    if not isinstance(user_name, str) or not user_name:
        return None
    if user_name.casefold() in RESERVED_CLIENT_IDS:
        return None
    return user_name
