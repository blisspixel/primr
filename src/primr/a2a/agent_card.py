"""Build an A2A AgentCard describing Primr's capabilities.

The AgentCard is a JSON document served at /.well-known/agent.json that tells
A2A clients what Primr can do and how to interact with it.

Requires: pip install primr[a2a]
"""

from __future__ import annotations

import logging
from importlib.metadata import version as pkg_version

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    HTTPAuthSecurityScheme,
    SecurityScheme,
)

logger = logging.getLogger(__name__)

# Skill definitions mapping to existing MCP tools.
#
# Input/output format documented in description since a2a-sdk v0.3.x
# AgentSkill does not have inputSchema/outputSchema fields.
# When SDK adds schema support, migrate to structured schemas.
_SKILLS: list[dict] = [
    {
        "id": "estimate_research",
        "name": "Estimate Research Cost",
        "description": (
            "Estimate the cost, time, and page count for a company research run. "
            "Call this before starting research.\n\n"
            'Input (JSON or natural language): {"url": "https://example.com", "mode": "full"}\n'
            "Modes: scrape (~$0.10, 5-10 min), deep (~$2.50, 10-15 min), "
            "full (~$0.55, ~30 min, default), premium (~$5, 50-75 min)\n\n"
            "Output: JSON with estimated_cost_usd, estimated_time_minutes, estimated_pages"
        ),
        "tags": ["estimate", "cost", "planning"],
        "examples": [
            "How much would it cost to research Acme Corp?",
            "Estimate research for https://example.com",
            '{"url": "https://acme.com", "mode": "deep"}',
        ],
    },
    {
        "id": "research_company",
        "name": "Research Company",
        "description": (
            "Start an asynchronous company research job. Returns a job ID for "
            "tracking. Streams progress events via SSE until completion.\n\n"
            "Input (JSON or natural language): "
            '{"url": "https://example.com", "name": "Acme Corp", "mode": "full"}\n'
            "Modes: scrape (website only), deep (external research), "
            "full (Grok-powered, default), premium (Gemini + Deep Research)\n\n"
            "Output: SSE stream of TaskStatusUpdateEvent, final artifact is "
            "a .docx research brief path"
        ),
        "tags": ["research", "company", "async", "intelligence", "streaming"],
        "examples": [
            "Research Acme Corp at https://acme.com",
            "Run a deep research job on https://example.com",
            '{"url": "https://acme.com", "name": "Acme Corp", "mode": "premium"}',
        ],
    },
    {
        "id": "check_jobs",
        "name": "Check Research Jobs",
        "description": (
            "Check the status of the current or most recent research job.\n\n"
            "Input: none required\n\n"
            "Output: JSON with job_id, company, stage, progress (0-100), status"
        ),
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
            "Returns scores and improvement suggestions.\n\n"
            'Input (JSON or natural language): {"path": "/path/to/report.docx"}\n'
            "If path omitted, uses the latest completed report.\n\n"
            "Output: JSON with overall_score (0-100), section_scores, "
            "improvement_suggestions, confidence_level"
        ),
        "tags": ["qa", "quality", "assessment"],
        "examples": [
            "Run QA on the latest report",
            "Check the quality of the Acme Corp report",
            '{"path": "output/acme-corp/report.docx"}',
        ],
    },
    {
        "id": "read_stage_scorecard",
        "name": "Read Stage Scorecard Summary",
        "description": (
            "Read a compact routed-stage eval scorecard summary by eval ID. "
            "Returns route, quality-score, status, blocker, and artifact metadata "
            "without prompt bodies, report bodies, raw run-state content, or "
            "quality-source bodies.\n\n"
            'Input (JSON or text): {"eval_id": "eval-2026-06-source-relevance"}\n\n'
            "Output: JSON with eval_id, artifact metadata, status counts, blocker "
            "counts, route totals, quality score stats, and compact scorecard rows"
        ),
        "tags": ["eval", "scorecard", "read", "routing"],
        "examples": [
            "Read stage scorecard eval-2026-06-source-relevance",
            '{"eval_id": "eval-2026-06-source-relevance"}',
        ],
    },
    {
        "id": "system_health",
        "name": "System Health Check",
        "description": (
            "Check Primr system health: API keys, dependencies, and configuration.\n\n"
            "Input: none required\n\n"
            "Output: JSON with status (healthy/degraded/unhealthy), checks array "
            "with individual component statuses"
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
    path: str = "/",
    scheme: str = "http",
) -> AgentCard:
    """Build an AgentCard for the Primr A2A server.

    Args:
        host: Server hostname.
        port: Server port that is actually listening for A2A traffic.
        version: Version string. If None, reads from package metadata.
        path: Path prefix the A2A app is mounted under. Must match the
            actual mount; in co-hosted mode this is ``/a2a/`` because the
            A2A app is mounted under the MCP Starlette listener rather
            than getting its own uvicorn server.
        scheme: ``http`` or ``https``.

    The previous signature accepted only host+port, which caused co-hosted
    deployments to advertise ``http://host:a2a_port/`` even though no
    listener was bound on ``a2a_port`` — clients following AgentCard.url
    would talk to whatever service did happen to be listening there and
    could leak bearer tokens to it.
    """
    if version is None:
        try:
            version = pkg_version("primr")
        except Exception as e:
            logger.warning("Failed to get primr version from package metadata: %s", e)
            version = "0.0.0"

    normalized_path = path if path.startswith("/") else f"/{path}"
    if not normalized_path.endswith("/"):
        normalized_path = normalized_path + "/"
    url = f"{scheme}://{host}:{port}{normalized_path}"

    skills = [
        AgentSkill(
            id=s["id"],
            name=s["name"],
            description=s["description"],
            tags=s["tags"],
            examples=s["examples"],
            input_modes=["text"],
            output_modes=["text"],
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
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
        ),
        skills=skills,
        security_schemes={
            "bearer": SecurityScheme(root=HTTPAuthSecurityScheme(scheme="bearer", type="http")),
        },
        security=[{"bearer": []}],
    )

    logger.info("Built AgentCard: %s v%s at %s (%d skills)", card.name, version, url, len(skills))
    return card
