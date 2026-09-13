"""Exercise the mounted HTTP endpoint through the real MCP SDK transport."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from primr.config.mcp import mcp_http_allowlists
from primr.mcp_server.server import create_mcp_server


@pytest.fixture(autouse=True)
def clean_http_config(monkeypatch):
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("MCP_ALLOWED_ORIGINS", raising=False)


async def _app(tmp_path, **kwargs):
    server = create_mcp_server(
        transport="streamable-http",
        journal_path=str(tmp_path / "journal.json"),
        skip_background_tasks=True,
        **kwargs,
    )
    with (
        patch.object(server, "_setup_signal_handlers"),
        patch("primr.mcp_server.server.configure_http_logging"),
        patch("uvicorn.Server") as runner,
    ):
        runner.return_value.serve = AsyncMock()
        await server.run_http()
    return runner.call_args.args[0].app


def _request(method="tools/list", params=None, version="2026-07-28"):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {
            **(params or {}),
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": version,
                "io.modelcontextprotocol/clientCapabilities": {},
            },
        },
    }


def _headers(**extra):
    return {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/list",
        **extra,
    }


def _payload(response):
    if response.headers["content-type"].startswith("text/event-stream"):
        return json.loads(
            next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
        )
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [None, "http://127.0.0.1:8000", "http://localhost:8000"])
async def test_modern_request_cache_fields_and_private_scope(tmp_path, origin):
    app = await _app(tmp_path, require_auth=False)
    headers = _headers(**({"Origin": origin} if origin else {}))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as client,
    ):
        response = await client.post("/mcp/", json=_request(), headers=headers)
    assert response.status_code == 200
    result = _payload(response)["result"]
    assert result["resultType"] == "complete"
    assert result["cacheScope"] == "private"
    assert result["ttlMs"] == 300_000
    assert result["tools"]
    assert "mcp-session-id" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("extra_headers", "status"),
    [
        ({"Origin": "https://untrusted.example"}, 403),
        ({"Origin": "null"}, 403),
        ({"Origin": "http://localhost:8000.untrusted.example"}, 403),
        ({"Host": "untrusted.example"}, 421),
        ({"Host": "untrusted.example", "X-Forwarded-Host": "localhost:8000"}, 421),
    ],
)
async def test_rejects_untrusted_origin_or_host(tmp_path, extra_headers, status):
    app = await _app(tmp_path, require_auth=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as client,
    ):
        response = await client.post("/mcp/", json=_request(), headers=_headers(**extra_headers))
    assert response.status_code == status
    assert '"tools"' not in response.text


@pytest.mark.asyncio
async def test_modern_discovery_and_transport_errors(tmp_path):
    app = await _app(tmp_path, require_auth=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as client,
    ):
        discovered = await client.post(
            "/mcp/",
            json=_request(method="server/discover"),
            headers=_headers(**{"Mcp-Method": "server/discover"}),
        )
        mismatched = await client.post(
            "/mcp/", json=_request(), headers=_headers(**{"Mcp-Method": "prompts/list"})
        )
        unsupported = await client.post(
            "/mcp/",
            json=_request(version="2099-01-01"),
            headers=_headers(**{"MCP-Protocol-Version": "2099-01-01"}),
        )
    assert discovered.status_code == 200
    result = _payload(discovered)["result"]
    assert "2026-07-28" in result["supportedVersions"]
    assert {"tools", "resources", "prompts"}.issubset(result["capabilities"])
    assert "mcp-session-id" not in discovered.headers
    assert mismatched.status_code == 400
    assert _payload(mismatched)["error"]["code"] == -32020
    assert unsupported.status_code == 400
    assert _payload(unsupported)["error"]["code"] == -32022


@pytest.mark.asyncio
async def test_explicit_ingress_requires_auth_and_allows_configured_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "mcp.example.com")
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://agent.example.com")
    monkeypatch.setenv("MCP_ADMIN_TOKENS", "test-only-admin-token")
    app = await _app(tmp_path, host="0.0.0.0", allow_plaintext=True, require_auth=True)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://mcp.example.com"
        ) as client,
    ):
        headers = _headers(Origin="https://agent.example.com")
        unauthenticated = await client.post("/mcp/", json=_request(), headers=headers)
        headers["Authorization"] = "Bearer test-only-admin-token"
        authenticated = await client.post("/mcp/", json=_request(), headers=headers)
        headers["Origin"] = "https://untrusted.example"
        untrusted = await client.post("/mcp/", json=_request(), headers=headers)
    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    assert _payload(authenticated)["result"]["tools"]
    assert untrusted.status_code == 403


@pytest.mark.asyncio
async def test_legacy_initialize_and_session_request(tmp_path):
    app = await _app(tmp_path, require_auth=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
        ) as client,
    ):
        headers = {
            "Accept": "application/json, text/event-stream",
            "Origin": "http://localhost:8000",
        }
        initialized = await client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1"},
                },
            },
            headers=headers,
        )
        assert initialized.status_code == 200
        assert _payload(initialized)["result"]["protocolVersion"] == "2025-11-25"
        headers["Mcp-Session-Id"] = initialized.headers["mcp-session-id"]
        headers["MCP-Protocol-Version"] = "2025-11-25"
        notification = await client.post(
            "/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=headers
        )
        listed = await client.post(
            "/mcp/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers
        )
        headers["Origin"] = "https://untrusted.example"
        rejected = await client.post(
            "/mcp/", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, headers=headers
        )
    assert notification.status_code == 202
    assert listed.status_code == 200
    assert _payload(listed)["result"]["tools"]
    assert rejected.status_code == 403


@pytest.mark.parametrize("host", ["0.0.0.0", "::"])
def test_wildcard_listener_requires_explicit_ingress(host):
    with pytest.raises(ValueError, match="MCP_ALLOWED_HOSTS is required"):
        mcp_http_allowlists(host, 8000)


@pytest.mark.parametrize(
    "authority",
    [
        "*",
        "*.example.com",
        "example.com:*",
        "https://example.com",
        "user@example.com",
        "example.com/path",
        "example.com:65536",
        "0.0.0.0",
        "[::]",
        "[0:0:0:0:0:0:0:0]",
        "example.com:",
        "example.com\u0001",
        "example!.com",
        "-example.com",
        "example..com",
    ],
)
def test_invalid_config_fails_closed(monkeypatch, authority):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", authority)
    with pytest.raises(ValueError, match="MCP_ALLOWED_HOSTS"):
        mcp_http_allowlists("0.0.0.0", 8000)


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "https://*.example.com",
        "https://example.com/path",
        "https://example.com?query=1",
        "https://[invalid]",
    ],
)
def test_invalid_origin_config_fails_closed(monkeypatch, origin):
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", origin)
    with pytest.raises(ValueError, match="MCP_ALLOWED_ORIGINS"):
        mcp_http_allowlists("127.0.0.1", 8000)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "192.0.2.1", "mcp.example.com"])
def test_explicit_listener_authorities_support_default_port(host):
    hosts, origins = mcp_http_allowlists(host, 80)
    authority = f"[{host}]" if ":" in host else host
    assert authority in hosts
    assert f"{authority}:80" in hosts
    if host in {"127.0.0.1", "::1", "localhost"}:
        assert f"http://{authority}" in origins


def test_explicit_hosts_do_not_grant_browser_origin_trust(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "proxy.example.com")
    hosts, origins = mcp_http_allowlists("127.0.0.1", 8000)
    assert "proxy.example.com" in hosts
    assert not any("proxy.example.com" in origin for origin in origins)


def test_config_accepts_multiple_exact_authorities_and_origins(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", " Example.COM:443, other.example.com ")
    monkeypatch.setenv(
        "MCP_ALLOWED_ORIGINS", "https://Agent.Example.com,https://tool.example.com:8443"
    )
    assert mcp_http_allowlists("0.0.0.0", 8000) == (
        ["example.com:443", "other.example.com"],
        ["https://agent.example.com", "https://tool.example.com:8443"],
    )
