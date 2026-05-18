"""
Rate limiting for the API service.

This module provides:
- Token bucket rate limiting
- Per-key rate limits
- Configurable limits and windows
"""

import threading
import time
from dataclasses import dataclass, field

from primr.utils.logging_config import get_logger

logger = get_logger("api.rate_limit")


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_hour: int = 100
    requests_per_minute: int = 20
    burst_size: int = 10
    window_seconds: int = 3600


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""

    capacity: float
    tokens: float
    last_update: float = field(default_factory=time.time)
    refill_rate: float = 0.0  # Tokens per second

    def __post_init__(self):
        if self.refill_rate == 0.0:
            # Default: refill to capacity over 1 hour
            self.refill_rate = self.capacity / 3600

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed
        """
        now = time.time()

        # Refill tokens based on time elapsed
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def time_until_available(self, tokens: int = 1) -> float:
        """
        Calculate time until tokens are available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds until available (0 if available now)
        """
        if self.tokens >= tokens:
            return 0.0

        needed = tokens - self.tokens
        return needed / self.refill_rate


class RateLimiter:
    """
    Rate limiter using token bucket algorithm.

    Example:
        limiter = RateLimiter()

        if limiter.allow("user-123"):
            # Process request
            pass
        else:
            # Rate limited
            retry_after = limiter.retry_after("user-123")
    """

    def __init__(self, config: RateLimitConfig | None = None):
        """
        Initialize the rate limiter.

        Args:
            config: Rate limit configuration
        """
        self._config = config or RateLimitConfig()
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        logger.debug(f"RateLimiter initialized: {self._config.requests_per_hour}/hour")

    def allow(self, key: str, tokens: int = 1) -> bool:
        """
        Check if a request is allowed.

        Args:
            key: Identifier (API key, user ID, IP, etc.)
            tokens: Number of tokens to consume

        Returns:
            True if allowed
        """
        with self._lock:
            bucket = self._get_or_create_bucket(key)
            allowed = bucket.consume(tokens)

            if not allowed:
                logger.debug(f"Rate limited: {key}")

            return allowed

    def retry_after(self, key: str, tokens: int = 1) -> float:
        """
        Get seconds until request would be allowed.

        Args:
            key: Identifier
            tokens: Number of tokens needed

        Returns:
            Seconds until allowed
        """
        with self._lock:
            bucket = self._get_or_create_bucket(key)
            return bucket.time_until_available(tokens)

    def get_remaining(self, key: str) -> int:
        """
        Get remaining requests for a key.

        Args:
            key: Identifier

        Returns:
            Number of remaining requests
        """
        with self._lock:
            bucket = self._get_or_create_bucket(key)
            # Refill first
            now = time.time()
            elapsed = now - bucket.last_update
            bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
            bucket.last_update = now
            return int(bucket.tokens)

    def reset(self, key: str) -> None:
        """
        Reset rate limit for a key.

        Args:
            key: Identifier to reset
        """
        with self._lock:
            if key in self._buckets:
                del self._buckets[key]

    def set_limit(self, key: str, requests_per_hour: int) -> None:
        """
        Set custom limit for a key.

        Args:
            key: Identifier
            requests_per_hour: Custom limit
        """
        with self._lock:
            self._buckets[key] = TokenBucket(
                capacity=float(requests_per_hour),
                tokens=float(requests_per_hour),
                refill_rate=requests_per_hour / 3600,
            )

    def _get_or_create_bucket(self, key: str) -> TokenBucket:
        """Get or create a token bucket for a key."""
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                capacity=float(self._config.requests_per_hour),
                tokens=float(self._config.requests_per_hour),
                refill_rate=self._config.requests_per_hour / 3600,
            )
        return self._buckets[key]


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter


def reset_rate_limiter() -> None:
    """Reset the global rate limiter (useful for testing)."""
    global _limiter
    _limiter = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def check_rate_limit(key: str) -> tuple[bool, float]:
    """
    Check rate limit for a key.

    Args:
        key: Identifier

    Returns:
        Tuple of (allowed, retry_after_seconds)
    """
    limiter = get_rate_limiter()
    allowed = limiter.allow(key)
    retry_after = 0.0 if allowed else limiter.retry_after(key)
    return allowed, retry_after
