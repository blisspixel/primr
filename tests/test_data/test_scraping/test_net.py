"""Tests for shared HTTP helpers."""

from unittest.mock import Mock, patch

import pytest
import requests

from primr.data.scraping.net import (
    extract_host,
    get_default_headers,
    head_exists,
    is_in_scope,
    is_same_domain,
    make_request,
    normalize_url_for_request,
)
from primr.data.scraping.profiles import HttpHeaderProfile


def _response(status_code: int, url: str, location: str | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    response._content = b"ok"
    if location is not None:
        response.headers["Location"] = location
    return response


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

    def test_follows_safe_relative_redirect(self):
        redirect = _response(302, "https://example.com/start", "/next")
        final = _response(200, "https://example.com/next")

        with patch("requests.request", side_effect=[redirect, final]) as mock_req:
            assert make_request("https://example.com/start") is final

        assert mock_req.call_count == 2
        assert mock_req.call_args_list[0].kwargs["url"] == "https://example.com/start"
        assert mock_req.call_args_list[1].kwargs["url"] == "https://example.com/next"
        assert mock_req.call_args_list[0].kwargs["allow_redirects"] is False
        assert mock_req.call_args_list[1].kwargs["allow_redirects"] is False

    def test_blocks_unsafe_redirect_before_second_request(self):
        redirect = _response(302, "https://example.com/start", "http://127.0.0.1/admin")

        with (
            patch("requests.request", return_value=redirect) as mock_req,
            pytest.raises(ValueError, match="Invalid URL"),
        ):
            make_request("https://example.com/start")

        mock_req.assert_called_once()


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

    def test_returns_false_on_unsafe_redirect(self):
        """Should return False when a redirect target fails SSRF validation."""
        with patch("primr.data.scraping.net.make_request", side_effect=ValueError("Invalid URL")):
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
        """Should exclude the port from the per-host identity."""
        assert extract_host("https://example.com:8080/path") == "example.com"

    def test_excludes_credentials_and_dns_root_dot(self):
        """Should return only the canonical hostname used by rate-limit state."""
        assert extract_host("https://user:secret@Example.COM.:8080/path") == "example.com"

    def test_invalid_url_returns_empty_host(self):
        """Should fail closed when the URL authority is invalid."""
        assert extract_host("https://example.com:invalid/path") == ""

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

    def test_embedded_www_not_stripped(self):
        """Only a leading 'www.' is stripped; an embedded 'www.' must not be.

        Regression: host.replace('www.', '') corrupted hosts like
        'my-www.example.com' into 'my-.example.com'.
        """
        assert (
            is_same_domain("https://my-www.example.com/a", "https://my-www.example.com/b") is True
        )
        # The corrupted form must NOT be treated as the same domain.
        assert is_same_domain("https://my-www.example.com/a", "https://my-.example.com/b") is False
        # Leading www. is still normalized away.
        assert is_same_domain("https://www.example.com/a", "https://example.com/b") is True


class TestIsInScope:
    """Tests for is_in_scope function (same domain + subdomains)."""

    def test_same_domain_in_scope(self):
        assert is_in_scope("https://example.com/x", "https://example.com") is True

    def test_subdomain_in_scope(self):
        assert is_in_scope("https://docs.example.com/x", "https://example.com") is True

    def test_external_out_of_scope(self):
        assert is_in_scope("https://linkedin.com/x", "https://example.com") is False

    def test_embedded_www_not_stripped(self):
        """Regression: an embedded 'www.' must not be stripped, which would
        corrupt the host and mis-classify scope."""
        # Same host with an embedded www. is in scope with itself.
        assert is_in_scope("https://my-www.example.com/a", "https://my-www.example.com") is True
        # A genuinely different host is not pulled into scope by the corruption.
        assert is_in_scope("https://my-.example.com/a", "https://my-www.example.com") is False


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
