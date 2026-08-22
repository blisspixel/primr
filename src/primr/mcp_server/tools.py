"""
Tool handler implementations for MCP server.

This module provides executable tools for research operations:
- estimate_run - Cost/time estimates
- estimate_strategy - Strategy cost/time estimates
- research_company - Initiate research pipeline
- generate_strategy - Generate strategy documents
- check_jobs - Check Deep Research job status
- run_qa - Run quality assessment
- doctor - System health check
- clear_jobs - Clear stale jobs
- cancel_job - Cancel active job

Agentic tools (from agentic_tools.py):
- query_roadmap - Query roadmap for version status, blockers, features
- get_hypotheses - Retrieve hypotheses for a company
- save_hypothesis - Save or update a hypothesis

Requirements: 5.1-5.13, 6.1-6.7, 7.1-7.6, 8.1-8.6, 18.1-18.12
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from mcp.server import Server
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from primr.mcp_server import research_validation
from primr.mcp_server.agentic_tools import handle_agentic_tool, register_agentic_tools
from primr.mcp_server.approval_tokens import (
    approval_token_audit,
    bind_runtime_budget,
    enforce_approval_token,
    issue_approval_token,
    research_approval_args,
    strategy_approval_args,
)
from primr.mcp_server.audit_log import audit_tool_calls
from primr.mcp_server.cloud_diagnostics import get_cloud_diagnostics as _get_cloud_diagnostics
from primr.mcp_server.job_responses import build_job_response, include_artifacts_requested
from primr.mcp_server.job_store import JobInProgressError, ResearchJobState
from primr.mcp_server.job_tools import handle_cancel_job as _handle_cancel_job
from primr.mcp_server.platforms import normalize_platform
from primr.mcp_server.research_policy import (
    build_research_estimate as _build_research_estimate,
)
from primr.mcp_server.research_policy import (
    coerce_budget_usd as _coerce_budget_usd,
)
from primr.mcp_server.research_policy import (
    enforce_cost_cap as _enforce_cost_cap,
)
from primr.mcp_server.resource_auth import (
    caller_can_inline_legacy_report_content,
    caller_can_manage_job,
    caller_can_read_report,
    caller_client_id,
    caller_is_local_stdio,
    caller_owns_job_resource,
)
from primr.mcp_server.server_context import MCPServerContext
from primr.mcp_server.skill_pack_tools import handle_skill_pack_tool, register_skill_pack_tools
from primr.mcp_server.strategy_operations import run_strategy_generation
from primr.mcp_server.tool_authz import (
    TOOL_REQUIRED_SCOPES,
    authorize_tool_call,
    scope_denied_response,
)
from primr.mcp_server.tool_catalog import build_base_tools
from primr.mcp_server.types import MCPErrorCode

logger = logging.getLogger(__name__)
_normalize_platform = normalize_platform


def register_tools(server: Server, mcp_server: MCPServerContext) -> None:
    """Register all Primr tools with the MCP server."""

    # Get agentic tools
    agentic_tools = register_agentic_tools(server, mcp_server)
    # Get skill-pack tools (estimate_skill_pack, generate_skill_pack)
    skill_pack_tools = register_skill_pack_tools(server, mcp_server)

    async def list_tools() -> list[Tool]:
        """List available tools."""
        return build_base_tools() + agentic_tools + skill_pack_tools

    @audit_tool_calls(lambda: mcp_server)
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        import json

        # Rate limiting and authz use a trusted transport-aware caller id.
        ctx = getattr(mcp_server, "_auth_context", None)
        client_id = caller_client_id(mcp_server)

        if not (authz := authorize_tool_call(name, ctx)).allowed:
            return scope_denied_response(name, authz)

        rate_limit_bucket = name if name in TOOL_REQUIRED_SCOPES else "unknown_tool"
        rate_result = mcp_server.rate_limiter.check_and_record(client_id, rate_limit_bucket)
        if not rate_result.allowed:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": True,
                            "error_type": "rate_limit_exceeded",
                            "error_code": MCPErrorCode.RATE_LIMIT_EXCEEDED,
                            "message": "Rate limit exceeded",
                            "retry_after_seconds": rate_result.retry_after_seconds,
                        }
                    ),
                )
            ]

        # Try agentic tools first
        agentic_result = await handle_agentic_tool(name, arguments, mcp_server)
        if agentic_result is not None:
            return agentic_result

        # Try skill_pack tools
        skill_pack_result = await handle_skill_pack_tool(name, arguments, mcp_server)
        if skill_pack_result is not None:
            return skill_pack_result

        # Dispatch to handler
        if name == "estimate_run":
            return await _handle_estimate_run(mcp_server, arguments)
        elif name == "estimate_strategy":
            return await _handle_estimate_strategy(arguments)
        elif name == "research_company":
            return await _handle_research_company(mcp_server, arguments, client_id)
        elif name == "generate_strategy":
            return await _handle_generate_strategy(mcp_server, arguments)
        elif name == "check_jobs":
            return await _handle_check_jobs(mcp_server, arguments, client_id)
        elif name == "run_qa":
            return await _handle_run_qa(mcp_server, arguments)
        elif name == "doctor":
            return await _handle_doctor(mcp_server, arguments)
        elif name == "clear_jobs":
            return await _handle_clear_jobs(mcp_server, arguments, client_id)
        elif name == "cancel_job":
            return await _handle_cancel_job(mcp_server, arguments, client_id)
        elif name == "wait_for_status_change":
            return await _handle_wait_for_status_change(mcp_server, arguments, client_id)
        elif name == "delegate_to_agent":
            return await _handle_delegate_to_agent(mcp_server, arguments)
        elif name == "show_usage":
            return await _handle_show_usage(mcp_server, client_id)

        # Spec 2026-07-28: an unknown tool is a protocol-level Invalid Params
        # error, not tool-execution failure content.
        raise MCPError(INVALID_PARAMS, f"Unknown tool: {name}")

    async def _on_list_tools(
        _ctx: object, _params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=await list_tools())

    async def _on_call_tool(_ctx: object, params: CallToolRequestParams) -> CallToolResult:
        return CallToolResult(content=list(await call_tool(params.name, params.arguments or {})))

    server.add_request_handler("tools/list", PaginatedRequestParams, _on_list_tools)
    server.add_request_handler("tools/call", CallToolRequestParams, _on_call_tool)


async def _handle_estimate_run(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle estimate_run tool.

    Requirements: 18.1, 18.2, 18.3
    """
    import json

    if validation_error := research_validation.validate_research_estimate_arguments(arguments):
        return [TextContent(type="text", text=json.dumps(validation_error))]

    company_url = arguments.get("company_url")

    # Validate URL
    url_result = mcp_server.url_validator.validate(company_url)
    if not url_result.valid:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": url_result.error_type,
                        "error_code": {
                            "invalid_url": MCPErrorCode.INVALID_URL,
                            "ssrf_blocked": MCPErrorCode.SSRF_BLOCKED,
                            "url_unreachable": MCPErrorCode.URL_UNREACHABLE,
                        }.get(url_result.error_type, MCPErrorCode.INVALID_URL),
                        "message": url_result.error_message,
                    }
                ),
            )
        ]

    estimate = _build_research_estimate(arguments)
    estimate.update(
        issue_approval_token(
            tool_name="research_company",
            approval_args=research_approval_args(arguments),
            max_cost_usd=float(estimate["estimated_cost_usd"]),
        )
    )

    return [
        TextContent(
            type="text",
            text=json.dumps(estimate),
        )
    ]


