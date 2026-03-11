"""
Tests for the types module.

Tests type definitions, protocols, and type guards.
"""

import pytest

from primr.types import (
    # Protocols
    AIClientProtocol,
    # Enums
    AIModelType,
    CacheProtocol,
    CompanyInfo,
    ConsoleProtocol,
    GradeResult,
    LoggerProtocol,
    LogLevel,
    OutputFormat,
    # Generic types
    Result,
    ScrapedPage,
    ScraperProtocol,
    ScrapeTier,
    # TypedDicts
    SearchResult,
    ThinkingLevel,
    is_scraped_page,
    is_search_result,
    # Type guards
    is_valid_url,
)

# =============================================================================
# ENUM TESTS
# =============================================================================


class TestAIModelType:
    """Tests for AIModelType enum."""

    def test_values(self):
        """Test enum values."""
        assert AIModelType.RESEARCH.value == "research"
        assert AIModelType.REPORT.value == "report"

    def test_str_conversion(self):
        """Test string conversion."""
        assert str(AIModelType.RESEARCH) == "research"
        assert str(AIModelType.REPORT) == "report"

    def test_from_string(self):
        """Test creating from string."""
        assert AIModelType("research") == AIModelType.RESEARCH
        assert AIModelType("report") == AIModelType.REPORT


class TestThinkingLevel:
    """Tests for ThinkingLevel enum."""

    def test_values(self):
        """Test enum values."""
        assert ThinkingLevel.LOW.value == "low"
        assert ThinkingLevel.HIGH.value == "high"

    def test_str_conversion(self):
        """Test string conversion."""
        assert str(ThinkingLevel.LOW) == "low"


class TestScrapeTier:
    """Tests for ScrapeTier enum."""

    def test_all_tiers_exist(self):
        """Test all scraping tiers are defined."""
        tiers = [
            ScrapeTier.REQUESTS,
            ScrapeTier.HTTPX,
            ScrapeTier.PLAYWRIGHT,
            ScrapeTier.PLAYWRIGHT_AGGRESSIVE,
            ScrapeTier.VISION,
            ScrapeTier.CACHE,
        ]
        assert len(tiers) == 6

    def test_tier_order(self):
        """Test tier values for ordering."""
        assert ScrapeTier.REQUESTS.value == "requests"
        assert ScrapeTier.CACHE.value == "cache"


class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_all_formats(self):
        """Test all output formats."""
        formats = [f.value for f in OutputFormat]
        assert "txt" in formats
        assert "docx" in formats
        assert "pdf" in formats
        assert "html" in formats
        assert "json" in formats


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_standard_levels(self):
        """Test standard logging levels."""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"


# =============================================================================
# TYPED DICT TESTS
# =============================================================================


class TestSearchResult:
    """Tests for SearchResult TypedDict."""

    def test_valid_search_result(self):
        """Test creating a valid search result."""
        result: SearchResult = {
            "title": "Test Company",
            "url": "https://example.com",
            "snippet": "A test company description",
        }
        assert result["title"] == "Test Company"
        assert result["url"] == "https://example.com"

    def test_search_result_keys(self):
        """Test required keys."""
        result: SearchResult = {
            "title": "Test",
            "url": "https://test.com",
            "snippet": "Test snippet",
        }
        assert "title" in result
        assert "url" in result
        assert "snippet" in result


class TestScrapedPage:
    """Tests for ScrapedPage TypedDict."""

    def test_valid_scraped_page(self):
        """Test creating a valid scraped page."""
        page: ScrapedPage = {
            "url": "https://example.com",
            "content": "Page content here",
            "tier": "requests",
            "timestamp": "2025-01-01T00:00:00",
            "word_count": 100,
        }
        assert page["tier"] == "requests"
        assert page["word_count"] == 100


class TestGradeResult:
    """Tests for GradeResult TypedDict."""

    def test_valid_grade_result(self):
        """Test creating a valid grade result."""
        grade: GradeResult = {
            "score": 8.5,
            "needs_research": False,
            "feedback": "Good content",
            "suggestions": ["Add more details"],
        }
        assert grade["score"] == 8.5
        assert not grade["needs_research"]


