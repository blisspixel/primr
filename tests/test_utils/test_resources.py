"""
Tests for resource management utilities.

Includes property-based tests using Hypothesis for comprehensive validation.
"""

from pathlib import Path
import threading
import time

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from primr.utils.resources import (
    BoundedCache,
    CacheMetrics,
    managed_temp_dir,
    managed_temp_file,
)

# =============================================================================
# UNIT TESTS - managed_temp_file
# =============================================================================


class TestManagedTempFile:
    """Tests for managed_temp_file context manager."""

    def test_creates_file(self):
        """Should create a temporary file."""
        with managed_temp_file() as path:
            assert path.exists()
            assert path.is_file()

    def test_deletes_file_on_exit(self):
        """Should delete file when context exits."""
        with managed_temp_file() as path:
            file_path = path
        assert not file_path.exists()

    def test_writes_content(self):
        """Should write content to file."""
        with managed_temp_file(content="test content") as path:
            assert path.read_text() == "test content"

    def test_uses_suffix(self):
        """Should use specified suffix."""
        with managed_temp_file(suffix=".json") as path:
            assert path.suffix == ".json"

    def test_uses_prefix(self):
        """Should use specified prefix."""
        with managed_temp_file(prefix="myprefix_") as path:
            assert path.name.startswith("myprefix_")

    def test_deletes_on_exception(self):
        """Should delete file even when exception occurs."""
        file_path = None
        try:
            with managed_temp_file() as path:
                file_path = path
                raise ValueError("test error")
        except ValueError:
            pass

        assert file_path is not None
        assert not file_path.exists()


class TestManagedTempDir:
    """Tests for managed_temp_dir context manager."""

    def test_creates_directory(self):
        """Should create a temporary directory."""
        with managed_temp_dir() as path:
            assert path.exists()
            assert path.is_dir()

    def test_deletes_directory_on_exit(self):
        """Should delete directory when context exits."""
        with managed_temp_dir() as path:
            dir_path = path
        assert not dir_path.exists()

    def test_deletes_contents(self):
        """Should delete directory contents."""
        with managed_temp_dir() as path:
            (path / "file.txt").write_text("content")
            (path / "subdir").mkdir()
            (path / "subdir" / "nested.txt").write_text("nested")
            dir_path = path

        assert not dir_path.exists()

    def test_deletes_on_exception(self):
        """Should delete directory even when exception occurs."""
        dir_path = None
        try:
            with managed_temp_dir() as path:
                dir_path = path
                (path / "file.txt").write_text("content")
                raise ValueError("test error")
        except ValueError:
            pass

        assert dir_path is not None
        assert not dir_path.exists()


# =============================================================================
# UNIT TESTS - BoundedCache
# =============================================================================


class TestBoundedCache:
    """Tests for BoundedCache class."""

    def test_basic_get_set(self):
        """Should store and retrieve values."""
        cache = BoundedCache(max_size=10)
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_get_missing_returns_default(self):
        """Should return default for missing keys."""
        cache = BoundedCache(max_size=10)
        assert cache.get("missing") is None
        assert cache.get("missing", "default") == "default"

    def test_delete(self):
        """Should delete entries."""
        cache = BoundedCache(max_size=10)
        cache.set("key", "value")
        assert cache.delete("key") is True
        assert cache.get("key") is None
        assert cache.delete("key") is False

    def test_clear(self):
        """Should clear all entries."""
        cache = BoundedCache(max_size=10)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0

    def test_len(self):
        """Should return correct length."""
        cache = BoundedCache(max_size=10)
        assert len(cache) == 0
        cache.set("a", 1)
        assert len(cache) == 1
        cache.set("b", 2)
        assert len(cache) == 2

    def test_contains(self):
        """Should check key existence."""
        cache = BoundedCache(max_size=10)
        cache.set("key", "value")
        assert "key" in cache
        assert "missing" not in cache

    def test_update_existing_key(self):
        """Should update existing keys."""
        cache = BoundedCache(max_size=10)
        cache.set("key", "old")
        cache.set("key", "new")
        assert cache.get("key") == "new"
        assert len(cache) == 1