async def _handle_estimate_strategy(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle estimate_strategy tool."""
    import json

    from primr.mcp_server.resources import get_strategy_catalog

    strategy_type = arguments.get("strategy_type")
    platform = arguments.get("platform")
    if platform:
        platform = _normalize_platform(platform)

    strategy = next((item for item in get_strategy_catalog() if item["id"] == strategy_type), None)
    if strategy is None:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "invalid_strategy_type",
                        "message": f"Unknown strategy type: {strategy_type}",
                    }
                ),
            )
        ]

    if strategy["requires_platform"] and not platform:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "missing_platform",
                        "message": "platform is required for ai_strategy estimates",
                    }
                ),
            )
        ]

    estimated_cost_usd = float(cast("float", strategy["estimated_cost_usd"]))
    payload = {
        "strategy_type": strategy["id"],
        "estimated_cost_usd": estimated_cost_usd,
        "estimated_time_minutes": strategy["estimated_time_minutes"],
        "requires_platform": strategy["requires_platform"],
        "platform": platform,
        "cost_basis": strategy["cost_basis"],
        "cost_warning": (
            "Strategy generation incurs real API charges. Get explicit user approval "
            "before generate_strategy."
        ),
    }
    payload.update(
        issue_approval_token(
            tool_name="generate_strategy",
            approval_args=strategy_approval_args(arguments),
            max_cost_usd=estimated_cost_usd,
        )
    )
    return [TextContent(type="text", text=json.dumps(payload))]


async def _handle_research_company(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle research_company tool.

    Returns immediately with job_id (async model).
    Starts background task to run research pipeline (unless disabled for testing).

    Requirements: 5.1-5.13
    """
    import json

    if validation_error := research_validation.validate_research_execution_arguments(arguments):
        return [TextContent(type="text", text=json.dumps(validation_error))]

    company_name = arguments.get("company_name")
    company_url = arguments.get("company_url")
    mode = arguments.get("mode", "full")
    platform = arguments.get("platform")
    skip_qa = arguments.get("skip_qa", False)
    verify = arguments.get("verify", False)
    max_estimated_cost_usd = arguments.get("max_estimated_cost_usd")
    destination = arguments.get("destination")

    # The fast pipeline uses company_name in report and working-folder paths.
    # Reject traversal and drive prefixes before artifacts are written.
    from primr.utils.validators import InputValidationError, validate_company_name

    try:
        company_name = validate_company_name(company_name or "")
    except InputValidationError as e:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "invalid_company_name",
                        "message": e.reason,
                    }
                ),
            )
        ]

    # destination is documented as output/-scoped, so validate it through the
    # same path guard used for report_path tools before mkdir()/copy2().
    if destination is not None:
        dest_result = mcp_server.path_validator.validate(destination, client_id)
        if not dest_result.valid:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": True,
                            "error_type": dest_result.error_type,
                            "error_code": MCPErrorCode.PATH_TRAVERSAL_BLOCKED,
                            "message": f"Invalid destination: {dest_result.error_message}",
                        }
                    ),
                )
            ]
        destination = str(dest_result.resolved_path)

    # Keep execution shape aligned with the estimate: no_ai_strategy lowers the
    # approved cost, so it must also suppress platform-driven strategy work.
    no_ai_strategy = arguments.get("no_ai_strategy", False)
    if platform is not None:
        platform = _normalize_platform(platform)
    if no_ai_strategy or mode not in ("full", "premium"):
        platform = None
    elif platform is None:
        platform = "agnostic"

    # Validate URL
    url_result = mcp_server.url_validator.validate(company_url)
    if not url_result.valid:
        error_code = {
            "invalid_url": MCPErrorCode.INVALID_URL,
            "ssrf_blocked": MCPErrorCode.SSRF_BLOCKED,
            "url_unreachable": MCPErrorCode.URL_UNREACHABLE,
        }.get(url_result.error_type, MCPErrorCode.INVALID_URL)

        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": url_result.error_type,
                        "error_code": error_code,
                        "message": url_result.error_message,
                    }
                ),
            )
        ]

    estimate = _build_research_estimate(arguments)
    cost_cap_error = _enforce_cost_cap(
        estimated_cost=float(estimate["estimated_cost_usd"]),
        max_estimated_cost_usd=max_estimated_cost_usd,
        operation_name="research_company",
    )
    if cost_cap_error is not None:
        return [TextContent(type="text", text=json.dumps(cost_cap_error))]
    approval_error = enforce_approval_token(
        tool_name="research_company",
        approval_args=research_approval_args(arguments),
        estimated_cost_usd=float(estimate["estimated_cost_usd"]),
        approval_token=arguments.get("approval_token"),
    )
    if approval_error is not None:
        return [TextContent(type="text", text=json.dumps(approval_error))]
    budget_usd = bind_runtime_budget(
        _coerce_budget_usd(max_estimated_cost_usd),
        arguments.get("approval_token"),
    )

    # Try to create job
    try:
        job = mcp_server.job_store.create(
            company_name=company_name,
            mode=mode,
            owner_client_id=client_id,
        )
    except JobInProgressError as e:
        active = mcp_server.job_store.get(e.active_job_id)
        may_identify_active_job = active is not None and caller_can_manage_job(
            mcp_server,
            active,
            client_id,
        )
        payload: dict[str, Any] = {
            "error": True,
            "error_type": "job_in_progress",
            "error_code": MCPErrorCode.JOB_IN_PROGRESS,
            "message": "A research job is already in progress",
        }
        if may_identify_active_job:
            payload["message"] = f"Job {e.active_job_id} already in progress"
            payload["active_job_id"] = e.active_job_id
        return [
            TextContent(
                type="text",
                text=json.dumps(payload),
            )
        ]

    token_audit = approval_token_audit(arguments.get("approval_token"))
    approved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    job.governance_audit = {
        "estimate": {
            "cost_usd": float(estimate["estimated_cost_usd"]),
            "time_minutes": int(estimate["estimated_time_minutes"]),
            "estimated_at": token_audit["estimated_at"] if token_audit else approved_at,
        },
        "approval": {
            "approval_token_id": token_audit["approval_token_id"] if token_audit else None,
            "approved_at": approved_at,
            "bound_to_estimate": token_audit is not None,
        },
        "approved_ceiling_usd": budget_usd,
    }
    mcp_server.job_store.update(job)

    # Start a supervised worker process for the research pipeline.
    # Skip if _skip_background_tasks is set (for testing)
    if not getattr(mcp_server, "_skip_background_tasks", False):
        try:
            task = await mcp_server.job_supervisor.start(
                job=job,
                company_url=company_url,
                mode=mode,
                platform=platform,
                skip_qa=skip_qa,
                verify=verify,
                destination=destination,
                budget_usd=budget_usd,
            )
            # Track the process monitor for graceful shutdown.
            mcp_server._track_task(task)
        except Exception:
            logger.exception("Failed to start research worker for job %s", job.job_id)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": True,
                            "error_type": "worker_spawn_failed",
                            "message": "Research worker failed to start",
                            "job_id": job.job_id,
                        }
                    ),
                )
            ]

    logger.info("Created research job %s for %s", job.job_id, company_name)

    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "job_id": job.job_id,
                    "accepted": True,
                    "status_uri": "primr://research/status",
                }
            ),
        )
    ]


