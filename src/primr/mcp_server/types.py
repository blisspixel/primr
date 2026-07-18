"""
MCP-specific type definitions for Primr.

This module contains all dataclasses and enums used by the MCP server,
including job state, tool results, and resource responses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any


class ResearchMode(str, Enum):
    """Research pipeline execution modes."""

    SCRAPE = "scrape"
    DEEP = "deep"
    FULL = "full"
    PREMIUM = "premium"


class Platform(str, Enum):
    """Supported platforms for AI strategy generation.

    Aliases accepted by the CLI (--platform):
      microsoft / ms → azure
      amazon        → aws
      google        → gcp
      nvidia        → private
    """

    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"
    PRIVATE = "private"


class StrategyType(str, Enum):
    """Available strategy document types."""

    AI_STRATEGY = "ai_strategy"
    CUSTOMER_EXPERIENCE = "customer_experience"
    MODERN_SECURITY_COMPLIANCE = "modern_security_compliance"
    DATA_FABRIC_STRATEGY = "data_fabric_strategy"
    SKILLS = "skills"


class JobStatus(str, Enum):
    """High-level job status."""

    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchStage(str, Enum):
    """
    Monotonic stage enum - cannot regress once advanced.

    Stage progression: IDLE -> ACCEPTED -> SCRAPING -> EXTRACTING ->
                       DEEP_RESEARCH -> WRITING -> QA -> COMPLETED
    Terminal states: COMPLETED, FAILED, CANCELLED
    """

    IDLE = "idle"
    ACCEPTED = "accepted"
    SCRAPING = "scraping"
    EXTRACTING = "extracting"
    DEEP_RESEARCH = "deep_research"
    WRITING = "writing"
    QA = "qa"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ResearchStatus:
    """
    Current research job status returned by primr://research/status resource.

    Field requirements by status:
    - IN_PROGRESS: job_id, company_name, mode, start_time, current_stage required
    - COMPLETED: completion_time, output_paths required
    - FAILED: error_type, error_message required
    """

    status: JobStatus
    job_id: str | None = None
    company_name: str | None = None
    mode: ResearchMode | None = None
    start_time: datetime | None = None
    current_stage: ResearchStage | None = None
    stage_progress_percent: int | None = None  # 0-100 within current stage
    stage_started_at: datetime | None = None  # When current stage began
    last_heartbeat_time: datetime | None = None  # Last progress update
    stage_expected_minutes: int | None = None  # Best-effort heuristic
    possibly_stuck: bool = False  # True if heartbeat stale > 120s
    completion_time: datetime | None = None
    output_paths: list[str] | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class JobAcceptedResult:
    """
    Returned immediately when research_company is called.

    This is the ONLY result type for research_company (async model).
    Clients monitor progress via primr://research/status resource.
    """

    job_id: str
    accepted: bool
    status_uri: str = "primr://research/status"


@dataclass
class EstimateResult:
    """Returned by estimate_run tool - cost/time estimates without execution."""

    estimated_cost_usd: float
    estimated_time_minutes: int
    planned_pages: int | None = None
    mode: ResearchMode = ResearchMode.FULL


@dataclass
class DoctorResult:
    """Returned by doctor tool - system health status."""

    orphaned_stores_count: int
    config_valid: bool
    api_keys_configured: bool
    warnings: list[str] = field(default_factory=list)
    status: str = "healthy"
    checks: list[dict[str, Any]] = field(default_factory=list)
    audit_log: dict[str, Any] | None = None


@dataclass
class LatestOutput:
    """Response for primr://output/latest resource."""

    report_path: str | None = None
    company_name: str | None = None
    generation_timestamp: datetime | None = None
    report_type: str | None = None
    content_preview: str | None = None  # First 2000 characters
    full_content: str | None = None  # Complete report when requested


@dataclass
class ArtifactInfo:
    """Single artifact in the pipeline artifacts resource."""

    artifact_type: str  # e.g., "scraped_content", "insights", "dossier", "report"
    file_path: str
    size_bytes: int
    preview: str  # First 500 characters
    content_hash: str | None = None  # SHA256, optional


@dataclass
class ArtifactsResponse:
    """Response for primr://output/artifacts resource."""

    job_id: str | None = None
    job_status: JobStatus | None = None
    artifacts: list[ArtifactInfo] = field(default_factory=list)


@dataclass
class ConfigState:
    """
    Response for primr://config resource.

    Built from allowlist schema - never includes sensitive values.
    """

    available_modes: list[str] = field(default_factory=list)
    available_strategies: dict[str, str] = field(default_factory=dict)
    configured_vendors: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """
    Result for synchronous tools (generate_strategy, run_qa, doctor, etc.).

    NOTE: research_company returns JobAcceptedResult (async model) - NOT ToolResult.
    """

    success: bool
    output_path: str | None = None
    duration_seconds: float | None = None
    qa_score: int | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class JobInfo:
    """Job information returned by check_jobs tool."""

    job_id: str
    status: JobStatus
    company_name: str | None = None
    output_path: str | None = None
    estimated_completion_time: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class QAResult:
    """Result from run_qa tool."""

    overall_score: int
    category_scores: dict[str, int] = field(default_factory=dict)
    improvement_suggestions: list[str] = field(default_factory=list)


class MCPErrorCode(IntEnum):
    """
    Standard JSON-RPC and MCP-specific error codes.

    All codes are unique - no collisions.
    """

    # JSON-RPC standard errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # MCP-specific errors (unique codes)
    RATE_LIMIT_EXCEEDED = -32001
    PATH_TRAVERSAL_BLOCKED = -32002
    JOB_IN_PROGRESS = -32003
    RESOURCE_NOT_FOUND = -32004
    INVALID_URL = -32005
    REPORT_NOT_FOUND = -32006
    AUTHENTICATION_FAILED = -32007
    SSRF_BLOCKED = -32008
    JOB_NOT_FOUND = -32009
    JOB_CANCELLED = -32010
    URL_UNREACHABLE = -32011
    CANCEL_NOT_AUTHORIZED = -32012
    COST_CAP_REQUIRED = -32013
    COST_CAP_EXCEEDED = -32014
    INSUFFICIENT_SCOPE = -32015
    APPROVAL_TOKEN_REQUIRED = -32016
    INVALID_APPROVAL_TOKEN = -32017
