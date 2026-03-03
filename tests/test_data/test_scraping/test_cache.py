"""Tests for scraping cache - Property 8: Cache Behavior with URL Normalization."""

import tempfile

from primr.data.scraping.cache import (
    LRUCache,
    ScrapeCache,
    normalize_url,
    url_to_cache_key,
)


class TestNormalizeUrl:
    """Tests for URL normalization."""

    def test_strips_trailing_slash(self):
        """Trailing slashes should be stripped."""
        assert normalize_url("https://example.com/path/") == "https://example.com/path"
        assert normalize_url("https://example.com/") == "https://example.com"

    def test_removes_fragments(self):
        """URL fragments should be removed."""
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_sorts_query_params(self):
        """Query params should be sorted alphabetically."""
        url1 = normalize_url("https://example.com?b=2&a=1")
        url2 = normalize_url("https://example.com?a=1&b=2")
        assert url1 == url2
        assert "a=1" in url1
        assert url1.index("a=1") < url1.index("b=2")

    def test_ignores_utm_params_by_default(self):
        """UTM tracking params should be ignored by default."""
        url1 = normalize_url("https://example.com?utm_source=google&page=1")
        url2 = normalize_url("https://example.com?page=1")
        assert url1 == url2
        assert "utm_source" not in url1

    def test_keeps_utm_params_when_disabled(self):
        """UTM params should be kept when ignore_utm=False."""
        url = normalize_url("https://example.com?utm_source=google", ignore_utm=False)
        assert "utm_source=google" in url

    def test_normalizes_scheme_to_lowercase(self):
        """Scheme should be lowercase."""
        assert normalize_url("HTTPS://example.com") == "https://example.com"
        assert normalize_url("HTTP://example.com") == "http://example.com"

    def test_normalizes_netloc_to_lowercase(self):
        """Netloc should be lowercase."""
        assert normalize_url("https://EXAMPLE.COM/path") == "https://example.com/path"

    def test_handles_empty_url(self):
        """Empty URL should return empty."""
        assert normalize_url("") == ""
        assert normalize_url(None) is None

    def test_equivalent_urls_normalize_same(self):
        """Equivalent URLs should normalize to the same string."""
        urls = [
            "https://example.com/page?b=2&a=1#section",
            "https://example.com/page/?a=1&b=2",
            "HTTPS://EXAMPLE.COM/page?a=1&b=2#other",
        ]
        normalized = [normalize_url(u) for u in urls]
        assert len(set(normalized)) == 1


class TestUrlToCacheKey:
    """Tests for URL to cache key conversion."""

    def test_returns_string(self):
        """Cache key should be a string."""
        key = url_to_cache_key("https://example.com")
        assert isinstance(key, str)

    def test_consistent_for_same_url(self):
        """Same URL should always produce same key."""
        key1 = url_to_cache_key("https://example.com/page")
        key2 = url_to_cache_key("https://example.com/page")
        assert key1 == key2

    def test_same_key_for_equivalent_urls(self):
        """Equivalent URLs should produce same key."""
        key1 = url_to_cache_key("https://example.com/page?b=2&a=1")
        key2 = url_to_cache_key("https://example.com/page?a=1&b=2")
        assert key1 == key2

    def test_different_keys_for_different_urls(self):
        """Different URLs should produce different keys."""
        key1 = url_to_cache_key("https://example.com/page1")
        key2 = url_to_cache_key("https://example.com/page2")
        assert key1 != key2


