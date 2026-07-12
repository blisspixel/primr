"""Deterministic ordering tests for A2A long-job lifecycle events."""

import asyncio

import pytest

from primr.a2a.lifecycle_events import A2ALifecycleEvents, cancel_race_response


class _Queue:
    def __init__(self) -> None:
        self.events = []
        self.progress_entered = asyncio.Event()
        self.release_progress = asyncio.Event()

    async def enqueue_event(self, event):
        if event == "progress-blocked":
            self.progress_entered.set()
            await self.release_progress.wait()
        self.events.append(event)


@pytest.mark.asyncio
async def test_progress_cannot_follow_terminal_event() -> None:
    lifecycle = A2ALifecycleEvents()
    queue = _Queue()
    research_task = asyncio.create_task(asyncio.sleep(30))
    try:
        assert await lifecycle.enqueue_terminal_once(
            job_id="job-1", event_queue=queue, event="terminal"
        )
        assert not await lifecycle.enqueue_progress_if_current(
            job_id="job-1",
            research_task=research_task,
            event_queue=queue,
            event="progress",
        )
        assert queue.events == ["terminal"]
    finally:
        research_task.cancel()
        await asyncio.gather(research_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_inflight_progress_is_ordered_before_terminal() -> None:
    lifecycle = A2ALifecycleEvents()
    queue = _Queue()
    research_task = asyncio.create_task(asyncio.sleep(30))
    progress = asyncio.create_task(
        lifecycle.enqueue_progress_if_current(
            job_id="job-1",
            research_task=research_task,
            event_queue=queue,
            event="progress-blocked",
        )
    )
    await queue.progress_entered.wait()
    terminal = asyncio.create_task(
        lifecycle.enqueue_terminal_once(job_id="job-1", event_queue=queue, event="terminal")
    )
    queue.release_progress.set()
    try:
        assert await progress
        assert await terminal
        assert queue.events == ["progress-blocked", "terminal"]
    finally:
        research_task.cancel()
        await asyncio.gather(research_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_pending_cancel_suppresses_progress_until_released() -> None:
    lifecycle = A2ALifecycleEvents()
    queue = _Queue()
    research_task = asyncio.create_task(asyncio.sleep(30))
    lifecycle.begin_cancel("job-1")
    try:
        assert not await lifecycle.enqueue_progress_if_current(
            job_id="job-1",
            research_task=research_task,
            event_queue=queue,
            event="progress",
        )
        lifecycle.end_cancel("job-1")
        assert await lifecycle.enqueue_progress_if_current(
            job_id="job-1",
            research_task=research_task,
            event_queue=queue,
            event="progress",
        )
    finally:
        research_task.cancel()
        await asyncio.gather(research_task, return_exceptions=True)


def test_cancel_race_response_distinguishes_terminal_from_unconfirmed() -> None:
    completed = cancel_race_response("completed")
    unconfirmed = cancel_race_response("cancellation_failed")
    assert completed.error_type == "job_already_terminal"
    assert "completed" in completed.message
    assert unconfirmed.error_type == "cancellation_failed"
    assert "could not be confirmed" in unconfirmed.message
