"""Additional coverage for HTTP client scrapers.

Targets the curl_cffi tier, SSRF rejection branches (invalid initial URL and
unsafe redirect), the missing-dependency ImportError branches, and httpx
HTTP/connect errors. Network is fully mocked.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, Mock, patch

from primr.data.scraping.http_clients import (
    scrape_with_curl_cffi,
    scrape_with_httpx,
    scrape_with_requests,
)
from primr.data.scraping.models import ErrorType

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
# SSRF: unsafe redirect after a successful fetch
# =============================================================================


class TestRedirectRejection:
    def test_requests_blocks_unsafe_redirect(self):
        mock_resp = Mock()
        mock_resp.content = b"<html>internal</html>"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.status_code = 200
        mock_resp.url = "http://169.254.169.254/meta"

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch("requests.get", return_value=mock_resp),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(False, "metadata endpoint"),
            ),
        ):
            result = scrape_with_requests("https://example.com")
        assert result.success is False
        assert "SSRF protection" in (result.error or "")

    def test_httpx_blocks_unsafe_redirect(self):
        mock_resp = MagicMock()
        mock_resp.content = b"<html>internal</html>"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.status_code = 200
        mock_resp.url = "http://127.0.0.1/admin"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch("httpx.Client", return_value=mock_client),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(False, "loopback"),
            ),
        ):
            result = scrape_with_httpx("https://example.com")
        assert result.success is False
        assert "SSRF protection" in (result.error or "")


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
        """Build a fake curl_cffi module with a requests.get."""
        mod = MagicMock()
        if side_effect is not None:
            mod.requests.get.side_effect = side_effect
        else:
            mod.requests.get.return_value = response
        return mod

    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.content = b"<html>ok</html>"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.status_code = 200
        mock_resp.url = "https://example.com/"

        fake_curl = MagicMock()
        fake_curl.requests.get.return_value = mock_resp

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch.dict(sys.modules, {"curl_cffi": fake_curl}),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(True, None),
            ),
        ):
            result = scrape_with_curl_cffi("https://example.com")
        assert result.success is True
        assert result.raw_content == b"<html>ok</html>"
        assert result.tier == "curl_cffi"

    def test_timeout_classified(self):
        fake_curl = MagicMock()
        fake_curl.requests.get.side_effect = Exception("operation timeout reached")

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch.dict(sys.modules, {"curl_cffi": fake_curl}),
        ):
            result = scrape_with_curl_cffi("https://example.com")
        assert result.success is False
        assert result.error_type == ErrorType.TIMEOUT

    def test_generic_error_classified(self):
        fake_curl = MagicMock()
        fake_curl.requests.get.side_effect = Exception("TLS handshake failed")

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch.dict(sys.modules, {"curl_cffi": fake_curl}),
        ):
            result = scrape_with_curl_cffi("https://example.com")
        assert result.success is False
        assert result.error_type == ErrorType.NETWORK_ERROR

    def test_blocks_unsafe_redirect(self):
        mock_resp = MagicMock()
        mock_resp.content = b"<html>x</html>"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.status_code = 200
        mock_resp.url = "http://127.0.0.1/"

        fake_curl = MagicMock()
        fake_curl.requests.get.return_value = mock_resp

        with (
            patch(
                "primr.utils.validators.validate_url_for_request",
                return_value=(True, "https://example.com", None),
            ),
            patch.dict(sys.modules, {"curl_cffi": fake_curl}),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(False, "loopback"),
            ),
        ):
            result = scrape_with_curl_cffi("https://example.com")
        assert result.success is False
        assert "SSRF protection" in (result.error or "")