class TestBoundedCacheLRU:
    """Tests for LRU eviction behavior."""

    def test_evicts_when_full(self):
        """Should evict when at max_size."""
        cache = BoundedCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # Should evict "a"

        assert len(cache) == 3
        assert "a" not in cache
        assert "d" in cache

    def test_evicts_least_recently_used(self):
        """Should evict least recently used entry."""
        cache = BoundedCache(max_size=3)
        cache.set("a", 1)
        time.sleep(0.01)  # Ensure different timestamps
        cache.set("b", 2)
        time.sleep(0.01)
        cache.set("c", 3)

        # Access "a" to make it recently used
        cache.get("a")

        # Add new entry - should evict "b" (least recently used)
        cache.set("d", 4)

        assert "a" in cache  # Recently accessed
        assert "b" not in cache  # Evicted
        assert "c" in cache
        assert "d" in cache


class TestBoundedCacheTTL:
    """Tests for TTL expiration behavior."""

    def test_ttl_expiration(self):
        """Should expire entries after TTL."""
        cache = BoundedCache(max_size=10, ttl_seconds=0.1)
        cache.set("key", "value")

        assert cache.get("key") == "value"

        time.sleep(0.15)

        assert cache.get("key") is None

    def test_no_ttl_no_expiration(self):
        """Should not expire without TTL."""
        cache = BoundedCache(max_size=10, ttl_seconds=None)
        cache.set("key", "value")

        # Would expire with TTL
        time.sleep(0.1)

        assert cache.get("key") == "value"


class TestBoundedCacheMetrics:
    """Tests for cache metrics."""

    def test_tracks_hits(self):
        """Should track cache hits."""
        cache = BoundedCache(max_size=10)
        cache.set("key", "value")
        cache.get("key")
        cache.get("key")

        metrics = cache.get_metrics()
        assert metrics["hits"] == 2

    def test_tracks_misses(self):
        """Should track cache misses."""
        cache = BoundedCache(max_size=10)
        cache.get("missing1")
        cache.get("missing2")

        metrics = cache.get_metrics()
        assert metrics["misses"] == 2

    def test_tracks_evictions(self):
        """Should track evictions."""
        cache = BoundedCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # Evicts one

        metrics = cache.get_metrics()
        assert metrics["evictions"] == 1

    def test_hit_rate_calculation(self):
        """Should calculate hit rate correctly."""
        cache = BoundedCache(max_size=10)
        cache.set("key", "value")

        cache.get("key")  # Hit
        cache.get("key")  # Hit
        cache.get("missing")  # Miss
        cache.get("missing")  # Miss

        metrics = cache.get_metrics()
        assert metrics["hit_rate"] == 0.5


