"""
Agentic tool handler implementations for MCP server.

This module provides tools for the agentic architecture:
- query_roadmap - Query roadmap for version status, blockers, features
- get_hypotheses - Retrieve hypotheses for a company
- save_hypothesis - Save or update a hypothesis

Requirements: 7.4, 7.5, 7.6
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent, Tool

if TYPE_CHECKING:
    from mcp.server import Server
    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)


def register_agentic_tools(server: Server, mcp_server: PrimrMCPServer) -> list[Tool]:
    """
    Register agentic architecture tools with the MCP server.

    Returns the list of tools for inclusion in list_tools().
    """
    return [
        Tool(
            name="query_roadmap",
            description="Query the roadmap for version status, blockers, or features",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query (e.g., 'What's blocking v1.7.0?')",
                    },
                    "version": {
                        "type": "string",
                        "description": "Specific version to query (e.g., '1.7.0' or 'v1.7.0')",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_hypotheses",
            description="Retrieve hypotheses for a company from research memory",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "Company name to retrieve hypotheses for",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["untested", "validated", "invalidated", "confirmed"],
                        "description": "Filter by confidence level (optional)",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Filter by topic (optional)",
                    },
                    "include_expired": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include expired hypotheses",
                    },
                },
                "required": ["company"],
            },
        ),
        Tool(
            name="save_hypothesis",
            description="Save or update a hypothesis in research memory",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "Company name",
                    },
                    "hypothesis_id": {
                        "type": "string",
                        "description": "Unique hypothesis ID",
                    },
                    "claim": {
                        "type": "string",
                        "description": "The hypothesis claim (required for new hypotheses)",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["untested", "validated", "invalidated", "confirmed"],
                        "description": "Confidence level",
                    },
                    "evidence": {
                        "type": "string",
                        "description": "Evidence supporting the confidence change",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Topic category (e.g., 'technology', 'financials')",
                    },
                },
                "required": ["company", "hypothesis_id"],
            },
        ),
    ]


async def handle_agentic_tool(
    name: str,
    arguments: dict[str, Any],
    mcp_server: PrimrMCPServer,
) -> list[TextContent] | None:
    """
    Handle agentic tool calls.

    Returns None if the tool is not an agentic tool.
    """
    if name == "query_roadmap":
        return await _handle_query_roadmap(arguments)
    elif name == "get_hypotheses":
        return await _handle_get_hypotheses(arguments, mcp_server)
    elif name == "save_hypothesis":
        return await _handle_save_hypothesis(arguments, mcp_server)

    return None


async def _handle_query_roadmap(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle query_roadmap tool.

    Requirements: 7.4
    """
    from primr.agentic.roadmap_api import RoadmapAPI, VersionStatus

    query = arguments.get("query", "")
    version = arguments.get("version")

    try:
        api = RoadmapAPI()

        # If specific version requested
        if version:
            # Normalize version (remove 'v' prefix if present)
            version_num = version.lstrip("v")
            v = api.get_version(version_num)

            if v:
                features_info = [
                    {"name": f.name, "status": f.status.value}
                    for f in v.features
                ]
                blockers = api.get_blockers(version_num)

                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "version": v.number,
                        "title": v.title,
                        "status": v.status.value,
                        "features": features_info,
                        "blockers": blockers,
                        "dependencies": v.dependencies,
                    }),
                )]
            else:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": True,
                        "error_type": "version_not_found",
                        "message": f"Version {version} not found in roadmap",
                    }),
                )]

        # Handle natural language queries
        query_lower = query.lower()

        # Blockers query
        if "blocking" in query_lower or "blocker" in query_lower:
            # Extract version from query
            match = re.search(r"v?(\d+\.\d+\.\d+)", query)
            if match:
                version_num = match.group(1)
                blockers = api.get_blockers(version_num)
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "version": version_num,
                        "blockers": blockers,
                    }),
                )]

        # Status query
        if "in progress" in query_lower or "current" in query_lower:
            versions = api.list_by_status(VersionStatus.IN_PROGRESS)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "in_progress",
                    "versions": [
                        {"number": v.number, "title": v.title}
                        for v in versions
                    ],
                }),
            )]

        if "planned" in query_lower or "upcoming" in query_lower:
            versions = api.list_by_status(VersionStatus.PLANNED)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "planned",
                    "versions": [
                        {"number": v.number, "title": v.title}
                        for v in versions
                    ],
                }),
            )]

        if "completed" in query_lower or "done" in query_lower:
            versions = api.list_by_status(VersionStatus.COMPLETED)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "completed",
                    "versions": [
                        {"number": v.number, "title": v.title}
                        for v in versions
                    ],
                }),
            )]

        # Default: return full roadmap summary
        return [TextContent(
            type="text",
            text=api.to_json(),
        )]

    except FileNotFoundError:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "roadmap_not_found",
                "message": "ROADMAP.md not found",
            }),
        )]
    except Exception as e:
        logger.exception("Roadmap query failed")
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "roadmap_query_failed",
                "message": str(e),
            }),
        )]


