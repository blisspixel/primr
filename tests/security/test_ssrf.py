"""
SSRF (Server-Side Request Forgery) protection tests.

Tests that verify URLs pointing to internal/private addresses are blocked
across all HTTP client implementations.
"""

import pytest

from primr.data.scraping.http_clients import (
    scrape_with_httpx,
    scrape_with_requests,
)
from primr.data.scraping.net import head_exists, make_request
from primr.utils.validators import validate_url_for_request


class TestURLValidation:
    """Test URL validation for SSRF protection."""

    def test_validate_url_localhost(self):
        """Test that localhost URLs are blocked."""
        test_cases = [
            ("http://localhost:8080/admin", "localhost"),
            ("http://127.0.0.1/admin", "loopback"),
            ("http://127.0.0.2/admin", "loopback"),
        ]

        for url, expected_keyword in test_cases:
            is_valid, returned_url, error_msg = validate_url_for_request(url)
            assert not is_valid, f"Should block localhost URL: {url}"
            assert error_msg is not None, f"Should have error message for: {url}"
            assert expected_keyword in error_msg.lower() or "not allowed" in error_msg.lower(), \
                f"Error message should mention {expected_keyword}/not allowed: {error_msg}"

    def test_validate_url_private_ips(self):
        """Test that private IP addresses are blocked."""
        test_cases = [
            "http://192.168.1.1/admin",
            "http://192.168.0.1/router",
            "http://10.0.0.1/internal",
            "http://10.255.255.255/internal",
            "http://172.16.0.1/internal",
            "http://172.31.255.255/internal",
        ]

        for url in test_cases:
            is_valid, returned_url, error_msg = validate_url_for_request(url)
            assert not is_valid, f"Should block private IP: {url}"
            assert error_msg is not None, f"Should have error message for: {url}"
            assert "private" in error_msg.lower(), \
                f"Error message should mention private: {error_msg}"

    def test_validate_url_link_local(self):
        """Test that link-local addresses are blocked."""
        test_cases = [
            "http://169.254.1.1/admin",
            "http://169.254.169.254/metadata",  # AWS metadata service
        ]

        for url in test_cases:
            is_valid, returned_url, error_msg = validate_url_for_request(url)
            assert not is_valid, f"Should block link-local address: {url}"
            assert error_msg is not None, f"Should have error message for: {url}"
            assert "link-local" in error_msg.lower() or "private" in error_msg.lower(), \
                f"Error message should mention link-local/private: {error_msg}"

    def test_validate_url_invalid_schemes(self):
        """Test that non-HTTP schemes are blocked."""
        test_cases = [
            "file:///etc/passwd",
            "ftp://example.com/file",
        ]

        for url in test_cases:
            is_valid, returned_url, error_msg = validate_url_for_request(url)
            assert not is_valid, f"Should block non-HTTP scheme: {url}"
            assert error_msg is not None, f"Should have error message for: {url}"
            assert "scheme" in error_msg.lower() or "http" in error_msg.lower() or \
                   "allowed" in error_msg.lower() or "suspicious" in error_msg.lower(), \
                f"Error message should indicate URL is not allowed: {error_msg}"

    def test_validate_url_valid_public(self):
        """Test that valid public URLs are allowed."""
        test_cases = [
            "https://example.com",
            "http://example.com/path",
            "https://www.google.com",
            "https://api.github.com/users",
        ]

        for url in test_cases:
            is_valid, normalized, error_msg = validate_url_for_request(url)
            assert is_valid, f"Should allow public URL: {url}, error: {error_msg}"
            assert normalized is not None and len(normalized) > 0, \
                f"Should return normalized URL for: {url}"
            assert error_msg is None, f"Should not have error for valid URL: {url}"

    def test_validate_url_malformed(self):
        """Test that malformed URLs are rejected."""
        test_cases = [
            "://no-scheme.com",
            "",
            "   ",
        ]

        for url in test_cases:
            is_valid, returned_url, error_msg = validate_url_for_request(url)
            assert not is_valid, f"Should reject malformed URL: {url}"
            assert error_msg is not None, f"Should have error message for: {url}"


