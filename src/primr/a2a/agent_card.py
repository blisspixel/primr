"""Build an A2A AgentCard describing Primr's capabilities.

The AgentCard is a JSON document served at /.well-known/agent.json that tells
A2A clients what Primr can do and how to interact with it.

Requires: pip install primr[a2a]
"""

from __future__ import annotations

import logging
from importlib.metadata import version as pkg_version

from a2a.types import (
    AgentAuthentication,
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

logger = logging.getLogger(__name__)

# Skill definitions mapping to existing MCP tools
_SKILLS: list[dict] = [
    {
        "id": "estimate_research",
        "name": "Estimate Research Cost",
        "description": (
            "Estimate the cost, time, and page count for a company research run. "
            "Call this before starting research."
        ),
        "tags": ["estimate", "cost", "planning"],
        "examples": [
            "How much would it cost to research Acme Corp?",
            "Estimate research for https://example.com",
        ],
    },
    {
        "id": "research_company",
        "name": "Research Company",
        "description": (
            "Start an asynchronous company research job. Returns a job ID for tracking. "
            "Supports modes: scrape (website only), deep (external research), "
            "full (Grok-powered), premium (Gemini + Deep Research)."
        ),
        "tags": ["research", "company", "async", "intelligence"],
        "examples": [
            "Research Acme Corp at https://acme.com",
            "Run a deep research job on https://example.com",
        ],
    },
    {
        "id": "check_jobs",
        "name": "Check Research Jobs",
        "description": "Check the status of the current or most recent research job.",
        "tags": ["status", "jobs", "monitoring"],
        "examples": [
            "What's the status of the current research?",
            "Is the research job finished?",
        ],
    },
    {
        "id": "run_qa",
        "name": "Run Quality Assessment",
        "description": (
            "Run a quality assessment on a completed research report. "
            "Returns scores and improvement suggestions."
        ),
        "tags": ["qa", "quality", "assessment"],
        "examples": [
            "Run QA on the latest report",
            "Check the quality of the Acme Corp report",
        ],
    },
    {
        "id": "system_health",
        "name": "System Health Check",
        "description": (
            "Check Primr system health: API keys, dependencies, and configuration."
        ),
        "tags": ["health", "doctor", "diagnostics"],
        "examples": [
            "Is the system healthy?",
            "Run a health check",
        ],
    },
]


def build_agent_card(
    host: str = "localhost",
    port: int = 9000,
    version: str | None = None,
) -> AgentCard:
    """Build an AgentCard for the Primr A2A server.

    Args:
        host: Server hostname.
        port: Server port.
        version: Version string. If None, reads from package metadata.

    Returns:
        Configured AgentCard instance.
    """
    if version is None:
        try:
            version = pkg_version("primr")
        except Exception:
            version = "0.0.0"

    url = f"http://{host}:{port}/"

    skills = [
        AgentSkill(
            id=s["id"],
            name=s["name"],
            description=s["description"],
            tags=s["tags"],
            examples=s["examples"],
        )
        for s in _SKILLS
    ]

    card = AgentCard(
        name="Primr Research Agent",
        description=(
            "Company research agent that generates strategic intelligence briefs "
            "from adaptive scraping and AI-powered research and synthesis. "
            "Supports website scraping, deep external research, and premium "
            "Gemini-powered analysis."
        ),
        url=url,
        version=version,
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
        ),
        skills=skills,
        authentication=AgentAuthentication(schemes=["bearer"]),
    )

    logger.info("Built AgentCard: %s v%s at %s (%d skills)", card.name, version, url, len(skills))
    return card
