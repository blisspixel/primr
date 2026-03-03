"""
Tests for security middleware.

Task 4: Security middleware
- 4.1-4.8: Path validation
- 4.9-4.16: URL/SSRF validation
- 4.17-4.20: Rate limiting
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from primr.mcp_server.security import (
    PathValidator,
    RateLimiter,
    URLValidator,
)


class TestPathValidator:
    """Tests for PathValidator (Requirements 11.1-11.10)."""

    @pytest.fixture
    def temp_output(self):
        """Create a temporary output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()
            (output_dir / "report.md").write_text("test")
            yield output_dir

    @pytest.fixture
    def validator(self, temp_output):
        """Create a PathValidator with temp output as allowed root."""
        return PathValidator(allowed_roots=[str(temp_output)])

    def test_valid_path_in_allowed_root(self, validator, temp_output):
        """Valid path within allowed root passes validation."""
        result = validator.validate("report.md")

        assert result.valid
        assert result.resolved_path is not None

    def test_path_traversal_blocked(self, validator):
        """Path with .. is blocked."""
        result = validator.validate("../etc/passwd")

        assert not result.valid
        assert result.error_type == "path_traversal_blocked"

    def test_encoded_traversal_blocked(self, validator):
        """URL-encoded path traversal is blocked."""
        test_cases = [
            "%2e%2e/etc/passwd",
            "..%2fetc/passwd",
            "%2e./etc/passwd",
            ".%2e/etc/passwd",
            "%252e%252e/etc/passwd",
        ]

        for path in test_cases:
            result = validator.validate(path)
            assert not result.valid, f"Path {path} should be blocked"
            assert result.error_type == "path_traversal_blocked"

    def test_unicode_homoglyph_blocked(self, validator):
        """Unicode homoglyphs are blocked."""
        # Fullwidth period (U+FF0E)
        result = validator.validate("test\uff0e\uff0e/etc/passwd")

        assert not result.valid
        assert result.error_type == "path_traversal_blocked"

    @pytest.mark.skipif(os.name == "nt", reason="Windows allows backslashes")
    def test_windows_separator_blocked_on_unix(self, validator):
        """Windows path separators blocked on non-Windows."""
        result = validator.validate("test\\..\\etc\\passwd")

        assert not result.valid
        assert result.error_type == "path_traversal_blocked"

    def test_path_outside_allowed_root_blocked(self, validator):
        """Path outside allowed roots is blocked."""
        result = validator.validate("/etc/passwd")

        assert not result.valid
        assert result.error_type == "path_traversal_blocked"

    def test_resolve_safe_returns_path_when_valid(self, validator, temp_output):
        """resolve_safe returns path when valid."""
        resolved = validator.resolve_safe("report.md")

        assert resolved is not None
        assert resolved.exists()

    def test_resolve_safe_returns_none_when_invalid(self, validator):
        """resolve_safe returns None when invalid."""
        resolved = validator.resolve_safe("../etc/passwd")

        assert resolved is None

    def test_symlink_blocked(self, temp_output):
        """Symlinks in output directory are blocked."""
        validator = PathValidator(allowed_roots=[str(temp_output)])

        # Create a symlink
        symlink_path = temp_output / "link"
        try:
            symlink_path.symlink_to("/etc")
        except OSError:
            pytest.skip("Cannot create symlinks (requires admin on Windows)")

        result = validator.validate("link/passwd")

        assert not result.valid
        assert result.error_type == "path_traversal_blocked"