class TestHTTPClientSSRF:
    """Test SSRF protection in HTTP client functions."""

    def test_scrape_with_requests_blocks_localhost(self):
        """Test that scrape_with_requests blocks localhost URLs."""
        result = scrape_with_requests("http://localhost:8080/admin")

        assert not result.success, "Should fail for blocked URL"
        assert result.error is not None, "Should have error message"
        assert "not allowed" in result.error.lower() or "localhost" in result.error.lower(), \
            f"Error should mention blocking: {result.error}"

    def test_scrape_with_requests_blocks_private_ip(self):
        """Test that scrape_with_requests blocks private IP addresses."""
        result = scrape_with_requests("http://192.168.1.1/admin")

        assert not result.success, "Should fail for blocked URL"
        assert result.error is not None, "Should have error message"
        assert "not allowed" in result.error.lower() or "private" in result.error.lower(), \
            f"Error should mention blocking: {result.error}"

    def test_scrape_with_httpx_blocks_localhost(self):
        """Test that scrape_with_httpx blocks localhost URLs."""
        result = scrape_with_httpx("http://127.0.0.1:8080/admin")

        assert not result.success, "Should fail for blocked URL"
        assert result.error is not None, "Should have error message"
        assert "not allowed" in result.error.lower() or "localhost" in result.error.lower(), \
            f"Error should mention blocking: {result.error}"

    def test_make_request_blocks_internal_ip(self):
        """Test that make_request blocks internal IP addresses."""
        with pytest.raises(ValueError) as exc_info:
            make_request("http://10.0.0.1/internal")

        error_msg = str(exc_info.value)
        assert "not allowed" in error_msg.lower() or "private" in error_msg.lower(), \
            f"Error should mention blocking: {error_msg}"

    def test_head_exists_blocks_localhost(self):
        """Test that head_exists blocks localhost URLs."""
        result = head_exists("http://localhost/admin")
        assert result is False, "Should return False for blocked URL"


class TestRedirectSSRFProtection:
    """Test SSRF protection against redirect-based bypass attacks."""

    def test_validate_final_url_after_redirect_blocks_private_ip(self):
        """Test that validate_final_url_after_redirect blocks private IPs."""
        from primr.utils.security import validate_final_url_after_redirect

        test_cases = [
            "http://192.168.1.1/admin",
            "http://10.0.0.1/internal",
            "http://172.16.0.1/internal",
            "http://127.0.0.1/localhost",
        ]

        for url in test_cases:
            is_safe, error = validate_final_url_after_redirect(url)
            assert not is_safe, f"Should block private IP in final URL: {url}"
            assert error is not None, f"Should have error message for: {url}"

    def test_validate_final_url_after_redirect_blocks_metadata(self):
        """Test that validate_final_url_after_redirect blocks cloud metadata endpoints."""
        from primr.utils.security import validate_final_url_after_redirect

        is_safe, error = validate_final_url_after_redirect("http://169.254.169.254/latest/meta-data/")
        assert not is_safe, "Should block metadata endpoint in final URL"
        assert error is not None

    def test_validate_final_url_after_redirect_allows_public(self):
        """Test that validate_final_url_after_redirect allows public URLs."""
        from primr.utils.security import validate_final_url_after_redirect

        test_cases = [
            "https://example.com",
            "https://www.google.com",
            "https://api.github.com/users",
        ]

        for url in test_cases:
            is_safe, error = validate_final_url_after_redirect(url)
            assert is_safe, f"Should allow public URL: {url}, error: {error}"
            assert error is None, f"Should not have error for valid URL: {url}"

    def test_security_module_exports_redirect_validator(self):
        """Test that the security module exports validate_final_url_after_redirect."""
        from primr.utils.security import validate_final_url_after_redirect

        assert callable(validate_final_url_after_redirect)
        result = validate_final_url_after_redirect("https://example.com")
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestOrchestratorSSRFProtection:
    """Test SSRF protection at the orchestrator level."""

    def test_orchestrator_blocks_localhost(self):
        """Test that ScrapeOrchestrator blocks localhost URLs."""
        from primr.data.scraping.models import ErrorType
        from primr.data.scraping.orchestrator import ScrapeOrchestrator

        orchestrator = ScrapeOrchestrator()
        result = orchestrator.scrape_url("http://localhost:8080/admin")

        assert not result.success, "Should fail for localhost URL"
        assert result.error_type == ErrorType.HARD_BLOCK, "Should be HARD_BLOCK"
        assert "SSRF" in result.error or "blocked" in result.error.lower(), \
            f"Error should mention SSRF blocking: {result.error}"

    def test_orchestrator_blocks_private_ip(self):
        """Test that ScrapeOrchestrator blocks private IP addresses."""
        from primr.data.scraping.models import ErrorType
        from primr.data.scraping.orchestrator import ScrapeOrchestrator

        orchestrator = ScrapeOrchestrator()

        test_cases = [
            "http://192.168.1.1/admin",
            "http://10.0.0.1/internal",
            "http://172.16.0.1/internal",
        ]

        for url in test_cases:
            result = orchestrator.scrape_url(url)
            assert not result.success, f"Should fail for private IP: {url}"
            assert result.error_type == ErrorType.HARD_BLOCK, f"Should be HARD_BLOCK for: {url}"

    def test_orchestrator_blocks_metadata_endpoint(self):
        """Test that ScrapeOrchestrator blocks cloud metadata endpoints."""
        from primr.data.scraping.models import ErrorType
        from primr.data.scraping.orchestrator import ScrapeOrchestrator

        orchestrator = ScrapeOrchestrator()
        result = orchestrator.scrape_url("http://169.254.169.254/latest/meta-data/")

        assert not result.success, "Should fail for metadata endpoint"
        assert result.error_type == ErrorType.HARD_BLOCK, "Should be HARD_BLOCK"

    def test_orchestrator_blocks_loopback(self):
        """Test that ScrapeOrchestrator blocks loopback addresses."""
        from primr.data.scraping.models import ErrorType
        from primr.data.scraping.orchestrator import ScrapeOrchestrator

        orchestrator = ScrapeOrchestrator()
        result = orchestrator.scrape_url("http://127.0.0.1/admin")

        assert not result.success, "Should fail for loopback address"
        assert result.error_type == ErrorType.HARD_BLOCK, "Should be HARD_BLOCK"


