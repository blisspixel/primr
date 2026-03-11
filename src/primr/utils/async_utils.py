"""
Async/Sync Boundary Utilities.

This module provides a unified approach to crossing async/sync boundaries,
consolidating patterns that were previously scattered across the codebase.

**Feature: code-quality-improvements**

The module provides:
- run_sync: Run async code from sync context (safe event loop handling)
- run_async: Run sync code from async context (via executor)
- ensure_async: Wrap sync functions to be async-compatible
- AsyncBridge: Context manager for managing async/sync transitions

Usage:
    # From sync code, call async function
    result = run_sync(async_function())

    # From async code, call blocking sync function
    result = await run_async(blocking_function, arg1, arg2)

    # Wrap a sync function for async use
    async_fn = ensure_async(sync_function)
    result = await async_fn(arg1, arg2)
"""

from __future__ import annotations

import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

# Default thread pool for blocking operations
_default_executor: ThreadPoolExecutor | None = None
_executor_max_workers: int = 4


def _get_default_executor() -> ThreadPoolExecutor:
    """Get or create the default thread pool executor."""
    global _default_executor
    if _default_executor is None:
        _default_executor = ThreadPoolExecutor(
            max_workers=_executor_max_workers, thread_name_prefix="primr-async-"
        )
    return _default_executor


def configure_executor(max_workers: int = 4) -> None:
    """
    Configure the default executor for async operations.

    Call this at application startup if you need different settings.

    Args:
        max_workers: Maximum number of worker threads
    """
    global _executor_max_workers, _default_executor
    _executor_max_workers = max_workers
    # Reset executor so it gets recreated with new settings
    if _default_executor is not None:
        _default_executor.shutdown(wait=False)
        _default_executor = None


def shutdown_executor(wait: bool = True) -> None:
    """
    Shutdown the default executor.

    Call this at application shutdown for clean resource cleanup.

    Args:
        wait: If True, wait for pending tasks to complete
    """
    global _default_executor
    if _default_executor is not None:
        _default_executor.shutdown(wait=wait)
        _default_executor = None


# =============================================================================
# SYNC -> ASYNC: Running async code from sync context
# =============================================================================


def run_sync(coro: Awaitable[T]) -> T:
    """
    Run an async coroutine from synchronous code.

    This function safely handles event loop detection and creation,
    avoiding the common pitfall of nested event loops.

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine

    Raises:
        RuntimeError: If called from within an async context (use await instead)

    Example:
        async def fetch_data():
            return await api.get("/data")

        # From sync code:
        result = run_sync(fetch_data())
    """
    try:
        # Check if we're already in an async context
        loop = asyncio.get_running_loop()
        # If we get here, we're in an async context - this is an error
        raise RuntimeError(
            "run_sync() cannot be called from within an async context. "
            "Use 'await' directly instead."
        )
    except RuntimeError as e:
        if "no running event loop" not in str(e).lower():
            raise

    # Not in async context - safe to create/use event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


def run_sync_new_loop(coro: Awaitable[T]) -> T:
    """
    Run an async coroutine in a fresh event loop.

    Use this when you need isolation from any existing event loop,
    such as in tests or when running in a thread.

    If called from a thread that already has a running event loop,
    the coroutine is executed in a new thread to avoid conflicts.

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine

    Example:
        result = run_sync_new_loop(async_operation())
    """
    try:
        asyncio.get_running_loop()
        # A loop is already running in this thread — we can't call
        # run_until_complete here, so delegate to a worker thread.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()  # type: ignore[arg-type]
    except RuntimeError:
        pass

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# ASYNC -> SYNC: Running sync code from async context
# =============================================================================


async def run_async(func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """
    Run a blocking sync function from async code without blocking the event loop.

    The function is executed in a thread pool executor, allowing the event
    loop to continue processing other tasks.

    Args:
        func: The sync function to run
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function

    Returns:
        The result of the function

    Example:
        async def process():
            # This won't block the event loop
            result = await run_async(blocking_io_operation, filename)
            return result
    """
    loop = asyncio.get_running_loop()
    executor = _get_default_executor()

    # functools.partial handles kwargs
    if kwargs:
        func_with_args = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, func_with_args)
    else:
        return await loop.run_in_executor(executor, func, *args)


async def run_async_with_timeout(
    func: Callable[P, T], timeout: float, *args: P.args, **kwargs: P.kwargs
) -> T:
    """
    Run a blocking sync function with a timeout.

    Args:
        func: The sync function to run
        timeout: Maximum time to wait in seconds
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function

    Returns:
        The result of the function

    Raises:
        asyncio.TimeoutError: If the function doesn't complete within timeout

    Example:
        try:
            result = await run_async_with_timeout(slow_operation, 30.0, arg1)
        except asyncio.TimeoutError:
            logger.warning("Operation timed out")
    """
    return await asyncio.wait_for(run_async(func, *args, **kwargs), timeout=timeout)


