"""Additional coverage for HTTP client scrapers.

Targets the curl_cffi tier, SSRF rejection branches (invalid initial URL and
unsafe redirect before connection), the missing-dependency ImportError branches, and httpx
HTTP/connect errors. Network is fully mocked.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import urlparse

from primr.data.scraping.http_clients import (
    scrape_with_curl_cffi,
    scrape_with_httpx,
    scrape_with_requests,
)
from primr.data.scraping.models import ErrorType
from primr.utils.security import SafeUrlResolution


def _resolution(url: str) -> SafeUrlResolution:
    parsed = urlparse(url)
    hostname = parsed.hostname or "example.com"
    return SafeUrlResolution(
        original_url=url,
        request_url=url,
        host_header=hostname,
        sni_hostname=hostname if parsed.scheme == "https" else None,
        resolved_ip=hostname,
    )


def _allow_all(url: str):
    return _resolution(url), None


# =============================================================================
# SSRF: invalid initial URL
# =============================================================================


class TestInvalidUrlRejection:
    def test_requests_rejects_invalid_url(self):
        with patch(
            "primr.utils.validators.validate_url_for_request",
            return_value=(False, None, "blocked host"),
        ):
            result = scrape_with_requests("http://169.254.169.254/")
        assert result.success is False
        assert result.error_type == ErrorType.NETWORK_ERROR
        assert "Invalid URL" in (result.error or "")
        assert result.tier == "requests"

    def test_httpx_rejects_invalid_url(self):
        with patch(
            "primr.utils.validators.validate_url_for_request",
            return_value=(False, None, "blocked host"),
        ):
            result = scrape_with_httpx("http://localhost/")
        assert result.success is False
        assert result.tier == "httpx"

    def test_curl_cffi_rejects_invalid_url(self):
        with patch(
            "primr.utils.validators.validate_url_for_request",
            return_value=(False, None, "blocked host"),
        ):
            result = scrape_with_curl_cffi("http://10.0.0.1/")
        assert result.success is False
        assert result.tier == "curl_cffi"


# =============================================================================
# SSRF: unsafe redirect before the next fetch
# =============================================================================


class TestRedirectRejection:
    def test_requests_blocks_unsafe_redirect_before_second_request(self):
        mock_resp = Mock()
        mock_resp.content = b""
        mock_resp.headers = {"Location": "http://169.254.169.254/meta"}
        mock_resp.status_code = 302
        mock_resp.url = "https://example.com"

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                side_effect=[
                    (True, "https://example.com", None),
                    (False, "http://169.254.169.254/meta", "metadata endpoint"),
                ],
            ),
            patch("requests.Session.get", return_value=mock_resp) as mock_get,
        ):
            result = scrape_with_requests("https://example.com")
        assert result.success is False
        assert "SSRF protection" in (result.error or "")
        assert mock_get.call_count == 1

    def test_httpx_blocks_unsafe_redirect_before_second_request(self):
        mock_resp = MagicMock()
        mock_resp.content = b""
        mock_resp.headers = {"Location": "http://127.0.0.1/admin"}
        mock_resp.status_code = 302
        mock_resp.url = "https://example.com"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                side_effect=[
                    (True, "https://example.com", None),
                    (False, "http://127.0.0.1/admin", "loopback"),
                ],
            ),
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch("httpx.Client", return_value=mock_client),
        ):
            result = scrape_with_httpx("https://example.com")
        assert result.success is False
        assert "SSRF protection" in (result.error or "")
        assert mock_client.get.call_count == 1


# =============================================================================
# httpx error branches
# =============================================================================


class TestHttpxErrors:
    def test_connect_error(self):
        import httpx

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch("httpx.Client") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value = mock_client
            result = scrape_with_httpx("https://example.com")
        assert result.success is False
        assert result.error_type == ErrorType.NETWORK_ERROR

    def test_generic_http_error(self):
        import httpx

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch("httpx.Client") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.side_effect = httpx.HTTPError("protocol error")
            mock_client_cls.return_value = mock_client
            result = scrape_with_httpx("https://example.com")
        assert result.success is False
        assert result.error_type == ErrorType.NETWORK_ERROR

    def test_timeout_error(self):
        import httpx

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch("httpx.Client") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("slow")
            mock_client_cls.return_value = mock_client
            result = scrape_with_httpx("https://example.com", timeout=3)
        assert result.success is False
        assert result.error_type == ErrorType.TIMEOUT


# =============================================================================
# curl_cffi tier
# =============================================================================


class TestCurlCffi:
    def _make_module(self, response=None, side_effect=None):
        """Build a fake curl_cffi module with a Session.get."""
        session = MagicMock()
        session.__enter__.return_value = session
        session.__exit__.return_value = False
        if side_effect is not None:
            session.get.side_effect = side_effect
        else:
            session.get.return_value = response
        requests = MagicMock()
        requests.Session.return_value = session
        return SimpleNamespace(CurlOpt=SimpleNamespace(RESOLVE="RESOLVE"), requests=requests)

    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.content = b"<html>ok</html>"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.status_code = 200
        mock_resp.url = "https://example.com/"

        fake_curl = self._make_module(response=mock_resp)

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch.dict(sys.modules, {"curl_cffi": fake_curl}),
        ):
            result = scrape_with_curl_cffi("https://example.com")
        assert result.success is True
        assert result.raw_content == b"<html>ok</html>"
        assert result.tier == "curl_cffi"

    def test_timeout_classified(self):
        fake_curl = self._make_module(side_effect=Exception("operation timeout reached"))

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch.dict(sys.modules, {"curl_cffi": fake_curl}),
        ):
            result = scrape_with_curl_cffi("https://example.com")
        assert result.success is False
        assert result.error_type == ErrorType.TIMEOUT

    def test_generic_error_classified(self):
        fake_curl = self._make_module(side_effect=Exception("TLS handshake failed"))

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch.dict(sys.modules, {"curl_cffi": fake_curl}),
        ):
            result = scrape_with_curl_cffi("https://example.com")
        assert result.success is False
        assert result.error_type == ErrorType.NETWORK_ERROR

    def test_blocks_unsafe_redirect(self):
        mock_resp = MagicMock()
        mock_resp.content = b""
        mock_resp.headers = {"Location": "http://127.0.0.1/"}
        mock_resp.status_code = 302
        mock_resp.url = "https://example.com"

        fake_curl = self._make_module(response=mock_resp)

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                side_effect=[
                    (True, "https://example.com", None),
                    (False, "http://127.0.0.1/", "loopback"),
                ],
            ),
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch.dict(sys.modules, {"curl_cffi": fake_curl}),
        ):
            result = scrape_with_curl_cffi("https://example.com")
        assert result.success is False
        assert "SSRF protection" in (result.error or "")
        assert fake_curl.requests.Session.return_value.get.call_count == 1
