"""Exercise response limits below SDK buffering and decompression."""

import gzip
import io
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

import httpx
import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.response import HTTPResponse

from primr.data.http_body import BoundedHTTPTransport
from primr.data.http_client import HTTPClient, HTTPClientConfig
from primr.data.pinned_requests import create_pinned_session
from primr.utils.errors import ScrapingError
from primr.utils.security import SafeUrlResolution
from tests.test_data.test_http_body_limits import LazyBody


def response(body, *, headers=None, status=200):
    result = requests.Response()
    result.status_code = status
    result.url = "https://example.com/start"
    result.request = requests.Request("GET", result.url).prepare()
    result.headers.update(headers or {})
    result.raw = HTTPResponse(
        body=io.BytesIO(body), headers=headers or {}, preload_content=False, decode_content=False
    )
    return result


@pytest.mark.parametrize("status", [200, 302])
@pytest.mark.parametrize("compressed", [False, True])
def test_requests_adapter_bounds_final_and_redirect_bodies(monkeypatch, status, compressed):
    body = b"a" * 10_000
    headers = {"Location": "/final"} if status == 302 else {}
    if compressed:
        body = gzip.compress(body)
        headers["Content-Encoding"] = "gzip"
    result = response(body, status=status, headers=headers)
    monkeypatch.setattr(HTTPAdapter, "send", lambda *args, **kwargs: result)
    with (
        create_pinned_session(max_body_bytes=128) as session,
        pytest.raises(requests.RequestException, match="limit"),
    ):
        session.get("https://example.com/start", allow_redirects=False, timeout=2)
    assert result.raw.closed
    assert result._content is False


def test_requests_redirect_control_preserves_response_and_next_request(monkeypatch):
    result = response(
        gzip.compress(b"ok"),
        status=302,
        headers={
            "Content-Encoding": "gzip",
            "Location": "/final",
        },
    )
    monkeypatch.setattr(HTTPAdapter, "send", lambda *args, **kwargs: result)
    with create_pinned_session(max_body_bytes=128) as session:
        received = session.get("https://example.com/start", allow_redirects=False, timeout=2)
    assert received is result
    assert received.content == b"ok"
    assert received.next.url == "https://example.com/final"
    assert received.raw.closed


def test_head_does_not_read_or_reject_get_representation_size(monkeypatch):
    result = response(b"", headers={"Content-Length": "999999999999", "Content-Encoding": "br"})
    monkeypatch.setattr(HTTPAdapter, "send", lambda *args, **kwargs: result)
    result.raw.read1 = Mock(side_effect=AssertionError("HEAD body must not be read"))
    with create_pinned_session(max_body_bytes=8) as session:
        assert session.head("https://example.com/file", timeout=2).content == b""
    assert result.raw.closed


@pytest.mark.parametrize("status", [200, 302])
def test_httpx_transport_bounds_decoding_before_client_read(monkeypatch, status):
    source = LazyBody([gzip.compress(b"a" * 10_000), b"unread"])
    result = httpx.Response(status, stream=source, headers={"content-encoding": "gzip"})
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *args: result)
    with (
        httpx.Client(transport=BoundedHTTPTransport(time.monotonic() + 2, limit=128)) as client,
        pytest.raises(ValueError, match="decoded-body limit"),
    ):
        client.get("https://example.com")
    assert source.closed
    assert source.reads == 1


def test_httpx_transport_retains_one_decoding_and_host_sni(monkeypatch):
    source = LazyBody([gzip.compress(b"ordinary text")])
    result = httpx.Response(200, stream=source, headers={"content-encoding": "gzip"})
    calls = []

    def send(_self, request):
        calls.append(request)
        return result

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", send)
    with httpx.Client(transport=BoundedHTTPTransport(time.monotonic() + 2, limit=128)) as client:
        received = client.get(
            "https://93.184.216.34/",
            headers={"Host": "example.com"},
            extensions={"sni_hostname": "example.com"},
        )
    assert received.content == b"ordinary text"
    assert calls[0].headers["Host"] == "example.com"
    assert calls[0].extensions["sni_hostname"] == "example.com"
    assert source.closed


