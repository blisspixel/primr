"""A2A AgentExecutor bridging A2A protocol to Primr's pipeline.

Dispatches incoming A2A messages to the appropriate Primr tool handler
based on skill_id, translating between A2A message format and Primr internals.

Requires: pip install primr[a2a]
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.types import Message, TaskState, TaskStatus, TaskStatusUpdateEvent
from a2a.utils import new_agent_text_message
from typing_extensions import override  # noqa: UP035 - mypy resolves override here, not typing

from primr.a2a.authz import (
    A2ASkillAuthorizationDecision,
    a2a_scope_denied_text,
    authorize_a2a_skill,
)
from primr.a2a.input_parsing import (
    parse_research_params as _parse_research_params,
)
from primr.a2a.input_parsing import (
    research_arguments_from_a2a_params as _research_arguments_from_a2a_params,
)
from primr.a2a.resource_reads import handle_a2a_resource_read, resource_read_skill_list
from primr.a2a.skill_ids import A2A_RESOURCE_READ_SKILLS
from primr.a2a.types import A2ATaskMapping
from primr.mcp_server.approval_tokens import (
    enforce_approval_token,
    issue_approval_token,
    research_approval_args,
)
from primr.mcp_server.pipeline_runner import PipelineRunner, get_doctor_status, run_qa_analysis
from primr.mcp_server.research_policy import (
    build_research_estimate,
    coerce_budget_usd,
    enforce_cost_cap,
)

if TYPE_CHECKING:
    from a2a.server.events import EventQueue

    from primr.a2a.task_store import PrimrTaskStore
    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)

# Poll interval for long-running jobs (seconds)
_JOB_POLL_INTERVAL = 5


def _status_message(text: str, task_id: str | None, context_id: str | None) -> Message:
    return new_agent_text_message(text, task_id=task_id, context_id=context_id)


def _status_update_event(
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
            message=_status_message(text, task_id=task_id, context_id=context_id),
        ),
    )


class PrimrAgentExecutor(AgentExecutor):
    """A2A executor that bridges to Primr's research pipeline.

    Skill dispatch:
        - estimate_research -> synchronous cost estimate
        - research_company  -> async job, streams progress via SSE
        - check_jobs        -> synchronous job status
        - run_qa            -> synchronous QA analysis
        - read_report_by_job -> synchronous explicit owned-job report read
        - read_calibration_summary_by_job -> synchronous compact job calibration summary
        - read_artifacts_by_job -> synchronous compact job artifact metadata
        - read_qa_summary_by_job -> synchronous compact job QA summary
        - read_usage_summary_by_job -> synchronous compact job usage summary
        - read_source_summary_by_job -> synchronous compact job source summary
        - read_trace_summary_by_job -> synchronous compact job scrape trace summary
        - read_verification_summary_by_job -> synchronous compact job verification summary
        - read_stage_scorecard -> synchronous compact eval scorecard summary
        - system_health     -> synchronous doctor check
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
        started_at = time.perf_counter()
        audit_payload: dict[str, Any] | None = None
        caught_exception: BaseException | None = None

        logger.info("A2A execute: skill=%s, text=%s", skill_id, text[:100] if text else "")

        try:
            decision = authorize_a2a_skill(skill_id, getattr(self._mcp, "_auth_context", None))
            if not decision.allowed:
                audit_payload = _scope_denial_payload(skill_id, decision)
                await self._enqueue_scope_denial(skill_id, decision, context, event_queue)
                return

            if skill_id == "estimate_research":
                audit_payload = await self._handle_estimate(text, event_queue)
            elif skill_id == "research_company":
                audit_payload = await self._handle_research(text, context, event_queue)
            elif skill_id == "check_jobs":
                audit_payload = await self._handle_check_jobs(event_queue)
            elif skill_id == "run_qa":
                audit_payload = await self._handle_qa(text, event_queue)
            elif skill_id in A2A_RESOURCE_READ_SKILLS:
                audit_payload = await handle_a2a_resource_read(
                    skill_id,
                    text,
                    event_queue,
                    mcp_server=self._mcp,
                    client_id=_a2a_client_id(self._mcp),
                )
            elif skill_id == "system_health":
                audit_payload = await self._handle_doctor(event_queue)
            else:
                audit_payload = await self._handle_unknown(skill_id, text, event_queue)
        except Exception as exc:
            caught_exception = exc
            audit_payload = {"error": True, "error_type": exc.__class__.__name__}
            logger.exception("A2A executor error for skill=%s", skill_id)
            task_id = context.task_id
            context_id = context.context_id or task_id
            if task_id and context_id:
                await event_queue.enqueue_event(
                    _status_update_event(
                        state=TaskState.failed,
                        text="Internal error processing request",
                        task_id=task_id,
                        context_id=context_id,
                        final=True,
                    )
                )
            else:
                await event_queue.enqueue_event(
                    new_agent_text_message("Internal error processing request")
                )
        finally:
            self._record_a2a_skill_audit(
                skill_id=skill_id,
                arguments={"skill_id": skill_id, "text": text},
                result_payload=audit_payload,
                started_at=started_at,
                exception=caught_exception,
            )

    @override
    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Cancel a running research task."""
        started_at = time.perf_counter()
        audit_payload: dict[str, Any] | None = None
        caught_exception: BaseException | None = None
        task_id = context.task_id
        decision = authorize_a2a_skill("cancel_task", getattr(self._mcp, "_auth_context", None))
        try:
            if not decision.allowed:
                audit_payload = _scope_denial_payload("cancel_task", decision)
                await self._enqueue_scope_denial("cancel_task", decision, context, event_queue)
                return

            if not task_id:
                audit_payload = {"error": True, "error_type": "missing_task_id"}
                await event_queue.enqueue_event(new_agent_text_message("No task ID to cancel"))
                return

            job_id = self._task_store.get_job_id(task_id)
            if not job_id:
                audit_payload = {"error": True, "error_type": "job_not_found"}
                await event_queue.enqueue_event(
                    new_agent_text_message(f"No job found for task {task_id}")
                )
                return

            job = self._mcp.job_store.get(job_id)
            if job is None or not _caller_owns_job(job, _a2a_client_id(self._mcp)):
                audit_payload = {
                    "error": True,
                    "error_type": "job_not_found",
                    "job_id": job_id,
                }
                await event_queue.enqueue_event(
                    new_agent_text_message(f"No job found for task {task_id}")
                )
                return

            runner = self._runners.get(job_id)
            if runner:
                runner.request_cancel()
                logger.info("Cancel requested for task %s (job %s)", task_id, job_id)

            context_id = context.context_id or task_id
            audit_payload = {"status": "cancel_requested", "job_id": job_id}
            await event_queue.enqueue_event(
                _status_update_event(
                    state=TaskState.canceled,
                    text=f"Cancellation requested for job {job_id}",
                    task_id=task_id,
                    context_id=context_id,
                    final=True,
                )
            )
        except Exception as exc:
            caught_exception = exc
            audit_payload = {"error": True, "error_type": exc.__class__.__name__}
            raise
        finally:
            self._record_a2a_skill_audit(
                skill_id="cancel_task",
                arguments={"skill_id": "cancel_task", "task_id": task_id},
                result_payload=audit_payload,
                started_at=started_at,
                exception=caught_exception,
            )

    def _record_a2a_skill_audit(
        self,
        *,
        skill_id: str | None,
        arguments: dict[str, Any],
        result_payload: dict[str, Any] | None,
        started_at: float,
        exception: BaseException | None = None,
    ) -> None:
        auth_context = getattr(self._mcp, "_auth_context", None)
        self._mcp.audit_log.record_a2a_skill_call(
            skill_id=skill_id,
            arguments=arguments,
            result_payload=result_payload,
            auth_context=auth_context,
            client_id=_a2a_client_id(self._mcp),
            started_at=started_at,
            exception=exception,
        )

    async def _enqueue_scope_denial(
        self,
        skill_id: str | None,
        decision: A2ASkillAuthorizationDecision,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Emit a terminal A2A denial without invoking the skill handler."""
        text = a2a_scope_denied_text(skill_id, decision)
        task_id = context.task_id
        context_id = context.context_id or task_id
        if task_id and context_id:
            await event_queue.enqueue_event(
                _status_update_event(
                    state=TaskState.failed,
                    text=text,
                    task_id=task_id,
                    context_id=context_id,
                    final=True,
                )
            )
            return

        await event_queue.enqueue_event(new_agent_text_message(text))

    # -------------------------------------------------------------------------
    # Skill handlers
    # -------------------------------------------------------------------------

    async def _handle_estimate(self, text: str, event_queue: EventQueue) -> dict[str, Any]:
        """Handle estimate_research skill - synchronous."""
        params = _parse_research_params(text)
        arguments = _research_arguments_from_a2a_params(params)
        company_url = str(arguments.get("company_url") or "")

        if not company_url:
            await event_queue.enqueue_event(
                new_agent_text_message("Please provide a company URL to estimate.")
            )
            return {"error": True, "error_type": "missing_url"}

        # Validate URL
        url_result = self._mcp.url_validator.validate(company_url)
        if not url_result.valid:
            await event_queue.enqueue_event(
                new_agent_text_message(f"Invalid URL: {url_result.error_message}")
            )
            return {"error": True, "error_type": "invalid_url"}

        try:
            estimate = build_research_estimate(arguments)
            estimate.update(
                issue_approval_token(
                    tool_name="research_company",
                    approval_args=research_approval_args(arguments),
                    max_cost_usd=float(estimate["estimated_cost_usd"]),
                )
            )
            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(estimate, indent=2, default=str))
            )
            payload: dict[str, Any] = {"status": "estimated"}
            payload.update(
                {
                    "estimated_cost_usd": estimate.get("estimated_cost_usd"),
                    "estimated_time_minutes": estimate.get("estimated_time_minutes"),
                    "approval_token_id": estimate.get("approval_token_id"),
                }
            )
            return payload
        except Exception:
            # Don't echo the raw exception — provider errors can contain
            # internal hostnames, file paths, or API-key fragments. The
            # operator-side log has the full traceback.
            logger.exception("A2A estimate failed")
            await event_queue.enqueue_event(
                new_agent_text_message("Estimate failed (see server logs)")
            )
            return {"error": True, "error_type": "estimate_failed"}

    async def _handle_research(
        self,
        text: str,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> dict[str, Any]:
        """Handle research_company skill - async with SSE streaming."""
        params = _parse_research_params(text)
        arguments = _research_arguments_from_a2a_params(params)
        company_url = str(arguments.get("company_url") or "")
        company_name = str(arguments.get("company_name") or "Unknown")
        mode = str(arguments.get("mode") or "full")
        platform = arguments.get("platform")
        skip_qa = bool(arguments.get("skip_qa", False))
        verify = bool(arguments.get("verify", False))
        destination = arguments.get("destination")
        max_estimated_cost_usd = arguments.get("max_estimated_cost_usd")

        if not company_url:
            await event_queue.enqueue_event(
                new_agent_text_message("Please provide a company URL to research.")
            )
            return {"error": True, "error_type": "missing_url"}

        # Validate URL
        url_result = self._mcp.url_validator.validate(company_url)
        if not url_result.valid:
            await event_queue.enqueue_event(
                new_agent_text_message(f"Invalid URL: {url_result.error_message}")
            )
            return {"error": True, "error_type": "invalid_url"}

        # Validate company name. It is interpolated into report filenames and
        # the working-folder path downstream, so '../', '/', '\\', or drive
        # prefixes could otherwise write artifacts outside OUTPUT_DIR. The CLI
        # and MCP research_company entry points already gate this; the A2A
        # handler must too.
        from primr.utils.validators import InputValidationError, validate_company_name

        try:
            company_name = validate_company_name(company_name)
        except InputValidationError as e:
            await event_queue.enqueue_event(
                new_agent_text_message(f"Invalid company name: {e.reason}")
            )
            return {"error": True, "error_type": "invalid_company_name"}

        if bool(arguments.get("no_ai_strategy", False)):
            platform = None

        if destination is not None:
            dest_result = self._mcp.path_validator.validate(
                str(destination),
                _a2a_client_id(self._mcp),
            )
            if not dest_result.valid:
                payload = {
                    "error": True,
                    "error_type": dest_result.error_type,
                    "message": f"Invalid destination: {dest_result.error_message}",
                }
                await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload)))
                return payload
            destination = str(dest_result.resolved_path)

        estimate = build_research_estimate(arguments)
        estimated_cost_usd = float(estimate["estimated_cost_usd"])
        cost_cap_error = enforce_cost_cap(
            estimated_cost=estimated_cost_usd,
            max_estimated_cost_usd=max_estimated_cost_usd,
            operation_name="research_company",
        )
        if cost_cap_error is not None:
            payload = dict(cost_cap_error)
            payload.setdefault("estimated_cost_usd", estimated_cost_usd)
            await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload)))
            return payload

        approval_error = enforce_approval_token(
            tool_name="research_company",
            approval_args=research_approval_args(arguments),
            estimated_cost_usd=estimated_cost_usd,
            approval_token=arguments.get("approval_token"),
        )
        if approval_error is not None:
            payload = dict(approval_error)
            payload["estimated_cost_usd"] = estimated_cost_usd
            payload["max_estimated_cost_usd"] = coerce_budget_usd(max_estimated_cost_usd)
            await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload)))
            return payload

        budget_usd = coerce_budget_usd(max_estimated_cost_usd)

        # Create job in the shared job store
        try:
            job = self._mcp.job_store.create(
                company_name=company_name,
                mode=mode,
                owner_client_id=_a2a_client_id(self._mcp),
            )
        except Exception:
            logger.exception("A2A job_store.create failed for %s", company_name)
            await event_queue.enqueue_event(
                new_agent_text_message("Cannot start research (see server logs)")
            )
            return {"error": True, "error_type": "job_create_failed"}

        # Register A2A task mapping
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or task_id
        mapping = A2ATaskMapping(
            task_id=task_id,
            job_id=job.job_id,
            skill_id="research_company",
        )
        self._task_store.register_mapping(mapping)

        # Signal task is working
        await event_queue.enqueue_event(
            _status_update_event(
                state=TaskState.working,
                text=f"Research started: job {job.job_id}",
                task_id=task_id,
                context_id=context_id,
                final=False,
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
                        platform=str(platform) if platform else None,
                        skip_qa=skip_qa,
                        verify=verify,
                        destination=str(destination) if destination else None,
                        budget_usd=budget_usd,
                    )
                )

                # Poll job store and emit progress events
                while not research_task.done():
                    await asyncio.sleep(_JOB_POLL_INTERVAL)
                    current_job = self._mcp.job_store.get(job.job_id)
                    if current_job:
                        progress = f"{current_job.current_stage.value}" + (
                            f" ({current_job.stage_progress_percent}%)"
                            if current_job.stage_progress_percent
                            else ""
                        )
                        await event_queue.enqueue_event(
                            _status_update_event(
                                state=TaskState.working,
                                text=progress,
                                task_id=task_id,
                                context_id=context_id,
                                final=False,
                            )
                        )

                # Wait for completion
                await research_task

                # Final status
                final_job = self._mcp.job_store.get(job.job_id)
                if final_job and final_job.is_terminal():
                    from primr.mcp_server.job_store import ResearchStage

                    if final_job.current_stage == ResearchStage.COMPLETED:
                        paths = (
                            ", ".join(final_job.output_paths) if final_job.output_paths else "N/A"
                        )
                        await event_queue.enqueue_event(
                            _status_update_event(
                                state=TaskState.completed,
                                text=f"Research complete. Output: {paths}",
                                task_id=task_id,
                                context_id=context_id,
                                final=True,
                            )
                        )
                    else:
                        error_msg = final_job.error_message or "Unknown error"
                        await event_queue.enqueue_event(
                            _status_update_event(
                                state=TaskState.failed,
                                text=f"Research failed: {error_msg}",
                                task_id=task_id,
                                context_id=context_id,
                                final=True,
                            )
                        )
            except Exception:
                logger.exception("Research pipeline error for job %s", job.job_id)
                await event_queue.enqueue_event(
                    _status_update_event(
                        state=TaskState.failed,
                        text="Research pipeline error",
                        task_id=task_id,
                        context_id=context_id,
                        final=True,
                    )
                )
            finally:
                self._runners.pop(job.job_id, None)

        # Run in background - the event_queue bridges to SSE
        task = asyncio.create_task(_run_and_stream())
        self._mcp._track_task(task)
        return {
            "status": "started",
            "job_id": job.job_id,
            "estimated_cost_usd": estimated_cost_usd,
            "max_estimated_cost_usd": budget_usd,
        }

    async def _handle_check_jobs(self, event_queue: EventQueue) -> dict[str, Any]:
        """Handle check_jobs skill - synchronous.

        Only return job metadata for jobs the caller owns; otherwise report
        idle. Without this gate any authenticated A2A client could enumerate
        other tenants' active research and harvest output_paths from completed
        runs.
        """
        active = self._mcp.job_store.get_active()
        result: dict[str, object]
        from primr.job_status import build_job_status

        owner_client_id = _a2a_client_id(self._mcp)
        if active and _caller_owns_job(active, owner_client_id):
            progress = active.stage_progress_percent or 0
            canonical = build_job_status(
                job_id=active.job_id,
                source="agent_job",
                status=active.get_status(),
                company_name=active.company_name,
                mode=active.mode,
                stage=active.current_stage,
                percent=active.stage_progress_percent,
                possibly_stuck=active.is_possibly_stuck(),
                started_at=active.start_time,
                updated_at=active.last_heartbeat_time,
                artifacts_available=None,
            )
            result = {
                "job_status": canonical,
                "job_id": active.job_id,
                "company": active.company_name,
                "stage": active.current_stage.value,
                "progress": progress,
                "status": "in_progress",
            }
        else:
            terminal = self._mcp.job_store.get_latest_terminal()
            if terminal and _caller_owns_job(terminal, owner_client_id):
                stage = terminal.current_stage.value
                canonical = build_job_status(
                    job_id=terminal.job_id,
                    source="agent_job",
                    status=terminal.get_status(),
                    company_name=terminal.company_name,
                    mode=terminal.mode,
                    stage=terminal.current_stage,
                    percent=terminal.stage_progress_percent,
                    possibly_stuck=False,
                    started_at=terminal.start_time,
                    updated_at=terminal.last_heartbeat_time,
                    completed_at=terminal.completion_time,
                    artifacts_available=bool(terminal.output_paths),
                    error_message=terminal.error_message,
                    error_code=terminal.error_type,
                    error_source="agent_job" if terminal.error_message else None,
                )
                result = {
                    "job_status": canonical,
                    "job_id": terminal.job_id,
                    "company": terminal.company_name,
                    "stage": stage,
                    "status": stage
                    if stage in ("completed", "failed", "cancelled")
                    else "finished",
                    "artifact_metadata_uri": (f"primr://output/artifacts/by_job/{terminal.job_id}"),
                    "report_read_uri": f"primr://output/report/by_job/{terminal.job_id}",
                    "output_paths_available": bool(terminal.output_paths),
                }
            else:
                result = {
                    "job_status": build_job_status(source="agent_job", status="idle"),
                    "status": "idle",
                    "message": "No active or recent jobs",
                }

        await event_queue.enqueue_event(new_agent_text_message(json.dumps(result, indent=2)))
        return result

    async def _handle_qa(self, text: str, event_queue: EventQueue) -> dict[str, Any]:
        """Handle run_qa skill - synchronous."""
        params = _parse_research_params(text)
        report_path = params.get("path", "")

        if not report_path:
            # Try to find the caller's latest report from the most recent job. Don't
            # auto-target jobs created by stdio/MCP — leaking another tenant's
            # report path via A2A would defeat the by_job ownership gate.
            terminal = self._mcp.job_store.get_latest_terminal()
            if (
                terminal
                and _caller_owns_job(terminal, _a2a_client_id(self._mcp))
                and terminal.output_paths
            ):
                report_path = terminal.output_paths[0]
            else:
                await event_queue.enqueue_event(
                    new_agent_text_message("Please provide a report path for QA analysis.")
                )
                return {"error": True, "error_type": "missing_report_path"}

        try:
            qa_result = await run_qa_analysis(report_path)
            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(qa_result, indent=2, default=str))
            )
            return qa_result if isinstance(qa_result, dict) else {"status": "qa_completed"}
        except Exception:
            logger.exception("A2A QA analysis failed for %s", report_path)
            await event_queue.enqueue_event(
                new_agent_text_message("QA analysis failed (see server logs)")
            )
            return {"error": True, "error_type": "qa_failed"}

    async def _handle_doctor(self, event_queue: EventQueue) -> dict[str, Any]:
        """Handle system_health skill - synchronous."""
        try:
            status = get_doctor_status()
            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(status, indent=2, default=str))
            )
            return status if isinstance(status, dict) else {"status": "healthy"}
        except Exception:
            logger.exception("A2A health check failed")
            await event_queue.enqueue_event(
                new_agent_text_message("Health check failed (see server logs)")
            )
            return {"error": True, "error_type": "health_check_failed"}

    async def _handle_unknown(
        self, skill_id: str | None, text: str, event_queue: EventQueue
    ) -> dict[str, Any]:
        """Handle unrecognized skill - try to route by content."""
        available = (
            "estimate_research, research_company, check_jobs, run_qa, "
            f"{resource_read_skill_list()}, system_health"
        )
        await event_queue.enqueue_event(
            new_agent_text_message(f"Unknown skill '{skill_id}'. Available skills: {available}")
        )
        return {"error": True, "error_type": "unknown_skill"}