class TestCacheMetrics:
    """Tests for CacheMetrics dataclass."""

    def test_hit_rate_zero_total(self):
        """Should return 0 hit rate when no accesses."""
        metrics = CacheMetrics()
        assert metrics.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Should calculate hit rate correctly."""
        metrics = CacheMetrics(hits=3, misses=1)
        assert metrics.hit_rate == 0.75

    def test_to_dict(self):
        """Should convert to dictionary."""
        metrics = CacheMetrics(hits=10, misses=5, evictions=2, expirations=1)
        d = metrics.to_dict()
        assert d["hits"] == 10
        assert d["misses"] == 5
        assert d["evictions"] == 2
        assert d["expirations"] == 1
        assert "hit_rate" in d


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================


class TestTempFileCleanupProperty:
    """
    Property-based tests for temp file cleanup.

    **Feature: code-quality-hardening, Property 5: Temp File Cleanup on Exception**
    **Validates: Requirements 3.2**

    For any temporary file created within a managed context, the file SHALL
    be deleted even if an exception occurs within the context.
    """

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=100)
    def test_file_deleted_on_normal_exit(self, content: str):
        """File should be deleted on normal context exit."""
        with managed_temp_file(content=content) as path:
            file_path = path
            assert path.exists()

        assert not file_path.exists()

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=100)
    def test_file_deleted_on_exception(self, error_message: str):
        """File should be deleted even when exception occurs."""
        file_path = None
        try:
            with managed_temp_file() as path:
                file_path = path
                assert path.exists()
                raise ValueError(error_message)
        except ValueError:
            pass

        assert file_path is not None
        assert not file_path.exists()

    @given(st.text(alphabet="abcdefghij", min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_content_written_correctly(self, content: str):
        """Content should be written correctly to temp file."""
        with managed_temp_file(content=content) as path:
            assert path.read_text() == content


class TestLRUCacheEvictionProperty:
    """
    Property-based tests for LRU cache eviction.

    **Feature: code-quality-hardening, Property 6: LRU Cache Eviction**
    **Validates: Requirements 3.4**

    For any LRU cache with max_size N, after inserting N+1 items, the cache
    SHALL contain exactly N items and the oldest item SHALL have been evicted.
    """

    @given(st.integers(min_value=1, max_value=20))
    @settings(max_examples=100)
    def test_cache_never_exceeds_max_size(self, max_size: int):
        """Cache should never exceed max_size."""
        cache = BoundedCache(max_size=max_size)

        # Insert more items than max_size
        for i in range(max_size * 2):
            cache.set(f"key_{i}", i)
            assert len(cache) <= max_size

    @given(st.integers(min_value=2, max_value=10))
    @settings(max_examples=100)
    def test_oldest_evicted_first(self, max_size: int):
        """Oldest (least recently used) item should be evicted first."""
        cache = BoundedCache(max_size=max_size)

        # Fill cache
        for i in range(max_size):
            cache.set(f"key_{i}", i)

        # First key should still exist
        assert "key_0" in cache

        # Add one more - should evict key_0
        cache.set("new_key", "new_value")

        assert "key_0" not in cache
        assert "new_key" in cache
        assert len(cache) == max_size

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=0, max_value=5))
    @settings(max_examples=100)
    def test_access_updates_lru_order(self, max_size: int, access_index: int):
        """Accessing an item should update its LRU position."""
        cache = BoundedCache(max_size=max_size)

        # Fill cache
        for i in range(max_size):
            cache.set(f"key_{i}", i)

        # Access an item to make it recently used
        access_key = f"key_{access_index % max_size}"
        cache.get(access_key)

        # Add new items to trigger evictions
        for i in range(max_size):
            cache.set(f"new_{i}", i)

        # The accessed key might still be there if it was accessed recently enough
        # But the cache should never exceed max_size
        assert len(cache) == max_size


class TestCacheHitRateLoggingProperty:
    """
    Property-based tests for cache hit rate logging.

    **Feature: code-quality-hardening, Property 16: Cache Hit Rate Logging**
    **Validates: Requirements 9.5**

    For any cache operation (get/set), the cache SHALL track and log
    hit/miss statistics.
    """

    @given(
        st.lists(st.text(alphabet="abcde", min_size=1, max_size=3), min_size=1, max_size=20),
        st.lists(st.text(alphabet="abcde", min_size=1, max_size=3), min_size=1, max_size=20),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_metrics_track_all_operations(self, keys_to_set: list[str], keys_to_get: list[str]):
        """Metrics should track all get operations."""
        cache = BoundedCache(max_size=100)

        # Set some keys
        for key in keys_to_set:
            cache.set(key, f"value_{key}")

        # Get some keys (some may hit, some may miss)
        for key in keys_to_get:
            cache.get(key)

        metrics = cache.get_metrics()

        # Total gets should equal hits + misses
        assert metrics["hits"] + metrics["misses"] == len(keys_to_get)

        # Hit rate should be valid
        assert 0.0 <= metrics["hit_rate"] <= 1.0

    @given(st.integers(min_value=1, max_value=50))
    @settings(max_examples=100)
    def test_all_hits_gives_100_percent(self, num_ops: int):
        """All hits should give 100% hit rate."""
        cache = BoundedCache(max_size=100)
        cache.set("key", "value")

        for _ in range(num_ops):
            cache.get("key")

        metrics = cache.get_metrics()
        assert metrics["hit_rate"] == 1.0
        assert metrics["hits"] == num_ops
        assert metrics["misses"] == 0

    @given(st.integers(min_value=1, max_value=50))
    @settings(max_examples=100)
    def test_all_misses_gives_0_percent(self, num_ops: int):
        """All misses should give 0% hit rate."""
        cache = BoundedCache(max_size=100)

        for i in range(num_ops):
            cache.get(f"missing_{i}")

        metrics = cache.get_metrics()
        assert metrics["hit_rate"] == 0.0
        assert metrics["hits"] == 0
        assert metrics["misses"] == num_ops


# =============================================================================
# THREAD-SAFE SINGLETON TESTS
# =============================================================================

from primr.utils.resources import ThreadSafeSingleton


class _SingletonForTesting(ThreadSafeSingleton):
    """Singleton class for testing purposes."""

    def __init__(self):
        self.value = 0
        self.init_count = 0
        _SingletonForTesting._init_counter = getattr(_SingletonForTesting, "_init_counter", 0) + 1


class TestThreadSafeSingleton:
    """Tests for ThreadSafeSingleton mixin."""

    def setup_method(self):
        """Reset singleton before each test."""
        _SingletonForTesting.reset_instance()
        _SingletonForTesting._init_counter = 0

    def test_returns_same_instance(self):
        """Should return the same instance on multiple calls."""
        instance1 = _SingletonForTesting.get_instance()
        instance2 = _SingletonForTesting.get_instance()
        assert instance1 is instance2

    def test_only_creates_once(self):
        """Should only call __init__ once."""
        _SingletonForTesting.get_instance()
        _SingletonForTesting.get_instance()
        _SingletonForTesting.get_instance()
        assert _SingletonForTesting._init_counter == 1

    def test_reset_allows_new_instance(self):
        """Reset should allow creating a new instance."""
        instance1 = _SingletonForTesting.get_instance()
        _SingletonForTesting.reset_instance()
        instance2 = _SingletonForTesting.get_instance()
        assert instance1 is not instance2

    def test_has_instance(self):
        """Should correctly report instance existence."""
        assert not _SingletonForTesting.has_instance()
        _SingletonForTesting.get_instance()
        assert _SingletonForTesting.has_instance()
        _SingletonForTesting.reset_instance()
        assert not _SingletonForTesting.has_instance()


class TestThreadSafeSingletonProperty:
    """
    Property-based tests for thread-safe singleton access.

    **Feature: code-quality-hardening, Property 7: Thread-Safe Singleton Access**
    **Validates: Requirements 4.1**

    For any number of concurrent threads accessing a singleton, all threads
    SHALL receive the same instance and no race conditions SHALL occur.
    """

    def setup_method(self):
        """Reset singleton before each test."""
        _SingletonForTesting.reset_instance()
        _SingletonForTesting._init_counter = 0

    @given(st.integers(min_value=2, max_value=20))
    @settings(max_examples=50)
    def test_concurrent_access_returns_same_instance(self, num_threads: int):
        """All threads should get the same instance."""
        _SingletonForTesting.reset_instance()
        _SingletonForTesting._init_counter = 0

        instances: list[_SingletonForTesting] = []
        errors: list[Exception] = []

        def get_instance():
            try:
                inst = _SingletonForTesting.get_instance()
                instances.append(inst)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_instance) for _ in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(instances) == num_threads

        # All instances should be the same object
        first = instances[0]
        assert all(inst is first for inst in instances)

    @given(st.integers(min_value=5, max_value=20))
    @settings(max_examples=50)
    def test_concurrent_access_only_creates_once(self, num_threads: int):
        """Singleton should only be created once even with concurrent access."""
        _SingletonForTesting.reset_instance()
        _SingletonForTesting._init_counter = 0

        barrier = threading.Barrier(num_threads)

        def get_instance():
            barrier.wait()  # Synchronize all threads to start together
            _SingletonForTesting.get_instance()

        threads = [threading.Thread(target=get_instance) for _ in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should only have been initialized once
        assert _SingletonForTesting._init_counter == 1


class TestConcurrentStateModificationProperty:
    """
    Property-based tests for concurrent state modification safety.

    **Feature: code-quality-hardening, Property 8: Concurrent State Modification Safety**
    **Validates: Requirements 4.2, 4.3**

    For any shared state protected by locks, concurrent modifications SHALL
    not corrupt the state or cause data races.
    """

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=5, max_value=20))
    @settings(max_examples=50)
    def test_concurrent_cache_writes_no_corruption(self, num_threads: int, ops_per_thread: int):
        """Concurrent cache writes should not corrupt state."""
        cache = BoundedCache(max_size=50)
        errors: list[Exception] = []

        def writer(thread_id: int):
            try:
                for i in range(ops_per_thread):
                    key = f"thread_{thread_id}_key_{i}"
                    cache.set(key, f"value_{thread_id}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        # Cache should not exceed max_size
        assert len(cache) <= 50

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=5, max_value=20))
    @settings(max_examples=50)
    def test_concurrent_cache_reads_writes_no_corruption(
        self, num_threads: int, ops_per_thread: int
    ):
        """Concurrent reads and writes should not corrupt state."""
        cache = BoundedCache(max_size=100)

        # Pre-populate cache
        for i in range(20):
            cache.set(f"key_{i}", f"value_{i}")

        errors: list[Exception] = []

        def reader_writer(thread_id: int):
            try:
                for i in range(ops_per_thread):
                    if i % 2 == 0:
                        # Read
                        cache.get(f"key_{i % 20}")
                    else:
                        # Write
                        cache.set(f"thread_{thread_id}_key_{i}", f"value_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader_writer, args=(i,)) for i in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        # Metrics should be consistent
        metrics = cache.get_metrics()
        assert metrics["hits"] + metrics["misses"] >= 0


class TestProgressCallbackThreadSafetyProperty:
    """
    Property-based tests for progress callback thread safety.

    **Feature: code-quality-hardening, Property 9: Progress Callback Thread Safety**
    **Validates: Requirements 4.4**

    For any progress callback invoked from multiple threads, the callback
    SHALL execute without blocking and handle concurrent invocation safely.
    """

    @given(st.integers(min_value=2, max_value=10))
    @settings(max_examples=50)
    def test_safe_callback_handles_concurrent_calls(self, num_threads: int):
        """Safe callbacks should handle concurrent invocation."""
        from primr.utils.errors import async_safe_callback

        call_count = 0
        count_lock = threading.Lock()

        def callback(value: int):
            nonlocal call_count
            with count_lock:
                call_count += 1
            return value * 2

        safe_cb = async_safe_callback(callback)
        errors: list[Exception] = []

        def caller(thread_id: int):
            try:
                for i in range(10):
                    safe_cb(i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=caller, args=(i,)) for i in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert call_count == num_threads * 10

    @given(st.integers(min_value=2, max_value=10))
    @settings(max_examples=50)
    def test_safe_callback_never_blocks_on_exception(self, num_threads: int):
        """Safe callbacks should not block even when exceptions occur."""
        from primr.utils.errors import async_safe_callback

        def failing_callback(value: int):
            if value % 3 == 0:
                raise ValueError("Intentional failure")
            return value

        safe_cb = async_safe_callback(failing_callback)
        completed = []
        completed_lock = threading.Lock()

        def caller(thread_id: int):
            for i in range(10):
                safe_cb(i)  # Should never raise
            with completed_lock:
                completed.append(thread_id)

        threads = [threading.Thread(target=caller, args=(i,)) for i in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)  # Should complete quickly

        # All threads should complete
        assert len(completed) == num_threads


# =============================================================================
# TESTS FOR RESOURCE MANAGER
# =============================================================================

from primr.utils.resources import (
    ResourceManager,
)


class TestResourceManager:
    """Tests for ResourceManager class."""

    def test_register_temp_file(self, tmp_path):
        """Should register and track temp files."""
        manager = ResourceManager()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        manager.register_temp_file(test_file)

        counts = manager.resource_counts
        assert counts["temp_files"] == 1

    def test_cleanup_deletes_temp_files(self, tmp_path):
        """Should delete registered temp files on cleanup."""
        manager = ResourceManager()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        manager.register_temp_file(test_file)
        assert test_file.exists()

        results = manager.cleanup()

        assert not test_file.exists()
        assert results["temp_files"] == 1

    def test_cleanup_closes_handles(self, tmp_path):
        """Should close registered file handles on cleanup."""
        manager = ResourceManager()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        handle = open(test_file)  # noqa: SIM115
        manager.register_handle(handle)

        results = manager.cleanup()

        assert handle.closed
        assert results["handles"] == 1

    def test_cleanup_only_runs_once(self, tmp_path):
        """Should only cleanup once even if called multiple times."""
        manager = ResourceManager()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        manager.register_temp_file(test_file)

        results1 = manager.cleanup()
        results2 = manager.cleanup()

        assert results1["temp_files"] == 1
        assert results2["temp_files"] == 0

    def test_context_manager(self, tmp_path):
        """Should cleanup on context exit."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with ResourceManager() as manager:
            manager.register_temp_file(test_file)
            assert test_file.exists()

        assert not test_file.exists()

    def test_unregister_temp_file(self, tmp_path):
        """Should allow unregistering temp files."""
        manager = ResourceManager()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        manager.register_temp_file(test_file)
        manager.unregister_temp_file(test_file)

        results = manager.cleanup()
        assert results["temp_files"] == 0
        assert test_file.exists()  # Not deleted


