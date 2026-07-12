"""Tests for A2A SDK server call-context ownership."""

import pytest

a2a = pytest.importorskip("a2a")

from starlette.authentication import AuthCredentials, SimpleUser
from starlette.requests import Request

from primr.a2a.call_context import (
    LOCAL_A2A_CLIENT_ID,
    TRUSTED_LOCAL_A2A_USER,
    PrimrA2ACallContextBuilder,
    context_client_id,
)


def test_loopback_no_auth_builder_installs_trusted_local_user() -> None:
    context = PrimrA2ACallContextBuilder(trusted_local_unauthenticated=True).build(_request())

    assert context.user is TRUSTED_LOCAL_A2A_USER
    assert context.user.is_authenticated is False
    assert context_client_id(context) == LOCAL_A2A_CLIENT_ID


def test_auth_required_builder_leaves_anonymous_request_untrusted() -> None:
    context = PrimrA2ACallContextBuilder(trusted_local_unauthenticated=False).build(_request())

    assert context.user.is_authenticated is False
    assert context_client_id(context) is None


def test_authenticated_user_is_preserved_even_on_local_listener() -> None:
    context = PrimrA2ACallContextBuilder(trusted_local_unauthenticated=True).build(
        _request(user=SimpleUser("client-1"), scopes=["read"])
    )

    assert context.user.is_authenticated is True
    assert context_client_id(context) == "client-1"


def test_authenticated_reserved_subject_cannot_impersonate_local_user() -> None:
    context = PrimrA2ACallContextBuilder(trusted_local_unauthenticated=False).build(
        _request(user=SimpleUser("a2a"), scopes=["read", "report"])
    )

    assert context.user is not TRUSTED_LOCAL_A2A_USER
    assert context.user.is_authenticated is True
    assert context_client_id(context) is None


def _request(
    *,
    user: SimpleUser | None = None,
    scopes: list[str] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 9000),
    }
    if user is not None:
        scope["user"] = user
        scope["auth"] = AuthCredentials(scopes or [])
    return Request(scope)