class TestURLValidator:
    """Tests for URLValidator (Requirements 17.1-17.10)."""

    @pytest.fixture
    def validator(self):
        """Create a URLValidator."""
        return URLValidator()

    def test_valid_https_url(self, validator):
        """Valid HTTPS URL passes validation."""
        result = validator.validate("https://example.com")

        assert result.valid

    def test_valid_http_url(self, validator):
        """Valid HTTP URL passes validation."""
        result = validator.validate("http://example.com")

        assert result.valid

    def test_invalid_scheme_blocked(self, validator):
        """Non-HTTP schemes are blocked."""
        test_cases = [
            "file:///etc/passwd",
            "ftp://example.com",
            "gopher://example.com",
            "data:text/html,<script>alert(1)</script>",
        ]

        for url in test_cases:
            result = validator.validate(url)
            assert not result.valid, f"URL {url} should be blocked"
            assert result.error_type == "invalid_url"

    def test_localhost_blocked(self, validator):
        """Localhost URLs are blocked."""
        result = validator.validate("http://127.0.0.1")

        assert not result.valid
        assert result.error_type == "ssrf_blocked"

    def test_private_ip_blocked(self, validator):
        """Private IP ranges are blocked."""
        test_cases = [
            "http://10.0.0.1",
            "http://172.16.0.1",
            "http://192.168.1.1",
        ]

        for url in test_cases:
            result = validator.validate(url)
            assert not result.valid, f"URL {url} should be blocked"
            assert result.error_type == "ssrf_blocked"

    def test_metadata_endpoint_blocked_by_ip(self, validator):
        """AWS/GCP/Azure metadata endpoint blocked by IP."""
        result = validator.validate("http://169.254.169.254/latest/meta-data/")

        assert not result.valid
        assert result.error_type == "ssrf_blocked"

    def test_metadata_endpoint_blocked_by_hostname(self, validator):
        """Metadata endpoints blocked by hostname."""
        test_cases = [
            "http://metadata.google.internal",
            "http://metadata.goog",
        ]

        for url in test_cases:
            result = validator.validate(url)
            assert not result.valid, f"URL {url} should be blocked"
            assert result.error_type == "ssrf_blocked"

    def test_empty_hostname_blocked(self, validator):
        """URL with empty hostname is blocked."""
        result = validator.validate("http:///path")

        assert not result.valid
        assert result.error_type == "invalid_url"

    def test_dns_failure_returns_unreachable(self, validator):
        """DNS resolution failure returns url_unreachable."""
        result = validator.validate("http://this-domain-does-not-exist-12345.invalid")

        assert not result.valid
        assert result.error_type == "url_unreachable"


class TestRateLimiter:
    """Tests for RateLimiter (Requirements 12.1-12.6)."""

    @pytest.fixture
    def limiter(self):
        """Create a RateLimiter."""
        return RateLimiter()

    def test_allows_requests_under_limit(self, limiter):
        """Requests under limit are allowed."""
        for i in range(5):
            result = limiter.check_and_record("client-1", "doctor")
            assert result.allowed, f"Request {i+1} should be allowed"

    def test_blocks_requests_over_limit(self, limiter):
        """Requests over limit are blocked."""
        # doctor has limit of 10/min
        for i in range(10):
            limiter.record("client-1", "doctor")

        result = limiter.check("client-1", "doctor")

        assert not result.allowed
        assert result.retry_after_seconds is not None
        assert result.retry_after_seconds > 0

    def test_different_clients_independent(self, limiter):
        """Different clients have independent limits."""
        # Exhaust client-1's limit
        for i in range(10):
            limiter.record("client-1", "doctor")

        # client-2 should still be allowed
        result = limiter.check("client-2", "doctor")

        assert result.allowed

    def test_different_tools_independent(self, limiter):
        """Different tools have independent limits."""
        # Exhaust doctor limit
        for i in range(10):
            limiter.record("client-1", "doctor")

        # estimate_run should still be allowed
        result = limiter.check("client-1", "estimate_run")

        assert result.allowed

    def test_per_tool_limits(self, limiter):
        """Different tools have different limits."""
        # research_company has limit of 2/min
        limiter.record("client-1", "research_company")
        limiter.record("client-1", "research_company")

        result = limiter.check("client-1", "research_company")

        assert not result.allowed

    def test_estimate_run_high_limit(self, limiter):
        """estimate_run has high limit (30/min)."""
        for i in range(25):
            result = limiter.check_and_record("client-1", "estimate_run")
            assert result.allowed, f"Request {i+1} should be allowed"

    def test_env_var_override(self):
        """Rate limits can be overridden via environment."""
        with patch.dict(os.environ, {"MCP_RATE_LIMIT_DOCTOR": "5"}):
            limiter = RateLimiter()

            assert limiter.get_limit("doctor") == 5

    def test_reset_clears_state(self, limiter):
        """reset() clears rate limit state."""
        for i in range(10):
            limiter.record("client-1", "doctor")

        limiter.reset("client-1")

        result = limiter.check("client-1", "doctor")
        assert result.allowed

    def test_retry_after_calculation(self, limiter):
        """retry_after_seconds is calculated correctly."""
        # Record requests
        for i in range(10):
            limiter.record("client-1", "doctor")

        result = limiter.check("client-1", "doctor")

        assert not result.allowed
        # Should be roughly 60 seconds (1 minute window)
        assert 0 < result.retry_after_seconds <= 60
