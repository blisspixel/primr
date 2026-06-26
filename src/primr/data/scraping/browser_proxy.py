"""Loopback egress proxy for Chromium-backed browser scraping tiers."""

from __future__ import annotations

import contextlib
import logging
import select
import socket
import socketserver
import threading
from dataclasses import dataclass
from typing import cast
from urllib.parse import ParseResult, urlparse, urlunparse

from primr.utils.security import resolve_safe_url_for_connect

logger = logging.getLogger(__name__)

_MAX_HEADER_BYTES = 64 * 1024
_SOCKET_TIMEOUT_SECONDS = 30.0
_TUNNEL_IDLE_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class _Target:
    url: str
    host: str
    port: int


class BrowserEgressProxy:
    """Local HTTP proxy that pins browser connections to validated IPs."""

    def __init__(self) -> None:
        self._server: _ThreadingProxyServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def server_url(self) -> str:
        if self._server is None:
            raise RuntimeError("Browser egress proxy is not running")
        host, port = cast("tuple[str, int]", self._server.server_address)
        return f"http://{host}:{port}"

    def start(self) -> BrowserEgressProxy:
        if self._server is not None:
            return self

        server = _ThreadingProxyServer(("127.0.0.1", 0), _BrowserEgressProxyHandler)
        thread = threading.Thread(
            target=server.serve_forever,
            name="primr-browser-egress-proxy",
            daemon=True,
        )
        thread.start()
        self._server = server
        self._thread = thread
        return self

    def close(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            with contextlib.suppress(Exception):
                server.shutdown()
            with contextlib.suppress(Exception):
                server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)

    def __enter__(self) -> BrowserEgressProxy:
        return self.start()

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


def browser_proxy_launch_args(proxy: BrowserEgressProxy | None) -> list[str]:
    """Return Chromium args that force browser traffic through ``proxy``."""

    if proxy is None:
        return []
    return [
        f"--proxy-server={proxy.server_url}",
        "--proxy-bypass-list=<-loopback>",
        "--disable-quic",
    ]


class _ThreadingProxyServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _BrowserEgressProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(_SOCKET_TIMEOUT_SECONDS)
        try:
            header_bytes, body_prefix = _read_http_header(self.request)
            method, target, version, header_lines = _parse_request_header(header_bytes)
            if method.upper() == "CONNECT":
                self._handle_connect(target)
                return
            self._handle_http_request(method, target, version, header_lines, body_prefix)
        except Exception as exc:
            logger.debug("Browser egress proxy request failed: %s", exc)
            with contextlib.suppress(Exception):
                _send_response(self.request, 502, "Bad Gateway")

    def _handle_connect(self, authority: str) -> None:
        target = _target_from_connect_authority(authority)
        upstream = _connect_validated(target.url)
        try:
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            _relay_bidirectional(self.request, upstream)
        finally:
            with contextlib.suppress(Exception):
                upstream.close()

    def _handle_http_request(
        self,
        method: str,
        target: str,
        version: str,
        header_lines: list[bytes],
        body_prefix: bytes,
    ) -> None:
        request_url = _absolute_request_url(target, header_lines)
        parsed = urlparse(request_url)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError(f"Unsupported proxy request scheme: {parsed.scheme}")

        upstream = _connect_validated(request_url)
        try:
            upstream.sendall(
                _rewrite_http_request(method, parsed, version, header_lines, body_prefix)
            )
            _relay_bidirectional(self.request, upstream)
        finally:
            with contextlib.suppress(Exception):
                upstream.close()


def _read_http_header(sock: socket.socket) -> tuple[bytes, bytes]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ValueError("Client closed before sending headers")
        data.extend(chunk)
        if len(data) > _MAX_HEADER_BYTES:
            raise ValueError("Proxy request headers exceed maximum size")

    header, body_prefix = bytes(data).split(b"\r\n\r\n", 1)
    return header, body_prefix