class TestHTTPClientClassSSRF:
    """Test SSRF protection in the HTTPClient class."""

    def test_http_client_blocks_localhost(self):
        """Test that HTTPClient blocks localhost URLs."""
        from primr.data.http_client import HTTPClient

        client = HTTPClient()

        with pytest.raises(ValueError) as exc_info:
            client.get("http://localhost:8080/admin")

        error_msg = str(exc_info.value).lower()
        assert "ssrf" in error_msg or "not allowed" in error_msg or "localhost" in error_msg, \
            f"Error should mention SSRF blocking: {exc_info.value}"

    def test_http_client_blocks_private_ip(self):
        """Test that HTTPClient blocks private IP addresses."""
        from primr.data.http_client import HTTPClient

        client = HTTPClient()

        test_cases = [
            "http://192.168.1.1/admin",
            "http://10.0.0.1/internal",
            "http://172.16.0.1/internal",
        ]

        for url in test_cases:
            with pytest.raises(ValueError) as exc_info:
                client.get(url)

            error_msg = str(exc_info.value).lower()
            assert "ssrf" in error_msg or "not allowed" in error_msg or "private" in error_msg, \
                f"Error should mention SSRF blocking for {url}: {exc_info.value}"

    def test_http_client_blocks_metadata_endpoint(self):
        """Test that HTTPClient blocks cloud metadata endpoints."""
        from primr.data.http_client import HTTPClient

        client = HTTPClient()

        with pytest.raises(ValueError) as exc_info:
            client.get("http://169.254.169.254/latest/meta-data/")

        error_msg = str(exc_info.value).lower()
        assert "ssrf" in error_msg or "not allowed" in error_msg or "metadata" in error_msg or "link-local" in error_msg, \
            f"Error should mention SSRF blocking: {exc_info.value}"


class TestBrowserScraperRedirectSSRF:
    """Test redirect SSRF protection in browser scrapers."""

    def test_playwright_scraper_impl_has_redirect_ssrf_check(self):
        """Verify _scrape_with_playwright_impl has redirect SSRF validation code."""
        import inspect

        from primr.data.scraping.browsers import _scrape_with_playwright_impl

        source = inspect.getsource(_scrape_with_playwright_impl)
        assert "validate_final_url_after_redirect" in source, \
            "_scrape_with_playwright_impl should validate final URL after redirects"

    def test_playwright_aggressive_scraper_has_redirect_ssrf_check(self):
        """Verify scrape_with_playwright_aggressive has redirect SSRF validation code."""
        import inspect

        from primr.data.scraping.browsers import scrape_with_playwright_aggressive

        source = inspect.getsource(scrape_with_playwright_aggressive)
        assert "validate_final_url_after_redirect" in source, \
            "scrape_with_playwright_aggressive should validate final URL after redirects"

    def test_drissionpage_scraper_has_redirect_ssrf_check(self):
        """Verify scrape_with_drissionpage has redirect SSRF validation code."""
        import inspect

        from primr.data.scraping.browsers import scrape_with_drissionpage

        source = inspect.getsource(scrape_with_drissionpage)
        assert "validate_final_url_after_redirect" in source, \
            "scrape_with_drissionpage should validate final URL after redirects"

    def test_drissionpage_stealth_scraper_has_redirect_ssrf_check(self):
        """Verify scrape_with_drissionpage_stealth has redirect SSRF validation code."""
        import inspect

        from primr.data.scraping.browsers import scrape_with_drissionpage_stealth

        source = inspect.getsource(scrape_with_drissionpage_stealth)
        assert "validate_final_url_after_redirect" in source, \
            "scrape_with_drissionpage_stealth should validate final URL after redirects"

    def test_vision_scraper_has_redirect_ssrf_check(self):
        """Verify scrape_with_vision has redirect SSRF validation code."""
        import inspect

        from primr.data.scraping.browsers import scrape_with_vision

        source = inspect.getsource(scrape_with_vision)
        assert "validate_final_url_after_redirect" in source, \
            "scrape_with_vision should validate final URL after redirects"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
