"""
Parallel web scraping with thread pool and rate limiting.

This module provides:
- Thread pool for concurrent scraping
- Per-domain rate limiting
- Circuit breaker for failing domains
- Progress tracking

Usage:
    scraper = ParallelScraper(max_workers=5)
    results = scraper.scrape_urls(urls)
"""

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from primr.types import ProgressCallback
from primr.utils.logging_config import get_logger

logger = get_logger("parallel_scraper")


@dataclass
class DomainState:
    """Tracks state for a single domain."""
    last_request: float = 0.0
    failure_count: int = 0
    success_count: int = 0
    is_open: bool = True  # Circuit breaker state

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        total = self.failure_count + self.success_count
        if total == 0:
            return 0.0
        return self.failure_count / total


@dataclass
class ScrapeResult:
    """Result of scraping a single URL."""
    url: str
    content: str | None = None
    error: str | None = None
    tier: str | None = None
    duration: float = 0.0

    @property
    def success(self) -> bool:
        """Check if scrape was successful."""
        return self.content is not None and self.error is None


class RateLimiter:
    """
    Per-domain rate limiter.

    Ensures minimum delay between requests to the same domain.
    """

    def __init__(self, min_delay: float = 1.0, max_delay: float = 3.0):
        """
        Initialize rate limiter.

        Args:
            min_delay: Minimum seconds between requests to same domain
            max_delay: Maximum delay (used for backoff)
        """
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._domains: dict[str, DomainState] = defaultdict(DomainState)
        self._lock = threading.Lock()

    def get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return "unknown"

    def wait_for_domain(self, url: str) -> None:
        """
        Wait if necessary before making request to domain.

        Args:
            url: URL to request
        """
        domain = self.get_domain(url)

        with self._lock:
            state = self._domains[domain]
            now = time.time()

            # Calculate delay based on failure rate
            delay = self._min_delay
            if state.failure_rate > 0.5:
                delay = min(self._max_delay, delay * 2)

            elapsed = now - state.last_request
            if elapsed < delay:
                wait_time = delay - elapsed
                time.sleep(wait_time)

            state.last_request = time.time()

    def record_success(self, url: str) -> None:
        """Record successful request."""
        domain = self.get_domain(url)
        with self._lock:
            self._domains[domain].success_count += 1

    def record_failure(self, url: str) -> None:
        """Record failed request."""
        domain = self.get_domain(url)
        with self._lock:
            self._domains[domain].failure_count += 1

    def get_stats(self) -> dict[str, dict]:
        """Get statistics for all domains."""
        with self._lock:
            return {
                domain: {
                    "success": state.success_count,
                    "failure": state.failure_count,
                    "failure_rate": state.failure_rate,
                }
                for domain, state in self._domains.items()
            }


class CircuitBreaker:
    """
    Circuit breaker for failing domains.

    Opens circuit (stops requests) when failure threshold is exceeded.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: float = 60.0,
        half_open_requests: int = 1
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Failures before opening circuit
            reset_timeout: Seconds before trying again
            half_open_requests: Requests to allow in half-open state
        """
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._half_open_requests = half_open_requests
        self._domains: dict[str, DomainState] = defaultdict(DomainState)
        self._open_time: dict[str, float] = {}
        self._lock = threading.Lock()

    def get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return "unknown"

    def is_open(self, url: str) -> bool:
        """
        Check if circuit is open (blocking requests).

        Args:
            url: URL to check

        Returns:
            True if circuit is open (should not make request)
        """
        domain = self.get_domain(url)

        with self._lock:
            state = self._domains[domain]

            if state.is_open:
                return False

            # Check if we should try half-open
            if domain in self._open_time:
                elapsed = time.time() - self._open_time[domain]
                if elapsed >= self._reset_timeout:
                    # Try half-open
                    logger.info(f"Circuit half-open for {domain}")
                    return False

            return True

    def record_success(self, url: str) -> None:
        """Record successful request, potentially closing circuit."""
        domain = self.get_domain(url)

        with self._lock:
            state = self._domains[domain]
            state.success_count += 1

            # Close circuit on success
            if not state.is_open:
                state.is_open = True
                state.failure_count = 0
                if domain in self._open_time:
                    del self._open_time[domain]
                logger.info(f"Circuit closed for {domain}")

    def record_failure(self, url: str) -> None:
        """Record failed request, potentially opening circuit."""
        domain = self.get_domain(url)

        with self._lock:
            state = self._domains[domain]
            state.failure_count += 1

            if state.failure_count >= self._failure_threshold:
                state.is_open = False
                self._open_time[domain] = time.time()
                logger.warning(
                    f"Circuit opened for {domain} after {state.failure_count} failures"
                )

    def get_open_circuits(self) -> list[str]:
        """Get list of domains with open circuits."""
        with self._lock:
            return [
                domain for domain, state in self._domains.items()
                if not state.is_open
            ]


