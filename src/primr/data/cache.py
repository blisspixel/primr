"""
SQLite-based smart cache for scraped content.

This module provides:
- Persistent SQLite cache with TTL support
- Cache statistics and monitoring
- Automatic cleanup of expired entries
- Thread-safe operations

Usage:
    cache = ContentCache()
    cache.set("https://example.com", "Page content")
    content = cache.get("https://example.com")
"""

import hashlib
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from primr.config.config import PROJECT_ROOT
from primr.utils.logging_config import get_logger

logger = get_logger("cache")


@dataclass
class CacheConfig:
    """Configuration for the content cache."""
    db_path: str = str(Path(PROJECT_ROOT) / "logs" / "cache.db")
    default_ttl_hours: int = 24
    max_entries: int = 10000
    cleanup_interval_hours: int = 1
    compression_threshold: int = 10000  # Compress content larger than this


@dataclass
class CacheEntry:
    """A single cache entry."""
    url: str
    content: str
    tier: str | None
    created_at: datetime
    expires_at: datetime
    size: int
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if entry is expired."""
        return datetime.now() > self.expires_at

    @property
    def age_hours(self) -> float:
        """Get age in hours."""
        return (datetime.now() - self.created_at).total_seconds() / 3600


@dataclass
class CacheStats:
    """Cache statistics."""
    total_entries: int
    total_size_bytes: int
    hit_count: int
    miss_count: int
    expired_count: int
    oldest_entry: datetime | None
    newest_entry: datetime | None

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate."""
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0


