"""
Resource management utilities.

This module provides context managers and classes for safe resource handling:
- Temporary file management with guaranteed cleanup
- HTTP client management with bounded connection pools
- Bounded caches with TTL and metrics

Example:
    from primr.utils.resources import managed_temp_file, BoundedCache

    with managed_temp_file(suffix=".txt", content="data") as path:
        process_file(path)
    # File is automatically deleted

    cache = BoundedCache(max_size=100, ttl_seconds=3600)
    cache.set("key", "value")
"""

from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# TEMPORARY FILE MANAGEMENT
# =============================================================================


@contextmanager
def managed_temp_file(
    suffix: str = ".tmp",
    prefix: str = "primr_",
    content: str | None = None,
    encoding: str = "utf-8",
) -> Generator[Path, None, None]:
    """
    Context manager for temporary files with guaranteed cleanup.

    Creates a temporary file that is automatically deleted when the context
    exits, even if an exception occurs.

    Args:
        suffix: File suffix (e.g., ".txt", ".json")
        prefix: File prefix for identification
        content: Optional content to write to the file
        encoding: Text encoding for content (default: utf-8)

    Yields:
        Path to the temporary file

    Example:
        with managed_temp_file(suffix=".json", content='{"key": "value"}') as path:
            data = json.loads(path.read_text())
        # File is deleted here

    Note:
        The file is deleted even if an exception occurs within the context.
    """
    fd = None
    path = None
    try:
        fd, path_str = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        path = Path(path_str)

        if content is not None:
            with open(fd, "w", encoding=encoding, closefd=False) as f:
                f.write(content)

        os.close(fd)
        fd = None  # Mark as closed

        yield path

    finally:
        # Close file descriptor if still open
        if fd is not None:
            with suppress(OSError):
                os.close(fd)

        # Delete the file
        if path is not None and path.exists():
            try:
                path.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete temp file {path}: {e}")


@contextmanager
def managed_temp_dir(prefix: str = "primr_") -> Generator[Path, None, None]:
    """
    Context manager for temporary directories with guaranteed cleanup.

    Creates a temporary directory that is automatically deleted (with all
    contents) when the context exits.

    Args:
        prefix: Directory prefix for identification

    Yields:
        Path to the temporary directory

    Example:
        with managed_temp_dir() as tmpdir:
            (tmpdir / "file.txt").write_text("data")
        # Directory and contents deleted here
    """
    import shutil

    path = None
    try:
        path = Path(tempfile.mkdtemp(prefix=prefix))
        yield path
    finally:
        if path is not None and path.exists():
            try:
                shutil.rmtree(path)
            except OSError as e:
                logger.warning(f"Failed to delete temp dir {path}: {e}")


# =============================================================================
# HTTP CLIENT MANAGEMENT
# =============================================================================


@contextmanager
def managed_http_client(
    timeout: float = 30.0, max_connections: int = 10, http2: bool = True
) -> Generator:
    """
    Context manager for HTTP client with bounded connection pool.

    Creates an httpx client with configured limits and ensures proper
    cleanup on exit.

    SECURITY WARNING: This returns a raw httpx client. Callers MUST validate
    URLs using `primr.utils.validators.validate_url_for_request()` before
    making requests, and validate final URLs after redirects using
    `primr.utils.security.validate_final_url_after_redirect()` to prevent
    SSRF attacks.

    Args:
        timeout: Request timeout in seconds
        max_connections: Maximum concurrent connections
        http2: Enable HTTP/2 support

    Yields:
        Configured httpx.Client instance

    Example:
        from primr.utils.validators import validate_url_for_request
        from primr.utils.security import validate_final_url_after_redirect

        with managed_http_client(timeout=10.0) as client:
            # Validate URL before request
            is_valid, url, error = validate_url_for_request(url)
            if not is_valid:
                raise ValueError(f"Invalid URL: {error}")

            response = client.get(url)

            # Validate final URL after redirects
            is_safe, error = validate_final_url_after_redirect(str(response.url))
            if not is_safe:
                raise ValueError(f"Unsafe redirect: {error}")
    """
    import httpx

    limits = httpx.Limits(
        max_connections=max_connections, max_keepalive_connections=max_connections // 2
    )

    client = httpx.Client(timeout=timeout, limits=limits, http2=http2, follow_redirects=True)

    try:
        yield client
    finally:
        client.close()


