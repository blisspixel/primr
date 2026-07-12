"""Focused A2A research-task cancellation workflow."""

from __future__ import annotations

from typing import Any

from a2a.types import TaskState
from a2a.utils import new_agent_text_message

from primr.a2a.lifecycle_events import A2ALifecycleEvents, cancel_race_response
from primr.a2a.status_events import status_update_event
from primr.mcp_server.types import ResearchStage
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


async def handle_cancel_request(
    *,
    mcp_server: Any,
    task_store: Any,
    lifecycle_events: A2ALifecycleEvents,
    context: Any,
    event_queue: Any,
    client_id: str,
) -> dict[str, Any]:
    """Cancel one owned A2A task and return its audit payload."""
    task_id = context.task_id
    if not task_id:
        await event_queue.enqueue_event(new_agent_text_message("No task ID to cancel"))
        return {"error": True, "error_type": "missing_task_id"}

    job_id = task_store.get_job_id(task_id)
    if not job_id:
        await event_queue.enqueue_event(new_agent_text_message(f"No job found for task {task_id}"))
        return {"error": True, "error_type": "job_not_found"}

    job = mcp_server.job_store.get(job_id)
    if job is None or not _caller_can_cancel_job(mcp_server, job, client_id):
        await event_queue.enqueue_event(new_agent_text_message(f"No job found for task {task_id}"))
        return {"error": True, "error_type": "job_not_found", "job_id": job_id}

    context_id = context.context_id or task_id
    if job.current_stage == ResearchStage.CANCELLED:
        await lifecycle_events.enqueue_terminal_once(
            job_id=job_id,
            event_queue=event_queue,
            event=status_update_event(
                state=TaskState.canceled,
                text=f"Research already cancelled: job {job_id}",
                task_id=task_id,
                context_id=context_id,
                final=True,
            ),
        )
        return {
            "status": "cancelled",
            "job_id": job_id,
            "worker_exit_confirmed": True,
            "idempotent": True,
        }

    if job.is_terminal():
        await event_queue.enqueue_event(
            new_agent_text_message(f"Job {job_id} is already {job.get_status().value}")
        )
        return {"error": True, "error_type": "job_already_terminal", "job_id": job_id}

    if getattr(mcp_server, "_skip_background_tasks", False):
        job.advance_stage(ResearchStage.CANCELLED)
        job.error_type = "user_cancelled"
        job.error_message = "Cancelled before worker start"
        mcp_server.job_store.update(job)
        outcome_status = "cancelled"
        worker_exit_confirmed = True
    else:
        lifecycle_events.begin_cancel(job_id)
        try:
            outcome = await mcp_server.job_supervisor.cancel(job_id)
        finally:
            lifecycle_events.end_cancel(job_id)
        outcome_status = outcome.status
        worker_exit_confirmed = outcome.worker_exit_confirmed

    if outcome_status != "cancelled":
        response = cancel_race_response(outcome_status)
        await event_queue.enqueue_event(new_agent_text_message(response.message))
        return {
            "error": True,
            "error_type": response.error_type,
            "status": outcome_status,
            "job_id": job_id,
            "worker_exit_confirmed": worker_exit_confirmed,
        }

    logger.info("Cancelled task %s after worker exit (job %s)", task_id, job_id)
    await lifecycle_events.enqueue_terminal_once(
        job_id=job_id,
        event_queue=event_queue,
        event=status_update_event(
            state=TaskState.canceled,
            text=f"Research cancelled: job {job_id}",
            task_id=task_id,
            context_id=context_id,
            final=True,
        ),
    )
    return {
        "status": "cancelled",
        "job_id": job_id,
        "worker_exit_confirmed": worker_exit_confirmed,
    }


def _caller_can_cancel_job(mcp_server: Any, job: Any, client_id: str) -> bool:
    context = getattr(mcp_server, "_auth_context", None)
    if context is not None and getattr(context, "is_admin", False) is True:
        return True
    return getattr(job, "owner_client_id", None) == client_id


__all__ = ["handle_cancel_request"]
