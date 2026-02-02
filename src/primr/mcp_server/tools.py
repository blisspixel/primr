"""
Tool handler implementations for MCP server.

This module provides executable tools for research operations:
- estimate_run - Cost/time estimates
- research_company - Initiate research pipeline
- generate_strategy - Generate strategy documents
- check_jobs - Check Deep Research job status
- run_qa - Run quality assessment
- doctor - System health check
- clear_jobs - Clear stale jobs
- cancel_job - Cancel active job

Requirements: 5.1-5.13, 6.1-6.7, 7.1-7.6, 8.1-8.6, 18.1-18.12
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from primr.mcp_server.job_store import JobInProgressError
from primr.mcp_server.types import (
    CloudVendor,
    JobStatus,
    MCPErrorCode,
    ResearchMode,
    ResearchStage,
    StrategyType,
)

if TYPE_CHECKING:
    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)


def register_tools(server: Server, mcp_server: "PrimrMCPServer") -> None:
    """Register all Primr tools with the MCP server."""

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="estimate_run",
                description="Estimate cost and time for a research run without executing",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "company_url": {
                            "type": "string",
                            "description": "Company website URL",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["scrape", "deep", "full"],
                            "default": "full",
                            "description": "Research mode",
                        },
                    },
                    "required": ["company_url"],
                },
            ),
            Tool(
                name="research_company",
                description="Initiate company research pipeline (async - returns job_id immediately)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "company_name": {
                            "type": "string",
                            "description": "Display name for the company",
                        },
                        "company_url": {
                            "type": "string",
                            "description": "Company website URL (must be valid HTTP/HTTPS)",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["scrape", "deep", "full"],
                            "default": "full",
                            "description": "Research mode",
                        },
                        "cloud_vendor": {
                            "type": "string",
                            "enum": ["azure", "aws", "gcp"],
                            "description": "Cloud vendor for AI strategy (optional)",
                        },
                        "skip_qa": {
                            "type": "boolean",
                            "default": False,
                            "description": "Skip quality assessment",
                        },
                    },
                    "required": ["company_name", "company_url"],
                },
            ),
            Tool(
                name="generate_strategy",
                description="Generate strategy document from existing report",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "report_path": {
                            "type": "string",
                            "description": "Path to existing research report",
                        },
                        "strategy_type": {
                            "type": "string",
                            "enum": ["ai_strategy", "customer_experience", "modern_security_compliance", "data_fabric_strategy"],
                            "description": "Type of strategy to generate",
                        },
                        "cloud_vendor": {
                            "type": "string",
                            "enum": ["azure", "aws", "gcp"],
                            "description": "Cloud vendor for AI strategy (optional)",
                        },
                    },
                    "required": ["report_path", "strategy_type"],
                },
            ),
            Tool(
                name="check_jobs",
                description="Check status of pending Deep Research jobs",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "Specific job ID to check (optional)",
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="run_qa",
                description="Run quality assessment on a report",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "report_path": {
                            "type": "string",
                            "description": "Path to report file (txt, md, docx)",
                        },
                    },
                    "required": ["report_path"],
                },
            ),
            Tool(
                name="doctor",
                description="Check system health and configuration",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            Tool(
                name="clear_jobs",
                description="Clear stale pending jobs",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "older_than_hours": {
                            "type": "integer",
                            "default": 24,
                            "description": "Clear jobs older than this (default: 24)",
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="cancel_job",
                description="Attempt best-effort cancellation of an active job",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "The job ID to cancel",
                        },
                    },
                    "required": ["job_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        import json

        # Rate limiting - use "stdio" for stdio mode, auth context for HTTP
        # HTTP mode client_id is extracted by auth middleware and stored in mcp_server._auth_context
        client_id = "stdio"
        if mcp_server._auth_context and mcp_server._auth_context.client_id:
            client_id = mcp_server._auth_context.client_id

        rate_result = mcp_server.rate_limiter.check_and_record(client_id, name)
        if not rate_result.allowed:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": True,
                    "error_type": "rate_limit_exceeded",
                    "error_code": MCPErrorCode.RATE_LIMIT_EXCEEDED,
                    "message": "Rate limit exceeded",
                    "retry_after_seconds": rate_result.retry_after_seconds,
                }),

            )]

        # Dispatch to handler
        if name == "estimate_run":
            return await _handle_estimate_run(mcp_server, arguments)
        elif name == "research_company":
            return await _handle_research_company(mcp_server, arguments, client_id)
        elif name == "generate_strategy":
            return await _handle_generate_strategy(mcp_server, arguments)
        elif name == "check_jobs":
            return await _handle_check_jobs(mcp_server, arguments)
        elif name == "run_qa":
            return await _handle_run_qa(mcp_server, arguments)
        elif name == "doctor":
            return await _handle_doctor(mcp_server, arguments)
        elif name == "clear_jobs":
            return await _handle_clear_jobs(mcp_server, arguments)
        elif name == "cancel_job":
            return await _handle_cancel_job(mcp_server, arguments, client_id)

        raise ValueError(f"Unknown tool: {name}")


async def _handle_estimate_run(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle estimate_run tool.

    Requirements: 18.1, 18.2, 18.3
    """
    import json

    company_url = arguments.get("company_url")
    mode = arguments.get("mode", "full")

    # Validate URL
    url_result = mcp_server.url_validator.validate(company_url)
    if not url_result.valid:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": url_result.error_type,
                "error_code": MCPErrorCode.INVALID_URL if url_result.error_type == "invalid_url" else MCPErrorCode.SSRF_BLOCKED,
                "message": url_result.error_message,
            }),
        )]

    # Estimate based on mode
    # These are rough estimates - actual implementation would use cost_estimator
    estimates = {
        "scrape": {"cost_usd": 0.05, "time_minutes": 8, "pages": 20},
        "deep": {"cost_usd": 0.50, "time_minutes": 15, "pages": 0},
        "full": {"cost_usd": 0.75, "time_minutes": 30, "pages": 20},
    }

    estimate = estimates.get(mode, estimates["full"])

    return [TextContent(
        type="text",
        text=json.dumps({
            "estimated_cost_usd": estimate["cost_usd"],
            "estimated_time_minutes": estimate["time_minutes"],
            "planned_pages": estimate["pages"],
            "mode": mode,
        }),
    )]


