"""A2A task store adapter wrapping Primr's SingleJobStore.

Maps A2A task IDs to Primr job IDs, enforcing the single-job model
across both MCP and A2A protocols.

Requires: pip install primr[a2a]
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from a2a.server.tasks import TaskStore
from a2a.types import Artifact, Message, Part, Role, Task, TaskState, TaskStatus, TextPart

from primr.a2a.call_context import context_client_id

if TYPE_CHECKING:
    from a2a.server.context import ServerCallContext

    from primr.a2a.types import A2ATaskMapping
    from primr.mcp_server.job_store import ResearchJobState, SingleJobStore

logger = logging.getLogger(__name__)

# Map Primr stages to A2A task states
_STAGE_TO_STATE: dict[str, TaskState] = {
    "idle": TaskState.submitted,
    "accepted": TaskState.submitted,
    "scraping": TaskState.working,
    "extracting": TaskState.working,
    "deep_research": TaskState.working,
    "writing": TaskState.working,
    "qa": TaskState.working,
    "completed": TaskState.completed,
    "failed": TaskState.failed,
    "cancelled": TaskState.canceled,
}


def _job_to_task_state(job: ResearchJobState) -> TaskState:
    """Map a Primr job stage to an A2A TaskState."""
    return _STAGE_TO_STATE.get(job.current_stage.value, TaskState.unknown)


def _agent_message(
    text: str,
    task_id: str | None,
    context_id: str | None,
    message_id: str,
) -> Message:
    return Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text=text))],
        message_id=message_id,
        task_id=task_id,
        context_id=context_id,
    )


def _job_to_task(job: ResearchJobState, task_id: str, context_id: str) -> Task:
    """Convert a Primr job to an A2A Task object."""
    state = _job_to_task_state(job)

    message_text = f"Research job {job.job_id}: {job.current_stage.value}"
    if job.stage_progress_percent is not None:
        message_text += f" ({job.stage_progress_percent}%)"
    if job.error_message:
        message_text += f" - {job.error_message}"

    status = TaskStatus(
        state=state,
        message=_agent_message(
            message_text,
            task_id,
            context_id,
            f"status-{job.job_id}",
        ),
    )

    task = Task(
        id=task_id,
        context_id=context_id,
        status=status,
    )

    # Attach artifacts if completed
    if state == TaskState.completed and job.output_paths:
        task.artifacts = [
            Artifact(
                artifact_id=f"report-{job.job_id}",
                parts=[
                    Part(
                        root=TextPart(
                            text=f"Report available at: {', '.join(job.output_paths)}",
                        )
                    )
                ],
            )
        ]

    return task


class PrimrTaskStore(TaskStore):
    """A2A TaskStore backed by Primr's SingleJobStore.

    Maintains a mapping from A2A task IDs to Primr job IDs.
    Thread-safe via lock.
    """

    def __init__(self, job_store: SingleJobStore):
        self._job_store = job_store
        self._mappings: dict[str, A2ATaskMapping] = {}
        self._lock = threading.Lock()

    def register_mapping(self, mapping: A2ATaskMapping) -> None:
        """Register a task-to-job mapping."""
        with self._lock:
            self._mappings[mapping.task_id] = mapping
            logger.debug(
                "Registered A2A task mapping: %s -> job %s",
                mapping.task_id,
                mapping.job_id,
            )

    def get_mapping(self, task_id: str) -> A2ATaskMapping | None:
        """Get the mapping for an A2A task ID."""
        with self._lock:
            return self._mappings.get(task_id)

    def get_job_id(self, task_id: str) -> str | None:
        """Get the Primr job ID for an A2A task ID."""
        mapping = self.get_mapping(task_id)
        return mapping.job_id if mapping else None

    async def get(self, task_id: str, context: ServerCallContext | None = None) -> Task | None:
        """Get a task by ID, translating from Primr job state."""
        mapping = self.get_mapping(task_id)
        if not mapping:
            return None

        job = self._job_store.get(mapping.job_id)
        if not job:
            return None
        if context_client_id(context) != job.owner_client_id:
            return None

        return _job_to_task(job, task_id, context_id=task_id)

    async def save(self, task: Task, context: ServerCallContext | None = None) -> None:
        """Save is a no-op - Primr job store is the source of truth."""
        del context
        logger.debug("PrimrTaskStore.save called for task %s (no-op)", task.id)

    async def delete(self, task_id: str, context: ServerCallContext | None = None) -> None:
        """Remove a task mapping."""
        del context
        with self._lock:
            self._mappings.pop(task_id, None)
            logger.debug("Removed A2A task mapping: %s", task_id)