async def _handle_get_hypotheses(
    arguments: dict[str, Any],
    mcp_server: PrimrMCPServer,
) -> list[TextContent]:
    """
    Handle get_hypotheses tool.

    Requirements: 7.5
    """
    from primr.agentic.memory import ResearchMemory
    from primr.agentic.models import ConfidenceLevel

    company = arguments.get("company")
    confidence_str = arguments.get("confidence")
    topic = arguments.get("topic")
    include_expired = arguments.get("include_expired", False)

    try:
        # Get memory storage path from config or use default
        memory_path = getattr(mcp_server, '_memory_path', None)
        if memory_path is None:
            memory_path = Path("logs/research_memory")

        memory = ResearchMemory(storage_path=memory_path)

        # Convert confidence string to enum if provided
        confidence = None
        if confidence_str:
            try:
                confidence = ConfidenceLevel(confidence_str)
            except ValueError:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": True,
                        "error_type": "invalid_confidence",
                        "message": f"Invalid confidence level: {confidence_str}",
                    }),
                )]

        # Get hypotheses
        hypotheses = memory.get_hypotheses(
            company,
            confidence=confidence,
            topic=topic,
            include_expired=include_expired,
        )

        return [TextContent(
            type="text",
            text=json.dumps({
                "company": company,
                "count": len(hypotheses),
                "hypotheses": [h.to_dict() for h in hypotheses],
            }),
        )]

    except Exception as e:
        logger.exception("Get hypotheses failed")
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "get_hypotheses_failed",
                "message": str(e),
            }),
        )]


async def _handle_save_hypothesis(
    arguments: dict[str, Any],
    mcp_server: PrimrMCPServer,
) -> list[TextContent]:
    """
    Handle save_hypothesis tool.

    Requirements: 7.6
    """
    from primr.agentic.memory import ResearchMemory
    from primr.agentic.models import ConfidenceLevel, Hypothesis

    company = arguments.get("company")
    hypothesis_id = arguments.get("hypothesis_id")
    claim = arguments.get("claim")
    confidence_str = arguments.get("confidence", "untested")
    evidence = arguments.get("evidence")
    topic = arguments.get("topic", "")

    try:
        # Get memory storage path from config or use default
        memory_path = getattr(mcp_server, '_memory_path', None)
        if memory_path is None:
            memory_path = Path("logs/research_memory")

        memory = ResearchMemory(storage_path=memory_path)

        # Convert confidence string to enum
        try:
            confidence = ConfidenceLevel(confidence_str)
        except ValueError:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": True,
                    "error_type": "invalid_confidence",
                    "message": f"Invalid confidence level: {confidence_str}",
                }),
            )]

        # Check if hypothesis exists
        existing = memory.get_hypotheses(company, include_expired=True)
        existing_ids = {h.id for h in existing}

        if hypothesis_id in existing_ids:
            # Update existing hypothesis
            if evidence:
                result = memory.update_hypothesis(
                    company,
                    hypothesis_id,
                    confidence,
                    evidence,
                )
                if result:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "success": True,
                            "action": "updated",
                            "hypothesis_id": hypothesis_id,
                            "confidence": confidence.value,
                        }),
                    )]
            else:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": True,
                        "error_type": "evidence_required",
                        "message": "Evidence is required when updating hypothesis confidence",
                    }),
                )]
        else:
            # Create new hypothesis
            if not claim:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": True,
                        "error_type": "claim_required",
                        "message": "Claim is required for new hypotheses",
                    }),
                )]

            new_hypothesis = Hypothesis(
                id=hypothesis_id,
                claim=claim,
                confidence=confidence,
                evidence=[evidence] if evidence else [],
                topic=topic,
            )

            memory.save_hypotheses(company, [new_hypothesis])

            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "action": "created",
                    "hypothesis_id": hypothesis_id,
                    "confidence": confidence.value,
                }),
            )]

    except Exception as e:
        logger.exception("Save hypothesis failed")
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_type": "save_hypothesis_failed",
                "message": str(e),
            }),
        )]
