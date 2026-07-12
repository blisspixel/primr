"""Execution-shape validation for provider-backed MCP research jobs."""

from __future__ import annotations

from typing import Any

from primr.mcp_server.types import MCPErrorCode

RESEARCH_MODES = frozenset({"scrape", "deep", "full", "premium"})
RESEARCH_PLATFORMS = frozenset(
    {
        "azure",
        "aws",
        "gcp",
        "agnostic",
        "private",
        "microsoft",
        "amazon",
        "google",
        "nvidia",
    }
)
RESEARCH_BOOLEAN_FIELDS = ("no_ai_strategy", "skip_qa", "verify")
ESTIMATE_BOOLEAN_FIELDS = ("no_ai_strategy", "verify")
INTEGRATED_STRATEGY_TYPE = "ai"


def validate_research_estimate_arguments(
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    """Reject estimates that cannot be executed by ``research_company``.

    Integrated MCP research currently owns one AI strategy document. Extra
    platform documents and YAML-defined strategy modules use the standalone
    ``estimate_strategy`` and ``generate_strategy`` flow after research.
    """
    if error := _validate_mode(arguments):
        return error
    if error := _validate_strategy_type(arguments):
        return error
    if error := _validate_boolean_fields(arguments, ESTIMATE_BOOLEAN_FIELDS):
        return error

    platforms = arguments.get("platforms")
    platform = arguments.get("platform")
    if platforms is not None and platform is not None:
        return {
            "error": True,
            "error_type": "conflicting_platform_parameters",
            "error_code": MCPErrorCode.INVALID_PARAMS,
            "parameter": "platforms",
            "message": "Use platform or platforms, not both",
        }
    if platforms is None:
        if platform is None:
            return None
        return _validate_platform(platform, parameter="platform")
    if not isinstance(platforms, list):
        return _invalid_parameter("platforms", "platforms must be an array with one item")
    if len(platforms) != 1:
        return {
            "error": True,
            "error_type": "unsupported_platform_fanout",
            "error_code": MCPErrorCode.INVALID_PARAMS,
            "parameter": "platforms",
            "message": (
                "estimate_run supports exactly one strategy platform because "
                "research_company produces one integrated AI strategy document"
            ),
        }
    return _validate_platform(platforms[0], parameter="platforms")


def validate_research_execution_arguments(
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    """Reject execution shapes the MCP input schema cannot itself enforce."""
    if error := _validate_mode(arguments):
        return error
    if "platforms" in arguments:
        return {
            "error": True,
            "error_type": "unsupported_platforms_parameter",
            "error_code": MCPErrorCode.INVALID_PARAMS,
            "parameter": "platforms",
            "message": (
                "research_company accepts one strategy target through platform; "
                "platforms fan-out is not supported"
            ),
        }
    if error := _validate_strategy_type(arguments):
        return error

    platform = arguments.get("platform")
    if platform is not None:
        if error := _validate_platform(platform, parameter="platform"):
            return error

    return _validate_boolean_fields(arguments, RESEARCH_BOOLEAN_FIELDS)


def _validate_mode(arguments: dict[str, Any]) -> dict[str, Any] | None:
    mode = arguments.get("mode", "full")
    if isinstance(mode, str) and mode in RESEARCH_MODES:
        return None
    return {
        "error": True,
        "error_type": "invalid_mode",
        "error_code": MCPErrorCode.INVALID_PARAMS,
        "message": "mode must be one of: scrape, deep, full, premium",
    }


def _validate_strategy_type(arguments: dict[str, Any]) -> dict[str, Any] | None:
    strategy_type = arguments.get("strategy_type", INTEGRATED_STRATEGY_TYPE)
    if strategy_type == INTEGRATED_STRATEGY_TYPE:
        return None
    return {
        "error": True,
        "error_type": "unsupported_strategy_type",
        "error_code": MCPErrorCode.INVALID_PARAMS,
        "parameter": "strategy_type",
        "message": (
            "Integrated research supports strategy_type 'ai' only; use "
            "estimate_strategy and generate_strategy for other strategy modules"
        ),
    }


def _validate_platform(value: Any, *, parameter: str) -> dict[str, Any] | None:
    if isinstance(value, str) and value in RESEARCH_PLATFORMS:
        return None
    if value == "ms":
        return {
            "error": True,
            "error_type": "unsupported_platform_fanout",
            "error_code": MCPErrorCode.INVALID_PARAMS,
            "parameter": parameter,
            "message": (
                "The ms alias expands to azure and private, but integrated research "
                "supports exactly one strategy platform"
            ),
        }
    return _invalid_parameter(
        parameter,
        f"{parameter} must contain a supported single-platform identifier",
        error_type="invalid_platform",
    )


def _validate_boolean_fields(
    arguments: dict[str, Any], field_names: tuple[str, ...]
) -> dict[str, Any] | None:
    for field_name in field_names:
        if field_name in arguments and not isinstance(arguments[field_name], bool):
            return _invalid_parameter(field_name, f"{field_name} must be a boolean")
    return None


def _invalid_parameter(
    parameter: str,
    message: str,
    *,
    error_type: str = "invalid_parameter",
) -> dict[str, Any]:
    return {
        "error": True,
        "error_type": error_type,
        "error_code": MCPErrorCode.INVALID_PARAMS,
        "parameter": parameter,
        "message": message,
    }


__all__ = [
    "validate_research_estimate_arguments",
    "validate_research_execution_arguments",
]
