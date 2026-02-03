"""
Rate Limiter - Per-API-key rate limiting for the control plane.

This module provides rate limiting to protect the control plane from abuse:
- Token bucket algorithm for smooth rate limiting
- Per-API-key limits
- Configurable rates and burst sizes
- Thread-safe implementation

Requirements: 9.5
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_second: float = 10.0  # Sustained rate
    burst_size: int = 20  # Maximum burst
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "requests_per_second": self.requests_per_second,
            "burst_size": self.burst_size,
        }


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    remaining: int  # Remaining tokens
    reset_after: float  # Seconds until bucket refills
    retry_after: float | None = None  # Seconds to wait if not allowed
    
    def to_dict(self) -> dict[str, Any]:
        result = {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "reset_after": self.reset_after,
        }
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        return result


class TokenBucket:
    """
    Token bucket rate limiter.
    
    Implements the token bucket algorithm:
    - Tokens are added at a fixed rate (requests_per_second)
    - Bucket has a maximum capacity (burst_size)
    - Each request consumes one token
    - If no tokens available, request is rejected
    """
    
    def __init__(self, config: RateLimitConfig) -> None:
        """
        Initialize token bucket.
        
        Args:
            config: Rate limit configuration
        """
        self.config = config
        self.tokens = float(config.burst_size)
        self.last_update = time.monotonic()
        self._lock = threading.Lock()
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(
            self.config.burst_size,
            self.tokens + elapsed * self.config.requests_per_second,
        )
        self.last_update = now
    
    def try_acquire(self, tokens: int = 1) -> RateLimitResult:
        """
        Try to acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire (default 1)
            
        Returns:
            RateLimitResult indicating if request is allowed
        """
        with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return RateLimitResult(
                    allowed=True,
                    remaining=int(self.tokens),
                    reset_after=self.config.burst_size / self.config.requests_per_second,
                )
            else:
                # Calculate how long until enough tokens are available
                tokens_needed = tokens - self.tokens
                retry_after = tokens_needed / self.config.requests_per_second
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_after=self.config.burst_size / self.config.requests_per_second,
                    retry_after=retry_after,
                )
    
    def get_remaining(self) -> int:
        """Get remaining tokens without consuming any."""
        with self._lock:
            self._refill()
            return int(self.tokens)


class RateLimiter:
    """
    Per-API-key rate limiter.
    
    Maintains separate token buckets for each API key.
    """
    
    def __init__(self, default_config: RateLimitConfig | None = None) -> None:
        """
        Initialize rate limiter.
        
        Args:
            default_config: Default rate limit config for all API keys
        """
        self.default_config = default_config or RateLimitConfig()
        self._buckets: dict[str, TokenBucket] = {}
        self._configs: dict[str, RateLimitConfig] = {}
        self._lock = threading.Lock()
    
    def set_config(self, api_key_hash: str, config: RateLimitConfig) -> None:
        """
        Set rate limit config for an API key.
        
        Args:
            api_key_hash: Hashed API key
            config: Rate limit configuration
        """
        with self._lock:
            self._configs[api_key_hash] = config
            # Reset bucket with new config
            if api_key_hash in self._buckets:
                del self._buckets[api_key_hash]
    
    def get_config(self, api_key_hash: str) -> RateLimitConfig:
        """Get rate limit config for an API key."""
        with self._lock:
            return self._configs.get(api_key_hash, self.default_config)
    
    def _get_bucket(self, api_key_hash: str) -> TokenBucket:
        """Get or create token bucket for an API key."""
        with self._lock:
            if api_key_hash not in self._buckets:
                config = self._configs.get(api_key_hash, self.default_config)
                self._buckets[api_key_hash] = TokenBucket(config)
            return self._buckets[api_key_hash]
    
    def check(self, api_key_hash: str, tokens: int = 1) -> RateLimitResult:
        """
        Check rate limit for an API key.
        
        Args:
            api_key_hash: Hashed API key
            tokens: Number of tokens to consume (default 1)
            
        Returns:
            RateLimitResult indicating if request is allowed
        """
        bucket = self._get_bucket(api_key_hash)
        return bucket.try_acquire(tokens)
    
    def get_remaining(self, api_key_hash: str) -> int:
        """Get remaining tokens for an API key."""
        bucket = self._get_bucket(api_key_hash)
        return bucket.get_remaining()
    
    def cleanup_inactive(self, max_age_seconds: float = 3600) -> int:
        """
        Clean up inactive buckets to free memory.
        
        Args:
            max_age_seconds: Remove buckets not used for this long
            
        Returns:
            Number of buckets removed
        """
        now = time.monotonic()
        removed = 0
        
        with self._lock:
            to_remove = []
            for key, bucket in self._buckets.items():
                if now - bucket.last_update > max_age_seconds:
                    to_remove.append(key)
            
            for key in to_remove:
                del self._buckets[key]
                removed += 1
        
        return removed


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, message: str, result: RateLimitResult) -> None:
        super().__init__(message)
        self.result = result