@pytest.fixture
def local_endpoint(monkeypatch):
    """Only this fixture permits the explicitly owned loopback test server."""

    class Handler(BaseHTTPRequestHandler):
        attempts = {}

        def do_GET(self):
            self.attempts[self.path] = self.attempts.get(self.path, 0) + 1
            retry_ok = self.path == "/retry-ok"
            ordinary = self.path == "/ok" or retry_ok
            body = b"ordinary text" if ordinary else b"x" * 4096
            compressed = ordinary or self.path == "/compressed"
            if compressed:
                body = gzip.compress(body)
            status = 302 if self.path == "/redirect" else 500 if self.path == "/retry" else 200
            if retry_ok and self.attempts[self.path] == 1:
                status = 500
            self.send_response(status)
            if compressed:
                self.send_header("Content-Encoding", "gzip")
            if self.path == "/redirect":
                self.send_header("Location", "/ok")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def resolve(url):
        return SafeUrlResolution(
            original_url=url,
            request_url=url,
            host_header=f"127.0.0.1:{server.server_port}",
            sni_hostname=None,
            resolved_ip="127.0.0.1",
        ), None

    monkeypatch.setattr("primr.utils.security.resolve_safe_url_for_connect", resolve)
    monkeypatch.setattr(
        "primr.utils.validators.validate_url_for_request", lambda url: (True, url, None)
    )
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.parametrize("backend", ["requests", "httpx", "curl"])
@pytest.mark.parametrize("path", ["/plain", "/compressed", "/redirect", "/ok"])
def test_native_sdk_body_and_decoder_controls(local_endpoint, monkeypatch, backend, path):
    """Real SDK I/O proves callback abort and decoder ordering, without external traffic."""
    url = local_endpoint + path
    if backend == "curl":
        from primr.data.scraping import http_clients

        monkeypatch.setattr(http_clients, "DEFAULT_MAX_BODY_BYTES", 256)
        result = http_clients.scrape_with_curl_cffi(url, timeout=2)
        assert result.success is (path == "/ok")
        if result.success:
            assert result.raw_content == b"ordinary text"
        return
    if backend == "requests":
        client = create_pinned_session(max_body_bytes=256)
        exception = requests.RequestException
    else:
        client = httpx.Client(transport=BoundedHTTPTransport(time.monotonic() + 2, limit=256))
        exception = ValueError
    with client:
        if path == "/ok":
            assert client.get(url).content == b"ordinary text"
        else:
            with pytest.raises(exception, match="limit"):
                client.get(url)


def test_status_retry_body_is_bounded_before_urllib3_can_drain_it(local_endpoint):
    with HTTPClient(HTTPClientConfig(max_retries=2, backoff_factor=0)) as client:
        client._session.get_adapter(local_endpoint).max_body_bytes = 256
        with pytest.raises(ScrapingError, match="limit"):
            client.get(local_endpoint + "/retry")


def test_normal_bounded_error_response_can_still_retry(local_endpoint):
    with HTTPClient(HTTPClientConfig(max_retries=2, backoff_factor=0)) as client:
        client._session.get_adapter(local_endpoint).max_body_bytes = 256
        received = client.get(local_endpoint + "/retry-ok")
    assert received.status_code == 200
    assert received.content == b"ordinary text"


@pytest.mark.parametrize("compressed", [False, True])
def test_requests_aggregate_budget_includes_intermediate_redirects(monkeypatch, compressed):
    from primr.data.scraping.net import make_request

    results = []
    for path in ("/middle", "/final"):
        body = b"x" * 600
        results.append(
            response(
                gzip.compress(body) if compressed else body,
                status=302,
                headers={"Location": path, **({"Content-Encoding": "gzip"} if compressed else {})},
            )
        )
    calls = []

    def send(*args, **kwargs):
        result = results[len(calls)]
        calls.append(result)
        return result

    monkeypatch.setattr(HTTPAdapter, "send", send)
    monkeypatch.setattr(
        "primr.utils.redirect_target.request_url_for_hop", lambda url, **k: (True, url, "")
    )
    with pytest.raises(requests.RequestException, match="limit"):
        make_request("https://example.com/start", max_body_bytes=1000, max_total_body_bytes=1000)
    assert len(calls) == 2
    assert all(result.raw.closed for result in results)


def test_requests_aggregate_budget_preserves_small_redirect_control(monkeypatch):
    from primr.data.scraping.net import make_request

    results = iter(
        [
            response(b"abc", status=302, headers={"Location": "/final"}),
            response(b"ordinary text"),
        ]
    )
    monkeypatch.setattr(HTTPAdapter, "send", lambda *a, **k: next(results))
    monkeypatch.setattr(
        "primr.utils.redirect_target.request_url_for_hop", lambda url, **k: (True, url, "")
    )
    result = make_request(
        "https://example.com/start", max_body_bytes=1000, max_total_body_bytes=1000
    )
    assert result.content == b"ordinary text"
    assert result.primr_body_bytes == 3 + len(result.content)


def test_requests_aggregate_budget_includes_status_retry_bodies(monkeypatch):
    from urllib3.util.retry import Retry

    results = iter([response(b"x" * 600, status=500), response(b"y" * 600)])
    calls = []

    def send(*args, **kwargs):
        result = next(results)
        calls.append(result)
        return result

    monkeypatch.setattr(HTTPAdapter, "send", send)
    with (
        create_pinned_session(
            max_body_bytes=1000,
            max_total_body_bytes=1000,
            max_retries=Retry(total=2, status_forcelist=[500]),
        ) as session,
        pytest.raises(requests.RequestException, match="limit"),
    ):
        session.get("https://example.com/start", timeout=2)
    assert len(calls) == 2
    assert all(result.raw.closed for result in calls)
