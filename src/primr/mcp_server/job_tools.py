"""Focused MCP job lifecycle tool handlers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from primr.mcp_server.resource_auth import caller_can_manage_job
from primr.mcp_server.types import MCPErrorCode, ResearchStage
from primr.utils.logging_config import get_logger

if TYPE_CHECKING:
    from primr.mcp_server.server import PrimrMCPServer

logger = get_logger(__name__)


def _text(payload: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload))]


async def handle_cancel_job(
    mcp_server: PrimrMCPServer,
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """Cancel an owned job only after its supervised worker exits."""
    job_id = arguments.get("job_id")
    job = mcp_server.job_store.get(job_id)
    if not job:
        return _text(
            {
                "error": True,
                "error_type": "job_not_found",
                "error_code": MCPErrorCode.JOB_NOT_FOUND,
                "message": f"Job not found: {job_id}",
            }
        )

    # Authorize before returning state so this cannot become a job-id
    # existence oracle.
    if not caller_can_manage_job(mcp_server, job, client_id):
        return _text(
            {
                "error": True,
                "error_type": "job_not_found",
                "error_code": MCPErrorCode.JOB_NOT_FOUND,
                "message": f"Job not found: {job_id}",
            }
        )

    if job.current_stage == ResearchStage.CANCELLED:
        return _text(
            {
                "success": True,
                "job_id": job_id,
                "status": "cancelled",
                "worker_exit_confirmed": True,
                "termination_method": "already_exited",
                "message": "Job was already cancelled.",
            }
        )

    if job.is_terminal():
        return _text(
            {
                "error": True,
                "error_type": "job_already_terminal",
                "message": f"Job {job_id} is already {job.get_status().value}",
            }
        )

    if getattr(mcp_server, "_skip_background_tasks", False):
        # Test and embedding mode creates no worker. The accepted but never
        # started job can be cancelled directly.
        job.advance_stage(ResearchStage.CANCELLED)
        job.error_type = "user_cancelled"
        job.error_message = f"Cancelled before worker start by {client_id}"
        mcp_server.job_store.update(job)
        termination_method = "not_started"
    else:
        outcome = await mcp_server.job_supervisor.cancel(job_id)
        if outcome.status != "cancelled":
            terminal_outcome = outcome.status in {"completed", "failed", "already_terminal"}
            error_type = "job_already_terminal" if terminal_outcome else "cancellation_failed"
            if outcome.error_message:
                message = outcome.error_message
            elif outcome.status == "completed":
                message = "Job completed before cancellation could take effect"
            elif outcome.status == "failed":
                message = "Job failed before cancellation could take effect"
            elif outcome.status == "already_terminal":
                message = "Job reached a terminal state before cancellation could take effect"
            else:
                message = "Worker exit could not be confirmed"
            return _text(
                {
                    "error": True,
                    "error_type": error_type,
                    "job_id": job_id,
                    "status": outcome.status,
                    "worker_exit_confirmed": outcome.worker_exit_confirmed,
                    "message": message,
                }
            )
        termination_method = outcome.termination_method

    logger.info("Job %s cancelled by %s", job_id, client_id)
    return _text(
        {
            "success": True,
            "job_id": job_id,
            "status": "cancelled",
            "worker_exit_confirmed": True,
            "termination_method": termination_method,
            "message": "Job cancelled. Any partial artifacts have been preserved.",
        }
    )


__all__ = ["handle_cancel_job"]