async def _handle_research_company(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle research_company tool.

    Returns immediately with job_id (async model).
    Starts background task to run research pipeline (unless disabled for testing).

    Requirements: 5.1-5.13
    """
    import asyncio
    import json

    company_name = arguments.get("company_name")
    company_url = arguments.get("company_url")
    mode = arguments.get("mode", "full")
    cloud_vendor = arguments.get("cloud_vendor")
    skip_qa = arguments.get("skip_qa", False)

    # Validate URL
    url_result = mcp_server.url_validator.validate(company_url)
    if not url_result.valid:
        error_code = {
            "invalid_url": MCPErrorCode.INVALID_URL,
            "ssrf_blocked": MCPErrorCode.SSRF_BLOCKED,
            "url_unreachable": MCPErrorCode.URL_UNREACHABLE,
        }.get(url_result.error_type, MCPErrorCode.INVALID_URL)

        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": url_result.error_type,
                "error_code": error_code,
                "message": url_result.error_message,
            }),
        )]

    # Try to create job
    try:
        job = mcp_server.job_store.create(
            company_name=company_name,
            mode=mode,
            owner_client_id=client_id,
        )
    except JobInProgressError as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "job_in_progress",
                "error_code": MCPErrorCode.JOB_IN_PROGRESS,
                "message": f"Job {e.active_job_id} already in progress",
                "active_job_id": e.active_job_id,
            }),
        )]

    # Start background task to run research pipeline
    # Skip if _skip_background_tasks is set (for testing)
    if not getattr(mcp_server, '_skip_background_tasks', False):
        from primr.mcp_server.pipeline_runner import PipelineRunner

        runner = PipelineRunner(mcp_server)
        task = asyncio.create_task(
            runner.run_research(
                job=job,
                company_url=company_url,
                mode=mode,
                cloud_vendor=cloud_vendor,
                skip_qa=skip_qa,
            )
        )
        # Track task for graceful shutdown
        mcp_server._track_task(task)

    logger.info("Created research job %s for %s", job.job_id, company_name)

    return [TextContent(
        type="text",
        text=json.dumps({
            "job_id": job.job_id,
            "accepted": True,
            "status_uri": "primr://research/status",
        }),
    )]


async def _handle_generate_strategy(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle generate_strategy tool.

    Requirements: 6.1-6.7
    """
    import json

    report_path = arguments.get("report_path")
    strategy_type = arguments.get("strategy_type")
    cloud_vendor = arguments.get("cloud_vendor")

    # Validate path
    path_result = mcp_server.path_validator.validate(report_path)
    if not path_result.valid:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": path_result.error_type,
                "error_code": MCPErrorCode.PATH_TRAVERSAL_BLOCKED,
                "message": path_result.error_message,
            }),
        )]

    # Check if file exists (only after path validation passes)
    if not path_result.resolved_path.exists():
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "report_not_found",
                "error_code": MCPErrorCode.REPORT_NOT_FOUND,
                "message": f"Report not found: {report_path}",
            }),
        )]

    # Run strategy generation
    try:
        from primr.mcp_server.pipeline_runner import run_strategy_generation

        result = await run_strategy_generation(
            report_path=str(path_result.resolved_path),
            strategy_type=strategy_type,
            cloud_vendor=cloud_vendor,
        )

        return [TextContent(
            type="text",
            text=json.dumps({
                "success": True,
                "output_path": result["output_path"],
                "strategy_type": result["strategy_type"],
                "qa_score": result.get("qa_score"),
            }),
        )]

    except Exception:
        logger.exception("Strategy generation failed")
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "strategy_generation_failed",
                "message": "Strategy generation failed - see server logs",
            }),
        )]