# =============================================================================
# BOUNDED CACHE WITH TTL
# =============================================================================


@dataclass
class CacheEntry:
    """Internal cache entry with value and metadata."""

    value: Any
    created_at: float
    last_accessed: float


@dataclass
class CacheMetrics:
    """Cache performance metrics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate (0.0 to 1.0)."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "hit_rate": round(self.hit_rate, 4),
        }


class BoundedCache:
    """
    Thread-safe cache with size limits, TTL, and metrics.

    Implements LRU (Least Recently Used) eviction when the cache
    reaches its maximum size. Optionally supports TTL-based expiration.

    Attributes:
        max_size: Maximum number of entries
        ttl_seconds: Time-to-live for entries (None = no expiration)
        name: Cache name for logging

    Example:
        cache = BoundedCache(max_size=100, ttl_seconds=3600, name="api_cache")
        cache.set("key", {"data": "value"})
        result = cache.get("key")  # Returns {"data": "value"}
        print(cache.get_metrics())  # {"hits": 1, "misses": 0, ...}
    """

    def __init__(self, max_size: int = 100, ttl_seconds: float | None = None, name: str = "cache"):
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive or None")

        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.name = name

        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._metrics = CacheMetrics()

    def get(self, key: str, default: T | None = None) -> T | None:
        """
        Get value from cache.

        Args:
            key: Cache key
            default: Value to return if key not found

        Returns:
            Cached value or default
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._metrics.misses += 1
                return default

            # Check TTL expiration
            if self.ttl_seconds is not None:
                age = time.time() - entry.created_at
                if age > self.ttl_seconds:
                    del self._cache[key]
                    self._metrics.expirations += 1
                    self._metrics.misses += 1
                    return default

            # Update access time for LRU
            entry.last_accessed = time.time()
            self._metrics.hits += 1
            result: T = entry.value
            return result

    def set(self, key: str, value: Any) -> None:
        """
        Set value in cache.

        If cache is at max_size, evicts the least recently used entry.

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            now = time.time()

            # If key exists, update it
            if key in self._cache:
                self._cache[key] = CacheEntry(value=value, created_at=now, last_accessed=now)
                return

            # Evict if at capacity
            while len(self._cache) >= self.max_size:
                self._evict_lru()

            # Add new entry
            self._cache[key] = CacheEntry(value=value, created_at=now, last_accessed=now)

    def _evict_lru(self) -> None:
        """Evict the least recently used entry."""
        if not self._cache:
            return

        # Find LRU entry
        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
        del self._cache[lru_key]
        self._metrics.evictions += 1

    def delete(self, key: str) -> bool:
        """
        Delete entry from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        """Return number of entries in cache."""
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """Check if key exists in cache (without updating access time)."""
        with self._lock:
            return key in self._cache

    def get_metrics(self) -> dict[str, Any]:
        """
        Get cache performance metrics.

        Returns:
            Dictionary with hits, misses, evictions, expirations, hit_rate
        """
        with self._lock:
            metrics = self._metrics.to_dict()
            metrics["size"] = len(self._cache)
            metrics["max_size"] = self.max_size
            metrics["name"] = self.name
            return metrics

    def log_metrics(self) -> None:
        """Log cache metrics at INFO level."""
        metrics = self.get_metrics()
        logger.info(
            f"Cache '{self.name}' metrics: "
            f"size={metrics['size']}/{metrics['max_size']}, "
            f"hit_rate={metrics['hit_rate']:.1%}, "
            f"hits={metrics['hits']}, misses={metrics['misses']}, "
            f"evictions={metrics['evictions']}"
        )


# =============================================================================
# THREAD-SAFE SINGLETON PATTERN
# =============================================================================


