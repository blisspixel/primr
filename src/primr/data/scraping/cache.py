"""
LRU and disk caching with URL normalization.

Caches raw content and extracted text separately to allow re-parsing
without re-scraping.
"""

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger("primr.scraping.cache")

# =============================================================================
# URL Normalization
# =============================================================================


def normalize_url(url: str, ignore_utm: bool = True) -> str:
    """
    Normalize URL for cache key.

    Rules:
    - Strip trailing slash
    - Normalize scheme (prefer https)
    - Remove fragments (#section)
    - Sort query params alphabetically
    - Optionally ignore utm_* params

    Args:
        url: URL to normalize
        ignore_utm: Whether to strip utm_* tracking params

    Returns:
        Normalized URL string
    """
    if not url:
        return url

    parsed = urlparse(url)

    # Normalize scheme (prefer https)
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    if scheme not in ("http", "https"):
        scheme = "https"

    # Normalize netloc (lowercase)
    netloc = parsed.netloc.lower()

    # Strip trailing slash from path
    path = parsed.path.rstrip("/")
    if not path:
        path = ""

    # Sort query params and optionally remove utm_*
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    if ignore_utm:
        query_params = {k: v for k, v in query_params.items() if not k.lower().startswith("utm_")}
    # Sort params and flatten single-value lists
    sorted_params = sorted((k, v[0] if len(v) == 1 else v) for k, v in query_params.items())
    query = urlencode(sorted_params, doseq=True) if sorted_params else ""

    # Remove fragment
    fragment = ""

    # Reconstruct URL
    normalized = urlunparse((scheme, netloc, path, "", query, fragment))
    return normalized


def url_to_cache_key(url: str) -> str:
    """Convert URL to a safe cache key (hash)."""
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


# =============================================================================
# LRU Cache (Memory)
# =============================================================================


class LRUCache:
    """
    Thread-safe LRU cache with configurable max size.

    Prevents unbounded memory growth during long scraping sessions.
    """

    def __init__(self, max_size: int = 100):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        """Get item from cache, moving it to end (most recently used)."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def set(self, key: str, value: bytes) -> None:
        """Set item in cache, evicting oldest if at capacity."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
            else:
                if len(self._cache) >= self._max_size:
                    # Evict oldest (first) item
                    self._cache.popitem(last=False)
                self._cache[key] = value

    def delete(self, key: str) -> bool:
        """Delete item from cache. Returns True if found."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all items from cache."""
        with self._lock:
            self._cache.clear()

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._cache

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def keys(self) -> list:
        """Return list of keys (snapshot)."""
        with self._lock:
            return list(self._cache.keys())


# =============================================================================
# Scrape Cache (Memory + Disk)
# =============================================================================


