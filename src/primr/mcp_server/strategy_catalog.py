"""Standalone strategy catalog and execution mapping."""

from __future__ import annotations

from primr.core.strategy_estimate import AI_STRATEGY_IDS, estimate_standalone_strategy
from primr.mcp_server.types import StrategyType

AI_STRATEGY_TYPES = AI_STRATEGY_IDS
GENERIC_STRATEGY_YAMLS = {
    StrategyType.CUSTOMER_EXPERIENCE.value: "customer_experience",
    StrategyType.MODERN_SECURITY_COMPLIANCE.value: "modern_security_compliance",
    StrategyType.DATA_FABRIC_STRATEGY.value: "data_fabric_strategy",
    StrategyType.SKILLS.value: "skills",
}


def get_strategy_catalog() -> list[dict[str, object]]:
    """Return standalone strategies priced against their actual execution seam."""
    items = [
        {
            "id": StrategyType.AI_STRATEGY.value,
            "name": "AI Strategy",
            "description": "Business-first AI portfolio, economics, operating model, architecture, and governance",
            "requires_platform": True,
        },
        {
            "id": StrategyType.CUSTOMER_EXPERIENCE.value,
            "name": "Customer Experience Strategy",
            "description": "CX transformation and digital experience improvement plan",
            "requires_platform": False,
        },
        {
            "id": StrategyType.MODERN_SECURITY_COMPLIANCE.value,
            "name": "Security & Compliance Strategy",
            "description": "Zero Trust architecture and compliance posture assessment",
            "requires_platform": False,
        },
        {
            "id": StrategyType.DATA_FABRIC_STRATEGY.value,
            "name": "Data Fabric Strategy",
            "description": "Modern data platform for agentic AI and semantic layers",
            "requires_platform": False,
        },
        {
            "id": StrategyType.SKILLS.value,
            "name": "Skills Ideation",
            "description": "Top-5 roles x top-3 skills hypothesis grounded in research signals",
            "requires_platform": False,
        },
    ]
    catalog: list[dict[str, object]] = []
    for item in items:
        estimate = estimate_standalone_strategy(str(item["id"]))
        catalog.append(
            {
                **item,
                "estimated_time_minutes": estimate.estimated_time_minutes,
                "estimated_cost_usd": estimate.estimated_cost_usd,
                "cost_basis": estimate.cost_basis,
            }
        )
    return catalog


__all__ = ["AI_STRATEGY_TYPES", "GENERIC_STRATEGY_YAMLS", "get_strategy_catalog"]
