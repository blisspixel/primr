"""Tests for rate limiter."""

import pytest
import threading
import time

from primr.data.scraping.config import RateLimitConfig
from primr.data.scraping.rate_limiter import RateLimiter, NoOpRateLimiter


class TestRateLimiter:
    """Tests for RateLimiter."""
    
    def test_acquire_release_basic(self):
        """Basic acquire/release should work."""
        config = RateLimitConfig(
            per_host_concurrency=2,
            per_host_requests_per_minute=60,
        )
        limiter = RateLimiter(config)
        
        # Should not block
        limiter.acquire("example.com")
        limiter.release("example.com")
    
    def test_concurrency_limit(self):
        """Concurrency limit should be enforced."""
        config = RateLimitConfig(
            per_host_concurrency=2,
            per_host_requests_per_minute=1000,  # High rate to not interfere
        )
        limiter = RateLimiter(config)
        
        acquired = []
        blocked = threading.Event()
        
        def acquire_and_hold():
            limiter.acquire("example.com")
            acquired.append(True)
            # Hold for a bit
            time.sleep(0.2)
            limiter.release("example.com")
        
        def try_acquire():
            # This should block until one of the others releases
            start = time.time()
            limiter.acquire("example.com")
            elapsed = time.time() - start
            if elapsed > 0.1:  # Blocked for at least 100ms
                blocked.set()
            limiter.release("example.com")
        
        # Start 2 threads that acquire and hold
        t1 = threading.Thread(target=acquire_and_hold)
        t2 = threading.Thread(target=acquire_and_hold)
        t1.start()
        t2.start()
        
        # Give them time to acquire
        time.sleep(0.05)
        
        # Third thread should block
        t3 = threading.Thread(target=try_acquire)
        t3.start()
        
        t1.join()
        t2.join()
        t3.join()
        
        # Third thread should have been blocked
        assert blocked.is_set(), "Third acquire should have blocked"
    
    def test_backoff_increases_delay(self):
        """Backoff should increase delay."""
        config = RateLimitConfig(
            base_delay_seconds=0.1,
            backoff_multiplier=2.0,
        )
        limiter = RateLimiter(config)
        
        # Apply backoff multiple times
        limiter.backoff("example.com")
        stats1 = limiter.get_stats("example.com")
        
        limiter.backoff("example.com")
        stats2 = limiter.get_stats("example.com")
        
        assert stats2["backoff_count"] > stats1["backoff_count"]
    
    def test_reset_backoff(self):
        """Reset backoff should clear backoff state."""
        config = RateLimitConfig()
        limiter = RateLimiter(config)
        
        limiter.backoff("example.com")
        assert limiter.get_stats("example.com")["backoff_count"] > 0
        
        limiter.reset_backoff("example.com")
        assert limiter.get_stats("example.com")["backoff_count"] == 0
    
    def test_per_host_isolation(self):
        """Different hosts should have independent limits."""
        config = RateLimitConfig(per_host_concurrency=1)
        limiter = RateLimiter(config)
        
        # Acquire for host1
        limiter.acquire("host1.com")
        
        # Should be able to acquire for host2 immediately
        start = time.time()
        limiter.acquire("host2.com")
        elapsed = time.time() - start
        
        assert elapsed < 0.1, "Different hosts should not block each other"
        
        limiter.release("host1.com")
        limiter.release("host2.com")
    
    def test_get_stats(self):
        """get_stats should return host statistics."""
        config = RateLimitConfig()
        limiter = RateLimiter(config)
        
        stats = limiter.get_stats("example.com")
        
        assert "host" in stats
        assert "tokens" in stats
        assert "backoff_count" in stats
        assert stats["host"] == "example.com"

    def test_waiting_for_token_does_not_hold_semaphore(self):
        """Token wait should not occupy concurrency slots."""
        config = RateLimitConfig(
            per_host_concurrency=1,
            per_host_requests_per_minute=60,  # 1 token/sec refill
            base_delay_seconds=0.01,
        )
        limiter = RateLimiter(config)
        host = "example.com"

        # Force the next acquire to wait for token refill.
        limiter._tokens[host] = 0.0
        limiter._last_refill[host] = time.time()
        sem = limiter._get_semaphore(host)

        started = threading.Event()

        def wait_for_token_then_release():
            started.set()
            limiter.acquire(host)
            limiter.release(host)

        thread = threading.Thread(target=wait_for_token_then_release, daemon=True)
        thread.start()
        started.wait(timeout=1)
        time.sleep(0.05)

        # If semaphore is still available, token wait is not holding it.
        acquired = sem.acquire(blocking=False)
        if acquired:
            sem.release()

        thread.join(timeout=2)
        assert acquired is True


class TestNoOpRateLimiter:
    """Tests for NoOpRateLimiter."""
    
    def test_acquire_release_noop(self):
        """NoOp limiter should not block."""
        limiter = NoOpRateLimiter()
        
        # Should complete instantly
        start = time.time()
        for _ in range(100):
            limiter.acquire("example.com")
            limiter.release("example.com")
        elapsed = time.time() - start
        
        assert elapsed < 0.1, "NoOp limiter should not delay"
    
    def test_backoff_noop(self):
        """NoOp limiter backoff should do nothing."""
        limiter = NoOpRateLimiter()
        
        # Should not raise
        limiter.backoff("example.com")
        limiter.reset_backoff("example.com")