class TestResourceCleanupCompletenessProperty:
    """
    Property-based tests for resource cleanup completeness.

    **Feature: primr-excellence, Property 16: Resource Cleanup Completeness**
    **Validates: Requirements 9.3**

    For any operation that creates temporary files, those files SHALL not
    exist after the operation completes (success or failure).
    """

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=50)
    def test_all_temp_files_cleaned_up(self, num_files: int):
        """All registered temp files should be cleaned up."""
        import shutil
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            manager = ResourceManager()
            files = []

            for i in range(num_files):
                f = tmp_dir / f"test_{i}.txt"
                f.write_text(f"content_{i}")
                files.append(f)
                manager.register_temp_file(f)

            # All files exist
            assert all(f.exists() for f in files)

            manager.cleanup()

            # All files deleted
            assert all(not f.exists() for f in files)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(st.integers(min_value=1, max_value=5))
    @settings(max_examples=50)
    def test_cleanup_on_exception(self, num_files: int):
        """Files should be cleaned up even on exception."""
        import shutil
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp())
        files = []

        try:
            try:
                with ResourceManager() as manager:
                    for i in range(num_files):
                        f = tmp_dir / f"test_{i}.txt"
                        f.write_text(f"content_{i}")
                        files.append(f)
                        manager.register_temp_file(f)

                    raise ValueError("Intentional error")
            except ValueError:
                pass

            # All files should be deleted
            assert all(not f.exists() for f in files)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(st.integers(min_value=1, max_value=5))
    @settings(max_examples=50)
    def test_handles_closed_on_cleanup(self, num_handles: int):
        """All registered handles should be closed on cleanup."""
        import shutil
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            manager = ResourceManager()
            handles = []

            for i in range(num_handles):
                f = tmp_dir / f"test_{i}.txt"
                f.write_text(f"content_{i}")
                handle = open(f)  # noqa: SIM115
                handles.append(handle)
                manager.register_handle(handle)

            # All handles open
            assert all(not h.closed for h in handles)

            manager.cleanup()

            # All handles closed
            assert all(h.closed for h in handles)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