class ThreadSafeSingleton:
    """
    Thread-safe singleton mixin using double-check locking.

    Subclasses automatically get thread-safe singleton behavior.

    Example:
        class MyService(ThreadSafeSingleton):
            def __init__(self):
                self.data = []

        # Always returns the same instance, thread-safely
        service = MyService.get_instance()
    """

    _instances: dict[type, Any] = {}
    _locks: dict[type, threading.Lock] = {}
    _meta_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ThreadSafeSingleton":
        """
        Get the singleton instance (thread-safe).

        Uses double-check locking pattern to ensure thread safety
        while minimizing lock contention.

        Returns:
            The singleton instance
        """
        # Fast path: instance already exists
        if cls in ThreadSafeSingleton._instances:
            instance: ThreadSafeSingleton = ThreadSafeSingleton._instances[cls]
            return instance

        # Slow path: need to create instance
        # First, ensure we have a lock for this class
        with ThreadSafeSingleton._meta_lock:
            if cls not in ThreadSafeSingleton._locks:
                ThreadSafeSingleton._locks[cls] = threading.Lock()

        # Now use the class-specific lock
        with ThreadSafeSingleton._locks[cls]:
            # Double-check after acquiring lock
            if cls not in ThreadSafeSingleton._instances:
                ThreadSafeSingleton._instances[cls] = cls()

        result: ThreadSafeSingleton = ThreadSafeSingleton._instances[cls]
        return result

    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset the singleton instance (useful for testing).

        Thread-safe reset that removes the cached instance.
        """
        with ThreadSafeSingleton._meta_lock:
            if cls not in ThreadSafeSingleton._locks:
                ThreadSafeSingleton._locks[cls] = threading.Lock()

        with ThreadSafeSingleton._locks[cls]:
            if cls in ThreadSafeSingleton._instances:
                del ThreadSafeSingleton._instances[cls]

    @classmethod
    def has_instance(cls) -> bool:
        """Check if an instance exists (without creating one)."""
        return cls in ThreadSafeSingleton._instances


# =============================================================================
# RESOURCE MANAGER
# =============================================================================


class ResourceManager:
    """
    Manages cleanup of resources on exit.

    Tracks temporary files, file handles, and browser processes,
    ensuring they are cleaned up on exit (normal or via signal).

    Registered with atexit for automatic cleanup.

    Example:
        manager = ResourceManager()

        # Register resources
        manager.register_temp_file(Path("/tmp/data.txt"))
        manager.register_handle(open("file.txt"))
        manager.register_process(browser_pid)

        # Cleanup happens automatically on exit, or manually:
        manager.cleanup()
    """

    def __init__(self) -> None:
        self._temp_files: set[Path] = set()
        self._open_handles: set[Any] = set()  # IO handles
        self._browser_processes: set[int] = set()
        self._lock = threading.RLock()
        self._cleaned_up = False

    def register_temp_file(self, path: Path) -> None:
        """
        Register a temporary file for cleanup.

        Args:
            path: Path to the temporary file
        """
        with self._lock:
            self._temp_files.add(path)

    def unregister_temp_file(self, path: Path) -> None:
        """
        Unregister a temporary file (e.g., if manually deleted).

        Args:
            path: Path to the temporary file
        """
        with self._lock:
            self._temp_files.discard(path)

    def register_handle(self, handle: Any) -> None:
        """
        Register a file handle for cleanup.

        Args:
            handle: File handle or IO object with close() method
        """
        with self._lock:
            self._open_handles.add(handle)

    def unregister_handle(self, handle: Any) -> None:
        """
        Unregister a file handle.

        Args:
            handle: File handle to unregister
        """
        with self._lock:
            self._open_handles.discard(handle)

    def register_process(self, pid: int) -> None:
        """
        Register a browser/subprocess for cleanup.

        Args:
            pid: Process ID
        """
        with self._lock:
            self._browser_processes.add(pid)

    def unregister_process(self, pid: int) -> None:
        """
        Unregister a process.

        Args:
            pid: Process ID to unregister
        """
        with self._lock:
            self._browser_processes.discard(pid)

    def cleanup(self) -> dict[str, int]:
        """
        Clean up all registered resources.

        Returns:
            Dict with counts of cleaned resources by type

        Note:
            Safe to call multiple times; only cleans up once.
        """
        with self._lock:
            if self._cleaned_up:
                return {"temp_files": 0, "handles": 0, "processes": 0}

            self._cleaned_up = True
            results = {
                "temp_files": 0,
                "handles": 0,
                "processes": 0,
            }

            # Close file handles
            for handle in list(self._open_handles):
                try:
                    if hasattr(handle, "close"):
                        handle.close()
                    results["handles"] += 1
                except Exception as e:
                    logger.warning(f"Failed to close handle: {e}")
            self._open_handles.clear()

            # Delete temp files
            for path in list(self._temp_files):
                try:
                    if path.exists():
                        path.unlink()
                        results["temp_files"] += 1
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {path}: {e}")
            self._temp_files.clear()

            # Terminate processes
            for pid in list(self._browser_processes):
                try:
                    import signal

                    os.kill(pid, signal.SIGTERM)
                    results["processes"] += 1
                except (OSError, ProcessLookupError) as e:
                    logger.debug(f"Process {pid} already terminated: {e}")
            self._browser_processes.clear()

            logger.debug(
                f"ResourceManager cleanup: {results['temp_files']} files, "
                f"{results['handles']} handles, {results['processes']} processes"
            )

            return results

    def __enter__(self) -> "ResourceManager":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit - cleanup resources."""
        self.cleanup()

    @property
    def resource_counts(self) -> dict[str, int]:
        """Get current counts of registered resources."""
        with self._lock:
            return {
                "temp_files": len(self._temp_files),
                "handles": len(self._open_handles),
                "processes": len(self._browser_processes),
            }


