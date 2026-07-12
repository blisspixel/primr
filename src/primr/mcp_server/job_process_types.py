"""Lifecycle records shared by the local supervised-job controller."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import BinaryIO, Literal, TypeVar

from primr.mcp_server.windows_job import WindowsJobObject

_T = TypeVar("_T")

CancellationReason = Literal["user_cancelled", "server_shutdown"]
CancellationStatus = Literal[
    "cancelled",
    "completed",
    "failed",
    "already_terminal",
    "not_running",
    "cancellation_failed",
]


@dataclass(frozen=True)
class CancellationOutcome:
    """Observed result of a local worker cancellation request."""

    status: CancellationStatus
    worker_exit_confirmed: bool
    termination_method: str | None = None
    error_message: str | None = None


@dataclass
class WorkerHandle:
    """One retained subprocess and its controller-owned lifecycle state."""

    job_id: str
    process: asyncio.subprocess.Process
    stderr_file: BinaryIO
    company_url: str
    mode: str
    budget_usd: float | None
    monitor_task: asyncio.Task[None] | None = None
    terminal_snapshot: dict | None = None
    terminal_exit_reason: str | None = None
    expected_sequence: int = 1
    ready: bool = False
    ready_event: asyncio.Event | None = None
    protocol_error: str | None = None
    cancel_reason: CancellationReason | None = None
    cancellation_task: asyncio.Task[CancellationOutcome] | None = None
    termination_method: str | None = None
    done: asyncio.Event | None = None
    windows_job: WindowsJobObject | None = None
    exit_observed: bool = False
    tree_cleanup_confirmed: bool = False
    tree_cleanup_error: str | None = None
    finalization_lock: asyncio.Lock | None = None


async def await_task_uninterruptibly(task: asyncio.Task[_T]) -> _T:
    """Wait for retained cleanup work despite repeated caller cancellation."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()


__all__ = [
    "CancellationOutcome",
    "CancellationReason",
    "CancellationStatus",
    "WorkerHandle",
    "await_task_uninterruptibly",
]
