"""Tests for shared HTTP helpers."""

from unittest.mock import Mock, patch

from primr.data.scraping.net import (
    extract_host,
    get_default_headers,
    head_exists,
    is_same_domain,
    make_request,
    normalize_url_for_request,
)
from primr.data.scraping.profiles import HttpHeaderProfile


class TestGetDefaultHeaders:
    """Tests for get_default_headers function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        headers = get_default_headers()
        assert isinstance(headers, dict)

    def test_has_user_agent(self):
        """Should include User-Agent header."""
        headers = get_default_headers()
        assert "User-Agent" in headers
        assert len(headers["User-Agent"]) > 0

    def test_has_accept_headers(self):
        """Should include Accept headers."""
        headers = get_default_headers()
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "Accept-Encoding" in headers

    def test_uses_profile_user_agent(self):
        """Should use User-Agent from profile."""
        profile = HttpHeaderProfile(
            name="test",
            user_agent="CustomAgent/1.0",
            accept_language="fr-FR",
            sec_ch_ua=None,
            sec_ch_ua_platform=None,
        )

        headers = get_default_headers(profile)
        assert headers["User-Agent"] == "CustomAgent/1.0"
        assert headers["Accept-Language"] == "fr-FR"

    def test_includes_sec_ch_ua_when_present(self):
        """Should include Sec-CH-UA headers when profile has them."""
        profile = HttpHeaderProfile(
            name="chrome",
            user_agent="Chrome/120",
            accept_language="en-US",
            sec_ch_ua='"Chromium";v="120"',
            sec_ch_ua_platform='"Windows"',
        )

        headers = get_default_headers(profile)
        assert headers["Sec-CH-UA"] == '"Chromium";v="120"'
        assert headers["Sec-CH-UA-Platform"] == '"Windows"'
        assert headers["Sec-CH-UA-Mobile"] == "?0"

    def test_excludes_sec_ch_ua_when_not_present(self):
        """Should not include Sec-CH-UA headers when profile doesn't have them."""
        profile = HttpHeaderProfile(
            name="safari",
            user_agent="Safari/17",
            accept_language="en-US",
            sec_ch_ua=None,
            sec_ch_ua_platform=None,
        )

        headers = get_default_headers(profile)
        assert "Sec-CH-UA" not in headers


class TestMakeRequest:
    """Tests for make_request function."""

    def test_makes_get_request(self):
        """Should make GET request by default."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com"

        with patch("requests.request", return_value=mock_response) as mock_req:
            make_request("https://example.com")

        mock_req.assert_called_once()
        assert mock_req.call_args[1]["method"] == "GET"

    def test_makes_head_request(self):
        """Should make HEAD request when specified."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com"

        with patch("requests.request", return_value=mock_response) as mock_req:
            make_request("https://example.com", method="HEAD")

        assert mock_req.call_args[1]["method"] == "HEAD"

    def test_uses_timeout(self):
        """Should use specified timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com"

        with patch("requests.request", return_value=mock_response) as mock_req:
            make_request("https://example.com", timeout=30)

        assert mock_req.call_args[1]["timeout"] == 30

    def test_merges_custom_headers(self):
        """Should merge custom headers with defaults."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com"

        custom_headers = {"X-Custom": "value"}

        with patch("requests.request", return_value=mock_response) as mock_req:
            make_request("https://example.com", headers=custom_headers)

        call_headers = mock_req.call_args[1]["headers"]
        assert call_headers["X-Custom"] == "value"
        assert "User-Agent" in call_headers  # Default still present

    def test_passes_cookies(self):
        """Should pass cookies to request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com"

        cookies = {"session": "abc"}

        with patch("requests.request", return_value=mock_response) as mock_req:
            make_request("https://example.com", cookies=cookies)

        assert mock_req.call_args[1]["cookies"] == cookies


class TestHeadExists:
    """Tests for head_exists function."""

    def test_returns_true_for_200(self):
        """Should return True for 200 status."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch("primr.data.scraping.net.make_request", return_value=mock_response):
            assert head_exists("https://example.com") is True

    def test_returns_true_for_301(self):
        """Should return True for redirect status."""
        mock_response = Mock()
        mock_response.status_code = 301

        with patch("primr.data.scraping.net.make_request", return_value=mock_response):
            assert head_exists("https://example.com") is True

    def test_returns_false_for_404(self):
        """Should return False for 404 status."""
        mock_response = Mock()
        mock_response.status_code = 404

        with patch("primr.data.scraping.net.make_request", return_value=mock_response):
            assert head_exists("https://example.com") is False

    def test_returns_false_on_exception(self):
        """Should return False on network exception."""
        import requests

        with patch(
            "primr.data.scraping.net.make_request", side_effect=requests.RequestException("Error")
        ):
            assert head_exists("https://example.com") is False

    def test_falls_back_to_get_on_405(self):
        """Should fall back to GET when HEAD returns 405."""
        head_response = Mock()
        head_response.status_code = 405

        get_response = Mock()
        get_response.status_code = 200

        with patch("primr.data.scraping.net.make_request") as mock_req:
            mock_req.side_effect = [head_response, get_response]
            result = head_exists("https://example.com")

        assert result is True
        assert mock_req.call_count == 2


class TestExtractHost:
    """Tests for extract_host function."""

    def test_extracts_simple_host(self):
        """Should extract host from simple URL."""
        assert extract_host("https://example.com/path") == "example.com"

    def test_extracts_host_with_port(self):
        """Should extract host with port."""
        assert extract_host("https://example.com:8080/path") == "example.com:8080"

    def test_extracts_subdomain(self):
        """Should include subdomain."""
        assert extract_host("https://www.example.com/path") == "www.example.com"

    def test_lowercases_host(self):
        """Should lowercase the host."""
        assert extract_host("https://EXAMPLE.COM/path") == "example.com"


class TestIsSameDomain:
    """Tests for is_same_domain function."""

    def test_same_domain_returns_true(self):
        """Should return True for same domain."""
        assert is_same_domain("https://example.com/page1", "https://example.com/page2") is True

    def test_different_domain_returns_false(self):
        """Should return False for different domains."""
        assert is_same_domain("https://example.com/page", "https://other.com/page") is False

    def test_different_subdomain_returns_false(self):
        """Should return False for different subdomains (simple comparison)."""
        # Note: This is simple comparison, not registered domain
        assert (
            is_same_domain("https://www.example.com/page", "https://api.example.com/page") is False
        )

    def test_case_insensitive(self):
        """Should be case insensitive."""
        assert is_same_domain("https://EXAMPLE.COM/page", "https://example.com/page") is True


class TestNormalizeUrlForRequest:
    """Tests for normalize_url_for_request function."""

    def test_adds_https_scheme(self):
        """Should add https:// if no scheme."""
        assert normalize_url_for_request("example.com") == "https://example.com"

    def test_preserves_http_scheme(self):
        """Should preserve http:// scheme."""
        assert normalize_url_for_request("http://example.com") == "http://example.com"

    def test_preserves_https_scheme(self):
        """Should preserve https:// scheme."""
        assert normalize_url_for_request("https://example.com") == "https://example.com"

    def test_strips_whitespace(self):
        """Should strip whitespace."""
        assert normalize_url_for_request("  https://example.com  ") == "https://example.com"
