"""A2A AgentExecutor bridging A2A protocol to Primr's pipeline.

Dispatches incoming A2A messages to the appropriate Primr tool handler
based on skill_id, translating between A2A message format and Primr internals.

Requires: pip install primr[a2a]
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.types import TaskState, TaskStatus, TaskStatusUpdateEvent
from a2a.utils import new_agent_text_message
from typing_extensions import override

from primr.a2a.types import A2ATaskMapping
from primr.mcp_server.pipeline_runner import PipelineRunner, get_doctor_status, run_qa_analysis

if TYPE_CHECKING:
    from a2a.server.events import EventQueue

    from primr.a2a.task_store import PrimrTaskStore
    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)

# Poll interval for long-running jobs (seconds)
_JOB_POLL_INTERVAL = 5


class PrimrAgentExecutor(AgentExecutor):
    """A2A executor that bridges to Primr's research pipeline.

    Skill dispatch:
        - estimate_research → synchronous cost estimate
        - research_company  → async job, streams progress via SSE
        - check_jobs        → synchronous job status
        - run_qa            → synchronous QA analysis
        - system_health     → synchronous doctor check
    """

    def __init__(self, mcp_server: PrimrMCPServer, task_store: PrimrTaskStore):
        self._mcp = mcp_server
        self._task_store = task_store
        self._runners: dict[str, PipelineRunner] = {}

    @override
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Dispatch incoming A2A message to appropriate handler."""
        message = context.message
        skill_id = _extract_skill_id(message)
        text = _extract_text(message)

        logger.info("A2A execute: skill=%s, text=%s", skill_id, text[:100] if text else "")

        try:
            if skill_id == "estimate_research":
                await self._handle_estimate(text, event_queue)
            elif skill_id == "research_company":
                await self._handle_research(text, context, event_queue)
            elif skill_id == "check_jobs":
                await self._handle_check_jobs(event_queue)
            elif skill_id == "run_qa":
                await self._handle_qa(text, event_queue)
            elif skill_id == "system_health":
                await self._handle_doctor(event_queue)
            else:
                await self._handle_unknown(skill_id, text, event_queue)
        except Exception:
            logger.exception("A2A executor error for skill=%s", skill_id)
            event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.failed,
                        message={
                            "role": "agent",
                            "parts": [{"kind": "text", "text": "Internal error processing request"}],
                            "messageId": str(uuid.uuid4()),
                        },
                    ),
                )
            )

    @override
    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Cancel a running research task."""
        task_id = context.task_id
        if not task_id:
            event_queue.enqueue_event(new_agent_text_message("No task ID to cancel"))
            return

        job_id = self._task_store.get_job_id(task_id)
        if not job_id:
            event_queue.enqueue_event(new_agent_text_message(f"No job found for task {task_id}"))
            return

        runner = self._runners.get(job_id)
        if runner:
            runner.request_cancel()
            logger.info("Cancel requested for task %s (job %s)", task_id, job_id)

        event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(
                    state=TaskState.canceled,
                    message={
                        "role": "agent",
                        "parts": [{"kind": "text", "text": f"Cancellation requested for job {job_id}"}],
                        "messageId": str(uuid.uuid4()),
                    },
                ),
            )
        )

    # -------------------------------------------------------------------------
    # Skill handlers
    # -------------------------------------------------------------------------

    async def _handle_estimate(self, text: str, event_queue: EventQueue) -> None:
        """Handle estimate_research skill — synchronous."""
        params = _parse_research_params(text)
        company_url = params.get("url", "")

        if not company_url:
            event_queue.enqueue_event(
                new_agent_text_message("Please provide a company URL to estimate.")
            )
            return

        # Validate URL
        url_result = self._mcp.url_validator.validate(company_url)
        if not url_result.valid:
            event_queue.enqueue_event(
                new_agent_text_message(f"Invalid URL: {url_result.error_message}")
            )
            return

        from primr.utils.cost_estimator import estimate_cost

        mode = params.get("mode", "full")
        mode_mapping = {"scrape": "scrape-only", "deep": "deep-research", "full": "complete", "premium": "premium"}
        estimator_mode = mode_mapping.get(mode, "complete")
        try:
            estimate = estimate_cost(estimator_mode, use_historical=False)
            event_queue.enqueue_event(new_agent_text_message(json.dumps(estimate, indent=2, default=str)))
        except Exception as e:
            event_queue.enqueue_event(new_agent_text_message(f"Estimate failed: {e}"))

    async def _handle_research(
        self,
        text: str,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle research_company skill — async with SSE streaming."""
        params = _parse_research_params(text)
        company_url = params.get("url", "")
        company_name = params.get("name", "Unknown")
        mode = params.get("mode", "full")

        if not company_url:
            event_queue.enqueue_event(
                new_agent_text_message("Please provide a company URL to research.")
            )
            return

        # Validate URL
        url_result = self._mcp.url_validator.validate(company_url)
        if not url_result.valid:
            event_queue.enqueue_event(
                new_agent_text_message(f"Invalid URL: {url_result.error_message}")
            )
            return

        # Create job in the shared job store
        try:
            job = self._mcp.job_store.create(
                company_name=company_name,
                mode=mode,
                owner_client_id="a2a",
            )
        except Exception as e:
            event_queue.enqueue_event(new_agent_text_message(f"Cannot start research: {e}"))
            return

        # Register A2A task mapping
        task_id = context.task_id or str(uuid.uuid4())
        mapping = A2ATaskMapping(
            task_id=task_id,
            job_id=job.job_id,
            skill_id="research_company",
        )
        self._task_store.register_mapping(mapping)

        # Signal task is working
        event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(
                    state=TaskState.working,
                    message={
                        "role": "agent",
                        "parts": [{"kind": "text", "text": f"Research started: job {job.job_id}"}],
                        "messageId": str(uuid.uuid4()),
                    },
                ),
            )
        )

        # Start pipeline in background
        runner = PipelineRunner(self._mcp)
        self._runners[job.job_id] = runner

        async def _run_and_stream() -> None:
            try:
                research_task = asyncio.create_task(
                    runner.run_research(
                        job=job,
                        company_url=company_url,
                        mode=mode,
                    )
                )

                # Poll job store and emit progress events
                while not research_task.done():
                    await asyncio.sleep(_JOB_POLL_INTERVAL)
                    current_job = self._mcp.job_store.get(job.job_id)
                    if current_job:
                        progress = (
                            f"{current_job.current_stage.value}"
                            + (f" ({current_job.stage_progress_percent}%)"
                               if current_job.stage_progress_percent
                               else "")
                        )
                        event_queue.enqueue_event(
                            TaskStatusUpdateEvent(
                                status=TaskStatus(
                                    state=TaskState.working,
                                    message={
                                        "role": "agent",
                                        "parts": [{"kind": "text", "text": progress}],
                                        "messageId": str(uuid.uuid4()),
                                    },
                                ),
                            )
                        )

                # Wait for completion
                await research_task

                # Final status
                final_job = self._mcp.job_store.get(job.job_id)
                if final_job and final_job.is_terminal():
                    from primr.mcp_server.job_store import ResearchStage

                    if final_job.current_stage == ResearchStage.COMPLETED:
                        paths = ", ".join(final_job.output_paths) if final_job.output_paths else "N/A"
                        event_queue.enqueue_event(
                            TaskStatusUpdateEvent(
                                status=TaskStatus(
                                    state=TaskState.completed,
                                    message={
                                        "role": "agent",
                                        "parts": [{"kind": "text", "text": f"Research complete. Output: {paths}"}],
                                        "messageId": str(uuid.uuid4()),
                                    },
                                ),
                            )
                        )
                    else:
                        error_msg = final_job.error_message or "Unknown error"
                        event_queue.enqueue_event(
                            TaskStatusUpdateEvent(
                                status=TaskStatus(
                                    state=TaskState.failed,
                                    message={
                                        "role": "agent",
                                        "parts": [{"kind": "text", "text": f"Research failed: {error_msg}"}],
                                        "messageId": str(uuid.uuid4()),
                                    },
                                ),
                            )
                        )
            except Exception:
                logger.exception("Research pipeline error for job %s", job.job_id)
                event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(
                            state=TaskState.failed,
                            message={
                                "role": "agent",
                                "parts": [{"kind": "text", "text": "Research pipeline error"}],
                                "messageId": str(uuid.uuid4()),
                            },
                        ),
                    )
                )
            finally:
                self._runners.pop(job.job_id, None)

        # Run in background — the event_queue bridges to SSE
        task = asyncio.create_task(_run_and_stream())
        self._mcp._track_task(task)

    async def _handle_check_jobs(self, event_queue: EventQueue) -> None:
        """Handle check_jobs skill — synchronous."""
        active = self._mcp.job_store.get_active()
        if active:
            progress = active.stage_progress_percent or 0
            result = {
                "job_id": active.job_id,
                "company": active.company_name,
                "stage": active.current_stage.value,
                "progress": progress,
                "status": "in_progress",
            }
        else:
            terminal = self._mcp.job_store.get_latest_terminal()
            if terminal:
                result = {
                    "job_id": terminal.job_id,
                    "company": terminal.company_name,
                    "stage": terminal.current_stage.value,
                    "status": terminal.current_stage.value,
                }
            else:
                result = {"status": "idle", "message": "No active or recent jobs"}

        event_queue.enqueue_event(new_agent_text_message(json.dumps(result, indent=2)))

    async def _handle_qa(self, text: str, event_queue: EventQueue) -> None:
        """Handle run_qa skill — synchronous."""
        params = _parse_research_params(text)
        report_path = params.get("path", "")

        if not report_path:
            # Try to find latest report from most recent job
            terminal = self._mcp.job_store.get_latest_terminal()
            if terminal and terminal.output_paths:
                report_path = terminal.output_paths[0]
            else:
                event_queue.enqueue_event(
                    new_agent_text_message("Please provide a report path for QA analysis.")
                )
                return

        try:
            qa_result = await run_qa_analysis(report_path)
            event_queue.enqueue_event(
                new_agent_text_message(json.dumps(qa_result, indent=2, default=str))
            )
        except Exception as e:
            event_queue.enqueue_event(new_agent_text_message(f"QA analysis failed: {e}"))

    async def _handle_doctor(self, event_queue: EventQueue) -> None:
        """Handle system_health skill — synchronous."""
        try:
            status = get_doctor_status()
            event_queue.enqueue_event(
                new_agent_text_message(json.dumps(status, indent=2, default=str))
            )
        except Exception as e:
            event_queue.enqueue_event(new_agent_text_message(f"Health check failed: {e}"))

    async def _handle_unknown(
        self, skill_id: str | None, text: str, event_queue: EventQueue
    ) -> None:
        """Handle unrecognized skill — try to route by content."""
        available = "estimate_research, research_company, check_jobs, run_qa, system_health"
        event_queue.enqueue_event(
            new_agent_text_message(
                f"Unknown skill '{skill_id}'. Available skills: {available}"
            )
        )


