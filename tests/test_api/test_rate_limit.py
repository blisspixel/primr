"""
Tests for the API rate limiting module.
"""

import pytest
import time

from primr.api.rate_limit import (
    RateLimiter,
    RateLimitConfig,
    TokenBucket,
    get_rate_limiter,
    reset_rate_limiter,
    check_rate_limit,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture
def limiter():
    """Create a fresh rate limiter."""
    return RateLimiter()


@pytest.fixture
def fast_limiter():
    """Create a rate limiter with fast refill for testing."""
    config = RateLimitConfig(requests_per_hour=10)
    return RateLimiter(config)


# =============================================================================
# TOKEN BUCKET TESTS
# =============================================================================

class TestTokenBucket:
    """Tests for TokenBucket class."""
    
    def test_initial_tokens(self):
        """Test initial token count."""
        bucket = TokenBucket(capacity=100, tokens=100)
        assert bucket.tokens == 100
    
    def test_consume_success(self):
        """Test successful token consumption."""
        bucket = TokenBucket(capacity=100, tokens=100)
        assert bucket.consume(1) is True
        assert bucket.tokens == 99
    
    def test_consume_multiple(self):
        """Test consuming multiple tokens."""
        bucket = TokenBucket(capacity=100, tokens=100)
        assert bucket.consume(10) is True
        assert bucket.tokens == 90
    
    def test_consume_insufficient(self):
        """Test consumption with insufficient tokens."""
        bucket = TokenBucket(capacity=100, tokens=5)
        assert bucket.consume(10) is False
        assert bucket.tokens == 5  # Unchanged
    
    def test_time_until_available(self):
        """Test time calculation."""
        bucket = TokenBucket(capacity=100, tokens=0, refill_rate=1.0)
        
        wait_time = bucket.time_until_available(5)
        assert wait_time == pytest.approx(5.0, rel=0.1)
    
    def test_time_until_available_has_tokens(self):
        """Test time when tokens available."""
        bucket = TokenBucket(capacity=100, tokens=10)
        
        wait_time = bucket.time_until_available(5)
        assert wait_time == 0.0


# =============================================================================
# RATE LIMITER TESTS
# =============================================================================

class TestRateLimiter:
    """Tests for RateLimiter class."""
    
    def test_allow_initial(self, limiter):
        """Test initial requests are allowed."""
        assert limiter.allow("user-1") is True
    
    def test_allow_multiple(self, limiter):
        """Test multiple requests are allowed."""
        for _ in range(10):
            assert limiter.allow("user-1") is True
    
    def test_different_keys_independent(self, limiter):
        """Test different keys have independent limits."""
        for _ in range(50):
            limiter.allow("user-1")
        
        # user-2 should still have full quota
        assert limiter.allow("user-2") is True
    
    def test_get_remaining(self, limiter):
        """Test getting remaining requests."""
        initial = limiter.get_remaining("user-1")
        
        limiter.allow("user-1")
        limiter.allow("user-1")
        
        remaining = limiter.get_remaining("user-1")
        assert remaining == initial - 2
    
    def test_reset_key(self, limiter):
        """Test resetting a key."""
        for _ in range(50):
            limiter.allow("user-1")
        
        before = limiter.get_remaining("user-1")
        limiter.reset("user-1")
        after = limiter.get_remaining("user-1")
        
        assert after > before
    
    def test_set_custom_limit(self, limiter):
        """Test setting custom limit."""
        limiter.set_limit("premium-user", 1000)
        
        remaining = limiter.get_remaining("premium-user")
        assert remaining == 1000
    
    def test_retry_after(self, fast_limiter):
        """Test retry after calculation."""
        # Exhaust tokens
        for _ in range(15):
            fast_limiter.allow("user-1")
        
        retry = fast_limiter.retry_after("user-1")
        assert retry >= 0


# =============================================================================
# RATE LIMIT CONFIG TESTS
# =============================================================================

class TestRateLimitConfig:
    """Tests for RateLimitConfig."""
    
    def test_default_values(self):
        """Test default configuration."""
        config = RateLimitConfig()
        assert config.requests_per_hour == 100
        assert config.requests_per_minute == 20
        assert config.burst_size == 10
    
    def test_custom_values(self):
        """Test custom configuration."""
        config = RateLimitConfig(
            requests_per_hour=500,
            requests_per_minute=50,
        )
        assert config.requests_per_hour == 500
        assert config.requests_per_minute == 50


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton access."""
    
    def test_get_limiter_returns_same(self):
        """Test get_rate_limiter returns same instance."""
        l1 = get_rate_limiter()
        l2 = get_rate_limiter()
        assert l1 is l2
    
    def test_reset_limiter(self):
        """Test reset creates new instance."""
        l1 = get_rate_limiter()
        reset_rate_limiter()
        l2 = get_rate_limiter()
        assert l1 is not l2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_check_rate_limit_allowed(self):
        """Test check_rate_limit when allowed."""
        allowed, retry_after = check_rate_limit("user-1")
        
        assert allowed is True
        assert retry_after == 0.0
    
    def test_check_rate_limit_returns_tuple(self):
        """Test check_rate_limit returns tuple."""
        result = check_rate_limit("user-1")
        
        assert isinstance(result, tuple)
        assert len(result) == 2


# =============================================================================
# THREAD SAFETY TESTS
# =============================================================================

class TestThreadSafety:
    """Tests for thread safety."""
    
    def test_concurrent_requests(self, limiter):
        """Test concurrent rate limit checks."""
        import threading
        
        results = []
        
        def make_requests():
            for _ in range(20):
                results.append(limiter.allow("shared-user"))
        
        threads = [threading.Thread(target=make_requests) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All should complete without error
        assert len(results) == 100