# =============================================================================
# FUNCTION WRAPPERS
# =============================================================================


def ensure_async(func: Callable[P, T]) -> Callable[P, Awaitable[T]]:
    """
    Wrap a sync function to make it async-compatible.

    The wrapped function will run in a thread pool when awaited,
    preventing it from blocking the event loop.

    Args:
        func: The sync function to wrap

    Returns:
        An async wrapper function

    Example:
        @ensure_async
        def blocking_operation(x: int) -> int:
            time.sleep(1)
            return x * 2

        # Now can be awaited
        result = await blocking_operation(5)
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return await run_async(func, *args, **kwargs)

    return wrapper


def ensure_sync(func: Callable[P, Awaitable[T]]) -> Callable[P, T]:
    """
    Wrap an async function to make it sync-compatible.

    The wrapped function will run the coroutine in an event loop
    when called from sync code.

    Args:
        func: The async function to wrap

    Returns:
        A sync wrapper function

    Example:
        @ensure_sync
        async def async_operation(x: int) -> int:
            await asyncio.sleep(0.1)
            return x * 2

        # Now can be called from sync code
        result = async_operation(5)
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return run_sync(func(*args, **kwargs))

    return wrapper


# =============================================================================
# CONTEXT MANAGERS
# =============================================================================


@contextmanager
def sync_context():
    """
    Context manager for sync code that may call async functions.

    Ensures proper event loop setup and cleanup.

    Example:
        with sync_context():
            result = run_sync(async_operation())
    """
    loop = None
    created_loop = False

    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            created_loop = True

        yield loop

    finally:
        if created_loop and loop is not None:
            loop.close()


class AsyncBridge:
    """
    Bridge for managing async/sync transitions in a class context.

    Useful when a class needs to support both sync and async interfaces.

    Example:
        class DataFetcher:
            def __init__(self):
                self._bridge = AsyncBridge()

            async def fetch_async(self, url: str) -> str:
                return await self._do_fetch(url)

            def fetch_sync(self, url: str) -> str:
                return self._bridge.run(self._do_fetch(url))
    """

    def __init__(self, executor: ThreadPoolExecutor | None = None):
        """
        Initialize the bridge.

        Args:
            executor: Optional custom executor for blocking operations
        """
        self._executor = executor

    def run(self, coro: Awaitable[T]) -> T:
        """
        Run a coroutine from sync context.

        Args:
            coro: The coroutine to run

        Returns:
            The result of the coroutine
        """
        return run_sync(coro)

    async def run_blocking(self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        """
        Run a blocking function from async context.

        Args:
            func: The blocking function
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            The result of the function
        """
        loop = asyncio.get_running_loop()
        executor = self._executor or _get_default_executor()

        if kwargs:
            func_with_args = functools.partial(func, *args, **kwargs)
            return await loop.run_in_executor(executor, func_with_args)
        else:
            return await loop.run_in_executor(executor, func, *args)


# =============================================================================
# UTILITIES
# =============================================================================


def is_async_context() -> bool:
    """
    Check if currently running in an async context.

    Returns:
        True if there's a running event loop, False otherwise

    Example:
        if is_async_context():
            result = await async_operation()
        else:
            result = run_sync(async_operation())
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


async def gather_with_concurrency(limit: int, *coros: Awaitable[T]) -> list[T]:
    """
    Run coroutines with a concurrency limit.

    Like asyncio.gather but limits how many coroutines run simultaneously.

    Args:
        limit: Maximum concurrent coroutines
        *coros: Coroutines to run

    Returns:
        List of results in the same order as input coroutines

    Example:
        results = await gather_with_concurrency(
            3,  # Max 3 concurrent
            fetch(url1),
            fetch(url2),
            fetch(url3),
            fetch(url4),
            fetch(url5),
        )
    """
    semaphore = asyncio.Semaphore(limit)

    async def limited_coro(coro: Awaitable[T]) -> T:
        async with semaphore:
            return await coro

    return await asyncio.gather(*(limited_coro(c) for c in coros))


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "AsyncBridge",
    # Configuration
    "configure_executor",
    # Wrappers
    "ensure_async",
    "ensure_sync",
    "gather_with_concurrency",
    # Utilities
    "is_async_context",
    # Async -> Sync
    "run_async",
    "run_async_with_timeout",
    # Sync -> Async
    "run_sync",
    "run_sync_new_loop",
    "shutdown_executor",
    # Context managers
    "sync_context",
]