class ContentCache:
    """
    SQLite-based content cache with TTL support.

    Features:
    - Persistent storage across sessions
    - Automatic TTL-based expiration
    - Hit/miss statistics
    - Thread-safe operations

    Example:
        cache = ContentCache()

        # Store content
        cache.set("https://example.com", "Page content", tier="requests")

        # Retrieve content
        content = cache.get("https://example.com")

        # Check stats
        stats = cache.get_stats()
        print(f"Hit rate: {stats.hit_rate:.1%}")
    """

    def __init__(self, config: CacheConfig | None = None):
        """
        Initialize the cache.

        Args:
            config: Optional configuration override
        """
        self._config = config or CacheConfig()
        self._lock = threading.Lock()
        self._hit_count = 0
        self._miss_count = 0
        self._last_cleanup = time.time()

        # Ensure directory exists
        Path(self._config.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

        logger.debug(f"ContentCache initialized: {self._config.db_path}")

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tier TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_url ON cache(url)
            """)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(
            self._config.db_path,
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _get_key(self, url: str) -> str:
        """Generate cache key from URL."""
        return hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()

    def get(self, url: str) -> str | None:
        """
        Get cached content for a URL.

        Args:
            url: URL to look up

        Returns:
            Cached content or None if not found/expired
        """
        key = self._get_key(url)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT content, expires_at FROM cache WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()

                if row is None:
                    self._miss_count += 1
                    return None

                # Check expiration
                expires_at = datetime.fromisoformat(row["expires_at"])
                if datetime.now() > expires_at:
                    self._miss_count += 1
                    # Delete expired entry
                    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                    conn.commit()
                    return None

                # Update hit count
                conn.execute(
                    "UPDATE cache SET hit_count = hit_count + 1 WHERE key = ?",
                    (key,)
                )
                conn.commit()

                self._hit_count += 1
                return str(row["content"])

    def set(
        self,
        url: str,
        content: str,
        tier: str | None = None,
        ttl_hours: int | None = None
    ) -> None:
        """
        Store content in cache.

        Args:
            url: URL as cache key
            content: Content to cache
            tier: Scraping tier that produced this content
            ttl_hours: Time-to-live in hours (uses default if not specified)
        """
        key = self._get_key(url)
        ttl = ttl_hours or self._config.default_ttl_hours

        now = datetime.now()
        expires_at = now + timedelta(hours=ttl)

        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO cache
                    (key, url, content, tier, created_at, expires_at, size, hit_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    key,
                    url,
                    content,
                    tier,
                    now.isoformat(),
                    expires_at.isoformat(),
                    len(content)
                ))
                conn.commit()

        # Trigger cleanup if needed
        self._maybe_cleanup()

    def delete(self, url: str) -> bool:
        """
        Delete a cache entry.

        Args:
            url: URL to delete

        Returns:
            True if entry was deleted
        """
        key = self._get_key(url)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM cache WHERE key = ?",
                    (key,)
                )
                conn.commit()
                return bool(cursor.rowcount > 0)

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries deleted
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("DELETE FROM cache")
                conn.commit()
                count: int = cursor.rowcount or 0

        self._hit_count = 0
        self._miss_count = 0
        logger.info(f"Cache cleared: {count} entries deleted")
        return count

    def cleanup_expired(self) -> int:
        """
        Remove expired entries.

        Returns:
            Number of entries removed
        """
        now = datetime.now().isoformat()

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM cache WHERE expires_at < ?",
                    (now,)
                )
                conn.commit()
                count: int = cursor.rowcount or 0

        if count > 0:
            logger.debug(f"Cleaned up {count} expired cache entries")

        return count

    def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed."""
        now = time.time()
        interval = self._config.cleanup_interval_hours * 3600

        if now - self._last_cleanup > interval:
            self._last_cleanup = now
            self.cleanup_expired()
            self._enforce_max_entries()

    def _enforce_max_entries(self) -> None:
        """Remove oldest entries if over max."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM cache")
                count = cursor.fetchone()[0]

                if count > self._config.max_entries:
                    # Delete oldest entries
                    to_delete = count - self._config.max_entries
                    conn.execute("""
                        DELETE FROM cache WHERE key IN (
                            SELECT key FROM cache
                            ORDER BY created_at ASC
                            LIMIT ?
                        )
                    """, (to_delete,))
                    conn.commit()
                    logger.debug(f"Removed {to_delete} oldest cache entries")

    def get_stats(self) -> CacheStats:
        """
        Get cache statistics.

        Returns:
            CacheStats object with current statistics
        """
        with self._lock:
            with self._get_connection() as conn:
                # Total entries and size
                cursor = conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(size), 0) FROM cache"
                )
                row = cursor.fetchone()
                total_entries = row[0]
                total_size = row[1]

                # Expired count
                now = datetime.now().isoformat()
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM cache WHERE expires_at < ?",
                    (now,)
                )
                expired_count = cursor.fetchone()[0]

                # Date range
                cursor = conn.execute(
                    "SELECT MIN(created_at), MAX(created_at) FROM cache"
                )
                row = cursor.fetchone()
                oldest = datetime.fromisoformat(row[0]) if row[0] else None
                newest = datetime.fromisoformat(row[1]) if row[1] else None

        return CacheStats(
            total_entries=total_entries,
            total_size_bytes=total_size,
            hit_count=self._hit_count,
            miss_count=self._miss_count,
            expired_count=expired_count,
            oldest_entry=oldest,
            newest_entry=newest
        )

    def get_entry(self, url: str) -> CacheEntry | None:
        """
        Get full cache entry details.

        Args:
            url: URL to look up

        Returns:
            CacheEntry or None if not found
        """
        key = self._get_key(url)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM cache WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()

                if row is None:
                    return None

                return CacheEntry(
                    url=row["url"],
                    content=row["content"],
                    tier=row["tier"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    expires_at=datetime.fromisoformat(row["expires_at"]),
                    size=row["size"],
                    hit_count=row["hit_count"]
                )

    def warm(self, urls: list[str], scrape_function: Callable[[str], tuple[str | None, str]]) -> int:
        """
        Warm the cache by pre-fetching URLs.

        Args:
            urls: URLs to pre-fetch
            scrape_function: Function to scrape URLs

        Returns:
            Number of URLs successfully cached
        """
        cached = 0
        for url in urls:
            if self.get(url) is None:
                try:
                    content, tier = scrape_function(url)
                    if content:
                        self.set(url, content, tier=tier)
                        cached += 1
                except Exception as e:
                    logger.warning(f"Failed to warm cache for {url}: {e}")

        logger.info(f"Cache warmed: {cached}/{len(urls)} URLs")
        return cached

    def get_urls_by_domain(self, domain: str) -> list[str]:
        """
        Get all cached URLs for a domain.

        Args:
            domain: Domain to search for

        Returns:
            List of cached URLs
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT url FROM cache WHERE url LIKE ?",
                    (f"%{domain}%",)
                )
                return [row["url"] for row in cursor.fetchall()]

    def invalidate_domain(self, domain: str) -> int:
        """
        Invalidate all cache entries for a domain.

        Args:
            domain: Domain to invalidate

        Returns:
            Number of entries invalidated
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM cache WHERE url LIKE ?",
                    (f"%{domain}%",)
                )
                conn.commit()
                count: int = cursor.rowcount or 0

        if count > 0:
            logger.info(f"Invalidated {count} cache entries for {domain}")

        return count


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_cache: ContentCache | None = None
_cache_lock = threading.Lock()


def get_cache() -> ContentCache:
    """
    Get the global cache instance.

    Returns:
        ContentCache instance
    """
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = ContentCache()
    return _cache


def reset_cache() -> None:
    """Reset the global cache (useful for testing)."""
    global _cache
    with _cache_lock:
        _cache = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def cache_get(url: str) -> str | None:
    """Get cached content for a URL."""
    return get_cache().get(url)


def cache_set(
    url: str,
    content: str,
    tier: str | None = None,
    ttl_hours: int | None = None
) -> None:
    """Store content in cache."""
    get_cache().set(url, content, tier=tier, ttl_hours=ttl_hours)


def cache_delete(url: str) -> bool:
    """Delete a cache entry."""
    return get_cache().delete(url)


def cache_clear() -> int:
    """Clear all cache entries."""
    return get_cache().clear()


def cache_stats() -> CacheStats:
    """Get cache statistics."""
    return get_cache().get_stats()
