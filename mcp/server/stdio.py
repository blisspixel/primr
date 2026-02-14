"""Minimal stdio transport shim."""

from contextlib import asynccontextmanager


@asynccontextmanager
async def stdio_server():
    """Yield dummy read/write streams for tests."""
    yield (None, None)
