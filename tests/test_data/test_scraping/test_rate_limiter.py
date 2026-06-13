"""Tests for rate limiter."""

import threading
import time

import pytest

from primr.data.scraping.config import RateLimitConfig
from primr.data.scraping.rate_limiter import NoOpRateLimiter, RateLimiter


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
        """A 3rd acquire blocks until one of the 2 held slots is released.

        Synchronized with a Barrier instead of sleeps so it is deterministic on
        slow/contended CI runners (the previous sleep(0.05) raced: the 3rd
        thread could start before both holders had acquired).
        """
        config = RateLimitConfig(
            per_host_concurrency=2,
            per_host_requests_per_minute=1000,  # High rate to not interfere
        )
        limiter = RateLimiter(config)

        both_acquired = threading.Barrier(3)  # 2 holders + main
        release_holders = threading.Event()
        blocked = threading.Event()

        def acquire_and_hold():
            limiter.acquire("example.com")
            both_acquired.wait(timeout=5)  # signal acquired; rendezvous with main
            release_holders.wait(timeout=5)  # hold the slot until told to release
            limiter.release("example.com")

        holders = [threading.Thread(target=acquire_and_hold) for _ in range(2)]
        for t in holders:
            t.start()
        # Both slots are provably held once the barrier trips - no sleep race.
        both_acquired.wait(timeout=5)

        def try_acquire():
            start = time.time()
            limiter.acquire("example.com")  # must block until a holder releases
            if time.time() - start > 0.1:
                blocked.set()
            limiter.release("example.com")

        t3 = threading.Thread(target=try_acquire)
        t3.start()
        time.sleep(0.2)  # t3 is blocked here: both slots are still held
        release_holders.set()  # free the slots

        for t in holders:
            t.join(timeout=5)
        t3.join(timeout=5)

        assert blocked.is_set(), "Third acquire should have blocked until a slot freed"

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

    @pytest.mark.timing
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

    @pytest.mark.timing
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
