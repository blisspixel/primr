"""
Per-host rate limiting with token bucket and concurrency control.

Used by both orchestrator and discovery (verify_urls_exist).
"""

import random
import threading
import time
from collections import defaultdict

from .config import RateLimitConfig


class RateLimiter:
    """
    Per-host rate limiting using token bucket + semaphore.

    Features:
    - Per-host concurrency limits (semaphore)
    - Per-host request rate limits (token bucket)
    - Exponential backoff for 429 responses
    - Random jitter to avoid detection patterns
    """

    def __init__(self, config: RateLimitConfig | None = None):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration (uses defaults if None)
        """
        self.config = config or RateLimitConfig()

        # Token bucket state per host
        self._tokens: dict[str, float] = defaultdict(
            lambda: float(self.config.per_host_requests_per_minute)
        )
        self._last_refill: dict[str, float] = defaultdict(time.time)

        # Concurrency semaphores per host
        self._semaphores: dict[str, threading.Semaphore] = {}

        # Backoff state per host
        self._backoff_until: dict[str, float] = defaultdict(float)
        self._backoff_count: dict[str, int] = defaultdict(int)

        # Lock for thread safety
        self._lock = threading.Lock()

    def acquire(self, host: str) -> None:
        """
        Acquire permission to make a request to host.
        Blocks until rate limit allows.

        Args:
            host: Target host (e.g., "example.com")
        """
        # Wait for backoff if active
        self._wait_for_backoff(host)

        # Acquire concurrency semaphore
        sem = self._get_semaphore(host)
        sem.acquire()

        # Wait for token bucket rate limit
        self._wait_for_token(host)

    def release(self, host: str) -> None:
        """
        Release concurrency slot after request completes.

        IMPORTANT: Always call this in a finally block!

        Args:
            host: Target host
        """
        sem = self._get_semaphore(host)
        sem.release()

    def backoff(self, host: str) -> None:
        """
        Apply exponential backoff after 429 response.

        Args:
            host: Target host that returned 429
        """
        with self._lock:
            self._backoff_count[host] += 1
            count = self._backoff_count[host]

            # Exponential backoff with jitter
            delay = min(
                self.config.base_delay_seconds * (self.config.backoff_multiplier ** count),
                60.0  # Cap at 60 seconds
            )
            delay += random.uniform(0, delay * 0.5)  # Add jitter

            self._backoff_until[host] = time.time() + delay

    def reset_backoff(self, host: str) -> None:
        """
        Reset backoff state after successful request.

        Args:
            host: Target host
        """
        with self._lock:
            self._backoff_count[host] = 0
            self._backoff_until[host] = 0

    def _get_semaphore(self, host: str) -> threading.Semaphore:
        """Get or create semaphore for host."""
        with self._lock:
            if host not in self._semaphores:
                self._semaphores[host] = threading.Semaphore(
                    self.config.per_host_concurrency
                )
            return self._semaphores[host]

    def _wait_for_backoff(self, host: str) -> None:
        """Wait if host is in backoff period."""
        with self._lock:
            until = self._backoff_until.get(host, 0)

        if until > 0:
            wait_time = until - time.time()
            if wait_time > 0:
                time.sleep(wait_time)

    def _wait_for_token(self, host: str) -> None:
        """Wait until token available, with jitter."""
        while True:
            with self._lock:
                # Refill tokens based on time elapsed
                now = time.time()
                elapsed = now - self._last_refill[host]
                refill = elapsed * (self.config.per_host_requests_per_minute / 60.0)

                self._tokens[host] = min(
                    self._tokens[host] + refill,
                    float(self.config.per_host_requests_per_minute)
                )
                self._last_refill[host] = now

                # Check if we have a token
                if self._tokens[host] >= 1.0:
                    self._tokens[host] -= 1.0
                    return

                # Calculate wait time
                tokens_needed = 1.0 - self._tokens[host]
                wait_time = tokens_needed * (60.0 / self.config.per_host_requests_per_minute)

            # Add jitter and wait
            jitter = random.uniform(0, self.config.base_delay_seconds)
            time.sleep(wait_time + jitter)

    def get_stats(self, host: str) -> dict:
        """
        Get rate limiter stats for a host.

        Args:
            host: Target host

        Returns:
            Dict with tokens, backoff_count, etc.
        """
        with self._lock:
            return {
                "host": host,
                "tokens": self._tokens.get(host, self.config.per_host_requests_per_minute),
                "backoff_count": self._backoff_count.get(host, 0),
                "backoff_until": self._backoff_until.get(host, 0),
            }


class NoOpRateLimiter:
    """
    No-op rate limiter for testing.

    Implements the same interface but doesn't actually limit.
    """

    def acquire(self, host: str) -> None:
        """No-op acquire."""

    def release(self, host: str) -> None:
        """No-op release."""

    def backoff(self, host: str) -> None:
        """No-op backoff."""

    def reset_backoff(self, host: str) -> None:
        """No-op reset."""