class ScrapeCache:
    """
    Combined memory + disk cache with TTL.

    Stores raw content and extracted text separately.
    Memory cache uses LRU eviction; disk cache uses TTL expiration.
    """

    def __init__(
        self,
        memory_size: int = 100,
        disk_ttl_hours: int = 24,
        cache_dir: str | None = None,
    ):
        """
        Initialize cache.

        Args:
            memory_size: Max items in memory LRU cache
            disk_ttl_hours: TTL for disk cache entries
            cache_dir: Directory for disk cache (default: logs/scrape_cache)
        """
        self.raw_memory = LRUCache(memory_size)
        self.extracted_memory = LRUCache(memory_size)
        self.disk_ttl_hours = disk_ttl_hours

        # Set up disk cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Default to project logs directory
            self.cache_dir = Path("logs") / "scrape_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_raw(self, url: str) -> bytes | None:
        """
        Get raw content. Check memory first, then disk.

        Returns: Raw bytes or None if not cached/expired
        """
        key = url_to_cache_key(url)

        # Check memory cache first
        cached = self.raw_memory.get(key)
        if cached is not None:
            return cached

        # Check disk cache
        raw_file = self.cache_dir / f"{key}_raw.bin"
        meta_file = self.cache_dir / f"{key}_meta.json"

        if raw_file.exists() and meta_file.exists():
            try:
                with open(meta_file) as f:
                    meta = json.load(f)

                # Check TTL
                cached_time = datetime.fromisoformat(meta["timestamp"])
                age_hours = (datetime.now() - cached_time).total_seconds() / 3600

                if age_hours < self.disk_ttl_hours:
                    with open(raw_file, "rb") as f:
                        content = f.read()
                    # Add to memory cache
                    self.raw_memory.set(key, content)
                    return content
            except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
                logger.debug("Disk cache read failed for raw %s: %s", url, e)

        return None

    def set_raw(self, url: str, content: bytes) -> None:
        """Cache raw content to both memory and disk."""
        key = url_to_cache_key(url)

        # Add to memory cache
        self.raw_memory.set(key, content)

        # Persist to disk
        try:
            raw_file = self.cache_dir / f"{key}_raw.bin"
            meta_file = self.cache_dir / f"{key}_meta.json"

            with open(raw_file, "wb") as f:
                f.write(content)

            with open(meta_file, "w") as f:
                json.dump(
                    {
                        "url": url,
                        "timestamp": datetime.now().isoformat(),
                        "size": len(content),
                        "type": "raw",
                    },
                    f,
                )
        except OSError as e:
            logger.debug("Disk cache write failed for %s (memory cache still valid): %s", url, e)

    def get_extracted(self, url: str) -> str | None:
        """
        Get extracted text. Check memory first, then disk.

        Returns: Extracted text or None if not cached/expired
        """
        key = url_to_cache_key(url)

        # Check memory cache first
        cached = self.extracted_memory.get(key)
        if cached is not None:
            return cached.decode("utf-8") if isinstance(cached, bytes) else cached

        # Check disk cache
        text_file = self.cache_dir / f"{key}_text.txt"
        meta_file = self.cache_dir / f"{key}_text_meta.json"

        if text_file.exists() and meta_file.exists():
            try:
                with open(meta_file) as f:
                    meta = json.load(f)

                # Check TTL
                cached_time = datetime.fromisoformat(meta["timestamp"])
                age_hours = (datetime.now() - cached_time).total_seconds() / 3600

                if age_hours < self.disk_ttl_hours:
                    with open(text_file, encoding="utf-8") as f:
                        text = f.read()
                    # Add to memory cache
                    self.extracted_memory.set(key, text.encode("utf-8"))
                    return text
            except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
                logger.debug("Disk cache read failed for extracted %s: %s", url, e)

        return None

    def set_extracted(self, url: str, text: str) -> None:
        """Cache extracted text to both memory and disk."""
        key = url_to_cache_key(url)

        # Add to memory cache (store as bytes for consistency)
        self.extracted_memory.set(key, text.encode("utf-8"))

        # Persist to disk
        try:
            text_file = self.cache_dir / f"{key}_text.txt"
            meta_file = self.cache_dir / f"{key}_text_meta.json"

            with open(text_file, "w", encoding="utf-8") as f:
                f.write(text)

            with open(meta_file, "w") as f:
                json.dump(
                    {
                        "url": url,
                        "timestamp": datetime.now().isoformat(),
                        "size": len(text),
                        "type": "extracted",
                    },
                    f,
                )
        except OSError as e:
            logger.debug("Disk cache write failed for extracted text %s (memory cache still valid): %s", url, e)

    def clear_memory(self) -> None:
        """Clear memory caches only."""
        self.raw_memory.clear()
        self.extracted_memory.clear()

    def clear_disk(self, max_age_hours: int | None = None) -> int:
        """
        Clear disk cache.

        Args:
            max_age_hours: If provided, only clear entries older than this.
                          If None, clear all entries.

        Returns: Number of entries cleared
        """
        cleared = 0

        for f in self.cache_dir.iterdir():
            if f.suffix == ".json" and "_meta" in f.name:
                try:
                    if max_age_hours is not None:
                        with open(f) as mf:
                            meta = json.load(mf)
                        cached_time = datetime.fromisoformat(meta["timestamp"])
                        age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                        if age_hours <= max_age_hours:
                            continue

                    # Delete meta file and corresponding data file
                    f.unlink()
                    data_file = f.with_suffix("").with_suffix(
                        ".bin" if "_raw" in f.stem else ".txt"
                    )
                    # Handle the naming pattern
                    base = f.stem.replace("_meta", "").replace("_text", "")
                    if "_text" in f.stem:
                        data_file = self.cache_dir / f"{base}_text.txt"
                    else:
                        data_file = self.cache_dir / f"{base}_raw.bin"

                    if data_file.exists():
                        data_file.unlink()
                    cleared += 1
                except (OSError, json.JSONDecodeError, KeyError, ValueError):
                    pass

        return cleared

    def clear_all(self) -> None:
        """Clear both memory and disk caches."""
        self.clear_memory()
        self.clear_disk()