# =============================================================================
# Helpers
# =============================================================================


def _extract_skill_id(message: Any) -> str | None:
    """Extract skill_id from an A2A message."""
    if isinstance(message, dict):
        metadata = message.get("metadata", {})
        if isinstance(metadata, dict):
            return metadata.get("skillId")
        return None
    # Try attribute access for SDK message objects
    metadata = getattr(message, "metadata", None)
    if isinstance(metadata, dict):
        return metadata.get("skillId")
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


def _a2a_client_id(mcp_server: Any) -> str:
    """Return the authenticated A2A client id, or the local A2A owner id."""
    context = getattr(mcp_server, "_auth_context", None)
    if context is not None and getattr(context, "is_authenticated", False):
        client_id = getattr(context, "client_id", None)
        if isinstance(client_id, str) and client_id:
            return client_id
    return "a2a"


def _caller_owns_job(job: Any, client_id: str) -> bool:
    """Return whether an A2A caller owns a job."""
    return getattr(job, "owner_client_id", None) == client_id


def _scope_denial_payload(
    skill_id: str | None,
    decision: A2ASkillAuthorizationDecision,
) -> dict[str, Any]:
    """Return the structured denial payload emitted to the caller."""
    return json.loads(a2a_scope_denied_text(skill_id, decision))
