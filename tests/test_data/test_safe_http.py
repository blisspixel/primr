"""Tests for the SSRF-safe HTTP GET helper.

The security contract under test: redirects are followed MANUALLY and every hop
(initial URL and each redirect target) is validated through the central SSRF
guard BEFORE a connection is made to it. A plain ``follow_redirects=True`` client
connects to each intermediate target first and only re-validates the final hop,
which is the redirect-SSRF gap this helper closes.

Tests are hermetic: httpx ``MockTransport`` provides responses (no network) and
``is_safe_url`` is faked so the per-hop loop logic is exercised without real DNS.
"""

from __future__ import annotations

import httpx

from primr.data.safe_http import safe_http_get


def _transport(handler):
    return httpx.MockTransport(handler)


def test_blocks_unsafe_initial_url(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.is_safe_url", lambda u: (False, "loopback"))
    # No transport needed: the request must never be attempted.
    assert safe_http_get("http://127.0.0.1/x") == (None, None, None)


def test_returns_body_on_safe_direct_response(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.is_safe_url", lambda u: (True, None))

    def handler(request):
        return httpx.Response(200, content=b"hello")

    status, body, final = safe_http_get(
        "https://public.example/page", transport=_transport(handler)
    )
    assert status == 200
    assert body == b"hello"
    assert final == "https://public.example/page"


def test_follows_a_safe_redirect(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.is_safe_url", lambda u: (True, None))

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

    def fake_is_safe(url: str):
        checked.append(url)
        if "127.0.0.1" in url or "169.254" in url:
            return (False, "blocked_internal")
        return (True, None)

    monkeypatch.setattr("primr.data.safe_http.is_safe_url", fake_is_safe)

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

    def fake_is_safe(url: str):
        checked.append(url)
        return (True, None)

    monkeypatch.setattr("primr.data.safe_http.is_safe_url", fake_is_safe)

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
    monkeypatch.setattr("primr.data.safe_http.is_safe_url", lambda u: (True, None))

    def handler(request):
        return httpx.Response(302, headers={"location": "https://public.example/next"})

    result = safe_http_get(
        "https://public.example/start", transport=_transport(handler), max_redirects=3
    )
    assert result == (None, None, None)


def test_redirect_without_location_returns_the_response(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.is_safe_url", lambda u: (True, None))

    def handler(request):
        return httpx.Response(302, content=b"no-location-here")

    status, body, _final = safe_http_get("https://public.example/x", transport=_transport(handler))
    assert status == 302
    assert body == b"no-location-here"


def test_request_failure_returns_none(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.is_safe_url", lambda u: (True, None))

    def handler(request):
        raise httpx.ConnectError("boom")

    assert safe_http_get("https://public.example/x", transport=_transport(handler)) == (
        None,
        None,
        None,
    )