# Global resource manager instance
_resource_manager: ResourceManager | None = None
_resource_manager_lock = threading.Lock()


def get_resource_manager() -> ResourceManager:
    """
    Get the global ResourceManager instance.

    Creates the instance on first call and registers with atexit.

    Returns:
        Global ResourceManager instance
    """
    global _resource_manager

    if _resource_manager is not None:
        return _resource_manager

    with _resource_manager_lock:
        if _resource_manager is None:
            _resource_manager = ResourceManager()
            import atexit

            atexit.register(_resource_manager.cleanup)

    return _resource_manager


# =============================================================================
# SIGNAL HANDLING
# =============================================================================


_original_sigint_handler: Any = None
_sigint_installed = False


def install_sigint_handler() -> None:
    """
    Install SIGINT handler for graceful shutdown.

    On SIGINT (Ctrl+C), cleans up resources before exiting.
    Safe to call multiple times.
    """
    global _original_sigint_handler, _sigint_installed

    if _sigint_installed:
        return

    import signal

    def sigint_handler(signum: int, frame: Any) -> None:
        """Handle SIGINT by cleaning up and exiting."""
        logger.info("Received SIGINT, cleaning up...")

        # Cleanup resources
        manager = get_resource_manager()
        manager.cleanup()

        # Call original handler or exit
        if _original_sigint_handler and callable(_original_sigint_handler):
            _original_sigint_handler(signum, frame)
        else:
            raise SystemExit(130)  # Standard exit code for SIGINT

    _original_sigint_handler = signal.signal(signal.SIGINT, sigint_handler)
    _sigint_installed = True
    logger.debug("SIGINT handler installed")


def uninstall_sigint_handler() -> None:
    """
    Restore original SIGINT handler.

    Useful for testing or when you want to handle SIGINT differently.
    """
    global _original_sigint_handler, _sigint_installed

    if not _sigint_installed:
        return

    import signal

    if _original_sigint_handler is not None:
        signal.signal(signal.SIGINT, _original_sigint_handler)

    _sigint_installed = False
    logger.debug("SIGINT handler uninstalled")
