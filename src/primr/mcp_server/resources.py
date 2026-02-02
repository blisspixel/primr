"""
Resource handler implementations for MCP server.

This module provides read-only resources for state inspection:
- primr://research/status - Current research job status
- primr://output/latest - Most recent research output
- primr://output/artifacts - Pipeline stage artifacts
- primr://config - Configuration state

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

from primr.mcp_server.types import (
    ArtifactInfo,
    ArtifactsResponse,
    ConfigState,
    JobStatus,
    LatestOutput,
    ResearchMode,
    ResearchStage,
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

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available resources."""
        return [
            Resource(
                uri="primr://research/status",
                name="Research Status",
                description="Current research job status and progress",
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
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> list[ReadResourceContents]:
        """Read a resource by URI."""
        uri_str = str(uri)

        if uri_str == "primr://research/status" or uri_str.startswith("primr://research/status"):
            return _read_research_status(mcp_server)
        elif uri_str == "primr://output/latest" or uri_str.startswith("primr://output/latest"):
            return _read_latest_output(mcp_server, uri_str)
        elif uri_str == "primr://output/artifacts" or uri_str.startswith("primr://output/artifacts"):
            return _read_artifacts(mcp_server)
        elif uri_str == "primr://config" or uri_str.startswith("primr://config"):
            return _read_config(mcp_server)
        elif uri_str == "primr://strategies/available" or uri_str.startswith("primr://strategies/available"):
            return _read_strategies_available()
        elif uri_str.startswith("primr://output/by_job/"):
            return _read_output_by_job(mcp_server, uri_str)
        elif uri_str == "primr://output/manifest/latest" or uri_str.startswith("primr://output/manifest/latest"):
            return _read_manifest_latest()

        raise ValueError(f"Unknown resource: {uri}")


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
        "stage_started_at": status.stage_started_at.isoformat() if status.stage_started_at else None,
        "last_heartbeat_time": status.last_heartbeat_time.isoformat() if status.last_heartbeat_time else None,
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
        "generation_timestamp": output.generation_timestamp.isoformat() if output.generation_timestamp else None,
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
        # Look for artifacts in company workspace
        workspace_dir = Path("output") / job.company_name.replace(" ", "_").lower()

        if workspace_dir.exists():
            for artifact_type, filename in ARTIFACT_FILES.items():
                artifact_path = workspace_dir / filename
                if artifact_path.exists():
                    try:
                        content = artifact_path.read_text(encoding="utf-8")
                        size = artifact_path.stat().st_size

                        # Calculate hash
                        content_hash = hashlib.sha256(content.encode()).hexdigest()

                        artifacts.append(ArtifactInfo(
                            artifact_type=artifact_type,
                            file_path=str(artifact_path),
                            size_bytes=size,
                            preview=content[:500],
                            content_hash=content_hash,
                        ))
                    except Exception as e:
                        logger.warning(f"Failed to read artifact {artifact_path}: {e}")

            # Add report files
            for report_file in workspace_dir.glob("report*"):
                if report_file.is_file() and not report_file.name.startswith("_raw"):
                    try:
                        content = report_file.read_text(encoding="utf-8")
                        size = report_file.stat().st_size
                        content_hash = hashlib.sha256(content.encode()).hexdigest()

                        artifacts.append(ArtifactInfo(
                            artifact_type="report",
                            file_path=str(report_file),
                            size_bytes=size,
                            preview=content[:500],
                            content_hash=content_hash,
                        ))
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


def _read_strategies_available() -> list[ReadResourceContents]:
    """
    Read available strategy types with metadata.

    Requirements: FR-5.1, FR-5.2
    """
    import json

    # Strategy metadata per design document
    strategies = [
        {
            "id": StrategyType.AI_STRATEGY.value,
            "name": "AI Strategy",
            "description": "AI/ML transformation roadmap with quick wins and bigger bets",
            "requires_cloud_vendor": True,
            "estimated_time_minutes": 15,
            "estimated_cost_usd": 0.30,
        },
        {
            "id": StrategyType.CUSTOMER_EXPERIENCE.value,
            "name": "Customer Experience Strategy",
            "description": "CX transformation and digital experience improvement plan",
            "requires_cloud_vendor": False,
            "estimated_time_minutes": 12,
            "estimated_cost_usd": 0.25,
        },
        {
            "id": StrategyType.MODERN_SECURITY_COMPLIANCE.value,
            "name": "Security & Compliance Strategy",
            "description": "Zero Trust architecture and compliance posture assessment",
            "requires_cloud_vendor": False,
            "estimated_time_minutes": 12,
            "estimated_cost_usd": 0.25,
        },
        {
            "id": StrategyType.DATA_FABRIC_STRATEGY.value,
            "name": "Data Fabric Strategy",
            "description": "Modern data platform for agentic AI and semantic layers",
            "requires_cloud_vendor": False,
            "estimated_time_minutes": 12,
            "estimated_cost_usd": 0.25,
        },
    ]

    data = {
        "schema_version": "1.0",
        "strategies": strategies,
    }

    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]


def _read_output_by_job(mcp_server: "PrimrMCPServer", uri: str) -> list[ReadResourceContents]:
    """
    Read output for a specific job ID.

    Requirements: FR-6.2
    """
    import json
    import re

    # Extract job_id from URI
    match = re.match(r"primr://output/by_job/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid job ID in URI: {uri}")
    
    requested_job_id = match.group(1)

    # Look up job in store
    job = mcp_server.job_store.get_by_id(requested_job_id)
    
    if job is None:
        # Return 404-like response
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


def _read_manifest_latest() -> list[ReadResourceContents]:
    """
    Read most recent run manifest (audit trail).

    Requirements: FR-7.3
    """
    import json

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

    # Find all run_manifest.json files
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
