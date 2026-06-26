from unittest.mock import Mock, patch

import pytest
import requests

from primr.data.pinned_requests import PinnedHTTPAdapter, create_pinned_session
from primr.utils.security import SafeUrlResolution


def _prepared(method: str, url: str) -> requests.PreparedRequest:
    return requests.Request(method, url).prepare()


def _resolution(
    *,
    original_url: str,
    request_url: str,
    host_header: str = "example.com",
    sni_hostname: str | None = "example.com",
    resolved_ip: str = "93.184.216.34",
) -> SafeUrlResolution:
    return SafeUrlResolution(
        original_url=original_url,
        request_url=request_url,
        host_header=host_header,
        sni_hostname=sni_hostname,
        resolved_ip=resolved_ip,
    )


def test_https_adapter_connects_to_validated_ip_with_host_and_sni():
    request = _prepared("GET", "https://example.com/research")
    adapter = PinnedHTTPAdapter()
    pool = Mock()

    with (
        patch(
            "primr.utils.security.resolve_safe_url_for_connect",
            return_value=(
                _resolution(
                    original_url="https://example.com/research",
                    request_url="https://93.184.216.34/research",
                ),
                None,
            ),
        ) as resolve,
        patch.object(adapter.poolmanager, "connection_from_host", return_value=pool) as conn,
    ):
        result = adapter.get_connection_with_tls_context(
            request,
            verify=True,
            proxies={},
            cert=None,
        )

    assert result is pool
    resolve.assert_called_once_with("https://example.com/research")
    assert request.url == "https://example.com/research"
    assert request.headers["Host"] == "example.com"
    assert conn.call_args.kwargs["scheme"] == "https"
    assert conn.call_args.kwargs["host"] == "93.184.216.34"
    assert conn.call_args.kwargs["port"] is None
    assert conn.call_args.kwargs["pool_kwargs"]["assert_hostname"] == "example.com"
    assert conn.call_args.kwargs["pool_kwargs"]["server_hostname"] == "example.com"


def test_http_adapter_connects_to_validated_ip_without_sni():
    request = _prepared("GET", "http://example.com:8080/jobs")
    adapter = PinnedHTTPAdapter()

    with (
        patch(
            "primr.utils.security.resolve_safe_url_for_connect",
            return_value=(
                _resolution(
                    original_url="http://example.com:8080/jobs",
                    request_url="http://93.184.216.34:8080/jobs",
                    host_header="example.com:8080",
                    sni_hostname=None,
                ),
                None,
            ),
        ),
        patch.object(adapter.poolmanager, "connection_from_host") as conn,
    ):
        adapter.get_connection_with_tls_context(request, verify=True, proxies={}, cert=None)

    assert request.headers["Host"] == "example.com:8080"
    assert conn.call_args.kwargs["scheme"] == "http"
    assert conn.call_args.kwargs["host"] == "93.184.216.34"
    assert conn.call_args.kwargs["port"] == 8080
    assert "assert_hostname" not in conn.call_args.kwargs["pool_kwargs"]
    assert "server_hostname" not in conn.call_args.kwargs["pool_kwargs"]


def test_adapter_blocks_rebind_before_opening_pool():
    request = _prepared("GET", "https://example.com/private")
    adapter = PinnedHTTPAdapter()

    with (
        patch(
            "primr.utils.security.resolve_safe_url_for_connect",
            return_value=(None, "Private/reserved IP addresses are blocked"),
        ),
        patch.object(adapter.poolmanager, "connection_from_host") as conn,
        pytest.raises(ValueError, match="Private/reserved"),
    ):
        adapter.get_connection_with_tls_context(request, verify=True, proxies={}, cert=None)

    conn.assert_not_called()


def test_adapter_rejects_proxies_because_target_would_not_be_pinned():
    request = _prepared("GET", "https://example.com/")
    adapter = PinnedHTTPAdapter()

    with pytest.raises(ValueError, match="proxies"):
        adapter.get_connection_with_tls_context(
            request,
            verify=True,
            proxies={"https": "http://proxy.example:8080"},
            cert=None,
        )


def test_create_pinned_session_mounts_adapter_and_ignores_environment_proxies():
    session = create_pinned_session()

    assert isinstance(session.get_adapter("https://example.com"), PinnedHTTPAdapter)
    assert isinstance(session.get_adapter("http://example.com"), PinnedHTTPAdapter)
    assert session.trust_env is False
    session.close()
