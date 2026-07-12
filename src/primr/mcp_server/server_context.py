"""Acyclic structural contract for modules that consume the MCP controller."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol


class MCPServerContext(Protocol):
    """Minimal shared controller surface without importing the server module."""

    audit_log: Any
    job_store: Any
    job_supervisor: Any
    path_validator: Any
    rate_limiter: Any
    url_validator: Any
    _auth_context_var: Any

    @property
    def transport(self) -> str:
        raise NotImplementedError

    @property
    def _auth_context(self) -> Any:
        raise NotImplementedError

    def _auth_context_from_scope(self, scope: Any) -> Any:
        raise NotImplementedError

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        raise NotImplementedError

    def controller_lifecycle(self) -> AbstractAsyncContextManager[None]:
        raise NotImplementedError


__all__ = ["MCPServerContext"]