async def _handle_check_jobs(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle check_jobs tool.

    Requirements: 7.1-7.6
    """
    import json

    job_id = arguments.get("job_id")

    jobs = []

    if job_id:
        # Check specific job
        job = mcp_server.job_store.get(job_id)
        if job:
            jobs.append({
                "job_id": job.job_id,
                "status": job.get_status().value,
                "company_name": job.company_name,
                "output_path": job.output_paths[0] if job.output_paths else None,
                "error_type": job.error_type,
                "error_message": job.error_message,
            })
        else:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": True,
                    "error_type": "job_not_found",
                    "error_code": MCPErrorCode.JOB_NOT_FOUND,
                    "message": f"Job not found: {job_id}",
                }),
            )]
    else:
        # Return all jobs (just the current one in single-job model)
        active = mcp_server.job_store.get_active()
        if active:
            jobs.append({
                "job_id": active.job_id,
                "status": active.get_status().value,
                "company_name": active.company_name,
                "output_path": active.output_paths[0] if active.output_paths else None,
            })

        terminal = mcp_server.job_store.get_latest_terminal()
        if terminal and (not active or terminal.job_id != active.job_id):
            jobs.append({
                "job_id": terminal.job_id,
                "status": terminal.get_status().value,
                "company_name": terminal.company_name,
                "output_path": terminal.output_paths[0] if terminal.output_paths else None,
            })

    return [TextContent(
        type="text",
        text=json.dumps({"jobs": jobs}),
    )]


async def _handle_run_qa(
    mcp_server: "PrimrMCPServer",
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
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": path_result.error_type,
                "error_code": MCPErrorCode.PATH_TRAVERSAL_BLOCKED,
                "message": path_result.error_message,
            }),
        )]

    # Check if file exists
    if not path_result.resolved_path.exists():
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "report_not_found",
                "error_code": MCPErrorCode.REPORT_NOT_FOUND,
                "message": f"Report not found: {report_path}",
            }),
        )]

    # Run QA analysis
    try:
        from primr.mcp_server.pipeline_runner import run_qa_analysis

        result = await run_qa_analysis(str(path_result.resolved_path))

        return [TextContent(
            type="text",
            text=json.dumps(result),
        )]

    except Exception:
        logger.exception("QA analysis failed")
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "qa_analysis_failed",
                "message": "QA analysis failed - see server logs",
            }),
        )]


async def _handle_doctor(
    _mcp_server: "PrimrMCPServer",
    _arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle doctor tool.

    Requirements: 18.4, 18.5
    """
    import json

    from primr.mcp_server.pipeline_runner import get_doctor_status

    result = get_doctor_status()

    return [TextContent(
        type="text",
        text=json.dumps(result),
    )]


async def _handle_clear_jobs(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle clear_jobs tool.

    Requirements: 18.6, 18.7
    """
    import json

    older_than_hours = arguments.get("older_than_hours", 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)

    cleared_count = 0

    # In single-job model, just check if the job is old and terminal
    job = mcp_server.job_store.get_latest_terminal()
    if job and job.completion_time and job.completion_time < cutoff:
        mcp_server.job_store.clear()
        cleared_count = 1

    return [TextContent(
        type="text",
        text=json.dumps({
            "success": True,
            "cleared_count": cleared_count,
        }),
    )]


async def _handle_cancel_job(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle cancel_job tool.

    Requirements: 18.8-18.11
    """
    import json

    job_id = arguments.get("job_id")

    # Get the job
    job = mcp_server.job_store.get(job_id)
    if not job:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "job_not_found",
                "error_code": MCPErrorCode.JOB_NOT_FOUND,
                "message": f"Job not found: {job_id}",
            }),
        )]

    # Check if already terminal
    if job.is_terminal():
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "job_already_terminal",
                "message": f"Job {job_id} is already {job.get_status().value}",
            }),
        )]

    # Check authorization (in HTTP mode, only owner or admin can cancel)
    # In stdio mode, always allowed (implicit single-user)
    # Admin check would require auth context from HTTP middleware
    is_owner = job.owner_client_id is None or job.owner_client_id == client_id
    if client_id != "stdio" and not is_owner:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "cancel_not_authorized",
                "error_code": MCPErrorCode.CANCEL_NOT_AUTHORIZED,
                "message": "Only the job owner or admin can cancel this job",
            }),
        )]

    # Cancel the job
    job.advance_stage(ResearchStage.CANCELLED)
    job.error_type = "user_cancelled"
    job.error_message = f"Cancelled by {client_id}"
    mcp_server.job_store.update(job)

    logger.info("Job %s cancelled by %s", job_id, client_id)

    return [TextContent(

        type="text",
        text=json.dumps({
            "success": True,
            "job_id": job_id,
            "status": "cancelled",
            "message": "Job cancelled. Any partial artifacts have been preserved.",
        }),
    )]
