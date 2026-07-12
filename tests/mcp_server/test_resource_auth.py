"""Transport and ownership contracts for MCP resource authorization."""

from types import SimpleNamespace

from primr.mcp_server.resource_auth import (
    TRUSTED_LOCAL_A2A_AUTH_CONTEXT,
    caller_can_manage_job,
    caller_can_read_audit,
    caller_can_read_report,
    caller_client_id,
    caller_is_local_stdio,
    caller_owns_job_resource,
)


def _server(transport: str, context=None):
    return SimpleNamespace(transport=transport, _auth_context=context)


def test_local_privilege_comes_from_transport_without_auth_context():
    server = _server("stdio")
    job = SimpleNamespace(owner_client_id="someone-else")

    assert caller_is_local_stdio(server) is True
    assert caller_client_id(server) == "stdio"
    assert caller_can_read_audit(server) is True
    assert caller_can_read_report(server) is True
    assert caller_owns_job_resource(server, job, "stdio") is True


def test_http_subject_named_stdio_gets_no_local_privilege():
    context = SimpleNamespace(
        client_id="stdio",
        scopes=[],
        is_authenticated=True,
        is_admin=False,
    )
    server = _server("streamable-http", context)
    job = SimpleNamespace(owner_client_id="owner-1")

    assert caller_is_local_stdio(server) is False
    assert caller_client_id(server) == "stdio"
    assert caller_can_read_audit(server) is False
    assert caller_can_read_report(server) is False
    assert caller_owns_job_resource(server, job, "stdio") is False
    assert caller_can_manage_job(server, job, "stdio") is False


def test_http_ownership_and_admin_management_are_explicit():
    owner_context = SimpleNamespace(
        client_id="owner-1",
        scopes=["report"],
        is_authenticated=True,
        is_admin=False,
    )
    owner_server = _server("streamable-http", owner_context)
    job = SimpleNamespace(owner_client_id="owner-1")

    assert caller_owns_job_resource(owner_server, job, "owner-1") is True
    assert caller_can_manage_job(owner_server, job, "owner-1") is True

    admin_context = SimpleNamespace(
        client_id="admin-1",
        scopes=["admin"],
        is_authenticated=True,
        is_admin=True,
    )
    admin_server = _server("streamable-http", admin_context)
    assert caller_owns_job_resource(admin_server, job, "admin-1") is False
    assert caller_can_manage_job(admin_server, job, "admin-1") is True


def test_unauthenticated_http_has_no_reserved_identity_privilege():
    server = _server("streamable-http")
    job = SimpleNamespace(owner_client_id=None)

    assert caller_client_id(server) == "anonymous"
    assert caller_can_read_audit(server) is False
    assert caller_can_read_report(server) is False
    assert caller_owns_job_resource(server, job, "anonymous") is False
    assert caller_can_manage_job(server, job, "anonymous") is False


def test_server_trusted_local_a2a_context_reads_only_local_a2a_jobs():
    server = _server("streamable-http", TRUSTED_LOCAL_A2A_AUTH_CONTEXT)
    local_job = SimpleNamespace(owner_client_id="a2a")
    other_job = SimpleNamespace(owner_client_id="owner-1")

    assert caller_is_local_stdio(server) is False
    assert caller_client_id(server) == "a2a"
    assert caller_can_read_report(server) is True
    assert caller_owns_job_resource(server, local_job, "a2a") is True
    assert caller_owns_job_resource(server, other_job, "a2a") is False
    assert caller_can_manage_job(server, local_job, "a2a") is True
    assert caller_can_manage_job(server, other_job, "a2a") is False


def test_authenticated_a2a_subject_does_not_receive_local_privilege():
    context = SimpleNamespace(
        client_id="a2a",
        scopes=["read", "report"],
        is_authenticated=True,
        is_admin=False,
    )
    server = _server("streamable-http", context)
    local_job = SimpleNamespace(owner_client_id="a2a")

    assert caller_can_read_report(server) is True
    assert caller_owns_job_resource(server, local_job, "a2a") is False
    assert caller_can_manage_job(server, local_job, "a2a") is False
