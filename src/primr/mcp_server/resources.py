"""
Resource handler implementations for MCP server.

This module provides read-only resources for state inspection:
- primr://research/status - Current research job status
- primr://output/latest - Most recent research output
- primr://output/artifacts - Pipeline stage artifacts
- primr://calibration/baseline/inspection?path=... - Calibration readiness blockers
- primr://config - Configuration state

Agentic resources (from agentic_resources.py):
- primr://roadmap - Roadmap data as JSON
- primr://memory/{company} - Company research memory
- primr://context - Current context map summary

Requirements: 2.1-2.13, 3.1-3.6, 3A.1-3A.8, 4.1-4.7
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource

from primr.mcp_server.agentic_resources import get_agentic_resources, read_agentic_resource
from primr.mcp_server.audit_log import read_agent_audit_recent_resource
from primr.mcp_server.calibration_resources import (
    CALIBRATION_BASELINE_INSPECTION_RESOURCE,
    CALIBRATION_BASELINE_INSPECTION_URI,
    read_calibration_baseline_inspection_resource,
)
from primr.mcp_server.tool_authz import ADMIN_SCOPE
from primr.mcp_server.types import (
    ArtifactInfo,
    ArtifactsResponse,
    ConfigState,
    JobStatus,
    LatestOutput,
    ResearchMode,
    ResearchStatus,
    StrategyType,
)

if TYPE_CHECKING:
    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)

# Artifact type mappings
ARTIFACT_FILES = {
    "scraped_content": "scraped_content.txt",
    "insights": "insights.txt",
    "dossier": "dossier.txt",
}


def register_resources(server: Server, mcp_server: "PrimrMCPServer") -> None:
    """Register all Primr resources with the MCP server."""

    # Get agentic resources
    agentic_resources = get_agentic_resources()

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available resources."""
        base_resources = [
            Resource(
                uri="primr://research/status",
                name="Research Status",
                description="Current research job status and progress",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://research/next-actions",
                name="Research Next Actions",
                description="Recommended next client actions for the active or latest job",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://agent/governance",
                name="Agent Governance",
                description="Recommended estimate, approval, and cost-cap contract for MCP clients",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://agent/audit/recent",
                name="Recent MCP Audit Events",
                description="Recent privacy-preserving MCP tool invocation audit events",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://research/modes",
                name="Research Modes",
                description="Available research modes, current defaults, and usage guidance",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://output/latest",
                name="Latest Output",
                description="Most recent research report",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://output/artifacts",
                name="Pipeline Artifacts",
                description="Intermediate pipeline stage outputs",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://config",
                name="Configuration",
                description="Current configuration state",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://strategies/available",
                name="Available Strategies",
                description="List of available strategy document types with metadata",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://output/by_job/{job_id}",
                name="Output by Job ID",
                description="Retrieve output for a specific job ID",
                mimeType="application/json",
            ),
            Resource(
                uri="primr://output/manifest/latest",
                name="Latest Run Manifest",
                description="Most recent run manifest (audit trail)",
                mimeType="application/json",
            ),
            CALIBRATION_BASELINE_INSPECTION_RESOURCE,
        ]
        # Include agentic resources
        return base_resources + agentic_resources

    @server.read_resource()
    async def read_resource(uri: str) -> list[ReadResourceContents]:
        """Read a resource by URI."""
        uri_str = str(uri)

        # Try agentic resources first
        agentic_result = read_agentic_resource(uri_str, mcp_server)
        if agentic_result is not None:
            return agentic_result

        if uri_str == "primr://research/status" or uri_str.startswith("primr://research/status"):
            return _read_research_status(mcp_server)
        elif uri_str == "primr://research/next-actions" or uri_str.startswith(
            "primr://research/next-actions"
        ):
            return _read_research_next_actions(mcp_server)
        elif uri_str == "primr://agent/governance" or uri_str.startswith(
            "primr://agent/governance"
        ):
            return _read_agent_governance()
        elif uri_str == "primr://agent/audit/recent" or uri_str.startswith(
            "primr://agent/audit/recent"
        ):
            return read_agent_audit_recent_resource(
                mcp_server,
                uri_str,
                can_read=_caller_can_read_audit(mcp_server),
            )
        elif uri_str == "primr://research/modes" or uri_str.startswith("primr://research/modes"):
            return _read_research_modes()
        elif uri_str == "primr://output/latest" or uri_str.startswith("primr://output/latest"):
            return _read_latest_output(mcp_server, uri_str)
        elif uri_str == "primr://output/artifacts" or uri_str.startswith(
            "primr://output/artifacts"
        ):
            return _read_artifacts(mcp_server)
        elif uri_str == "primr://config" or uri_str.startswith("primr://config"):
            return _read_config(mcp_server)
        elif uri_str == "primr://strategies/available" or uri_str.startswith(
            "primr://strategies/available"
        ):
            return _read_strategies_available()
        elif uri_str.startswith("primr://output/by_job/"):
            return _read_output_by_job(mcp_server, uri_str)
        elif uri_str == "primr://output/manifest/latest" or uri_str.startswith(
            "primr://output/manifest/latest"
        ):
            return _read_manifest_latest(mcp_server)
        elif uri_str == CALIBRATION_BASELINE_INSPECTION_URI or uri_str.startswith(
            f"{CALIBRATION_BASELINE_INSPECTION_URI}?"
        ):
            return read_calibration_baseline_inspection_resource(
                mcp_server,
                uri_str,
                client_id=_caller_client_id(mcp_server),
            )

        raise ValueError(f"Unknown resource: {uri}")


