"""Requests transport adapter that pins each request to a validated IP address."""

from __future__ import annotations

import math
import time
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from requests.utils import select_proxy
from urllib3.exceptions import InvalidHeader, MaxRetryError

from primr.data.http_body import DEFAULT_MAX_BODY_BYTES, read_bounded_chunks

if TYPE_CHECKING:
    from requests.models import PreparedRequest
    from urllib3 import HTTPConnectionPool


class PinnedHTTPAdapter(HTTPAdapter):
    """Resolve, validate, and pin the target IP before urllib3 opens a socket."""

    __attrs__ = [
        *HTTPAdapter.__attrs__,
        "max_body_bytes",
        "remaining_body_bytes",
        "consumed_body_bytes",
        "response_retries",
    ]

    def __init__(
        self,
        *args: Any,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        max_total_body_bytes: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if (
            isinstance(max_body_bytes, bool)
            or not isinstance(max_body_bytes, int)
            or max_body_bytes < 1
        ):
            raise ValueError("Response byte limit must be a positive integer")
        if max_total_body_bytes is not None and (
            isinstance(max_total_body_bytes, bool)
            or not isinstance(max_total_body_bytes, int)
            or max_total_body_bytes < 1
        ):
            raise ValueError("Aggregate response byte limit must be a positive integer")
        self.max_body_bytes = max_body_bytes
        self.remaining_body_bytes = max_total_body_bytes
        self.consumed_body_bytes = 0
        self.response_retries = self.max_retries
        # urllib3 drains status-retry bodies inside urlopen, before the adapter
        # sees them. Return them unread and retry only after bounded decoding.
        self.max_retries = self.max_retries.new(status=0, raise_on_status=False)

    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float | None, float | None] | None = None,
        verify: bool | str = True,
        cert: str | tuple[str, str] | None = None,
        proxies: dict[str, str] | None = None,
    ) -> requests.Response:
        """Bound bytes before Session can eagerly consume even a redirect body."""
        values = timeout if isinstance(timeout, tuple) else (timeout,)
        budget = max((float(v) for v in values if isinstance(v, (int, float))), default=30.0)
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("Request timeout must be positive and finite")
        deadline = time.monotonic() + budget
        retries = self.response_retries
        while True:
            remaining = deadline - time.monotonic()
            if self.remaining_body_bytes is not None and self.remaining_body_bytes <= 0:
                raise requests.RequestException("Aggregate HTTP response byte limit exceeded")
            if remaining <= 0:
                raise requests.Timeout("HTTP response deadline exceeded")
            effective_timeout = tuple(
                min(float(value), remaining) if isinstance(value, (int, float)) else remaining
                for value in (timeout if isinstance(timeout, tuple) else (timeout, timeout))
            )
            response = super().send(
                request,
                stream=stream,
                timeout=(effective_timeout[0], effective_timeout[1]),
                verify=verify,
                cert=cert,
                proxies=proxies,
            )
            limit = self.max_body_bytes
            if self.remaining_body_bytes is not None:
                limit = min(limit, self.remaining_body_bytes)
            buffered = False
            try:
                used = self._buffer_response(request, response, deadline, limit)
                buffered = True
            finally:
                if not buffered and self.remaining_body_bytes is not None:
                    self.consumed_body_bytes += self.remaining_body_bytes
                    self.remaining_body_bytes = 0
            self.consumed_body_bytes += used
            if self.remaining_body_bytes is not None:
                self.remaining_body_bytes -= used
            response.__dict__["primr_body_bytes"] = self.consumed_body_bytes
            if not retries.is_retry(
                request.method or "GET",
                response.status_code,
                bool(response.headers.get("Retry-After")),
            ):
                return response
            try:
                retries = retries.increment(request.method, request.url, response=response.raw)
            except MaxRetryError as exc:
                if self.response_retries.raise_on_status:
                    raise requests.exceptions.RetryError(str(exc), response=response) from exc
                return response
            try:
                delay = retries.get_retry_after(response.raw) or retries.get_backoff_time()
            except InvalidHeader as exc:
                raise requests.exceptions.InvalidHeader(str(exc), response=response) from exc
            if delay >= deadline - time.monotonic():
                raise requests.Timeout("HTTP retry exceeds request deadline", response=response)
            if delay:
                time.sleep(delay)

    def _buffer_response(
        self, request: PreparedRequest, response: requests.Response, deadline: float, limit: int
    ) -> int:
        """Own raw reading and cleanup before SDK redirects or status retries."""
        wire_bytes = 0
        try:
            if request.method == "HEAD" or response.status_code in {204, 304}:
                body = b""
            else:

                def raw_chunks() -> Iterator[bytes]:
                    nonlocal wire_bytes
                    # read1 returns after a raw socket read rather than waiting
                    # to fill a large chunk while a peer continually trickles.
                    while True:
                        if time.monotonic() >= deadline:
                            raise requests.Timeout("HTTP response deadline exceeded")
                        chunk = response.raw.read1(64 * 1024, decode_content=False)
                        if not chunk:
                            break
                        wire_bytes += len(chunk)
                        yield chunk

                body = read_bounded_chunks(raw_chunks(), response.headers, limit, deadline)
            response._content = body
            response._content_consumed = True
            return max(wire_bytes, len(body))
        except (TimeoutError, requests.Timeout) as exc:
            raise requests.Timeout(str(exc), response=response) from exc
        except Exception as exc:
            raise requests.RequestException(str(exc), response=response) from exc
        finally:
            try:
                response.raw.close()
            finally:
                response.close()

    def get_connection_with_tls_context(
        self,
        request: PreparedRequest,
        verify: bool | str | None,
        proxies: Mapping[str, str] | None = None,
        cert: tuple[str, str] | str | None = None,
    ) -> HTTPConnectionPool:
        """Return a pool for the validated IP while preserving Host and SNI."""
        from primr.utils.security import resolve_safe_url_for_connect

        if request.url is None:
            raise ValueError("URL must be set before sending a request")
        request_proxies = dict(proxies) if proxies is not None else None
        if select_proxy(request.url, request_proxies):
            raise ValueError("SSRF protection: pinned requests do not support proxies")

        resolution, guard_error = resolve_safe_url_for_connect(request.url)
        if resolution is None:
            raise ValueError(f"SSRF protection: {guard_error or 'URL blocked'}")

        _, raw_pool_kwargs = self.build_connection_pool_key_attributes(request, verify, cert)
        pool_kwargs: dict[str, Any] = dict(raw_pool_kwargs)
        parsed_request_url = urlparse(resolution.request_url)
        scheme = parsed_request_url.scheme.lower()
        host = parsed_request_url.hostname
        port = parsed_request_url.port
        if host is None:
            raise ValueError("SSRF protection: resolved URL has no host")

        if resolution.sni_hostname is not None:
            pool_kwargs["assert_hostname"] = resolution.sni_hostname
            pool_kwargs["server_hostname"] = resolution.sni_hostname

        request.headers["Host"] = resolution.host_header
        return self.poolmanager.connection_from_host(
            scheme=scheme,
            host=host,
            port=port,
            pool_kwargs=pool_kwargs,
        )


def mount_pinned_adapters(
    session: requests.Session,
    adapter: HTTPAdapter,
    *,
    trust_env: bool = False,
) -> requests.Session:
    """Mount a requests adapter for direct, SSRF-pinned HTTP and HTTPS egress."""
    session.trust_env = trust_env
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def create_pinned_session(
    adapter: HTTPAdapter | None = None, **adapter_kwargs: Any
) -> requests.Session:
    """Create a requests session that uses :class:`PinnedHTTPAdapter` for egress."""
    session = requests.Session()
    return mount_pinned_adapters(
        session,
        adapter or PinnedHTTPAdapter(**adapter_kwargs),
        trust_env=False,
    )
