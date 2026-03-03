"""Tests for scraping models."""

from datetime import datetime, timedelta

from primr.data.scraping.models import (
    Attempt,
    BlockType,
    ErrorType,
    HostState,
    ScrapeResult,
    ScrapeTier,
    ValidationResult,
)


class TestErrorType:
    """Tests for ErrorType enum."""

    def test_all_error_types_have_string_values(self):
        """All error types should have string values for serialization."""
        for error_type in ErrorType:
            assert isinstance(error_type.value, str)
            assert len(error_type.value) > 0

    def test_error_types_are_unique(self):
        """All error type values should be unique."""
        values = [e.value for e in ErrorType]
        assert len(values) == len(set(values))


class TestBlockType:
    """Tests for BlockType enum."""

    def test_all_block_types_have_string_values(self):
        """All block types should have string values for serialization."""
        for block_type in BlockType:
            assert isinstance(block_type.value, str)
            assert len(block_type.value) > 0

    def test_block_types_are_unique(self):
        """All block type values should be unique."""
        values = [b.value for b in BlockType]
        assert len(values) == len(set(values))


class TestAttempt:
    """Tests for Attempt dataclass."""

    def test_minimal_attempt(self):
        """Attempt can be created with just tier and success."""
        attempt = Attempt(tier="requests", success=True)
        assert attempt.tier == "requests"
        assert attempt.success is True
        assert attempt.error is None
        assert attempt.error_type is None

    def test_full_attempt(self):
        """Attempt can be created with all fields."""
        attempt = Attempt(
            tier="curl_cffi",
            success=False,
            error="Connection timeout",
            error_type=ErrorType.TIMEOUT,
            elapsed_ms=5000.0,
            http_status=None,
            blocked_reason=None,
        )
        assert attempt.tier == "curl_cffi"
        assert attempt.success is False
        assert attempt.error == "Connection timeout"
        assert attempt.error_type == ErrorType.TIMEOUT
        assert attempt.elapsed_ms == 5000.0


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """ValidationResult for valid content."""
        result = ValidationResult(valid=True, content_density=0.75)
        assert result.valid is True
        assert result.content_density == 0.75
        assert result.is_duplicate_template is False

    def test_invalid_result(self):
        """ValidationResult for invalid content."""
        result = ValidationResult(
            valid=False,
            reason="Content density too low",
            content_density=0.15,
            is_duplicate_template=False,
        )
        assert result.valid is False
        assert result.reason == "Content density too low"


class TestHostState:
    """Tests for HostState dataclass."""

    def test_initial_state(self):
        """HostState starts with clean state."""
        state = HostState(host="example.com")
        assert state.host == "example.com"
        assert state.cookies is None
        assert state.last_clearance_ts is None
        assert state.best_tier is None
        assert state.hard_blocked is False
        assert state.tier_failures == {}

    def test_has_fresh_clearance_no_cookies(self):
        """has_fresh_clearance returns False when no cookies."""
        state = HostState(host="example.com")
        assert state.has_fresh_clearance() is False

    def test_has_fresh_clearance_fresh(self):
        """has_fresh_clearance returns True for fresh cookies."""
        state = HostState(
            host="example.com",
            cookies={"cf_clearance": "abc123"},
            last_clearance_ts=datetime.now(),
        )
        assert state.has_fresh_clearance() is True

    def test_has_fresh_clearance_stale(self):
        """has_fresh_clearance returns False for stale cookies."""
        state = HostState(
            host="example.com",
            cookies={"cf_clearance": "abc123"},
            last_clearance_ts=datetime.now() - timedelta(minutes=15),
        )
        assert state.has_fresh_clearance(max_age_minutes=10) is False

    def test_record_tier_failure(self):
        """record_tier_failure increments failure count."""
        state = HostState(host="example.com")

        state.record_tier_failure("requests")
        assert state.tier_failures["requests"] == 1

        state.record_tier_failure("requests")
        assert state.tier_failures["requests"] == 2

        state.record_tier_failure("httpx")
        assert state.tier_failures["httpx"] == 1

    def test_should_skip_tier_below_threshold(self):
        """should_skip_tier returns False below threshold attempts."""
        state = HostState(host="example.com")
        state.tier_attempts["requests"] = 2
        state.tier_failures["requests"] = 2

        # Below threshold attempts, should not skip
        assert state.should_skip_tier("requests", threshold=3) is False

    def test_should_skip_tier_at_threshold(self):
        """should_skip_tier returns True at threshold with 100% failure rate."""
        state = HostState(host="example.com")
        # Need both attempts and failures at threshold for skip
        state.tier_attempts["requests"] = 3
        state.tier_failures["requests"] = 3

        assert state.should_skip_tier("requests", threshold=3) is True

    def test_should_skip_tier_unknown_tier(self):
        """should_skip_tier returns False for unknown tier."""
        state = HostState(host="example.com")
        assert state.should_skip_tier("unknown_tier") is False


class TestScrapeResult:
    """Tests for ScrapeResult dataclass."""

    def test_minimal_result(self):
        """ScrapeResult can be created with just url and success."""
        result = ScrapeResult(url="https://example.com", success=False)
        assert result.url == "https://example.com"
        assert result.success is False
        assert result.raw_content is None
        assert result.attempts == []

    def test_successful_result(self):
        """ScrapeResult for successful scrape."""
        result = ScrapeResult(
            url="https://example.com",
            success=True,
            raw_content=b"<html>content</html>",
            extracted_text="content",
            tier="requests",
            http_status=200,
            content_type="html",
            elapsed_ms=150.0,
        )
        assert result.success is True
        assert result.raw_content == b"<html>content</html>"
        assert result.tier == "requests"

    def test_result_with_cookies(self):
        """ScrapeResult can carry cookies for handoff."""
        result = ScrapeResult(
            url="https://example.com",
            success=True,
            cookies={"cf_clearance": "abc123"},
        )
        assert result.cookies == {"cf_clearance": "abc123"}

    def test_result_with_attempts(self):
        """ScrapeResult can track multiple attempts."""
        attempts = [
            Attempt(tier="requests", success=False, error="Timeout"),
            Attempt(tier="httpx", success=True),
        ]
        result = ScrapeResult(
            url="https://example.com",
            success=True,
            attempts=attempts,
        )
        assert len(result.attempts) == 2
        assert result.attempts[0].tier == "requests"
        assert result.attempts[1].tier == "httpx"


class TestScrapeTier:
    """Tests for ScrapeTier dataclass."""

    def test_tier_without_requires(self):
        """ScrapeTier can be created without requires."""
        def dummy_fn(url: str, timeout: int) -> ScrapeResult:
            return ScrapeResult(url=url, success=True)

        tier = ScrapeTier(name="test", scrape_fn=dummy_fn, timeout=15)
        assert tier.name == "test"
        assert tier.timeout == 15
        assert tier.requires is None

    def test_tier_with_requires(self):
        """ScrapeTier can specify a dependency."""
        def dummy_fn(url: str, timeout: int) -> ScrapeResult:
            return ScrapeResult(url=url, success=True)

        tier = ScrapeTier(
            name="curl_cffi",
            scrape_fn=dummy_fn,
            timeout=20,
            requires="curl_cffi",
        )
        assert tier.requires == "curl_cffi"