def _read_research_next_actions(mcp_server: "PrimrMCPServer") -> list[ReadResourceContents]:
    """Read recommended client actions for the active or latest job."""
    import json

    job = mcp_server.job_store.get_active()
    source = "active"
    if job is None:
        job = mcp_server.job_store.get_latest_terminal()
        source = "latest_terminal"

    if job is None:
        data = {
            "job_source": None,
            "job_id": None,
            "status": "idle",
            "recommended_action": "start_new_research",
            "message": "No active or recent job. Estimate a new run before starting research.",
            "follow_up": [
                "Read primr://research/modes",
                "Call estimate_run",
                "Get explicit user approval before research_company",
            ],
        }
    else:
        status = job.get_status().value
        if status == "in_progress":
            possibly_stuck = job.is_possibly_stuck()
            data = {
                "job_source": source,
                "job_id": job.job_id,
                "status": status,
                "recommended_action": "monitor_job",
                "message": "Research is still running. Monitor status instead of relaunching the job.",
                "follow_up": [
                    "Read primr://research/status",
                    "Use wait_for_status_change for short blocking waits",
                    "Reconnect and resume monitoring if the client session drops",
                ],
                "possibly_stuck": possibly_stuck,
            }
            if possibly_stuck:
                data["recommended_action"] = "inspect_or_cancel"
                data["message"] = (
                    "Research may be stuck. Inspect status and consider cancellation only if progress has stopped."
                )
                data["follow_up"].append(
                    "If the process was interrupted, use resume/recovery commands outside MCP when appropriate"
                )
        elif status == "completed":
            data = {
                "job_source": source,
                "job_id": job.job_id,
                "status": status,
                "recommended_action": "review_output",
                "message": "Research completed. Review outputs before deciding on QA or strategy generation.",
                "follow_up": [
                    "Read primr://output/latest",
                    "Read primr://output/manifest/latest",
                    "Run run_qa or estimate_strategy if another deliverable is needed",
                ],
                "output_paths": job.output_paths,
            }
        elif status == "failed":
            data = {
                "job_source": source,
                "job_id": job.job_id,
                "status": status,
                "recommended_action": "inspect_failure",
                "message": "Research failed. Inspect the error and decide whether to retry or recover.",
                "follow_up": [
                    "Read primr://research/status for error details",
                    "Run doctor if the issue looks environmental",
                    "Consider resume/recovery flows if the failure was due to interruption",
                ],
                "error_type": job.error_type,
                "error_message": job.error_message,
            }
        else:
            data = {
                "job_source": source,
                "job_id": job.job_id,
                "status": status,
                "recommended_action": "acknowledge_terminal_state",
                "message": "The latest job is no longer running.",
                "follow_up": [
                    "Read primr://research/status",
                    "Start a new estimate if another run is needed",
                ],
            }

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def _read_research_status(mcp_server: "PrimrMCPServer") -> list[ReadResourceContents]:
    """
    Read current research job status.

    Requirements: 2.1-2.13
    """
    import json

    job = mcp_server.job_store.get_active()

    if job is None:
        # Check for latest terminal job
        job = mcp_server.job_store.get_latest_terminal()

    if job is None:
        # No job at all
        status = ResearchStatus(status=JobStatus.IDLE)
    else:
        # Build status from job state
        possibly_stuck = job.is_possibly_stuck() if not job.is_terminal() else False

        status = ResearchStatus(
            status=job.get_status(),
            job_id=job.job_id,
            company_name=job.company_name,
            mode=ResearchMode(job.mode) if job.mode in [m.value for m in ResearchMode] else None,
            start_time=job.start_time,
            current_stage=job.current_stage,
            stage_progress_percent=job.stage_progress_percent,
            stage_started_at=job.stage_started_at,
            last_heartbeat_time=job.last_heartbeat_time,
            stage_expected_minutes=job.get_expected_minutes(),
            possibly_stuck=possibly_stuck,
            completion_time=job.completion_time,
            output_paths=job.output_paths if job.output_paths else None,
            error_type=job.error_type,
            error_message=job.error_message,
        )

    # Serialize to JSON
    data = {
        "status": status.status.value,
        "job_id": status.job_id,
        "company_name": status.company_name,
        "mode": status.mode.value if status.mode else None,
        "start_time": status.start_time.isoformat() if status.start_time else None,
        "current_stage": status.current_stage.value if status.current_stage else None,
        "stage_progress_percent": status.stage_progress_percent,
        "stage_started_at": status.stage_started_at.isoformat()
        if status.stage_started_at
        else None,
        "last_heartbeat_time": status.last_heartbeat_time.isoformat()
        if status.last_heartbeat_time
        else None,
        "stage_expected_minutes": status.stage_expected_minutes,
        "possibly_stuck": status.possibly_stuck,
        "completion_time": status.completion_time.isoformat() if status.completion_time else None,
        "output_paths": status.output_paths,
        "error_type": status.error_type,
        "error_message": status.error_message,
    }

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def _read_latest_output(mcp_server: "PrimrMCPServer", uri: str) -> list[ReadResourceContents]:
    """
    Read most recent research output.

    Requirements: 3.1-3.6, FR-6.1
    """
    import json

    # Check for full_content parameter
    full_content = "full_content=true" in uri.lower()

    # Get job_id from job store for provenance tracking (FR-6.1)
    job = mcp_server.job_store.get_latest_terminal()
    job_id = job.job_id if job else None

    # Find latest report in output directory
    output_dir = Path("output")
    if not output_dir.exists():
        data = {"message": "No reports available", "report_path": None, "job_id": job_id}
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    # Find most recent report file
    report_files = list(output_dir.glob("**/report*.md")) + list(output_dir.glob("**/report*.txt"))
    if not report_files:
        data = {"message": "No reports available", "report_path": None, "job_id": job_id}
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    # Get most recent by modification time
    latest_report = max(report_files, key=lambda p: p.stat().st_mtime)

    # Read content
    try:
        content = latest_report.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read report: {e}")
        content = ""

    # Extract company name from path or content
    company_name = latest_report.parent.name if latest_report.parent != output_dir else None

    # Build response
    output = LatestOutput(
        report_path=str(latest_report),
        company_name=company_name,
        generation_timestamp=datetime.fromtimestamp(latest_report.stat().st_mtime),
        report_type="markdown" if latest_report.suffix == ".md" else "text",
        content_preview=content[:2000] if content else None,
        full_content=content if full_content else None,
    )

    data = {
        "job_id": job_id,  # FR-6.1: Include job_id for provenance verification
        "report_path": output.report_path,
        "company_name": output.company_name,
        "generation_timestamp": output.generation_timestamp.isoformat()
        if output.generation_timestamp
        else None,
        "report_type": output.report_type,
        "content_preview": output.content_preview,
    }

    if full_content:
        data["full_content"] = output.full_content

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def _read_artifacts(mcp_server: "PrimrMCPServer") -> list[ReadResourceContents]:
    """
    Read pipeline artifacts.

    Requirements: 3A.1-3A.8
    """
    import json

    # Determine which job's artifacts to show
    active_job = mcp_server.job_store.get_active()
    if active_job:
        job = active_job
    else:
        job = mcp_server.job_store.get_latest_terminal()

    artifacts = []
    job_id = job.job_id if job else None
    job_status = job.get_status() if job else None

    if job and job.company_name:
        # Look for artifacts in the company workspace. Derive the path exactly
        # as the writer does (pipeline_runner._save_report): absolute OUTPUT_DIR
        # (not relative "output", which only matches when cwd == project root)
        # and the same slug, including the "/" -> "_" replacement.
        from primr.config.config import OUTPUT_DIR

        safe_name = job.company_name.replace(" ", "_").replace("/", "_").lower()
        workspace_dir = Path(OUTPUT_DIR) / safe_name

        if workspace_dir.exists():
            for artifact_type, filename in ARTIFACT_FILES.items():
                artifact_path = workspace_dir / filename
                if artifact_path.exists():
                    try:
                        content = artifact_path.read_text(encoding="utf-8")
                        size = artifact_path.stat().st_size

                        # Calculate hash
                        content_hash = hashlib.sha256(content.encode()).hexdigest()

                        artifacts.append(
                            ArtifactInfo(
                                artifact_type=artifact_type,
                                file_path=str(artifact_path),
                                size_bytes=size,
                                preview=content[:500],
                                content_hash=content_hash,
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Failed to read artifact {artifact_path}: {e}")

            # Add report files
            for report_file in workspace_dir.glob("report*"):
                if report_file.is_file() and not report_file.name.startswith("_raw"):
                    try:
                        content = report_file.read_text(encoding="utf-8")
                        size = report_file.stat().st_size
                        content_hash = hashlib.sha256(content.encode()).hexdigest()

                        artifacts.append(
                            ArtifactInfo(
                                artifact_type="report",
                                file_path=str(report_file),
                                size_bytes=size,
                                preview=content[:500],
                                content_hash=content_hash,
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Failed to read report {report_file}: {e}")

    response = ArtifactsResponse(
        job_id=job_id,
        job_status=job_status,
        artifacts=artifacts,
    )

    data = {
        "job_id": response.job_id,
        "job_status": response.job_status.value if response.job_status else None,
        "artifacts": [
            {
                "artifact_type": a.artifact_type,
                "file_path": a.file_path,
                "size_bytes": a.size_bytes,
                "preview": a.preview,
                "content_hash": a.content_hash,
            }
            for a in response.artifacts
        ],
    }

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def _read_config(mcp_server: "PrimrMCPServer") -> list[ReadResourceContents]:
    """
    Read configuration state.

    Requirements: 4.1-4.7
    """
    import json

    # Build config from allowlist schema (no sensitive values)
    config = ConfigState(
        available_modes=[m.value for m in ResearchMode],
        available_strategies={
            StrategyType.AI_STRATEGY.value: "AI/ML transformation roadmap",
            StrategyType.CUSTOMER_EXPERIENCE.value: "CX improvement plan",
            StrategyType.MODERN_SECURITY_COMPLIANCE.value: "Security posture assessment",
            StrategyType.DATA_FABRIC_STRATEGY.value: "Data platform modernization",
            StrategyType.SKILLS.value: "Skills ideation (roles x skills hypothesis)",
        },
        configured_vendors=["azure", "aws", "gcp"],
    )

    data = {
        "available_modes": config.available_modes,
        "available_strategies": config.available_strategies,
        "configured_vendors": config.configured_vendors,
    }

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def _read_agent_governance() -> list[ReadResourceContents]:
    """Read the recommended governance contract for generic MCP clients."""
    import json

    data = {
        "schema_version": "1.0",
        "principles": [
            "Call estimate tools before any cost-incurring tool",
            "Tell the user that research and strategy generation incur real API cost",
            "Get explicit user approval before execution",
            "Pass max_estimated_cost_usd into cost-incurring tools when possible",
            "Pass the approval_token returned by the matching estimate tool when enforcement is enabled",
            "Treat Primr as a long-running async job system, not a synchronous request",
            "If PRIMR_ENFORCE_MCP_COST_CAPS is enabled, cost-governed execution tools require max_estimated_cost_usd and approval_token",
        ],
        "research_flow": {
            "estimate_tool": "estimate_run",
            "execute_tool": "research_company",
            "cap_argument": "max_estimated_cost_usd",
            "approval_argument": "approval_token",
            "status_resource": "primr://research/status",
            "wait_tool": "wait_for_status_change",
            "expected_runtime": "standard runs are often 35-45 minutes; premium multi-vendor runs can reach 75-120 minutes",
            "client_behavior": "launch once, then monitor and resume rather than waiting synchronously",
        },
        "strategy_flow": {
            "estimate_tool": "estimate_strategy",
            "execute_tool": "generate_strategy",
            "cap_argument": "max_estimated_cost_usd",
            "approval_argument": "approval_token",
        },
        "skill_pack_flow": {
            "estimate_tool": "estimate_skill_pack",
            "execute_tool": "generate_skill_pack",
            "cap_argument": "max_estimated_cost_usd",
            "approval_argument": "approval_token",
        },
    }

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def _read_research_modes() -> list[ReadResourceContents]:
    """
    Read available research modes with current integration guidance.

    This resource is intended for agent clients and skill packages so they
    can discover current positioning without embedding stale mode tables.
    """
    import json

    data = {
        "schema_version": "1.0",
        "default_mode": "full",
        "default_mode_behavior": (
            "Standard research pipeline. When XAI_API_KEY is available, Primr uses the "
            "Grok hybrid path by default. Use premium to force Gemini Deep Research."
        ),
        "cost_warning": (
            "Research runs incur real API charges. Call estimate_run first and get explicit "
            "user approval before research_company."
        ),
        "search_defaults": {
            "provider": "duckduckgo",
            "search_api_key_required": False,
            "google_custom_search_optional": True,
        },
        "modes": [
            {
                "id": "scrape",
                "name": "Scrape",
                "summary": "Site corpus and extraction only.",
                "best_for": [
                    "quick first-party reconnaissance",
                    "capturing site structure and surface-level signals",
                ],
            },
            {
                "id": "deep",
                "name": "Deep",
                "summary": "External research only, useful when site access is weak or blocked.",
                "best_for": [
                    "protected or sparse websites",
                    "external validation and market context",
                ],
            },
            {
                "id": "full",
                "name": "Full",
                "summary": "Primary recommended mode for most runs.",
                "best_for": [
                    "standard end-to-end research",
                    "consultant-style strategic analysis",
                ],
            },
            {
                "id": "premium",
                "name": "Premium",
                "summary": "Maximum-depth pipeline using Gemini Deep Research.",
                "best_for": [
                    "high-depth deliverables",
                    "cases where longer runtime and higher cost are acceptable",
                ],
            },
        ],
    }

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def get_strategy_catalog() -> list[dict[str, object]]:
    """Return the shared strategy catalog used by resources and estimate tools."""
    return [
        {
            "id": StrategyType.AI_STRATEGY.value,
            "name": "AI Strategy",
            "description": "AI/ML transformation roadmap with quick wins and bigger bets",
            "requires_platform": True,
            "estimated_time_minutes": 15,
            "estimated_cost_usd": 0.30,
        },
        {
            "id": StrategyType.CUSTOMER_EXPERIENCE.value,
            "name": "Customer Experience Strategy",
            "description": "CX transformation and digital experience improvement plan",
            "requires_platform": False,
            "estimated_time_minutes": 12,
            "estimated_cost_usd": 0.25,
        },
        {
            "id": StrategyType.MODERN_SECURITY_COMPLIANCE.value,
            "name": "Security & Compliance Strategy",
            "description": "Zero Trust architecture and compliance posture assessment",
            "requires_platform": False,
            "estimated_time_minutes": 12,
            "estimated_cost_usd": 0.25,
        },
        {
            "id": StrategyType.DATA_FABRIC_STRATEGY.value,
            "name": "Data Fabric Strategy",
            "description": "Modern data platform for agentic AI and semantic layers",
            "requires_platform": False,
            "estimated_time_minutes": 12,
            "estimated_cost_usd": 0.25,
        },
        {
            "id": StrategyType.SKILLS.value,
            "name": "Skills Ideation",
            "description": "Top-5 roles x top-3 skills hypothesis grounded in recon and hiring signals",
            "requires_platform": False,
            "estimated_time_minutes": 8,
            "estimated_cost_usd": 0.08,
        },
    ]


def _read_strategies_available() -> list[ReadResourceContents]:
    """
    Read available strategy types with metadata.

    Requirements: FR-5.1, FR-5.2
    """
    import json

    data = {
        "schema_version": "1.0",
        "cost_warning": (
            "Strategy generation incurs real API charges. Surface the current estimate and "
            "get explicit user approval before generate_strategy."
        ),
        "strategies": get_strategy_catalog(),
    }

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def _caller_client_id(mcp_server: "PrimrMCPServer") -> str:
    """Resolve the calling client_id from the active auth context.

    Matches the dispatcher in tools.py: stdio has implicit single-user
    access, HTTP requests carry an auth_context.client_id set by middleware.
    Only treats the auth context as present when client_id is a real
    string — otherwise MagicMock-style placeholders in unit tests would
    look like an HTTP caller and trip ownership checks.
    """
    ctx = getattr(mcp_server, "_auth_context", None)
    if ctx is not None:
        cid = getattr(ctx, "client_id", None)
        if isinstance(cid, str) and cid:
            return cid
    return "stdio"


def _caller_can_read_audit(mcp_server: "PrimrMCPServer") -> bool:
    """Audit events are local-only by default and admin-only over HTTP."""
    if _caller_client_id(mcp_server) == "stdio":
        return True
    ctx = getattr(mcp_server, "_auth_context", None)
    scopes = getattr(ctx, "scopes", []) if ctx is not None else []
    return ADMIN_SCOPE in {str(scope) for scope in scopes}


def _caller_owns_job_resource(job, client_id: str) -> bool:
    """Ownership gate for output/by_job/* and manifest-by-job resources."""
    if client_id == "stdio":
        return True
    return job.owner_client_id is not None and job.owner_client_id == client_id


def _read_output_by_job(mcp_server: "PrimrMCPServer", uri: str) -> list[ReadResourceContents]:
    """
    Read output for a specific job ID.

    Owner-gated: HTTP clients only see their own jobs. Returning 404 on
    ownership mismatch prevents authenticated clients from probing for
    other users' job IDs and reading their report previews / paths.

    Requirements: FR-6.2
    """
    import json
    import re

    # Extract job_id from URI
    match = re.match(r"primr://output/by_job/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid job ID in URI: {uri}")

    requested_job_id = match.group(1)
    client_id = _caller_client_id(mcp_server)

    # Look up job in store
    job = mcp_server.job_store.get_by_id(requested_job_id)

    if job is None or not _caller_owns_job_resource(job, client_id):
        # 404 for both missing and not-owned, identical body shape.
        data = {
            "error": "job_not_found",
            "message": f"No job found with ID: {requested_job_id}",
            "job_id": requested_job_id,
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    # Check if job has output
    if not job.output_paths:
        data = {
            "error": "no_output",
            "message": f"Job {requested_job_id} has no output yet",
            "job_id": requested_job_id,
            "status": job.get_status().value,
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    # Find report in output paths
    report_path = None
    for path in job.output_paths:
        if "report" in path.lower():
            report_path = path
            break

    if not report_path and job.output_paths:
        report_path = job.output_paths[0]

    # Read report content
    content_preview = None
    if report_path:
        try:
            report_file = Path(report_path)
            if report_file.exists():
                content = report_file.read_text(encoding="utf-8")
                content_preview = content[:2000]
        except Exception as e:
            logger.warning(f"Failed to read report for job {requested_job_id}: {e}")

    # Build response
    data = {
        "job_id": job.job_id,
        "report_path": report_path,
        "company_name": job.company_name,
        "generation_timestamp": job.completion_time.isoformat() if job.completion_time else None,
        "report_type": "markdown" if report_path and report_path.endswith(".md") else "text",
        "content_preview": content_preview,
        "status": job.get_status().value,
    }

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def _read_manifest_latest(mcp_server: "PrimrMCPServer") -> list[ReadResourceContents]:
    """
    Read most recent run manifest (audit trail).

    Owner-gated: in HTTP mode this only returns a manifest that the caller
    actually owns. Previously this scanned output/**/run_manifest.json and
    returned the newest file, which leaked another client's company_url,
    artifact paths, and approval metadata. stdio retains full access.

    Requirements: FR-7.3
    """
    import json

    client_id = _caller_client_id(mcp_server)

    # Find latest run_manifest.json in output directory
    output_dir = Path("output")
    if not output_dir.exists():
        data = {
            "error": "no_manifest",
            "message": "No run manifests available",
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    # HTTP clients are restricted to manifests under their own job's
    # output paths; if they have no recent owned job we return 404
    # rather than scanning the whole directory.
    if client_id != "stdio":
        owned = mcp_server.job_store.get_latest_terminal()
        if owned is None or not _caller_owns_job_resource(owned, client_id):
            return [
                ReadResourceContents(
                    content=json.dumps(
                        {"error": "no_manifest", "message": "No manifests available"},
                        indent=2,
                    ),
                    mime_type="application/json",
                )
            ]
        # Limit the glob to directories that belong to the owned job.
        manifest_files: list[Path] = []
        for output_path in owned.output_paths or []:
            parent = Path(output_path).parent
            manifest_files.extend(parent.glob("**/run_manifest.json"))
    else:
        # stdio: legacy behavior — full scan.
        manifest_files = list(output_dir.glob("**/run_manifest.json"))
    if not manifest_files:
        data = {
            "error": "no_manifest",
            "message": "No run manifests available",
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    # Get most recent by modification time
    latest_manifest = max(manifest_files, key=lambda p: p.stat().st_mtime)

    # Read and return manifest content
    try:
        content = latest_manifest.read_text(encoding="utf-8")
        manifest_data = json.loads(content)
    except Exception as e:
        logger.warning(f"Failed to read manifest: {e}")
        data = {
            "error": "read_error",
            "message": f"Failed to read manifest: {e}",
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    return [
        ReadResourceContents(
            content=json.dumps(manifest_data, indent=2),
            mime_type="application/json",
        )
    ]
