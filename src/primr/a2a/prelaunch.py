"""Durable A2A job transitions before a worker assumes ownership."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, TypeVar

from primr.mcp_server.types import ResearchStage
from primr.utils.logging_config import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2a.server.events import EventQueue

    from primr.mcp_server.job_store import ResearchJobState, SingleJobStore

logger = get_logger(__name__)
_T = TypeVar("_T")


def terminalize_prelaunch_job(
    job_store: SingleJobStore,
    job: ResearchJobState,
    *,
    error_type: str,
    error_message: str,
    terminal_stage: ResearchStage = ResearchStage.FAILED,
) -> None:
    """Commit a terminal job when no retained worker owns its lifecycle."""
    if job.is_terminal():
        return
    job.error_type = error_type
    job.error_message = error_message
    if not job.advance_stage(terminal_stage):
        logger.error("Could not terminalize prelaunch A2A job %s", job.job_id)
        return
    try:
        job_store.update(job)
    except Exception:
        logger.exception("Could not persist terminal prelaunch A2A job %s", job.job_id)


async def publish_working_status(
    *,
    job_store: SingleJobStore,
    job: ResearchJobState,
    event_queue: EventQueue,
    event: Any,
) -> None:
    """Publish ownership intent or terminalize the still-unowned job."""
    try:
        await event_queue.enqueue_event(event)
    except asyncio.CancelledError:
        terminalize_prelaunch_job(
            job_store,
            job,
            error_type="a2a_request_cancelled_before_worker_start",
            error_message="A2A request cancelled before worker start",
            terminal_stage=ResearchStage.CANCELLED,
        )
        raise
    except Exception:
        terminalize_prelaunch_job(
            job_store,
            job,
            error_type="a2a_working_event_failed",
            error_message="Could not publish A2A working event before worker start",
        )
        raise


async def start_worker_or_terminalize(
    *,
    job_store: SingleJobStore,
    job: ResearchJobState,
    start_worker: Callable[[], Awaitable[_T]],
) -> _T:
    """Transfer ownership to a worker while preserving terminal job truth."""
    try:
        return await start_worker()
    except asyncio.CancelledError:
        terminalize_prelaunch_job(
            job_store,
            job,
            error_type="worker_start_cancelled",
            error_message="Worker startup was cancelled before ownership completed",
        )
        raise
    except Exception:
        terminalize_prelaunch_job(
            job_store,
            job,
            error_type="worker_spawn_failed",
            error_message="Research worker failed to start",
        )
        raise