async def _handle_generate_strategy(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Handle generate_strategy with the shared validated execution boundary."""
    from primr.mcp_server.strategy_tool_handler import handle_generate_strategy

    return await handle_generate_strategy(
        mcp_server,
        arguments,
        estimate_handler=_handle_estimate_strategy,
        strategy_runner=run_strategy_generation,
    )


async def _handle_check_jobs(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle check_jobs tool.

    Status reads are owner-gated. Authenticated HTTP callers receive metadata
    and explicit report-resource pointers.

    Requirements: 7.1-7.6
    """
    import json

    job_id = arguments.get("job_id")
    include_artifacts = include_artifacts_requested(
        arguments,
        local_stdio=caller_is_local_stdio(mcp_server),
    )
    report_scope_granted = caller_can_read_report(mcp_server)
    include_report_content = caller_can_inline_legacy_report_content(mcp_server)

    jobs = []

    def response_for(job: ResearchJobState) -> dict[str, Any]:
        return build_job_response(
            job,
            include_artifacts=include_artifacts,
            include_report_content=include_report_content,
            report_scope_granted=report_scope_granted,
        )

    if job_id:
        # Check specific job
        job = mcp_server.job_store.get(job_id)
        # Return 404 whether the job is missing OR owned by someone else, so
        # the caller cannot probe for the existence of another client's jobs.
        if not job or not caller_owns_job_resource(mcp_server, job, client_id):
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": True,
                            "error_type": "job_not_found",
                            "error_code": MCPErrorCode.JOB_NOT_FOUND,
                            "message": f"Job not found: {job_id}",
                        }
                    ),
                )
            ]
        jobs.append(response_for(job))
    else:
        # Return active plus latest terminal, but only if owned by this client.
        active = mcp_server.job_store.get_active()
        if active and caller_owns_job_resource(mcp_server, active, client_id):
            jobs.append(response_for(active))

        terminal = mcp_server.job_store.get_latest_terminal()
        if (
            terminal
            and caller_owns_job_resource(mcp_server, terminal, client_id)
            and (not active or terminal.job_id != active.job_id)
        ):
            jobs.append(response_for(terminal))

    return [
        TextContent(
            type="text",
            text=json.dumps({"jobs": jobs}),
        )
    ]