# =============================================================================
# Helpers
# =============================================================================

def _extract_skill_id(message: Any) -> str | None:
    """Extract skill_id from an A2A message."""
    if isinstance(message, dict):
        metadata = message.get("metadata", {})
        if isinstance(metadata, dict):
            return metadata.get("skillId")
    # Try attribute access for SDK message objects
    if hasattr(message, "metadata") and message.metadata:
        if isinstance(message.metadata, dict):
            return message.metadata.get("skillId")
    return None


def _extract_text(message: Any) -> str:
    """Extract text content from an A2A message."""
    parts = []
    if isinstance(message, dict):
        parts = message.get("parts", [])
    elif hasattr(message, "parts"):
        parts = message.parts or []

    texts = []
    for part in parts:
        if isinstance(part, dict):
            if part.get("kind") == "text":
                texts.append(part.get("text", ""))
        elif hasattr(part, "kind") and part.kind == "text":
            texts.append(getattr(part, "text", ""))
    return " ".join(texts)


def _parse_research_params(text: str) -> dict[str, str]:
    """Parse research parameters from message text.

    Supports both JSON format and natural language extraction.
    """
    # Try JSON first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Simple keyword extraction
    params: dict[str, str] = {}
    words = text.split()
    for word in words:
        if word.startswith(("http://", "https://")):
            params["url"] = word
            break

    # Extract mode if mentioned
    for mode in ("scrape", "deep", "full", "premium"):
        if mode in text.lower():
            params["mode"] = mode
            break

    # Try to extract company name (first few words before URL)
    if "url" in params:
        idx = text.find(params["url"])
        if idx > 0:
            name = text[:idx].strip().rstrip("at").strip()
            if name:
                params["name"] = name

    return params