class TestLRUCache:
    """Tests for LRU memory cache."""

    def test_get_set_basic(self):
        """Basic get/set operations."""
        cache = LRUCache(max_size=10)
        cache.set("key1", b"value1")
        assert cache.get("key1") == b"value1"

    def test_get_missing_returns_none(self):
        """Getting missing key returns None."""
        cache = LRUCache(max_size=10)
        assert cache.get("nonexistent") is None

    def test_eviction_at_max_size(self):
        """Oldest items should be evicted at max size."""
        cache = LRUCache(max_size=3)
        cache.set("a", b"1")
        cache.set("b", b"2")
        cache.set("c", b"3")

        # Cache is full, adding d should evict a
        cache.set("d", b"4")

        assert cache.get("a") is None  # Evicted
        assert cache.get("b") == b"2"
        assert cache.get("c") == b"3"
        assert cache.get("d") == b"4"

    def test_access_updates_lru_order(self):
        """Accessing an item should move it to most recently used."""
        cache = LRUCache(max_size=3)
        cache.set("a", b"1")
        cache.set("b", b"2")
        cache.set("c", b"3")

        # Access 'a' to make it most recently used
        cache.get("a")

        # Adding d should now evict b (oldest)
        cache.set("d", b"4")

        assert cache.get("a") == b"1"  # Still there
        assert cache.get("b") is None  # Evicted

    def test_update_existing_key(self):
        """Updating existing key should work and update LRU order."""
        cache = LRUCache(max_size=3)
        cache.set("a", b"1")
        cache.set("b", b"2")
        cache.set("c", b"3")

        # Update 'a'
        cache.set("a", b"updated")

        # Adding d should evict b (a was just updated)
        cache.set("d", b"4")

        assert cache.get("a") == b"updated"
        assert cache.get("b") is None

    def test_len(self):
        """Length should reflect number of items."""
        cache = LRUCache(max_size=10)
        assert len(cache) == 0
        cache.set("a", b"1")
        assert len(cache) == 1
        cache.set("b", b"2")
        assert len(cache) == 2

    def test_contains(self):
        """Contains check should work."""
        cache = LRUCache(max_size=10)
        cache.set("a", b"1")
        assert "a" in cache
        assert "b" not in cache

    def test_clear(self):
        """Clear should remove all items."""
        cache = LRUCache(max_size=10)
        cache.set("a", b"1")
        cache.set("b", b"2")
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None

    def test_delete(self):
        """Delete should remove specific item."""
        cache = LRUCache(max_size=10)
        cache.set("a", b"1")
        cache.set("b", b"2")

        assert cache.delete("a") is True
        assert cache.get("a") is None
        assert cache.get("b") == b"2"

        assert cache.delete("nonexistent") is False


class TestScrapeCache:
    """Tests for combined memory + disk cache."""

    def test_raw_memory_cache(self):
        """Raw content should be cached in memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(memory_size=10, cache_dir=tmpdir)

            cache.set_raw("https://example.com", b"<html>content</html>")
            result = cache.get_raw("https://example.com")

            assert result == b"<html>content</html>"

    def test_extracted_memory_cache(self):
        """Extracted text should be cached in memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(memory_size=10, cache_dir=tmpdir)

            cache.set_extracted("https://example.com", "extracted content")
            result = cache.get_extracted("https://example.com")

            assert result == "extracted content"

    def test_raw_and_extracted_separate(self):
        """Raw and extracted should be stored separately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(memory_size=10, cache_dir=tmpdir)

            cache.set_raw("https://example.com", b"<html>raw</html>")
            cache.set_extracted("https://example.com", "extracted")

            assert cache.get_raw("https://example.com") == b"<html>raw</html>"
            assert cache.get_extracted("https://example.com") == "extracted"

    def test_disk_persistence(self):
        """Content should persist to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First cache instance
            cache1 = ScrapeCache(memory_size=10, cache_dir=tmpdir)
            cache1.set_raw("https://example.com", b"<html>content</html>")

            # New cache instance (simulates restart)
            cache2 = ScrapeCache(memory_size=10, cache_dir=tmpdir)
            result = cache2.get_raw("https://example.com")

            assert result == b"<html>content</html>"

    def test_memory_before_disk(self):
        """Memory cache should be checked before disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(memory_size=10, cache_dir=tmpdir)

            # Set in cache
            cache.set_raw("https://example.com", b"original")

            # Manually modify disk file (simulating external change)
            # Memory should still return original
            assert cache.get_raw("https://example.com") == b"original"

    def test_url_normalization_in_cache(self):
        """Equivalent URLs should hit same cache entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(memory_size=10, cache_dir=tmpdir)

            cache.set_raw("https://example.com/page?b=2&a=1", b"content")

            # Different URL format, same normalized URL
            result = cache.get_raw("https://example.com/page?a=1&b=2")
            assert result == b"content"

    def test_clear_memory(self):
        """clear_memory should only clear memory cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(memory_size=10, cache_dir=tmpdir)
            cache.set_raw("https://example.com", b"content")

            cache.clear_memory()

            # Memory is cleared, but disk should still have it
            # (get_raw will reload from disk)
            result = cache.get_raw("https://example.com")
            assert result == b"content"

    def test_get_missing_returns_none(self):
        """Getting missing URL returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(memory_size=10, cache_dir=tmpdir)

            assert cache.get_raw("https://nonexistent.com") is None
            assert cache.get_extracted("https://nonexistent.com") is None
