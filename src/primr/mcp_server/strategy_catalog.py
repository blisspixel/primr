"""Standalone strategy catalog and execution mapping."""

from __future__ import annotations

from primr.config.models import DEEP_RESEARCH_COST
from primr.mcp_server.types import StrategyType

AI_STRATEGY_TYPES = frozenset({"ai", StrategyType.AI_STRATEGY.value})
GENERIC_STRATEGY_YAMLS = {
    StrategyType.CUSTOMER_EXPERIENCE.value: "customer_experience",
    StrategyType.MODERN_SECURITY_COMPLIANCE.value: "modern_security_compliance",
    StrategyType.DATA_FABRIC_STRATEGY.value: "data_fabric_strategy",
    StrategyType.SKILLS.value: "skills",
}

_COST_BASIS = (
    "Planning estimate for one standard Gemini Deep Research task; actual token "
    "and tool usage varies."
)


def get_strategy_catalog() -> list[dict[str, object]]:
    """Return standalone strategies priced against their actual execution seam."""
    task_cost = DEEP_RESEARCH_COST.standard_task_cost
    return [
        {
            "id": StrategyType.AI_STRATEGY.value,
            "name": "AI Strategy",
            "description": "Business-first AI portfolio, economics, operating model, architecture, and governance",
            "requires_platform": True,
            "estimated_time_minutes": 15,
            "estimated_cost_usd": task_cost,
            "cost_basis": _COST_BASIS,
        },
        {
            "id": StrategyType.CUSTOMER_EXPERIENCE.value,
            "name": "Customer Experience Strategy",
            "description": "CX transformation and digital experience improvement plan",
            "requires_platform": False,
            "estimated_time_minutes": 12,
            "estimated_cost_usd": task_cost,
            "cost_basis": _COST_BASIS,
        },
        {
            "id": StrategyType.MODERN_SECURITY_COMPLIANCE.value,
            "name": "Security & Compliance Strategy",
            "description": "Zero Trust architecture and compliance posture assessment",
            "requires_platform": False,
            "estimated_time_minutes": 12,
            "estimated_cost_usd": task_cost,
            "cost_basis": _COST_BASIS,
        },
        {
            "id": StrategyType.DATA_FABRIC_STRATEGY.value,
            "name": "Data Fabric Strategy",
            "description": "Modern data platform for agentic AI and semantic layers",
            "requires_platform": False,
            "estimated_time_minutes": 12,
            "estimated_cost_usd": task_cost,
            "cost_basis": _COST_BASIS,
        },
        {
            "id": StrategyType.SKILLS.value,
            "name": "Skills Ideation",
            "description": "Top-5 roles x top-3 skills hypothesis grounded in research signals",
            "requires_platform": False,
            "estimated_time_minutes": 8,
            "estimated_cost_usd": task_cost,
            "cost_basis": _COST_BASIS,
        },
    ]


__all__ = ["AI_STRATEGY_TYPES", "GENERIC_STRATEGY_YAMLS", "get_strategy_catalog"]
