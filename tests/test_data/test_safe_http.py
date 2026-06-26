"""Tests for the SSRF-safe HTTP helpers.

The security contract under test: redirects are followed MANUALLY and every hop
(initial URL and each redirect target) is validated through the central SSRF
guard BEFORE a connection is made to it. A plain ``follow_redirects=True`` client
connects to each intermediate target first and only re-validates the final hop,
which is the redirect-SSRF gap this helper closes.

Tests are hermetic: httpx ``MockTransport`` provides responses (no network) and
``resolve_safe_url_for_connect`` is faked so the per-hop loop logic is
exercised without real DNS.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
import pytest

from primr.data.safe_http import async_safe_http_head, safe_http_get
from primr.utils.security import SafeUrlResolution


def _transport(handler):
    return httpx.MockTransport(handler)


def _host_header(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "public.example"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 443 if parsed.scheme == "https" else 80
    if parsed.port and parsed.port != default_port:
        return f"{host}:{parsed.port}"
    return host


def _resolution(url: str, request_url: str | None = None) -> SafeUrlResolution:
    parsed = urlparse(url)
    hostname = parsed.hostname or "public.example"
    return SafeUrlResolution(
        original_url=url,
        request_url=request_url or url,
        host_header=_host_header(url),
        sni_hostname=hostname if parsed.scheme == "https" else None,
        resolved_ip=hostname,
    )


def _allow_all(url: str):
    return _resolution(url), None


def test_blocks_unsafe_initial_url(monkeypatch):
    monkeypatch.setattr(
        "primr.data.safe_http.resolve_safe_url_for_connect",
        lambda u: (None, "loopback"),
    )
    # No transport needed: the request must never be attempted.
    assert safe_http_get("http://127.0.0.1/x") == (None, None, None)


def test_returns_body_on_safe_direct_response(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", _allow_all)

    def handler(request):
        return httpx.Response(200, content=b"hello")

    status, body, final = safe_http_get(
        "https://public.example/page", transport=_transport(handler)
    )
    assert status == 200
    assert body == b"hello"
    assert final == "https://public.example/page"


def test_follows_a_safe_redirect(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", _allow_all)

    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://public.example/final"})
        return httpx.Response(200, content=b"final-body")

    status, body, final = safe_http_get(
        "https://public.example/start", transport=_transport(handler)
    )
    assert status == 200
    assert body == b"final-body"
    assert final == "https://public.example/final"


def test_validates_each_redirect_hop_and_never_connects_to_internal(monkeypatch):
    checked: list[str] = []

    def fake_resolve(url: str):
        checked.append(url)
        if "127.0.0.1" in url or "169.254" in url:
            return None, "blocked_internal"
        return _resolution(url), None

    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", fake_resolve)

    connected: list[str] = []

    def handler(request):
        connected.append(str(request.url))
        if request.url.host == "public.example":
            # Attacker-controlled public page redirects into an internal address.
            return httpx.Response(302, headers={"location": "http://127.0.0.1:6379/internal"})
        return httpx.Response(200, content=b"should-never-reach")

    result = safe_http_get("https://public.example/start", transport=_transport(handler))

    assert result == (None, None, None)
    # The internal redirect target WAS validated...
    assert any("127.0.0.1" in u for u in checked)
    # ...and was NEVER connected to (the gap a final-only check would miss).
    assert all("127.0.0.1" not in u for u in connected)


def test_relative_redirect_is_resolved_then_validated(monkeypatch):
    checked: list[str] = []

    def fake_resolve(url: str):
        checked.append(url)
        return _resolution(url), None

    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", fake_resolve)

    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/moved"})
        return httpx.Response(200, content=b"ok")

    status, _body, final = safe_http_get(
        "https://public.example/start", transport=_transport(handler)
    )
    assert status == 200
    assert final == "https://public.example/moved"
    assert "https://public.example/moved" in checked


def test_aborts_on_redirect_loop(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", _allow_all)

    def handler(request):
        return httpx.Response(302, headers={"location": "https://public.example/next"})

    result = safe_http_get(
        "https://public.example/start", transport=_transport(handler), max_redirects=3
    )
    assert result == (None, None, None)


def test_redirect_without_location_returns_the_response(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", _allow_all)

    def handler(request):
        return httpx.Response(302, content=b"no-location-here")

    status, body, _final = safe_http_get("https://public.example/x", transport=_transport(handler))
    assert status == 302
    assert body == b"no-location-here"


def test_request_failure_returns_none(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", _allow_all)

    def handler(request):
        raise httpx.ConnectError("boom")

    assert safe_http_get("https://public.example/x", transport=_transport(handler)) == (
        None,
        None,
        None,
    )


def test_get_connects_to_pinned_ip_with_original_host_and_sni(monkeypatch):
    def fake_resolve(url: str):
        return _resolution(url, "https://93.184.216.34/start"), None

    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", fake_resolve)

    observed: dict[str, object] = {}

    def handler(request):
        observed["url"] = str(request.url)
        observed["host"] = request.headers["host"]
        observed["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, content=b"ok")

    status, body, final = safe_http_get(
        "https://public.example/start", transport=_transport(handler)
    )

    assert (status, body, final) == (200, b"ok", "https://public.example/start")
    assert observed == {
        "url": "https://93.184.216.34/start",
        "host": "public.example",
        "sni": "public.example",
    }


@pytest.mark.asyncio
async def test_async_head_returns_final_url_on_safe_direct_response(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", _allow_all)

    def handler(request):
        return httpx.Response(200)

    status, final, blocked = await async_safe_http_head(
        "https://public.example/page", transport=_transport(handler)
    )
    assert status == 200
    assert final == "https://public.example/page"
    assert blocked is False


@pytest.mark.asyncio
async def test_async_head_follows_safe_relative_redirect(monkeypatch):
    checked: list[str] = []

    def fake_resolve(url: str):
        checked.append(url)
        return _resolution(url), None

    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", fake_resolve)

    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(204)

    status, final, blocked = await async_safe_http_head(
        "https://public.example/start", transport=_transport(handler)
    )
    assert status == 204
    assert final == "https://public.example/final"
    assert blocked is False
    assert "https://public.example/final" in checked


@pytest.mark.asyncio
async def test_async_head_blocks_unsafe_redirect_before_connect(monkeypatch):
    checked: list[str] = []

    def fake_resolve(url: str):
        checked.append(url)
        if "169.254.169.254" in url:
            return None, "metadata endpoint"
        return _resolution(url), None

    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", fake_resolve)

    connected: list[str] = []

    def handler(request):
        connected.append(str(request.url))
        if request.url.host == "public.example":
            return httpx.Response(
                302,
                headers={"location": "http://169.254.169.254/latest/meta-data"},
            )
        return httpx.Response(200)

    status, final, blocked = await async_safe_http_head(
        "https://public.example/start", transport=_transport(handler)
    )
    assert (status, final, blocked) == (None, None, True)
    assert any("169.254.169.254" in url for url in checked)
    assert all("169.254.169.254" not in url for url in connected)


@pytest.mark.asyncio
async def test_async_head_network_failure_propagates(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", _allow_all)

    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(httpx.ConnectError):
        await async_safe_http_head("https://public.example/x", transport=_transport(handler))


@pytest.mark.asyncio
async def test_async_head_connects_to_pinned_ip_with_original_host_and_sni(monkeypatch):
    def fake_resolve(url: str):
        return _resolution(url, "https://93.184.216.34/page"), None

    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", fake_resolve)

    observed: dict[str, object] = {}

    def handler(request):
        observed["url"] = str(request.url)
        observed["host"] = request.headers["host"]
        observed["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(204)

    status, final, blocked = await async_safe_http_head(
        "https://public.example/page", transport=_transport(handler)
    )

    assert (status, final, blocked) == (204, "https://public.example/page", False)
    assert observed == {
        "url": "https://93.184.216.34/page",
        "host": "public.example",
        "sni": "public.example",
    }
