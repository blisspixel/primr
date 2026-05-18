"""
Tests for the SQLite-based content cache.

Tests caching, TTL, statistics, and cleanup.
"""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import threading

import pytest

from primr.data.cache import (
    CacheConfig,
    CacheEntry,
    CacheStats,
    ContentCache,
    cache_clear,
    cache_delete,
    cache_get,
    cache_set,
    cache_stats,
    get_cache,
    reset_cache,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def temp_cache():
    """Create a cache with a temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = CacheConfig(
            db_path=str(Path(tmpdir) / "test_cache.db"), default_ttl_hours=1, max_entries=100
        )
        cache = ContentCache(config=config)
        yield cache


@pytest.fixture
def populated_cache(temp_cache):
    """Create a cache with some entries."""
    temp_cache.set("https://example1.com", "Content 1", tier="requests")
    temp_cache.set("https://example2.com", "Content 2", tier="httpx")
    temp_cache.set("https://example3.com", "Content 3", tier="playwright")
    return temp_cache


# =============================================================================
# CACHE CONFIG TESTS
# =============================================================================


class TestCacheConfig:
    """Tests for CacheConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CacheConfig()

        assert config.default_ttl_hours == 24
        assert config.max_entries == 10000
        assert config.cleanup_interval_hours == 1

    def test_custom_config(self):
        """Test custom configuration."""
        config = CacheConfig(default_ttl_hours=48, max_entries=5000)

        assert config.default_ttl_hours == 48
        assert config.max_entries == 5000


# =============================================================================
# CACHE ENTRY TESTS
# =============================================================================


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_is_expired_false(self):
        """Test non-expired entry."""
        entry = CacheEntry(
            url="https://example.com",
            content="Content",
            tier="requests",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            size=100,
        )

        assert not entry.is_expired

    def test_is_expired_true(self):
        """Test expired entry."""
        entry = CacheEntry(
            url="https://example.com",
            content="Content",
            tier="requests",
            created_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() - timedelta(hours=1),
            size=100,
        )

        assert entry.is_expired

    def test_age_hours(self):
        """Test age calculation."""
        entry = CacheEntry(
            url="https://example.com",
            content="Content",
            tier="requests",
            created_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() + timedelta(hours=1),
            size=100,
        )

        assert 1.9 < entry.age_hours < 2.1


# =============================================================================
# CACHE STATS TESTS
# =============================================================================


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_hit_rate_with_hits(self):
        """Test hit rate calculation."""
        stats = CacheStats(
            total_entries=10,
            total_size_bytes=1000,
            hit_count=80,
            miss_count=20,
            expired_count=0,
            oldest_entry=None,
            newest_entry=None,
        )

        assert stats.hit_rate == 0.8

    def test_hit_rate_no_requests(self):
        """Test hit rate with no requests."""
        stats = CacheStats(
            total_entries=0,
            total_size_bytes=0,
            hit_count=0,
            miss_count=0,
            expired_count=0,
            oldest_entry=None,
            newest_entry=None,
        )

        assert stats.hit_rate == 0.0


# =============================================================================
# CONTENT CACHE TESTS
# =============================================================================


class TestContentCache:
    """Tests for ContentCache class."""

    def test_initialization(self, temp_cache):
        """Test cache initialization."""
        assert temp_cache is not None

    def test_set_and_get(self, temp_cache):
        """Test basic set and get."""
        temp_cache.set("https://example.com", "Test content")
        content = temp_cache.get("https://example.com")

        assert content == "Test content"

    def test_get_nonexistent(self, temp_cache):
        """Test getting nonexistent entry."""
        content = temp_cache.get("https://nonexistent.com")

        assert content is None

    def test_set_with_tier(self, temp_cache):
        """Test setting with tier information."""
        temp_cache.set("https://example.com", "Content", tier="playwright")
        entry = temp_cache.get_entry("https://example.com")

        assert entry.tier == "playwright"

    def test_set_with_custom_ttl(self, temp_cache):
        """Test setting with custom TTL."""
        temp_cache.set("https://example.com", "Content", ttl_hours=48)
        entry = temp_cache.get_entry("https://example.com")

        # Should expire in ~48 hours
        hours_until_expiry = (entry.expires_at - datetime.now()).total_seconds() / 3600
        assert 47 < hours_until_expiry < 49

    def test_overwrite_existing(self, temp_cache):
        """Test overwriting existing entry."""
        temp_cache.set("https://example.com", "Original content")
        temp_cache.set("https://example.com", "New content")

        content = temp_cache.get("https://example.com")
        assert content == "New content"

    def test_delete(self, temp_cache):
        """Test deleting entry."""
        temp_cache.set("https://example.com", "Content")

        result = temp_cache.delete("https://example.com")

        assert result is True
        assert temp_cache.get("https://example.com") is None

    def test_delete_nonexistent(self, temp_cache):
        """Test deleting nonexistent entry."""
        result = temp_cache.delete("https://nonexistent.com")

        assert result is False

    def test_clear(self, populated_cache):
        """Test clearing all entries."""
        count = populated_cache.clear()

        assert count == 3
        assert populated_cache.get("https://example1.com") is None

    def test_expired_entry_returns_none(self, temp_cache):
        """Test that expired entries return None."""
        # Set with very short TTL
        CacheConfig(
            db_path=temp_cache._config.db_path,
            default_ttl_hours=0,  # Immediate expiration
        )

        # Manually insert expired entry
        with temp_cache._get_connection() as conn:
            past = (datetime.now() - timedelta(hours=1)).isoformat()
            conn.execute(
                """
                INSERT INTO cache (key, url, content, tier, created_at, expires_at, size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    temp_cache._get_key("https://expired.com"),
                    "https://expired.com",
                    "Expired content",
                    "requests",
                    past,
                    past,
                    100,
                ),
            )
            conn.commit()

        content = temp_cache.get("https://expired.com")
        assert content is None

    def test_cleanup_expired(self, temp_cache):
        """Test cleanup of expired entries."""
        # Insert expired entry
        with temp_cache._get_connection() as conn:
            past = (datetime.now() - timedelta(hours=1)).isoformat()
            conn.execute(
                """
                INSERT INTO cache (key, url, content, tier, created_at, expires_at, size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    "expired_key",
                    "https://expired.com",
                    "Expired content",
                    "requests",
                    past,
                    past,
                    100,
                ),
            )
            conn.commit()

        # Add valid entry
        temp_cache.set("https://valid.com", "Valid content")

        # Cleanup
        count = temp_cache.cleanup_expired()

        assert count == 1
        assert temp_cache.get("https://valid.com") == "Valid content"


# =============================================================================
# STATISTICS TESTS
# =============================================================================


class TestCacheStatistics:
    """Tests for cache statistics."""

    def test_stats_empty_cache(self, temp_cache):
        """Test stats on empty cache."""
        stats = temp_cache.get_stats()

        assert stats.total_entries == 0
        assert stats.total_size_bytes == 0
        assert stats.hit_count == 0
        assert stats.miss_count == 0

    def test_stats_with_entries(self, populated_cache):
        """Test stats with entries."""
        stats = populated_cache.get_stats()

        assert stats.total_entries == 3
        assert stats.total_size_bytes > 0

    def test_hit_count_tracking(self, temp_cache):
        """Test hit count tracking."""
        temp_cache.set("https://example.com", "Content")

        # Generate hits
        temp_cache.get("https://example.com")
        temp_cache.get("https://example.com")
        temp_cache.get("https://example.com")

        stats = temp_cache.get_stats()
        assert stats.hit_count == 3

    def test_miss_count_tracking(self, temp_cache):
        """Test miss count tracking."""
        # Generate misses
        temp_cache.get("https://nonexistent1.com")
        temp_cache.get("https://nonexistent2.com")

        stats = temp_cache.get_stats()
        assert stats.miss_count == 2

    def test_entry_hit_count(self, temp_cache):
        """Test per-entry hit count."""
        temp_cache.set("https://example.com", "Content")

        # Generate hits
        temp_cache.get("https://example.com")
        temp_cache.get("https://example.com")

        entry = temp_cache.get_entry("https://example.com")
        assert entry.hit_count == 2


# =============================================================================
# DOMAIN OPERATIONS TESTS
# =============================================================================


class TestDomainOperations:
    """Tests for domain-based operations."""

    def test_get_urls_by_domain(self, temp_cache):
        """Test getting URLs by domain."""
        temp_cache.set("https://example.com/page1", "Content 1")
        temp_cache.set("https://example.com/page2", "Content 2")
        temp_cache.set("https://other.com/page", "Content 3")

        urls = temp_cache.get_urls_by_domain("example.com")

        assert len(urls) == 2
        assert all("example.com" in url for url in urls)

    def test_invalidate_domain(self, temp_cache):
        """Test invalidating domain."""
        temp_cache.set("https://example.com/page1", "Content 1")
        temp_cache.set("https://example.com/page2", "Content 2")
        temp_cache.set("https://other.com/page", "Content 3")

        count = temp_cache.invalidate_domain("example.com")

        assert count == 2
        assert temp_cache.get("https://example.com/page1") is None
        assert temp_cache.get("https://other.com/page") == "Content 3"


# =============================================================================
# CACHE WARMING TESTS
# =============================================================================


class TestCacheWarming:
    """Tests for cache warming."""

    def test_warm_cache(self, temp_cache):
        """Test warming cache with URLs."""

        def mock_scrape(url):
            return f"Content from {url}", "mock"

        urls = ["https://example1.com", "https://example2.com"]
        count = temp_cache.warm(urls, mock_scrape)

        assert count == 2
        assert temp_cache.get("https://example1.com") is not None

    def test_warm_skips_existing(self, temp_cache):
        """Test that warming skips existing entries."""
        temp_cache.set("https://existing.com", "Existing content")

        scrape_calls = []

        def mock_scrape(url):
            scrape_calls.append(url)
            return f"Content from {url}", "mock"

        urls = ["https://existing.com", "https://new.com"]
        temp_cache.warm(urls, mock_scrape)

        # Should only scrape the new URL
        assert len(scrape_calls) == 1
        assert "https://new.com" in scrape_calls

    def test_warm_handles_failures(self, temp_cache):
        """Test that warming handles scrape failures."""

        def mock_scrape(url):
            if "fail" in url:
                raise Exception("Scrape failed")
            return f"Content from {url}", "mock"

        urls = ["https://good.com", "https://fail.com"]
        count = temp_cache.warm(urls, mock_scrape)

        assert count == 1
        assert temp_cache.get("https://good.com") is not None


# =============================================================================
# THREAD SAFETY TESTS
# =============================================================================


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_writes(self, temp_cache):
        """Test concurrent write operations."""
        errors = []

        def write_entries(start, count):
            try:
                for i in range(count):
                    temp_cache.set(f"https://example{start + i}.com", f"Content {start + i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_entries, args=(i * 100, 100)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        # Verify entries
        stats = temp_cache.get_stats()
        assert stats.total_entries == 500

    def test_concurrent_reads(self, populated_cache):
        """Test concurrent read operations."""
        errors = []
        results = []

        def read_entries(count):
            try:
                for _ in range(count):
                    content = populated_cache.get("https://example1.com")
                    results.append(content)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_entries, args=(100,)) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r == "Content 1" for r in results)