class TestCompanyInfo:
    """Tests for CompanyInfo TypedDict."""

    def test_minimal_company_info(self):
        """Test with minimal required fields."""
        # CompanyInfo has total=False, so all fields are optional
        info: CompanyInfo = {"name": "Test Corp"}
        assert info["name"] == "Test Corp"

    def test_full_company_info(self):
        """Test with all fields."""
        info: CompanyInfo = {
            "name": "Test Corp",
            "website": "https://test.com",
            "industry": "Technology",
            "description": "A test company",
        }
        assert info["industry"] == "Technology"


# =============================================================================
# PROTOCOL TESTS
# =============================================================================


class TestAIClientProtocol:
    """Tests for AIClientProtocol."""

    def test_protocol_implementation(self):
        """Test that a class can implement the protocol."""

        class MockAIClient:
            def generate(
                self,
                prompt: str,
                model_type: str = "research",
                temperature: float = 1.0,
                thinking_level: str = "high",
                **kwargs,
            ) -> str:
                return f"Response to: {prompt}"

            def generate_fast(self, prompt: str, model_type: str = "research") -> str:
                return f"Fast response to: {prompt}"

        client = MockAIClient()
        assert isinstance(client, AIClientProtocol)
        assert client.generate("test") == "Response to: test"
        assert client.generate_fast("test") == "Fast response to: test"


class TestScraperProtocol:
    """Tests for ScraperProtocol."""

    def test_protocol_implementation(self):
        """Test that a class can implement the protocol."""

        class MockScraper:
            def scrape(self, url: str, **kwargs) -> str | None:
                return f"Content from {url}"

            def scrape_multiple(self, urls: list, **kwargs) -> dict:
                return {url: f"Content from {url}" for url in urls}

        scraper = MockScraper()
        assert isinstance(scraper, ScraperProtocol)


class TestCacheProtocol:
    """Tests for CacheProtocol."""

    def test_protocol_implementation(self):
        """Test that a class can implement the protocol."""

        class MockCache:
            def __init__(self):
                self._data = {}

            def get(self, key: str) -> str | None:
                return self._data.get(key)

            def set(self, key: str, value: str, ttl: int | None = None) -> None:
                self._data[key] = value

            def delete(self, key: str) -> None:
                self._data.pop(key, None)

            def clear(self) -> None:
                self._data.clear()

        cache = MockCache()
        assert isinstance(cache, CacheProtocol)

        cache.set("key", "value")
        assert cache.get("key") == "value"
        cache.delete("key")
        assert cache.get("key") is None


class TestLoggerProtocol:
    """Tests for LoggerProtocol."""

    def test_protocol_implementation(self):
        """Test that a class can implement the protocol."""

        class MockLogger:
            def __init__(self):
                self.messages = []

            def debug(self, msg: str, *args, **kwargs) -> None:
                self.messages.append(("DEBUG", msg))

            def info(self, msg: str, *args, **kwargs) -> None:
                self.messages.append(("INFO", msg))

            def warning(self, msg: str, *args, **kwargs) -> None:
                self.messages.append(("WARNING", msg))

            def error(self, msg: str, *args, **kwargs) -> None:
                self.messages.append(("ERROR", msg))

        logger = MockLogger()
        assert isinstance(logger, LoggerProtocol)

        logger.info("test message")
        assert ("INFO", "test message") in logger.messages


class TestConsoleProtocol:
    """Tests for ConsoleProtocol."""

    def test_protocol_implementation(self):
        """Test that a class can implement the protocol."""

        class MockConsole:
            def text(self, msg: str) -> None:
                pass

            def step(self, msg: str) -> None:
                pass

            def ok(self, msg: str) -> None:
                pass

            def warn(self, msg: str) -> None:
                pass

            def error(self, msg: str) -> None:
                pass

        console = MockConsole()
        assert isinstance(console, ConsoleProtocol)


# =============================================================================
# RESULT TYPE TESTS
# =============================================================================


