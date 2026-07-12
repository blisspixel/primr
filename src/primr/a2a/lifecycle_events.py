"""Ordering and response helpers for A2A long-job lifecycle events."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CancelRaceResponse:
    """Truthful response when cancellation does not win the terminal race."""

    error_type: str
    message: str


def cancel_race_response(status: str) -> CancelRaceResponse:
    """Describe terminal races separately from unconfirmed cancellation."""
    if status == "completed":
        return CancelRaceResponse(
            "job_already_terminal",
            "Job completed before cancellation could take effect",
        )
    if status == "failed":
        return CancelRaceResponse(
            "job_already_terminal",
            "Job failed before cancellation could take effect",
        )
    if status == "already_terminal":
        return CancelRaceResponse(
            "job_already_terminal",
            "Job reached a terminal state before cancellation could take effect",
        )
    return CancelRaceResponse(
        "cancellation_failed",
        "Cancellation could not be confirmed; the job was not marked cancelled",
    )


class A2ALifecycleEvents:
    """Order progress before exactly one terminal event for each job."""

    def __init__(self) -> None:
        self._cancel_pending: set[str] = set()
        self._terminal_emitted: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}

    def begin_cancel(self, job_id: str) -> None:
        self._cancel_pending.add(job_id)

    def end_cancel(self, job_id: str) -> None:
        self._cancel_pending.discard(job_id)

    def cancel_is_pending(self, job_id: str) -> bool:
        return job_id in self._cancel_pending

    def _lock(self, job_id: str) -> asyncio.Lock:
        lock = self._locks.get(job_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[job_id] = lock
        return lock

    async def enqueue_terminal_once(
        self,
        *,
        job_id: str,
        event_queue: Any,
        event: Any,
    ) -> bool:
        """Enqueue at most one terminal event across research and cancel calls."""
        async with self._lock(job_id):
            if job_id in self._terminal_emitted:
                return False
            await event_queue.enqueue_event(event)
            self._terminal_emitted.add(job_id)
            return True

    async def enqueue_progress_if_current(
        self,
        *,
        job_id: str,
        research_task: asyncio.Task[Any],
        event_queue: Any,
        event: Any,
    ) -> bool:
        """Suppress progress after settlement or while cancellation is pending."""
        async with self._lock(job_id):
            if (
                research_task.done()
                or job_id in self._cancel_pending
                or job_id in self._terminal_emitted
            ):
                return False
            await event_queue.enqueue_event(event)
            return True


__all__ = ["A2ALifecycleEvents", "CancelRaceResponse", "cancel_race_response"]
