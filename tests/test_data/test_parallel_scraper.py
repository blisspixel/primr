"""
Tests for the parallel scraper module.

Tests rate limiting, circuit breaker, and parallel execution.
"""

import threading
import time
from unittest.mock import MagicMock, patch

from primr.data.parallel_scraper import (
    CircuitBreaker,
    ParallelScraper,
    RateLimiter,
    ScrapeResult,
    get_parallel_scraper,
    reset_parallel_scraper,
    scrape_urls_parallel,
)

# =============================================================================
# RATE LIMITER TESTS
# =============================================================================

class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_get_domain(self):
        """Test domain extraction from URL."""
        limiter = RateLimiter()
        assert limiter.get_domain("https://example.com/page") == "example.com"
        assert limiter.get_domain("http://www.test.org/path") == "www.test.org"
        assert limiter.get_domain("https://sub.domain.com:8080/") == "sub.domain.com:8080"

    def test_get_domain_invalid(self):
        """Test domain extraction with invalid URL."""
        limiter = RateLimiter()
        assert limiter.get_domain("not-a-url") == ""

    def test_record_success(self):
        """Test recording successful requests."""
        limiter = RateLimiter()
        url = "https://example.com/page"

        limiter.record_success(url)
        limiter.record_success(url)

        stats = limiter.get_stats()
        assert stats["example.com"]["success"] == 2
        assert stats["example.com"]["failure"] == 0

    def test_record_failure(self):
        """Test recording failed requests."""
        limiter = RateLimiter()
        url = "https://example.com/page"

        limiter.record_failure(url)

        stats = limiter.get_stats()
        assert stats["example.com"]["failure"] == 1

    def test_failure_rate_calculation(self):
        """Test failure rate calculation."""
        limiter = RateLimiter()
        url = "https://example.com/page"

        limiter.record_success(url)
        limiter.record_success(url)
        limiter.record_failure(url)
        limiter.record_failure(url)

        stats = limiter.get_stats()
        assert stats["example.com"]["failure_rate"] == 0.5

    def test_wait_for_domain_first_request(self):
        """Test that first request doesn't wait."""
        limiter = RateLimiter(min_delay=1.0)
        url = "https://example.com/page"

        start = time.time()
        limiter.wait_for_domain(url)
        elapsed = time.time() - start

        # First request should be immediate
        assert elapsed < 0.1

    def test_wait_for_domain_rate_limited(self):
        """Test that subsequent requests are rate limited."""
        limiter = RateLimiter(min_delay=0.2)
        url = "https://example.com/page"

        limiter.wait_for_domain(url)

        start = time.time()
        limiter.wait_for_domain(url)
        elapsed = time.time() - start

        # Should wait approximately min_delay
        assert elapsed >= 0.15  # Allow some tolerance

    def test_different_domains_not_limited(self):
        """Test that different domains are not rate limited together."""
        limiter = RateLimiter(min_delay=1.0)

        limiter.wait_for_domain("https://example1.com/page")

        start = time.time()
        limiter.wait_for_domain("https://example2.com/page")
        elapsed = time.time() - start

        # Different domain should be immediate
        assert elapsed < 0.1


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_closed(self):
        """Test that circuit starts closed (allowing requests)."""
        breaker = CircuitBreaker()
        assert not breaker.is_open("https://example.com")

    def test_opens_after_threshold(self):
        """Test that circuit opens after failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3)
        url = "https://example.com/page"

        breaker.record_failure(url)
        assert not breaker.is_open(url)

        breaker.record_failure(url)
        assert not breaker.is_open(url)

        breaker.record_failure(url)
        assert breaker.is_open(url)

    def test_success_closes_circuit(self):
        """Test that success closes an open circuit."""
        breaker = CircuitBreaker(failure_threshold=2)
        url = "https://example.com/page"

        # Open the circuit
        breaker.record_failure(url)
        breaker.record_failure(url)
        assert breaker.is_open(url)

        # Success should close it
        breaker.record_success(url)
        assert not breaker.is_open(url)

    def test_get_open_circuits(self):
        """Test getting list of open circuits."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Open circuit for one domain
        breaker.record_failure("https://bad.com/page")
        breaker.record_failure("https://bad.com/page")

        # Keep another domain closed
        breaker.record_failure("https://good.com/page")

        open_circuits = breaker.get_open_circuits()
        assert "bad.com" in open_circuits
        assert "good.com" not in open_circuits

    def test_different_domains_independent(self):
        """Test that different domains have independent circuits."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Open circuit for domain1
        breaker.record_failure("https://domain1.com/page")
        breaker.record_failure("https://domain1.com/page")

        # domain2 should still be closed
        assert breaker.is_open("https://domain1.com/page")
        assert not breaker.is_open("https://domain2.com/page")


# =============================================================================
# SCRAPE RESULT TESTS
# =============================================================================

class TestScrapeResult:
    """Tests for ScrapeResult dataclass."""

    def test_success_result(self):
        """Test successful scrape result."""
        result = ScrapeResult(
            url="https://example.com",
            content="Page content",
            tier="requests",
            duration=1.5
        )
        assert result.success
        assert result.content == "Page content"
        assert result.error is None

    def test_error_result(self):
        """Test error scrape result."""
        result = ScrapeResult(
            url="https://example.com",
            error="Connection timeout",
            duration=5.0
        )
        assert not result.success
        assert result.content is None
        assert result.error == "Connection timeout"

    def test_empty_content_is_failure(self):
        """Test that empty content is considered failure."""
        result = ScrapeResult(
            url="https://example.com",
            content=None,
            duration=1.0
        )
        assert not result.success


# =============================================================================
# PARALLEL SCRAPER TESTS
# =============================================================================

class TestParallelScraper:
    """Tests for ParallelScraper class."""

    def test_initialization(self):
        """Test scraper initialization."""
        scraper = ParallelScraper(max_workers=3, rate_limit_delay=0.5)
        assert scraper._max_workers == 3

    def test_scrape_empty_list(self):
        """Test scraping empty URL list."""
        scraper = ParallelScraper()
        results = scraper.scrape_urls([])
        assert results == []

    def test_scrape_with_mock_function(self):
        """Test scraping with mock scrape function."""
        def mock_scrape(url: str, silent: bool = False) -> tuple[str | None, str]:
            return f"Content from {url}", "mock"

        scraper = ParallelScraper(
            max_workers=2,
            rate_limit_delay=0.01,
            scrape_function=mock_scrape
        )

        urls = ["https://example1.com", "https://example2.com"]
        results = scraper.scrape_urls(urls)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert all(r.tier == "mock" for r in results)

    def test_scrape_with_failures(self):
        """Test scraping with some failures."""
        def mock_scrape(url: str, silent: bool = False) -> tuple[str | None, str]:
            if "fail" in url:
                return None, "Failed"
            return f"Content from {url}", "mock"

        scraper = ParallelScraper(
            max_workers=2,
            rate_limit_delay=0.01,
            scrape_function=mock_scrape
        )

        urls = ["https://good.com", "https://fail.com", "https://also-good.com"]
        results = scraper.scrape_urls(urls)

        assert len(results) == 3
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        assert len(successful) == 2
        assert len(failed) == 1

    def test_scrape_urls_dict(self):
        """Test scrape_urls_dict returns dictionary."""
        def mock_scrape(url: str, silent: bool = False) -> tuple[str | None, str]:
            return f"Content from {url}", "mock"

        scraper = ParallelScraper(
            max_workers=2,
            rate_limit_delay=0.01,
            scrape_function=mock_scrape
        )

        urls = ["https://example1.com", "https://example2.com"]
        result_dict = scraper.scrape_urls_dict(urls)

        assert isinstance(result_dict, dict)
        assert len(result_dict) == 2
        assert "https://example1.com" in result_dict

    def test_deduplicates_urls(self):
        """Test that duplicate URLs are deduplicated."""
        call_count = 0

        def mock_scrape(url: str, silent: bool = False) -> tuple[str | None, str]:
            nonlocal call_count
            call_count += 1
            return "Content", "mock"

        scraper = ParallelScraper(
            max_workers=2,
            rate_limit_delay=0.01,
            scrape_function=mock_scrape
        )

        urls = ["https://example.com", "https://example.com", "https://example.com"]
        results = scraper.scrape_urls(urls)

        # Should only scrape once
        assert call_count == 1
        assert len(results) == 1

    def test_progress_callback(self):
        """Test progress callback is called."""
        def mock_scrape(url: str, silent: bool = False) -> tuple[str | None, str]:
            return "Content", "mock"

        scraper = ParallelScraper(
            max_workers=1,
            rate_limit_delay=0.01,
            scrape_function=mock_scrape
        )

        progress_calls = []
        def progress_callback(current, total, msg):
            progress_calls.append((current, total, msg))

        urls = ["https://example1.com", "https://example2.com"]
        scraper.scrape_urls(urls, progress_callback=progress_callback)

        assert len(progress_calls) == 2
        assert progress_calls[-1][0] == 2  # Final call should be 2/2
        assert progress_calls[-1][1] == 2

    def test_circuit_breaker_integration(self):
        """Test circuit breaker stops requests to failing domain."""
        fail_count = 0

        def mock_scrape(url: str, silent: bool = False) -> tuple[str | None, str]:
            nonlocal fail_count
            if "bad.com" in url:
                fail_count += 1
                return None, "Failed"
            return "Content", "mock"

        scraper = ParallelScraper(
            max_workers=1,
            rate_limit_delay=0.01,
            circuit_breaker_threshold=2,
            scrape_function=mock_scrape
        )

        # First two failures should go through
        urls = [
            "https://bad.com/1",
            "https://bad.com/2",
            "https://bad.com/3",  # Should be blocked by circuit breaker
            "https://bad.com/4",  # Should be blocked
        ]
        results = scraper.scrape_urls(urls)

        # Circuit should open after 2 failures
        # So only 2 actual scrape attempts should be made
        assert fail_count == 2

    def test_get_stats(self):
        """Test getting scraper statistics."""
        def mock_scrape(url: str, silent: bool = False) -> tuple[str | None, str]:
            if "fail" in url:
                return None, "Failed"
            return "Content", "mock"

        scraper = ParallelScraper(
            max_workers=1,
            rate_limit_delay=0.01,
            scrape_function=mock_scrape
        )

        urls = ["https://good.com", "https://fail.com"]
        scraper.scrape_urls(urls)

        stats = scraper.get_stats()
        assert "rate_limiter" in stats
        assert "open_circuits" in stats

    def test_parallel_execution(self):
        """Test that scraping actually happens in parallel."""
        execution_times = []
        lock = threading.Lock()

        def mock_scrape(url: str, silent: bool = False) -> tuple[str | None, str]:
            with lock:
                execution_times.append(time.time())
            time.sleep(0.1)  # Simulate work
            return "Content", "mock"

        scraper = ParallelScraper(
            max_workers=3,
            rate_limit_delay=0.01,
            scrape_function=mock_scrape
        )

        # Use different domains to avoid rate limiting
        urls = [
            "https://domain1.com",
            "https://domain2.com",
            "https://domain3.com",
        ]

        start = time.time()
        scraper.scrape_urls(urls)
        total_time = time.time() - start

        # If parallel, should take ~0.1s, not ~0.3s
        # Allow some overhead
        assert total_time < 0.25


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self):
        """Reset state before each test."""
        reset_parallel_scraper()

    def test_get_parallel_scraper_singleton(self):
        """Test that get_parallel_scraper returns singleton."""
        scraper1 = get_parallel_scraper()
        scraper2 = get_parallel_scraper()
        assert scraper1 is scraper2

    def test_reset_parallel_scraper(self):
        """Test resetting the singleton."""
        scraper1 = get_parallel_scraper()
        reset_parallel_scraper()
        scraper2 = get_parallel_scraper()
        assert scraper1 is not scraper2

    @patch('primr.data.parallel_scraper.ParallelScraper')
    def test_scrape_urls_parallel(self, mock_scraper_class):
        """Test scrape_urls_parallel convenience function."""
        mock_instance = MagicMock()
        mock_instance.scrape_urls_dict.return_value = {"url": "content"}
        mock_scraper_class.return_value = mock_instance

        result = scrape_urls_parallel(["https://example.com"])

        assert result == {"url": "content"}
        mock_instance.scrape_urls_dict.assert_called_once()


# =============================================================================
# THREAD SAFETY TESTS
# =============================================================================

class TestThreadSafety:
    """Tests for thread safety of components."""

    def test_rate_limiter_thread_safe(self):
        """Test rate limiter is thread safe."""
        limiter = RateLimiter()
        errors = []

        def record_many(url: str, count: int):
            try:
                for _ in range(count):
                    limiter.record_success(url)
                    limiter.record_failure(url)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record_many, args=(f"https://domain{i}.com", 100))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_circuit_breaker_thread_safe(self):
        """Test circuit breaker is thread safe."""
        breaker = CircuitBreaker(failure_threshold=100)
        errors = []

        def record_many(url: str, count: int):
            try:
                for _ in range(count):
                    breaker.record_failure(url)
                    breaker.record_success(url)
                    breaker.is_open(url)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record_many, args=(f"https://domain{i}.com", 100))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
