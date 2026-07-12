"""Calibration-related MCP resource handlers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import AnyUrl, Resource

from primr.mcp_server.server_context import MCPServerContext
from primr.qa.calibration_baseline import inspect_calibration_baseline, read_calibration_baseline

CALIBRATION_BASELINE_INSPECTION_URI = "primr://calibration/baseline/inspection"
CALIBRATION_BASELINE_INSPECTION_RESOURCE = Resource(
    uri=AnyUrl(f"{CALIBRATION_BASELINE_INSPECTION_URI}?path={{baseline_path}}"),
    name="Calibration Baseline Inspection",
    description=(
        "Machine-readable readiness blockers for an existing baseline artifact. "
        "The path query must point inside MCP allowed roots."
    ),
    mimeType="application/json",
)


def read_calibration_baseline_inspection_resource(
    mcp_server: MCPServerContext,
    uri: str,
    *,
    client_id: str,
) -> list[ReadResourceContents]:
    """Read a path-validated calibration baseline inspection resource."""
    parsed = urlparse(uri)
    path_values = parse_qs(parsed.query).get("path", [])
    if parsed.netloc != "calibration" or parsed.path != "/baseline/inspection":
        raise ValueError(f"Invalid calibration baseline inspection URI: {uri}")
    if len(path_values) != 1 or not path_values[0]:
        return _json_resource(
            {
                "error": "missing_path",
                "message": (
                    "Expected URI format: "
                    "primr://calibration/baseline/inspection?path=<baseline.json>"
                ),
            }
        )

    requested_path = path_values[0]
    path_result = mcp_server.path_validator.validate(requested_path, client_id)
    if not path_result.valid or path_result.resolved_path is None:
        return _json_resource(
            {
                "error": "invalid_path",
                "error_type": path_result.error_type,
                "message": path_result.error_message,
            }
        )

    try:
        baseline = read_calibration_baseline(path_result.resolved_path)
        inspection = inspect_calibration_baseline(
            baseline,
            baseline_path=Path(requested_path),
        )
    except (OSError, ValueError) as exc:
        return _json_resource(
            {
                "error": "baseline_unavailable",
                "message": str(exc),
            }
        )
    return _json_resource(inspection)


def _json_resource(data: dict[str, Any]) -> list[ReadResourceContents]:
    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]
