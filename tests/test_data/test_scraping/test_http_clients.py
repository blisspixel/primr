"""Tests for HTTP client scrapers."""

from unittest.mock import MagicMock, Mock, patch

from primr.data.scraping.http_clients import (
    HTTP_TIERS,
    scrape_with_httpx,
    scrape_with_requests,
)
from primr.data.scraping.models import ErrorType, ScrapeResult


class TestScrapeWithRequests:
    """Tests for scrape_with_requests function."""

    def test_successful_scrape(self):
        """Should return ScrapeResult with raw content on success."""
        mock_response = Mock()
        mock_response.content = b"<html><body>Test content</body></html>"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        with patch("requests.get", return_value=mock_response):
            result = scrape_with_requests("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.success is True
        assert result.raw_content == b"<html><body>Test content</body></html>"
        assert result.http_status == 200
        assert result.tier == "requests"
        assert len(result.attempts) == 1
        assert result.attempts[0].tier == "requests"

    def test_timeout_error(self):
        """Should handle timeout errors."""
        import requests

        with patch("requests.get", side_effect=requests.Timeout("Connection timed out")):
            result = scrape_with_requests("https://example.com", timeout=5)

        assert result.success is False
        assert result.error_type == ErrorType.TIMEOUT
        assert "timeout" in result.error.lower()
        assert result.tier == "requests"

    def test_connection_error(self):
        """Should handle connection errors."""
        import requests

        with patch("requests.get", side_effect=requests.ConnectionError("Failed to connect")):
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

        with patch("requests.get", return_value=mock_response) as mock_get:
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

        with patch("requests.get", return_value=mock_response) as mock_get:
            scrape_with_requests("https://example.com", cookies=cookies)

        assert mock_get.call_args[1]["cookies"] == cookies

    def test_records_attempt_timing(self):
        """Should record attempt timing."""
        mock_response = Mock()
        mock_response.content = b"content"
        mock_response.headers = {}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        with patch("requests.get", return_value=mock_response):
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

        with patch("httpx.Client", return_value=mock_client):
            result = scrape_with_httpx("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.success is True
        assert result.raw_content == b"<html><body>HTTPX content</body></html>"
        assert result.tier == "httpx"

    def test_timeout_error(self):
        """Should handle timeout errors."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")

        with patch("httpx.Client", return_value=mock_client):
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

        mock_requests = Mock()
        mock_requests.get.return_value = mock_response

        with patch.dict("sys.modules", {"curl_cffi": Mock(requests=mock_requests)}):
            # Need to reimport to pick up the mock
            from primr.data.scraping import http_clients

            result = http_clients.scrape_with_curl_cffi("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.tier == "curl_cffi"

    def test_uses_impersonation(self):
        """Should use browser impersonation."""
        mock_response = Mock()
        mock_response.content = b"content"
        mock_response.headers = {}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"

        mock_requests = Mock()
        mock_requests.get.return_value = mock_response

        with patch.dict("sys.modules", {"curl_cffi": Mock(requests=mock_requests)}):
            from primr.data.scraping import http_clients

            http_clients.scrape_with_curl_cffi("https://example.com", impersonate="chrome119")

        # Verify impersonate was passed
        call_kwargs = mock_requests.get.call_args[1]
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

        with patch("requests.get", return_value=mock_response):
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

        with patch("requests.get", side_effect=requests.Timeout("Timeout")):
            result = scrape_with_requests("https://example.com")

        assert result.success is False
        assert result.error_type is not None
        assert result.error is not None