# =============================================================================
# SINGLETON TESTS
# =============================================================================


class TestSingleton:
    """Tests for singleton access."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_cache()

    def teardown_method(self):
        """Clean up after each test."""
        reset_cache()

    def test_get_cache_singleton(self):
        """Test that get_cache returns singleton."""
        cache1 = get_cache()
        cache2 = get_cache()

        assert cache1 is cache2

    def test_reset_cache(self):
        """Test resetting the singleton."""
        cache1 = get_cache()
        reset_cache()
        cache2 = get_cache()

        assert cache1 is not cache2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_cache()

    def teardown_method(self):
        """Clean up after each test."""
        reset_cache()

    def test_cache_set_and_get(self):
        """Test cache_set and cache_get."""
        cache_set("https://example.com", "Content")
        content = cache_get("https://example.com")

        assert content == "Content"

    def test_cache_delete(self):
        """Test cache_delete."""
        cache_set("https://example.com", "Content")
        result = cache_delete("https://example.com")

        assert result is True
        assert cache_get("https://example.com") is None

    def test_cache_clear(self):
        """Test cache_clear."""
        cache_set("https://example1.com", "Content 1")
        cache_set("https://example2.com", "Content 2")

        count = cache_clear()

        assert count == 2

    def test_cache_stats(self):
        """Test cache_stats."""
        cache_set("https://example.com", "Content")
        cache_get("https://example.com")

        stats = cache_stats()

        assert stats.total_entries == 1
        assert stats.hit_count == 1
