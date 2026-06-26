"""Tests for HTTP client scrapers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import urlparse

from primr.data.scraping.http_clients import (
    HTTP_TIERS,
    scrape_with_httpx,
    scrape_with_requests,
)
from primr.data.scraping.models import ErrorType, ScrapeResult
from primr.utils.security import SafeUrlResolution


def _mock_response(
    *,
    url: str,
    status_code: int,
    headers: dict[str, str] | None = None,
    content: bytes = b"content",
) -> Mock:
    response = Mock()
    response.content = content
    response.headers = headers or {}
    response.status_code = status_code
    response.url = url
    return response


def _host_header(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "example.com"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 443 if parsed.scheme == "https" else 80
    if parsed.port and parsed.port != default_port:
        return f"{host}:{parsed.port}"
    return host


def _resolution(url: str, request_url: str | None = None) -> SafeUrlResolution:
    parsed = urlparse(url)
    hostname = parsed.hostname or "example.com"
    return SafeUrlResolution(
        original_url=url,
        request_url=request_url or url,
        host_header=_host_header(url),
        sni_hostname=hostname if parsed.scheme == "https" else None,
        resolved_ip=hostname,
    )


def _allow_all(url: str):
    return _resolution(url), None


def _fake_curl_module(*, response=None, side_effect=None):
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    if side_effect is not None:
        session.get.side_effect = side_effect
    else:
        session.get.return_value = response

    requests = MagicMock()
    requests.Session.return_value = session
    return SimpleNamespace(CurlOpt=SimpleNamespace(RESOLVE="RESOLVE"), requests=requests), session


class TestScrapeWithRequests:
    """Tests for scrape_with_requests function."""

    def test_successful_scrape(self):
        """Should return ScrapeResult with raw content on success."""
        mock_response = Mock()
        mock_response.content = b"<html><body>Test content</body></html>"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        with patch("requests.Session.get", return_value=mock_response):
            result = scrape_with_requests("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.success is True
        assert result.raw_content == b"<html><body>Test content</body></html>"
        assert result.http_status == 200
        assert result.tier == "requests"
        assert len(result.attempts) == 1
        assert result.attempts[0].tier == "requests"

    def test_follows_safe_relative_redirect(self):
        """Should validate and follow a safe relative redirect."""
        redirect = _mock_response(
            url="https://example.com/start",
            status_code=302,
            headers={"Location": "/final"},
        )
        final = _mock_response(
            url="https://example.com/final",
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>final</html>",
        )

        with patch("requests.Session.get", side_effect=[redirect, final]) as mock_get:
            result = scrape_with_requests("https://example.com/start")

        assert result.success is True
        assert result.final_url == "https://example.com/final"
        assert result.raw_content == b"<html>final</html>"
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[1].args[0] == "https://example.com/final"
        assert all(call.kwargs["allow_redirects"] is False for call in mock_get.call_args_list)

    def test_timeout_error(self):
        """Should handle timeout errors."""
        import requests

        with patch("requests.Session.get", side_effect=requests.Timeout("Connection timed out")):
            result = scrape_with_requests("https://example.com", timeout=5)

        assert result.success is False
        assert result.error_type == ErrorType.TIMEOUT
        assert "timeout" in result.error.lower()
        assert result.tier == "requests"

    def test_connection_error(self):
        """Should handle connection errors."""
        import requests

        with patch(
            "requests.Session.get", side_effect=requests.ConnectionError("Failed to connect")
        ):
            result = scrape_with_requests("https://example.com")

        assert result.success is False
        assert result.error_type == ErrorType.NETWORK_ERROR
        assert result.tier == "requests"

    def test_uses_profile_headers(self):
        """Should use headers from profile."""
        from primr.data.scraping.profiles import HttpHeaderProfile

        profile = HttpHeaderProfile(
            name="test",
            user_agent="TestAgent/1.0",
            accept_language="en-US",
            sec_ch_ua='"Test";v="1"',
            sec_ch_ua_platform='"Windows"',
        )

        mock_response = Mock()
        mock_response.content = b"content"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        with patch("requests.Session.get", return_value=mock_response) as mock_get:
            scrape_with_requests("https://example.com", profile=profile)

        call_headers = mock_get.call_args[1]["headers"]
        assert call_headers["User-Agent"] == "TestAgent/1.0"
        assert call_headers["Accept-Language"] == "en-US"

    def test_passes_cookies(self):
        """Should pass cookies to request."""
        mock_response = Mock()
        mock_response.content = b"content"
        mock_response.headers = {}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        cookies = {"session": "abc123"}

        with patch("requests.Session.get", return_value=mock_response) as mock_get:
            scrape_with_requests("https://example.com", cookies=cookies)

        assert mock_get.call_args[1]["cookies"] == cookies

    def test_records_attempt_timing(self):
        """Should record attempt timing."""
        mock_response = Mock()
        mock_response.content = b"content"
        mock_response.headers = {}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        with patch("requests.Session.get", return_value=mock_response):
            result = scrape_with_requests("https://example.com")

        assert len(result.attempts) == 1
        assert result.attempts[0].elapsed_ms is not None
        assert result.attempts[0].elapsed_ms >= 0
        assert result.elapsed_ms is not None


class TestScrapeWithHttpx:
    """Tests for scrape_with_httpx function."""

    def test_successful_scrape(self):
        """Should return ScrapeResult with raw content on success."""
        mock_response = Mock()
        mock_response.content = b"<html><body>HTTPX content</body></html>"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get.return_value = mock_response

        with (
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch("httpx.Client", return_value=mock_client),
        ):
            result = scrape_with_httpx("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.success is True
        assert result.raw_content == b"<html><body>HTTPX content</body></html>"
        assert result.tier == "httpx"

    def test_follows_safe_relative_redirect(self):
        """Should validate and follow a safe relative redirect."""
        redirect = _mock_response(
            url="https://example.com/start",
            status_code=301,
            headers={"Location": "/final"},
        )
        final = _mock_response(
            url="https://example.com/final",
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>final</html>",
        )

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get.side_effect = [redirect, final]

        with (
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch("httpx.Client", return_value=mock_client) as mock_client_cls,
        ):
            result = scrape_with_httpx("https://example.com/start")

        assert result.success is True
        assert result.final_url == "https://example.com/final"
        assert mock_client.get.call_count == 2
        assert mock_client.get.call_args_list[1].args[0] == "https://example.com/final"
        assert mock_client_cls.call_args.kwargs["follow_redirects"] is False

    def test_connects_to_pinned_ip_with_original_host_and_sni(self):
        mock_response = _mock_response(
            url="https://93.184.216.34/page",
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>ok</html>",
        )
        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get.return_value = mock_response

        def fake_resolve(url: str):
            return _resolution(url, "https://93.184.216.34/page"), None

        with (
            patch("primr.utils.security.resolve_safe_url_for_connect", fake_resolve),
            patch("httpx.Client", return_value=mock_client),
        ):
            result = scrape_with_httpx("https://example.com/page")

        assert result.success is True
        assert result.final_url == "https://example.com/page"
        request = mock_client.get.call_args
        assert request.args[0] == "https://93.184.216.34/page"
        assert request.kwargs["headers"]["Host"] == "example.com"
        assert request.kwargs["extensions"] == {"sni_hostname": "example.com"}

    def test_blocks_private_rebind_result_before_connect(self):
        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)

        with (
            patch(
                "primr.utils.security.resolve_safe_url_for_connect",
                return_value=(None, "Private/reserved IP addresses are blocked"),
            ),
            patch("httpx.Client", return_value=mock_client),
        ):
            result = scrape_with_httpx("https://example.com/page")

        assert result.success is False
        assert "SSRF protection" in (result.error or "")
        mock_client.get.assert_not_called()

    def test_timeout_error(self):
        """Should handle timeout errors."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")

        with (
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch("httpx.Client", return_value=mock_client),
        ):
            result = scrape_with_httpx("https://example.com")

        assert result.success is False
        assert result.error_type == ErrorType.TIMEOUT
        assert result.tier == "httpx"