async def _handle_run_qa(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle run_qa tool.

    Requirements: 8.1-8.6
    """
    import json

    report_path = arguments.get("report_path")

    # Validate path
    path_result = mcp_server.path_validator.validate(report_path)
    if not path_result.valid:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": path_result.error_type,
                        "error_code": MCPErrorCode.PATH_TRAVERSAL_BLOCKED,
                        "message": path_result.error_message,
                    }
                ),
            )
        ]

    # Check if file exists
    if not path_result.resolved_path.exists():
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "report_not_found",
                        "error_code": MCPErrorCode.REPORT_NOT_FOUND,
                        "message": f"Report not found: {report_path}",
                    }
                ),
            )
        ]

    # Run QA analysis
    try:
        from primr.mcp_server.qa_operations import run_qa_analysis

        result = await run_qa_analysis(str(path_result.resolved_path))

        return [
            TextContent(
                type="text",
                text=json.dumps(result),
            )
        ]

    except Exception:
        # Same rationale as the strategy-generation handler: keep the
        # full traceback in the server log, return a generic message.
        logger.exception("QA analysis failed")
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "qa_analysis_failed",
                        "message": "QA analysis failed (see server logs)",
                    }
                ),
            )
        ]


async def _handle_doctor(
    mcp_server: MCPServerContext,
    _arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle doctor tool.

    In local mode: returns existing system health status.
    In cloud mode: adds Azure service diagnostics (Container App health,
    Cosmos DB, Blob Storage, Service Bus, App Insights, Cost Governor).

    Requirements: 18.4, 18.5, 10.7
    """
    import json

    from primr.mcp_server.cloud_detect import is_cloud_mode
    from primr.mcp_server.doctor_status import attach_cloud_diagnostics, get_doctor_status

    result = get_doctor_status(audit_log=mcp_server.audit_log)

    if is_cloud_mode():
        attach_cloud_diagnostics(result, await _get_cloud_diagnostics())
    else:
        result["cloud_mode"] = False

    return [
        TextContent(
            type="text",
            text=json.dumps(result, allow_nan=False),
        )
    ]


async def _handle_clear_jobs(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle clear_jobs tool.

    Owner-gated: HTTP clients can only clear jobs they own. Without this
    check, any authenticated HTTP caller could wipe another tenant's
    terminal job from the store (denial-of-service against the legitimate
    owner's job history). stdio retains full access.

    Requirements: 18.6, 18.7
    """
    import json

    older_than_hours = arguments.get("older_than_hours", 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)

    cleared_count = 0

    # In single-job model, just check if the job is old and terminal
    job = mcp_server.job_store.get_latest_terminal()
    if (
        job
        and job.completion_time
        and job.completion_time < cutoff
        and caller_owns_job_resource(mcp_server, job, client_id)
    ):
        mcp_server.job_store.clear()
        cleared_count = 1

    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "success": True,
                    "cleared_count": cleared_count,
                }
            ),
        )
    ]


async def _handle_wait_for_status_change(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle wait_for_status_change tool.

    Blocks until job status changes or timeout occurs. Ownership-gated like
    check_jobs: cross-client subscriptions to another user's job (which
    leaked progress, output_path, and error_message) return 404.
    """
    import json

    job_id = arguments.get("job_id")
    timeout_seconds = min(arguments.get("timeout_seconds", 60), 300)  # Cap at 5 minutes

    # Get current job state. Return 404 whether the job is missing OR owned
    # by someone else, so an attacker can't probe for live job IDs.
    job = mcp_server.job_store.get(job_id)
    if not job or not caller_owns_job_resource(mcp_server, job, client_id):
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "job_not_found",
                        "error_code": MCPErrorCode.JOB_NOT_FOUND,
                        "message": f"Job not found: {job_id}",
                    }
                ),
            )
        ]

    current_status = job.get_status()

    # If already terminal, return immediately
    if job.is_terminal():
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "job_id": job_id,
                        "status": current_status.value,
                        "changed": False,
                        "message": "Job is already in terminal state",
                        "output_path": job.output_paths[0] if job.output_paths else None,
                    }
                ),
            )
        ]

    # Wait for status change
    changed, new_status = await mcp_server.job_store.wait_for_status_change(
        job_id=job_id,
        current_status=current_status,
        timeout_seconds=timeout_seconds,
    )

    # Get updated job info
    job = mcp_server.job_store.get(job_id)
    if job is None:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "job_not_found",
                        "message": "Job disappeared while waiting",
                    }
                ),
            )
        ]

    result = {
        "job_id": job_id,
        "status": job.get_status().value,
        "previous_status": current_status.value,
        "changed": changed,
        "current_stage": job.current_stage.value,
        "stage_progress_percent": job.stage_progress_percent,
    }

    if job.is_terminal():
        result["output_path"] = job.output_paths[0] if job.output_paths else None
        if job.error_message:
            result["error_message"] = job.error_message

    if not changed:
        result["message"] = f"Timeout after {timeout_seconds}s, status unchanged"

    return [
        TextContent(
            type="text",
            text=json.dumps(result),
        )
    ]


