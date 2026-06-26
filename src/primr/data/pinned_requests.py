"""Requests transport adapter that pins each request to a validated IP address."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from requests.utils import select_proxy

if TYPE_CHECKING:
    from requests.models import PreparedRequest
    from urllib3 import HTTPConnectionPool


class PinnedHTTPAdapter(HTTPAdapter):
    """Resolve, validate, and pin the target IP before urllib3 opens a socket."""

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
        if select_proxy(request.url, proxies):
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