def _parse_request_header(header_bytes: bytes) -> tuple[str, str, str, list[bytes]]:
    lines = header_bytes.split(b"\r\n")
    if not lines:
        raise ValueError("Empty proxy request")
    try:
        method, target, version = lines[0].decode("ascii").split(" ", 2)
    except ValueError as exc:
        raise ValueError("Malformed proxy request line") from exc
    if not version.startswith("HTTP/"):
        raise ValueError("Malformed proxy HTTP version")
    return method, target, version, lines[1:]


def _target_from_connect_authority(authority: str) -> _Target:
    parsed = urlparse(f"//{authority}")
    if not parsed.hostname:
        raise ValueError("CONNECT target must include a host")
    port = parsed.port or 443
    return _Target(
        url=f"https://{_authority(parsed, default_port=443)}/",
        host=parsed.hostname,
        port=port,
    )


def _absolute_request_url(target: str, header_lines: list[bytes]) -> str:
    parsed = urlparse(target)
    if parsed.scheme and parsed.netloc:
        return target

    host = _header_value(header_lines, b"host")
    if not host:
        raise ValueError("Origin-form proxy request is missing Host header")
    path = target if target.startswith("/") else f"/{target}"
    return f"http://{host.decode('ascii')}{path}"


def _connect_validated(url: str) -> socket.socket:
    resolution, error = resolve_safe_url_for_connect(url)
    if resolution is None:
        raise ValueError(f"SSRF protection: {error or 'URL blocked'}")

    parsed = urlparse(resolution.request_url)
    if not parsed.hostname:
        raise ValueError("Resolved browser proxy URL has no host")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    return socket.create_connection(
        (resolution.resolved_ip, port),
        timeout=_SOCKET_TIMEOUT_SECONDS,
    )


def _rewrite_http_request(
    method: str,
    parsed: ParseResult,
    version: str,
    header_lines: list[bytes],
    body_prefix: bytes,
) -> bytes:
    origin_form = urlunparse(
        ("", "", parsed.path or "/", parsed.params, parsed.query, ""),
    )
    filtered_headers = _filter_proxy_headers(header_lines)
    if _header_value(filtered_headers, b"host") is None and parsed.netloc:
        filtered_headers.insert(0, f"Host: {parsed.netloc}".encode("ascii"))

    request_line = f"{method} {origin_form} {version}".encode("ascii")
    return b"\r\n".join([request_line, *filtered_headers]) + b"\r\n\r\n" + body_prefix


def _filter_proxy_headers(header_lines: list[bytes]) -> list[bytes]:
    blocked_prefixes = (
        b"proxy-authorization:",
        b"proxy-connection:",
    )
    filtered: list[bytes] = []
    for line in header_lines:
        lower = line.lower()
        if lower.startswith(blocked_prefixes):
            continue
        filtered.append(line)
    return filtered


def _header_value(header_lines: list[bytes], name: bytes) -> bytes | None:
    prefix = name.lower() + b":"
    for line in header_lines:
        if line.lower().startswith(prefix):
            return line.split(b":", 1)[1].strip()
    return None


def _authority(parsed: ParseResult, *, default_port: int) -> str:
    host = parsed.hostname
    if host is None:
        raise ValueError("Authority must include host")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port and parsed.port != default_port:
        return f"{host}:{parsed.port}"
    return host


def _relay_bidirectional(client: socket.socket, upstream: socket.socket) -> None:
    sockets = [client, upstream]
    for sock in sockets:
        sock.settimeout(None)
    while True:
        readable, _writable, _errored = select.select(
            sockets,
            [],
            sockets,
            _TUNNEL_IDLE_TIMEOUT_SECONDS,
        )
        if not readable:
            return
        for source in readable:
            target = upstream if source is client else client
            data = source.recv(16384)
            if not data:
                return
            target.sendall(data)


def _send_response(sock: socket.socket, status: int, reason: str) -> None:
    response = (
        f"HTTP/1.1 {status} {reason}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
    ).encode("ascii")
    sock.sendall(response)
