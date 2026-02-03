"""
Tests for async/sync boundary utilities.

**Feature: code-quality-improvements**
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from primr.utils.async_utils import (
    AsyncBridge,
    configure_executor,
    ensure_async,
    ensure_sync,
    gather_with_concurrency,
    is_async_context,
    run_async,
    run_async_with_timeout,
    run_sync,
    run_sync_new_loop,
    shutdown_executor,
    sync_context,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_executor():
    """Reset executor after each test."""
    yield
    shutdown_executor(wait=False)


# =============================================================================
# SYNC -> ASYNC TESTS
# =============================================================================

class TestRunSync:
    """Tests for run_sync function."""

    def test_run_sync_simple_coroutine(self):
        """run_sync should execute a simple coroutine."""
        async def simple():
            return 42
        
        result = run_sync(simple())
        assert result == 42

    def test_run_sync_with_await(self):
        """run_sync should handle coroutines with await."""
        async def with_await():
            await asyncio.sleep(0.01)
            return "done"
        
        result = run_sync(with_await())
        assert result == "done"

    def test_run_sync_preserves_exceptions(self):
        """run_sync should propagate exceptions."""
        async def raises():
            raise ValueError("test error")
        
        with pytest.raises(ValueError, match="test error"):
            run_sync(raises())

    def test_run_sync_new_loop_isolation(self):
        """run_sync_new_loop should use a fresh event loop."""
        results = []
        
        async def capture_loop():
            loop = asyncio.get_running_loop()
            results.append(id(loop))
            return loop
        
        run_sync_new_loop(capture_loop())
        run_sync_new_loop(capture_loop())
        
        # Each call should have a different loop
        assert len(results) == 2
        assert results[0] != results[1]


# =============================================================================
# ASYNC -> SYNC TESTS
# =============================================================================

class TestRunAsync:
    """Tests for run_async function."""

    @pytest.mark.asyncio
    async def test_run_async_blocking_function(self):
        """run_async should run blocking functions without blocking event loop."""
        def blocking():
            time.sleep(0.05)
            return "done"
        
        result = await run_async(blocking)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_run_async_with_args(self):
        """run_async should pass arguments correctly."""
        def add(a, b):
            return a + b
        
        result = await run_async(add, 2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_run_async_with_kwargs(self):
        """run_async should pass keyword arguments correctly."""
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"
        
        result = await run_async(greet, "World", greeting="Hi")
        assert result == "Hi, World!"

    @pytest.mark.asyncio
    async def test_run_async_preserves_exceptions(self):
        """run_async should propagate exceptions."""
        def raises():
            raise RuntimeError("test error")
        
        with pytest.raises(RuntimeError, match="test error"):
            await run_async(raises)

    @pytest.mark.asyncio
    async def test_run_async_with_timeout_success(self):
        """run_async_with_timeout should complete within timeout."""
        def fast():
            time.sleep(0.01)
            return "done"
        
        result = await run_async_with_timeout(fast, 1.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_run_async_with_timeout_exceeded(self):
        """run_async_with_timeout should raise on timeout."""
        def slow():
            time.sleep(10)
            return "done"
        
        with pytest.raises(asyncio.TimeoutError):
            await run_async_with_timeout(slow, 0.1)


# =============================================================================
# WRAPPER TESTS
# =============================================================================

class TestEnsureAsync:
    """Tests for ensure_async decorator."""

    @pytest.mark.asyncio
    async def test_ensure_async_wraps_sync_function(self):
        """ensure_async should make sync functions awaitable."""
        @ensure_async
        def sync_func(x):
            return x * 2
        
        result = await sync_func(5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_ensure_async_preserves_name(self):
        """ensure_async should preserve function name."""
        @ensure_async
        def my_function():
            pass
        
        assert my_function.__name__ == "my_function"


class TestEnsureSync:
    """Tests for ensure_sync decorator."""

    def test_ensure_sync_wraps_async_function(self):
        """ensure_sync should make async functions callable from sync code."""
        @ensure_sync
        async def async_func(x):
            await asyncio.sleep(0.01)
            return x * 2
        
        result = async_func(5)
        assert result == 10

    def test_ensure_sync_preserves_name(self):
        """ensure_sync should preserve function name."""
        @ensure_sync
        async def my_async_function():
            pass
        
        assert my_async_function.__name__ == "my_async_function"


# =============================================================================
# CONTEXT MANAGER TESTS
# =============================================================================

class TestSyncContext:
    """Tests for sync_context context manager."""

    def test_sync_context_provides_loop(self):
        """sync_context should provide an event loop."""
        with sync_context() as loop:
            assert loop is not None
            assert isinstance(loop, asyncio.AbstractEventLoop)

    def test_sync_context_allows_run_until_complete(self):
        """sync_context should allow running coroutines."""
        async def coro():
            return 42
        
        with sync_context() as loop:
            result = loop.run_until_complete(coro())
            assert result == 42


class TestAsyncBridge:
    """Tests for AsyncBridge class."""

    def test_bridge_run_executes_coroutine(self):
        """AsyncBridge.run should execute coroutines from sync code."""
        bridge = AsyncBridge()
        
        async def coro():
            return "result"
        
        result = bridge.run(coro())
        assert result == "result"

    @pytest.mark.asyncio
    async def test_bridge_run_blocking_executes_sync(self):
        """AsyncBridge.run_blocking should execute sync functions from async code."""
        bridge = AsyncBridge()
        
        def blocking():
            time.sleep(0.01)
            return "done"
        
        result = await bridge.run_blocking(blocking)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_bridge_with_custom_executor(self):
        """AsyncBridge should use custom executor if provided."""
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="custom-")
        bridge = AsyncBridge(executor=executor)
        
        def get_thread_name():
            import threading
            return threading.current_thread().name
        
        result = await bridge.run_blocking(get_thread_name)
        assert "custom-" in result
        
        executor.shutdown(wait=True)


# =============================================================================
# UTILITY TESTS
# =============================================================================

class TestIsAsyncContext:
    """Tests for is_async_context function."""

    def test_is_async_context_false_in_sync(self):
        """is_async_context should return False in sync code."""
        assert is_async_context() is False

    @pytest.mark.asyncio
    async def test_is_async_context_true_in_async(self):
        """is_async_context should return True in async code."""
        assert is_async_context() is True


class TestGatherWithConcurrency:
    """Tests for gather_with_concurrency function."""

    @pytest.mark.asyncio
    async def test_gather_with_concurrency_returns_all_results(self):
        """gather_with_concurrency should return all results."""
        async def task(n):
            await asyncio.sleep(0.01)
            return n * 2
        
        results = await gather_with_concurrency(
            3,
            task(1),
            task(2),
            task(3),
            task(4),
            task(5),
        )
        
        assert results == [2, 4, 6, 8, 10]

    @pytest.mark.asyncio
    async def test_gather_with_concurrency_limits_concurrent(self):
        """gather_with_concurrency should limit concurrent execution."""
        concurrent_count = 0
        max_concurrent = 0
        
        async def task():
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return True
        
        await gather_with_concurrency(
            2,  # Limit to 2 concurrent
            task(),
            task(),
            task(),
            task(),
        )
        
        assert max_concurrent <= 2


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================

class TestExecutorConfiguration:
    """Tests for executor configuration."""

    def test_configure_executor_changes_workers(self):
        """configure_executor should change worker count."""
        configure_executor(max_workers=2)
        
        # Verify by running concurrent tasks
        async def test():
            results = await gather_with_concurrency(
                10,  # More than workers
                run_async(lambda: 1),
                run_async(lambda: 2),
            )
            return results
        
        result = run_sync(test())
        assert result == [1, 2]

    def test_shutdown_executor_cleans_up(self):
        """shutdown_executor should clean up resources."""
        # Force executor creation
        run_sync(run_async(lambda: 1))
        
        # Shutdown should not raise
        shutdown_executor(wait=True)
