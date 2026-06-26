"""Tests for the browser egress proxy."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from unittest.mock import patch
from urllib.parse import urlparse

from primr.data.scraping.browser_proxy import BrowserEgressProxy, browser_proxy_launch_args
from primr.utils.url_security import SafeUrlResolution


def _start_one_shot_server(
    handler: Callable[[socket.socket], None],
) -> tuple[int, threading.Thread]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def _serve() -> None:
        try:
            conn, _addr = listener.accept()
            with conn:
                handler(conn)
        finally:
            listener.close()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return port, thread


def _proxy_address(proxy: BrowserEgressProxy) -> tuple[str, int]:
    parsed = urlparse(proxy.server_url)
    assert parsed.hostname is not None
    assert parsed.port is not None
    return parsed.hostname, parsed.port


def _recv_until_closed(sock: socket.socket) -> bytes:
    chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def test_browser_proxy_rewrites_absolute_http_request_to_validated_ip():
    seen_request = {}

    def upstream(conn: socket.socket) -> None:
        data = conn.recv(4096)
        seen_request["data"] = data
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")

    upstream_port, thread = _start_one_shot_server(upstream)
    request_url = f"http://example.com:{upstream_port}/path?q=1"
    resolution = SafeUrlResolution(
        original_url=request_url,
        request_url=f"http://127.0.0.1:{upstream_port}/path?q=1",
        host_header=f"example.com:{upstream_port}",
        sni_hostname=None,
        resolved_ip="127.0.0.1",
    )

    with (
        BrowserEgressProxy().start() as proxy,
        patch(
            "primr.data.scraping.browser_proxy.resolve_safe_url_for_connect",
            return_value=(resolution, None),
        ) as resolve,
        socket.create_connection(_proxy_address(proxy), timeout=5) as client,
    ):
        client.sendall(
            (
                f"GET {request_url} HTTP/1.1\r\n"
                f"Host: example.com:{upstream_port}\r\n"
                "Proxy-Connection: keep-alive\r\n\r\n"
            ).encode("ascii")
        )
        response = _recv_until_closed(client)

    thread.join(timeout=2)
    assert b"200 OK" in response
    assert seen_request["data"].split(b"\r\n", 1)[0] == b"GET /path?q=1 HTTP/1.1"
    assert b"Proxy-Connection:" not in seen_request["data"]
    resolve.assert_called_once_with(request_url)


def test_browser_proxy_connect_tunnels_to_validated_ip():
    def upstream(conn: socket.socket) -> None:
        assert conn.recv(4) == b"ping"
        conn.sendall(b"pong")

    upstream_port, thread = _start_one_shot_server(upstream)
    request_url = f"https://example.com:{upstream_port}/"
    resolution = SafeUrlResolution(
        original_url=request_url,
        request_url=f"https://127.0.0.1:{upstream_port}/",
        host_header=f"example.com:{upstream_port}",
        sni_hostname="example.com",
        resolved_ip="127.0.0.1",
    )

    with (
        BrowserEgressProxy().start() as proxy,
        patch(
            "primr.data.scraping.browser_proxy.resolve_safe_url_for_connect",
            return_value=(resolution, None),
        ) as resolve,
        socket.create_connection(_proxy_address(proxy), timeout=5) as client,
    ):
        client.sendall(f"CONNECT example.com:{upstream_port} HTTP/1.1\r\n\r\n".encode("ascii"))
        assert b"200 Connection Established" in client.recv(4096)
        client.sendall(b"ping")
        assert client.recv(4) == b"pong"

    thread.join(timeout=2)
    resolve.assert_called_once_with(request_url)


def test_browser_proxy_blocks_unsafe_connect_before_dialing():
    with (
        BrowserEgressProxy().start() as proxy,
        patch(
            "primr.data.scraping.browser_proxy.resolve_safe_url_for_connect",
            return_value=(None, "Private/reserved IP addresses are blocked"),
        ) as resolve,
        socket.create_connection(_proxy_address(proxy), timeout=5) as client,
    ):
        client.sendall(b"CONNECT 169.254.169.254:80 HTTP/1.1\r\n\r\n")
        response = client.recv(4096)

    assert b"502 Bad Gateway" in response
    resolve.assert_called_once_with("https://169.254.169.254:80/")


def test_browser_proxy_launch_args_force_chromium_through_proxy():
    with BrowserEgressProxy().start() as proxy:
        server_url = proxy.server_url
        args = browser_proxy_launch_args(proxy)

    assert args == [
        f"--proxy-server={server_url}",
        "--proxy-bypass-list=<-loopback>",
        "--disable-quic",
    ]
