"""
Agentic resource handler implementations for MCP server.

This module provides read-only resources for agentic architecture:
- primr://roadmap - Roadmap data as JSON
- primr://memory/{company} - Company research memory
- primr://context - Current context map summary

Requirements: 7.1, 7.2, 7.3
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource

from primr.mcp_server.server_context import MCPServerContext

logger = logging.getLogger(__name__)


def get_agentic_resources() -> list[Resource]:
    """
    Return the list of agentic resources for inclusion in list_resources().
    """
    return [
        Resource(
            uri="primr://roadmap",
            name="Roadmap",
            description="Project roadmap with versions, features, and blockers",
            mimeType="application/json",
        ),
        Resource(
            uri="primr://memory/{company}",
            name="Company Memory",
            description="Research memory for a specific company (hypotheses, patterns)",
            mimeType="application/json",
        ),
        Resource(
            uri="primr://context",
            name="Context Map",
            description="Current context map summary for agent orientation",
            mimeType="application/json",
        ),
    ]


def read_agentic_resource(
    uri: str,
    mcp_server: MCPServerContext,
) -> list[ReadResourceContents] | None:
    """
    Read an agentic resource by URI.

    Returns None if the URI is not an agentic resource.
    """
    uri_str = str(uri)

    if uri_str == "primr://roadmap" or uri_str.startswith("primr://roadmap"):
        return _read_roadmap()
    elif uri_str.startswith("primr://memory/"):
        return _read_memory(uri_str, mcp_server)
    elif uri_str == "primr://context" or uri_str.startswith("primr://context"):
        return _read_context()

    return None


def _read_roadmap() -> list[ReadResourceContents]:
    """
    Read roadmap data as JSON.

    Requirements: 7.1
    """
    from primr.agentic.roadmap_api import RoadmapAPI

    try:
        api = RoadmapAPI()
        roadmap_json = api.to_json()

        return [
            ReadResourceContents(
                content=roadmap_json,
                mime_type="application/json",
            )
        ]

    except FileNotFoundError:
        data = {
            "error": "roadmap_not_found",
            "message": "ROADMAP.md not found in project root",
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]
    except Exception as e:
        logger.exception("Failed to read roadmap")
        data = {
            "error": "roadmap_read_error",
            "message": str(e),
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]


def _read_memory(uri: str, mcp_server: MCPServerContext) -> list[ReadResourceContents]:
    """
    Read company research memory.

    Requirements: 7.2
    """
    import re

    from primr.agentic.memory import ResearchMemory

    # Extract company name from URI
    # URI format: primr://memory/{company}
    match = re.match(r"primr://memory/([^/?]+)", uri)
    if not match:
        data = {
            "error": "invalid_uri",
            "message": "Invalid memory URI format. Expected: primr://memory/{company}",
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    company = match.group(1)
    # URL decode the company name
    from urllib.parse import unquote

    company = unquote(company)

    try:
        memory_path = getattr(mcp_server, "_memory_path", None)
        memory = ResearchMemory(storage_path=memory_path)
        memory_json = memory.to_json(company)

        return [
            ReadResourceContents(
                content=memory_json,
                mime_type="application/json",
            )
        ]

    except Exception as e:
        logger.exception(f"Failed to read memory for {company}")
        data = {
            "error": "memory_read_error",
            "company": company,
            "message": str(e),
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]


def _read_context() -> list[ReadResourceContents]:
    """
    Read context map summary.

    Requirements: 7.3
    """
    # Check if CLAUDE.md exists
    claude_md_path = Path("CLAUDE.md")

    if not claude_md_path.exists():
        data = {
            "error": "context_not_found",
            "message": "CLAUDE.md not found in project root",
            "suggestion": "Run the agentic architecture setup to create CLAUDE.md",
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    try:
        content = claude_md_path.read_text(encoding="utf-8")

        # Extract key sections for summary
        summary = _extract_context_summary(content)

        data = {
            "context_map_path": str(claude_md_path),
            "summary": summary,
            "full_content_available": True,
            "quick_start": _extract_quick_start(content),
        }

        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]

    except Exception as e:
        logger.exception("Failed to read context map")
        data = {
            "error": "context_read_error",
            "message": str(e),
        }
        return [
            ReadResourceContents(
                content=json.dumps(data, indent=2),
                mime_type="application/json",
            )
        ]


def _extract_context_summary(content: str) -> dict:
    """
    Extract a summary of the context map sections.
    """
    import re

    sections = []

    # Find all ## headers
    for match in re.finditer(r"^## (.+)$", content, re.MULTILINE):
        sections.append(match.group(1))

    # Count key elements
    has_quick_start = "Quick Start" in content
    has_negative_constraints = "NEVER" in content or "Negative Constraints" in content
    has_verification = "Verification" in content
    has_progressive_disclosure = "<details>" in content

    return {
        "sections": sections,
        "has_quick_start": has_quick_start,
        "has_negative_constraints": has_negative_constraints,
        "has_verification_commands": has_verification,
        "has_progressive_disclosure": has_progressive_disclosure,
    }


def _extract_quick_start(content: str) -> str | None:
    """
    Extract the Quick Start section content.
    """
    import re

    # Find Quick Start section
    match = re.search(
        r"## Quick Start.*?\n(.*?)(?=\n---|\n## [^#])", content, re.DOTALL | re.IGNORECASE
    )

    if match:
        # Return just the content, not the header
        quick_start = match.group(1).strip()
        # Limit to first 1000 chars for summary
        if len(quick_start) > 1000:
            quick_start = quick_start[:1000] + "..."
        return quick_start

    return None