async def _handle_show_usage(
    mcp_server: MCPServerContext,
    client_id: str,
) -> list[TextContent]:
    """
    Handle show_usage tool.

    In local mode (no cloud env vars), returns a message that budget tracking
    is only available in cloud deployment.
    In cloud mode, queries the Control Plane API's /usage/{api_key_hash} endpoint.

    Requirements: 6.8
    """
    import hashlib
    import json
    import os

    from primr.mcp_server.cloud_detect import is_cloud_mode

    if not is_cloud_mode():
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "message": "Budget tracking available in cloud deployment. Local usage is not tracked.",
                    }
                ),
            )
        ]

    # Cloud mode: query the Control Plane API
    control_plane_url = os.environ.get("PRIMR_CONTROL_PLANE_URL", "http://localhost:8000")
    api_key_hash = f"sha256:{hashlib.sha256(client_id.encode()).hexdigest()}"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as http_client:
            resp = await http_client.get(f"{control_plane_url}/usage/{api_key_hash}")
            resp.raise_for_status()
            usage_data = resp.json()

        return [
            TextContent(
                type="text",
                text=json.dumps(usage_data),
            )
        ]
    except Exception:
        logger.exception("Failed to fetch usage data")
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "usage_fetch_failed",
                        "message": "Failed to fetch usage data. Please try again later.",
                    }
                ),
            )
        ]


