"""Shared A2A task status event construction."""

from a2a.types import Message, TaskState, TaskStatus, TaskStatusUpdateEvent
from a2a.utils import new_agent_text_message


def status_message(text: str, task_id: str | None, context_id: str | None) -> Message:
    return new_agent_text_message(text, task_id=task_id, context_id=context_id)


def status_update_event(
    *,
    state: TaskState,
    text: str,
    task_id: str,
    context_id: str,
    final: bool,
) -> TaskStatusUpdateEvent:
    return TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        final=final,
        status=TaskStatus(
            state=state,
            message=status_message(text, task_id=task_id, context_id=context_id),
        ),
    )


__all__ = ["status_message", "status_update_event"]