class ParallelScraper:
    """
    Parallel web scraper with rate limiting and circuit breaker.

    Example:
        scraper = ParallelScraper(max_workers=5)
        results = scraper.scrape_urls(urls, progress_callback=my_callback)

        for result in results:
            if result.success:
                print(f"Got {len(result.content)} chars from {result.url}")
    """

    def __init__(
        self,
        max_workers: int = 5,
        rate_limit_delay: float = 1.0,
        circuit_breaker_threshold: int = 3,
        scrape_function: Callable[[str], tuple[str | None, str]] | None = None
    ):
        """
        Initialize parallel scraper.

        Args:
            max_workers: Maximum concurrent scraping threads
            rate_limit_delay: Minimum delay between requests to same domain
            circuit_breaker_threshold: Failures before blocking domain
            scrape_function: Function to use for scraping (default: scrape_page)
        """
        self._max_workers = max_workers
        self._rate_limiter = RateLimiter(min_delay=rate_limit_delay)
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_threshold
        )
        self._scrape_function = scrape_function
        self._lock = threading.Lock()
        self._results: list[ScrapeResult] = []

        logger.info(
            f"ParallelScraper initialized: workers={max_workers}, "
            f"rate_limit={rate_limit_delay}s"
        )

    def _get_scrape_function(self):
        """Get the scrape function, importing lazily to avoid circular imports."""
        if self._scrape_function is not None:
            return self._scrape_function

        # Lazy import to avoid circular dependency
        from primr.data.scrape import scrape_page
        return scrape_page

    def _scrape_single(self, url: str) -> ScrapeResult:
        """
        Scrape a single URL with rate limiting and circuit breaker.

        Args:
            url: URL to scrape

        Returns:
            ScrapeResult with content or error
        """
        start_time = time.time()

        # Check circuit breaker
        if self._circuit_breaker.is_open(url):
            logger.debug(f"Circuit open, skipping {url}")
            return ScrapeResult(
                url=url,
                error="Circuit breaker open",
                duration=0.0
            )

        # Rate limit
        self._rate_limiter.wait_for_domain(url)

        try:
            scrape_fn = self._get_scrape_function()
            content, tier = scrape_fn(url, silent=True)
            duration = time.time() - start_time

            if content:
                self._rate_limiter.record_success(url)
                self._circuit_breaker.record_success(url)
                logger.debug(f"Scraped {url}: {len(content)} chars in {duration:.1f}s")
                return ScrapeResult(
                    url=url,
                    content=content,
                    tier=tier,
                    duration=duration
                )
            else:
                self._rate_limiter.record_failure(url)
                self._circuit_breaker.record_failure(url)
                return ScrapeResult(
                    url=url,
                    error=tier or "No content",
                    duration=duration
                )

        except Exception as e:
            duration = time.time() - start_time
            self._rate_limiter.record_failure(url)
            self._circuit_breaker.record_failure(url)
            logger.warning(f"Scrape failed for {url}: {e}")
            return ScrapeResult(
                url=url,
                error=str(e)[:100],
                duration=duration
            )

    def scrape_urls(
        self,
        urls: list[str],
        progress_callback: ProgressCallback | None = None
    ) -> list[ScrapeResult]:
        """
        Scrape multiple URLs in parallel.

        Args:
            urls: List of URLs to scrape
            progress_callback: Optional callback(current, total, message)

        Returns:
            List of ScrapeResult objects
        """
        if not urls:
            return []

        # Deduplicate URLs
        unique_urls = list(dict.fromkeys(urls))
        total = len(unique_urls)

        logger.info(f"Starting parallel scrape of {total} URLs")
        results: list[ScrapeResult] = []
        completed = 0

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # Submit all tasks
            future_to_url = {
                executor.submit(self._scrape_single, url): url
                for url in unique_urls
            }

            # Collect results as they complete
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Unexpected error scraping {url}: {e}")
                    results.append(ScrapeResult(url=url, error=str(e)))

                completed += 1
                if progress_callback:
                    progress_callback(completed, total, url)

        # Log summary
        successful = sum(1 for r in results if r.success)
        logger.info(
            f"Parallel scrape complete: {successful}/{total} successful"
        )

        return results

    def scrape_urls_dict(
        self,
        urls: list[str],
        progress_callback: ProgressCallback | None = None
    ) -> dict[str, str]:
        """
        Scrape multiple URLs and return as dictionary.

        Args:
            urls: List of URLs to scrape
            progress_callback: Optional callback(current, total, message)

        Returns:
            Dictionary mapping URL to content (only successful scrapes)
        """
        results = self.scrape_urls(urls, progress_callback)
        return {
            r.url: r.content
            for r in results
            if r.success and r.content
        }

    def get_stats(self) -> dict[str, Any]:
        """Get scraping statistics."""
        return {
            "rate_limiter": self._rate_limiter.get_stats(),
            "open_circuits": self._circuit_breaker.get_open_circuits(),
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_default_scraper: ParallelScraper | None = None


def get_parallel_scraper(
    max_workers: int = 5,
    rate_limit_delay: float = 1.0
) -> ParallelScraper:
    """
    Get or create the default parallel scraper.

    Args:
        max_workers: Maximum concurrent threads
        rate_limit_delay: Delay between requests to same domain

    Returns:
        ParallelScraper instance
    """
    global _default_scraper
    if _default_scraper is None:
        _default_scraper = ParallelScraper(
            max_workers=max_workers,
            rate_limit_delay=rate_limit_delay
        )
    return _default_scraper


def scrape_urls_parallel(
    urls: list[str],
    max_workers: int = 5,
    progress_callback: ProgressCallback | None = None
) -> dict[str, str]:
    """
    Convenience function to scrape URLs in parallel.

    Args:
        urls: List of URLs to scrape
        max_workers: Maximum concurrent threads
        progress_callback: Optional progress callback

    Returns:
        Dictionary mapping URL to content
    """
    scraper = ParallelScraper(max_workers=max_workers)
    return scraper.scrape_urls_dict(urls, progress_callback)


def reset_parallel_scraper() -> None:
    """Reset the default parallel scraper (useful for testing)."""
    global _default_scraper
    _default_scraper = None
