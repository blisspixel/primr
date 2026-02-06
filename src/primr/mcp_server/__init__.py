"""
Primr MCP Server Module.

This module provides Model Context Protocol (MCP) server capabilities for Primr,
enabling AI agents to drive company research programmatically.

Key components:
- server: MCPServer instance and configuration
- types: MCP-specific type definitions
- tools: Tool handler implementations
- resources: Resource handler implementations
- prompts: Prompt template definitions
- security: Security middleware (path validation, rate limiting)
- auth: HTTP authentication (token verification)
- job_store: Job state management with persistence
- logging_config: Stderr logging configuration for stdio mode
"""

from primr.mcp_server.auth import (
    AuthConfig,
    AuthContext,
    PrimrTokenVerifier,
)
from primr.mcp_server.server import PrimrMCPServer, create_mcp_server
from primr.mcp_server.types import (
    ArtifactInfo,
    ArtifactsResponse,
    CloudVendor,
    ConfigState,
    DoctorResult,
    EstimateResult,
    JobAcceptedResult,
    JobInfo,
    JobStatus,
    LatestOutput,
    MCPErrorCode,
    QAResult,
    ResearchMode,
    ResearchStage,
    ResearchStatus,
    StrategyType,
    ToolResult,
)

__all__ = [
    "ArtifactInfo",
    "ArtifactsResponse",
    "AuthConfig",
    "AuthContext",
    "CloudVendor",
    "ConfigState",
    "DoctorResult",
    "EstimateResult",
    "JobAcceptedResult",
    "JobInfo",
    "JobStatus",
    "LatestOutput",
    "MCPErrorCode",
    "PrimrMCPServer",
    "PrimrTokenVerifier",
    "QAResult",
    "ResearchMode",
    "ResearchStage",
    "ResearchStatus",
    "StrategyType",
    "ToolResult",
    "create_mcp_server",
]
