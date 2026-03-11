"""Primr MCP server exports with lazy loading."""

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "AuthConfig": ("primr.mcp_server.auth", "AuthConfig"),
    "AuthContext": ("primr.mcp_server.auth", "AuthContext"),
    "PrimrTokenVerifier": ("primr.mcp_server.auth", "PrimrTokenVerifier"),
    "PrimrMCPServer": ("primr.mcp_server.server", "PrimrMCPServer"),
    "create_mcp_server": ("primr.mcp_server.server", "create_mcp_server"),
    "ArtifactInfo": ("primr.mcp_server.types", "ArtifactInfo"),
    "ArtifactsResponse": ("primr.mcp_server.types", "ArtifactsResponse"),
    "CloudVendor": ("primr.mcp_server.types", "CloudVendor"),
    "ConfigState": ("primr.mcp_server.types", "ConfigState"),
    "DoctorResult": ("primr.mcp_server.types", "DoctorResult"),
    "EstimateResult": ("primr.mcp_server.types", "EstimateResult"),
    "JobAcceptedResult": ("primr.mcp_server.types", "JobAcceptedResult"),
    "JobInfo": ("primr.mcp_server.types", "JobInfo"),
    "JobStatus": ("primr.mcp_server.types", "JobStatus"),
    "LatestOutput": ("primr.mcp_server.types", "LatestOutput"),
    "MCPErrorCode": ("primr.mcp_server.types", "MCPErrorCode"),
    "QAResult": ("primr.mcp_server.types", "QAResult"),
    "ResearchMode": ("primr.mcp_server.types", "ResearchMode"),
    "ResearchStage": ("primr.mcp_server.types", "ResearchStage"),
    "ResearchStatus": ("primr.mcp_server.types", "ResearchStatus"),
    "StrategyType": ("primr.mcp_server.types", "StrategyType"),
    "ToolResult": ("primr.mcp_server.types", "ToolResult"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'primr.mcp_server' has no attribute '{name}'")
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