class TestScrapeWithCurlCffi:
    """Tests for scrape_with_curl_cffi function."""

    def test_successful_scrape(self):
        """Should return ScrapeResult with raw content on success."""
        mock_response = Mock()
        mock_response.content = b"<html><body>curl_cffi content</body></html>"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        fake_curl, _session = _fake_curl_module(response=mock_response)

        with (
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch.dict("sys.modules", {"curl_cffi": fake_curl}),
        ):
            # Need to reimport to pick up the mock
            from primr.data.scraping import http_clients

            result = http_clients.scrape_with_curl_cffi("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.tier == "curl_cffi"

    def test_follows_safe_relative_redirect(self):
        """Should validate and follow a safe relative redirect."""
        redirect = _mock_response(
            url="https://example.com/start",
            status_code=302,
            headers={"Location": "/final"},
        )
        final = _mock_response(
            url="https://example.com/final",
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>final</html>",
        )

        fake_curl, session = _fake_curl_module(side_effect=[redirect, final])

        with (
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch.dict("sys.modules", {"curl_cffi": fake_curl}),
        ):
            from primr.data.scraping import http_clients

            result = http_clients.scrape_with_curl_cffi("https://example.com/start")

        assert result.success is True
        assert result.final_url == "https://example.com/final"
        assert session.get.call_count == 2
        assert session.get.call_args_list[1].args[0] == "https://example.com/final"
        assert all(call.kwargs["allow_redirects"] is False for call in session.get.call_args_list)

    def test_connects_to_pinned_ip_with_libcurl_resolve(self):
        mock_response = Mock()
        mock_response.content = b"<html><body>curl_cffi content</body></html>"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/page"
        fake_curl, session = _fake_curl_module(response=mock_response)

        def fake_resolve(url: str):
            return (
                SafeUrlResolution(
                    original_url=url,
                    request_url="https://93.184.216.34/page",
                    host_header="example.com",
                    sni_hostname="example.com",
                    resolved_ip="93.184.216.34",
                ),
                None,
            )

        with (
            patch("primr.utils.security.resolve_safe_url_for_connect", fake_resolve),
            patch.dict("sys.modules", {"curl_cffi": fake_curl}),
        ):
            from primr.data.scraping import http_clients

            result = http_clients.scrape_with_curl_cffi("https://example.com/page")

        assert result.success is True
        assert result.final_url == "https://example.com/page"
        fake_curl.requests.Session.assert_called_once_with(
            curl_options={"RESOLVE": ["+example.com:443:93.184.216.34"]},
            trust_env=False,
        )
        assert session.get.call_args.args[0] == "https://example.com/page"

    def test_blocks_private_rebind_result_before_connect(self):
        fake_curl, session = _fake_curl_module(response=Mock())

        with (
            patch(
                "primr.utils.security.resolve_safe_url_for_connect",
                return_value=(None, "Private/reserved IP addresses are blocked"),
            ),
            patch.dict("sys.modules", {"curl_cffi": fake_curl}),
        ):
            from primr.data.scraping import http_clients

            result = http_clients.scrape_with_curl_cffi("https://example.com/page")

        assert result.success is False
        assert "SSRF protection" in (result.error or "")
        fake_curl.requests.Session.assert_not_called()
        session.get.assert_not_called()

    def test_uses_impersonation(self):
        """Should use browser impersonation."""
        mock_response = Mock()
        mock_response.content = b"content"
        mock_response.headers = {}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        fake_curl, session = _fake_curl_module(response=mock_response)

        with (
            patch("primr.utils.security.resolve_safe_url_for_connect", _allow_all),
            patch.dict("sys.modules", {"curl_cffi": fake_curl}),
        ):
            from primr.data.scraping import http_clients

            http_clients.scrape_with_curl_cffi("https://example.com", impersonate="chrome119")

        # Verify impersonate was passed
        call_kwargs = session.get.call_args[1]
        assert call_kwargs.get("impersonate") == "chrome119"


class TestHTTPTiersRegistry:
    """Tests for HTTP_TIERS registry."""

    def test_all_tiers_registered(self):
        """Should have all HTTP tiers registered."""
        assert "requests" in HTTP_TIERS
        assert "httpx" in HTTP_TIERS
        assert "curl_cffi" in HTTP_TIERS

    def test_tiers_are_callable(self):
        """All registered tiers should be callable."""
        for name, func in HTTP_TIERS.items():
            assert callable(func), f"Tier {name} is not callable"


class TestScrapeResultStructure:
    """Tests verifying ScrapeResult structure from HTTP clients."""

    def test_result_has_required_fields(self):
        """ScrapeResult should have all required fields."""
        mock_response = Mock()
        mock_response.content = b"content"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        with patch("requests.Session.get", return_value=mock_response):
            result = scrape_with_requests("https://example.com")

        # Check required fields exist
        assert hasattr(result, "url")
        assert hasattr(result, "success")
        assert hasattr(result, "raw_content")
        assert hasattr(result, "content_type")
        assert hasattr(result, "http_status")
        assert hasattr(result, "final_url")
        assert hasattr(result, "tier")
        assert hasattr(result, "attempts")

    def test_failed_result_has_error_info(self):
        """Failed ScrapeResult should have error information."""
        import requests

        with patch("requests.Session.get", side_effect=requests.Timeout("Timeout")):
            result = scrape_with_requests("https://example.com")

        assert result.success is False
        assert result.error_type is not None
        assert result.error is not None
