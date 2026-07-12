"""Compatibility policy for provisional worker terminal events."""

from __future__ import annotations

import signal

from primr.mcp_server.job_process_types import CancellationReason
from primr.mcp_server.job_store import ResearchJobState
from primr.mcp_server.types import ResearchStage

WORKER_EXIT_SUCCESS = 0
WORKER_EXIT_FAILURE = 1
WORKER_EXIT_CANCELLED = 130
WINDOWS_TERMINATE_PROCESS_EXIT = 1
WINDOWS_CONTROL_C_EXIT = 0xC000013A
WINDOWS_CONTROL_C_EXIT_SIGNED = WINDOWS_CONTROL_C_EXIT - (1 << 32)
_WINDOWS_DIRECT_FORCE_METHODS = frozenset(
    {
        "kill_process_fallback",
        "terminate_process_fallback",
        "terminate_job_object_and_process",
    }
)


def terminal_event_is_compatible(
    proposed: ResearchJobState,
    *,
    exit_reason: str | None,
    return_code: int | None,
    cancel_reason: CancellationReason | None,
    termination_method: str | None,
) -> bool:
    """Require state, reason, return code, and parent intent to agree."""
    if proposed.current_stage == ResearchStage.COMPLETED:
        return return_code == WORKER_EXIT_SUCCESS and exit_reason == "completed"
    if proposed.current_stage == ResearchStage.FAILED:
        return return_code == WORKER_EXIT_FAILURE and exit_reason == (
            proposed.error_type or "failed"
        )
    if proposed.current_stage == ResearchStage.CANCELLED:
        return (
            cancel_reason == "user_cancelled"
            and exit_reason == "user_cancelled"
            and proposed.error_type == "user_cancelled"
            and is_cancel_return_code(return_code, termination_method)
        )
    return False


def is_cancel_return_code(return_code: int | None, method: str | None) -> bool:
    """Recognize cooperative and controller-forced cancellation exits."""
    if return_code == WORKER_EXIT_CANCELLED:
        return True
    if return_code in {-getattr(signal, "SIGTERM", 15), -getattr(signal, "SIGKILL", 9)}:
        return True
    if method == "ctrl_break" and return_code in {
        WINDOWS_CONTROL_C_EXIT,
        WINDOWS_CONTROL_C_EXIT_SIGNED,
    }:
        return True
    return bool(
        method in _WINDOWS_DIRECT_FORCE_METHODS and return_code == WINDOWS_TERMINATE_PROCESS_EXIT
    )


__all__ = ["is_cancel_return_code", "terminal_event_is_compatible"]