async def _handle_delegate_to_agent(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle delegate_to_agent tool by calling an external A2A agent.

    Guarded by ImportError: only available when primr[a2a] is installed.
    """
    import json

    try:
        from primr.a2a.client import A2AClient
    except ImportError:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "missing_dependency",
                        "message": "A2A support not installed. Run: pip install primr[a2a]",
                    }
                ),
            )
        ]

    agent_url = arguments.get("agent_url", "")
    message = arguments.get("message", "")
    skill_id = arguments.get("skill_id")

    # Validate URL via SSRF protection
    url_result = mcp_server.url_validator.validate(agent_url)
    if not url_result.valid:
        error_code = {
            "invalid_url": MCPErrorCode.INVALID_URL,
            "ssrf_blocked": MCPErrorCode.SSRF_BLOCKED,
            "url_unreachable": MCPErrorCode.URL_UNREACHABLE,
        }.get(url_result.error_type, MCPErrorCode.INVALID_URL)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": url_result.error_type,
                        "error_code": error_code,
                        "message": f"Agent URL blocked: {url_result.error_message}",
                    }
                ),
            )
        ]

    try:
        async with A2AClient(agent_url=agent_url) as client:
            result = await client.send_message(message=message, skill_id=skill_id)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception:
        from primr.utils.security import redact_url_for_log

        logger.exception("A2A delegation failed: %s", redact_url_for_log(agent_url))
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "a2a_delegation_failed",
                        "message": "A2A delegation failed. Check server logs for details.",
                    }
                ),
            )
        ]
