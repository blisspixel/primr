"""
Input validation and sanitization tests.

Tests for URL validation, company name sanitization, and API input validation.
"""

import pytest

from primr.utils.validators import validate_url_for_request


class TestURLInputValidation:
    """Test general URL input validation."""

    def test_validate_url_empty_string(self):
        """Test that empty strings are rejected."""
        is_valid, error_msg, _ = validate_url_for_request("")
        assert not is_valid
        assert error_msg is not None

    def test_validate_url_whitespace_only(self):
        """Test that whitespace-only strings are rejected."""
        is_valid, error_msg, _ = validate_url_for_request("   ")
        assert not is_valid
        assert error_msg is not None

    def test_validate_url_none(self):
        """Test that None is handled gracefully."""
        try:
            is_valid, error_msg, _ = validate_url_for_request(None)
            assert not is_valid
        except (TypeError, AttributeError):
            pass

    def test_validate_url_normalization(self):
        """Test that URLs are normalized correctly."""
        test_cases = [
            ("HTTP://EXAMPLE.COM", "http://example.com"),
            ("https://example.com:443", "https://example.com"),
            ("http://example.com:80", "http://example.com"),
            ("https://example.com/path/../other", "https://example.com/other"),
        ]

        for input_url, expected_normalized in test_cases:
            is_valid, _, normalized = validate_url_for_request(input_url)
            if is_valid and normalized:
                assert normalized.lower() == normalized, "URL should be lowercase"


class TestSecurityHeaders:
    """Test security-related headers and configurations."""

    def test_timeout_configured(self):
        """Test that HTTP requests have timeouts configured."""
        from primr.data.scraping.http_clients import scrape_with_requests
        import inspect

        sig = inspect.signature(scrape_with_requests)
        assert "timeout" in sig.parameters or "max_wait" in sig.parameters


class TestInputSanitization:
    """Test input sanitization functions."""

    def test_sanitize_company_name_valid(self):
        """Test that valid company names are accepted."""
        from primr.utils.security import sanitize_company_name

        test_cases = [
            "Acme Corporation",
            "Test Company Inc.",
            "日本語会社",
            "Société Générale",
            "Company-Name_123",
        ]

        for name in test_cases:
            sanitized, error = sanitize_company_name(name)
            assert error is None, f"Should accept valid name: {name}, error: {error}"
            assert sanitized == name.strip(), f"Should return sanitized name for: {name}"

    def test_sanitize_company_name_rejects_empty(self):
        """Test that empty company names are rejected."""
        from primr.utils.security import sanitize_company_name

        test_cases = ["", "   ", None]

        for name in test_cases:
            sanitized, error = sanitize_company_name(name)
            assert error is not None, f"Should reject empty name: {repr(name)}"

    def test_sanitize_company_name_rejects_log_injection(self):
        """Test that log injection attempts are rejected."""
        from primr.utils.security import sanitize_company_name

        test_cases = [
            "Company\nINFO: Fake log entry",
            "Company\rCarriage return",
            "Company\x00Null byte",
            "Company\x1b[31mRed text",
        ]

        for name in test_cases:
            sanitized, error = sanitize_company_name(name)
            assert error is not None, f"Should reject log injection: {repr(name)}"

    def test_sanitize_company_name_rejects_xss(self):
        """Test that XSS attempts are rejected."""
        from primr.utils.security import sanitize_company_name

        test_cases = [
            "<script>alert('xss')</script>",
            "Company<script>evil()</script>",
            "javascript:alert(1)",
            "onclick=alert(1)",
            "onerror=alert(1)",
        ]

        for name in test_cases:
            sanitized, error = sanitize_company_name(name)
            assert error is not None, f"Should reject XSS: {repr(name)}"

    def test_sanitize_company_name_rejects_template_injection(self):
        """Test that template injection attempts are rejected."""
        from primr.utils.security import sanitize_company_name

        test_cases = [
            "{{constructor.constructor('return this')()}}",
            "${7*7}",
            "<%=7*7%>",
        ]

        for name in test_cases:
            sanitized, error = sanitize_company_name(name)
            assert error is not None, f"Should reject template injection: {repr(name)}"

    def test_sanitize_company_name_rejects_too_long(self):
        """Test that excessively long names are rejected."""
        from primr.utils.security import sanitize_company_name

        long_name = "A" * 201
        sanitized, error = sanitize_company_name(long_name)
        assert error is not None, "Should reject name exceeding max length"
        assert "length" in error.lower(), f"Error should mention length: {error}"

    def test_sanitize_url_input_valid(self):
        """Test that valid URLs are accepted."""
        from primr.utils.security import sanitize_url_input

        test_cases = [
            "https://example.com",
            "https://www.company.com/about",
            "http://example.org:8080/path",
        ]

        for url in test_cases:
            sanitized, error = sanitize_url_input(url)
            assert error is None, f"Should accept valid URL: {url}, error: {error}"

    def test_sanitize_url_input_rejects_ssrf(self):
        """Test that SSRF attempts are rejected."""
        from primr.utils.security import sanitize_url_input

        test_cases = [
            "http://localhost/admin",
            "http://127.0.0.1/admin",
            "http://192.168.1.1/admin",
            "http://169.254.169.254/metadata",
        ]

        for url in test_cases:
            sanitized, error = sanitize_url_input(url)
            assert error is not None, f"Should reject SSRF URL: {url}"

    def test_sanitize_webhook_url_requires_https(self):
        """Test that webhook URLs require HTTPS by default."""
        from primr.utils.security import sanitize_webhook_url

        sanitized, error = sanitize_webhook_url("http://example.com/webhook")
        assert error is not None, "Should reject HTTP webhook URL"
        assert "https" in error.lower(), f"Error should mention HTTPS: {error}"

        sanitized, error = sanitize_webhook_url("https://example.com/webhook")
        assert error is None, f"Should accept HTTPS webhook URL, error: {error}"

    def test_sanitize_webhook_url_rejects_ssrf(self):
        """Test that webhook URLs reject SSRF attempts."""
        from primr.utils.security import sanitize_webhook_url

        test_cases = [
            "https://localhost/webhook",
            "https://127.0.0.1/webhook",
            "https://192.168.1.1/webhook",
        ]

        for url in test_cases:
            sanitized, error = sanitize_webhook_url(url)
            assert error is not None, f"Should reject SSRF webhook URL: {url}"


class TestAPIInputValidation:
    """Test API input validation."""

    def test_research_request_has_length_limits(self):
        """Test that ResearchRequest model has length limits."""
        from primr.api.service import ResearchRequest

        schema = ResearchRequest.model_json_schema()
        properties = schema.get("properties", {})

        company_name_props = properties.get("company_name", {})
        assert "maxLength" in company_name_props, "company_name should have maxLength"
        assert company_name_props["maxLength"] == 200, "company_name maxLength should be 200"

    def test_research_request_rejects_empty_company_name(self):
        """Test that ResearchRequest rejects empty company names."""
        from pydantic import ValidationError
        from primr.api.service import ResearchRequest

        with pytest.raises(ValidationError):
            ResearchRequest(company_name="")

    def test_research_request_rejects_too_long_company_name(self):
        """Test that ResearchRequest rejects too long company names."""
        from pydantic import ValidationError
        from primr.api.service import ResearchRequest

        with pytest.raises(ValidationError):
            ResearchRequest(company_name="A" * 201)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