class TestResult:
    """Tests for Result generic type."""

    def test_ok_result(self):
        """Test creating a success result."""
        result = Result.ok("success value")
        assert result.is_ok
        assert not result.is_err
        assert result.value == "success value"
        assert result.error is None

    def test_err_result(self):
        """Test creating an error result."""
        error = ValueError("test error")
        result = Result.err(error)
        assert result.is_err
        assert not result.is_ok
        assert result.error == error

    def test_value_raises_on_error(self):
        """Test that accessing value on error raises."""
        error = ValueError("test error")
        result = Result.err(error)
        with pytest.raises(ValueError, match="test error"):
            _ = result.value

    def test_unwrap_or_with_ok(self):
        """Test unwrap_or with success result."""
        result = Result.ok("actual value")
        assert result.unwrap_or("default") == "actual value"

    def test_unwrap_or_with_err(self):
        """Test unwrap_or with error result."""
        result = Result.err(ValueError("error"))
        assert result.unwrap_or("default") == "default"

    def test_result_with_complex_type(self):
        """Test Result with complex types."""
        data = {"key": "value", "count": 42}
        result = Result.ok(data)
        assert result.value["key"] == "value"
        assert result.value["count"] == 42

    def test_result_with_none_value(self):
        """Test Result with None as valid value."""
        result = Result.ok(None)
        assert result.is_ok
        assert result.value is None


# =============================================================================
# TYPE GUARD TESTS
# =============================================================================


class TestIsValidUrl:
    """Tests for is_valid_url type guard."""

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        assert is_valid_url("http://example.com")

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        assert is_valid_url("https://example.com")

    def test_invalid_url_no_scheme(self):
        """Test URL without scheme."""
        assert not is_valid_url("example.com")

    def test_invalid_url_wrong_scheme(self):
        """Test URL with wrong scheme."""
        assert not is_valid_url("ftp://example.com")

    def test_invalid_url_not_string(self):
        """Test non-string value."""
        assert not is_valid_url(123)
        assert not is_valid_url(None)
        assert not is_valid_url(["http://example.com"])


class TestIsSearchResult:
    """Tests for is_search_result type guard."""

    def test_valid_search_result(self):
        """Test valid search result."""
        result = {
            "title": "Test",
            "url": "https://test.com",
            "snippet": "Test snippet",
        }
        assert is_search_result(result)

    def test_missing_key(self):
        """Test search result with missing key."""
        result = {"title": "Test", "url": "https://test.com"}
        assert not is_search_result(result)

    def test_not_dict(self):
        """Test non-dict value."""
        assert not is_search_result("not a dict")
        assert not is_search_result(None)


class TestIsScrapedPage:
    """Tests for is_scraped_page type guard."""

    def test_valid_scraped_page(self):
        """Test valid scraped page."""
        page = {
            "url": "https://test.com",
            "content": "Page content",
            "tier": "requests",
        }
        assert is_scraped_page(page)

    def test_missing_key(self):
        """Test scraped page with missing key."""
        page = {"url": "https://test.com", "content": "Content"}
        assert not is_scraped_page(page)

    def test_not_dict(self):
        """Test non-dict value."""
        assert not is_scraped_page([])
        assert not is_scraped_page(None)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestTypesIntegration:
    """Integration tests for types module."""

    def test_result_with_search_result(self):
        """Test Result containing SearchResult."""
        search_result: SearchResult = {
            "title": "Test",
            "url": "https://test.com",
            "snippet": "Test snippet",
        }
        result = Result.ok(search_result)
        assert result.is_ok
        assert result.value["title"] == "Test"

    def test_enum_in_typed_dict(self):
        """Test using enum values in typed dicts."""
        page: ScrapedPage = {
            "url": "https://test.com",
            "content": "Content",
            "tier": str(ScrapeTier.REQUESTS),
            "timestamp": "2025-01-01",
            "word_count": 10,
        }
        assert page["tier"] == "requests"

    def test_protocol_with_result(self):
        """Test protocol implementation returning Result."""

        class SafeScraper:
            def scrape(self, url: str, **kwargs) -> str | None:
                return f"Content from {url}"

            def scrape_multiple(self, urls: list, **kwargs) -> dict:
                return {}

            def safe_scrape(self, url: str) -> Result[str]:
                try:
                    content = self.scrape(url)
                    if content:
                        return Result.ok(content)
                    return Result.err(ValueError("No content"))
                except Exception as e:
                    return Result.err(e)

        scraper = SafeScraper()
        result = scraper.safe_scrape("https://test.com")
        assert result.is_ok
        assert "test.com" in result.value
