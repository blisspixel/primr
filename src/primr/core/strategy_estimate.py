"""Planning estimates for one standalone strategy operation."""

from __future__ import annotations

from dataclasses import dataclass

from primr.config.models import (
    DEEP_RESEARCH_COST,
    LITE_AI_STRATEGY_MAX_INPUT_TOKENS,
    LITE_AI_STRATEGY_MAX_OUTPUT_TOKENS,
    PrimrModels,
)
from primr.utils.cost_estimator import AI_STRATEGY_OVERHEAD, LITE_AI_STRATEGY_OVERHEAD

AI_STRATEGY_IDS = frozenset({"ai", "ai_strategy"})
GENERIC_STRATEGY_IDS = frozenset(
    {
        "customer_experience",
        "modern_security_compliance",
        "data_fabric_strategy",
        "skills",
    }
)
SUPPORTED_STRATEGY_IDS = AI_STRATEGY_IDS | GENERIC_STRATEGY_IDS


@dataclass(frozen=True)
class StandaloneStrategyEstimate:
    """Conservative estimate for the exact standalone execution shape."""

    strategy_type: str
    platforms: tuple[str, ...]
    lite_strategy: bool
    strategy_calls: int
    deep_research_tasks: int
    vendor_refresh_tasks: int
    model_name: str | None
    estimated_cost_usd: float
    estimated_time_min_minutes: int
    estimated_time_max_minutes: int
    cost_basis: str

    @property
    def estimated_time_minutes(self) -> int:
        """Return the conservative point value used by compact catalogs."""
        return self.estimated_time_max_minutes

    @property
    def estimated_time_range(self) -> str:
        return f"{self.estimated_time_min_minutes}-{self.estimated_time_max_minutes} min"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "primr.strategy-estimate.v1",
            "strategy_type": self.strategy_type,
            "platforms": list(self.platforms),
            "lite_strategy": self.lite_strategy,
            "strategy_calls": self.strategy_calls,
            "deep_research_tasks": self.deep_research_tasks,
            "vendor_refresh_tasks": self.vendor_refresh_tasks,
            "model_name": self.model_name,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_time_minutes": self.estimated_time_minutes,
            "estimated_time_range": self.estimated_time_range,
            "cost_basis": self.cost_basis,
        }


# Conservative token shape + grounding surcharge for one grounded lite vendor
# AI-news brief (Pro model + one live Google Search request).
_LITE_VENDOR_NEWS_INPUT_TOKENS = 8_000
_LITE_VENDOR_NEWS_OUTPUT_TOKENS = 12_000
_GROUNDING_REQUEST_COST = 0.035


def _lite_vendor_news_cost() -> float:
    """Conservative cost of one grounded lite vendor AI-news brief."""
    token_cost = PrimrModels.calculate_cost_conservative(
        PrimrModels.PRO_MODEL,
        _LITE_VENDOR_NEWS_INPUT_TOKENS,
        _LITE_VENDOR_NEWS_OUTPUT_TOKENS,
    )
    return round(token_cost + _GROUNDING_REQUEST_COST, 6)


def estimate_standalone_strategy(
    strategy_type: str,
    *,
    platforms: tuple[str, ...] = ("agnostic",),
    lite_strategy: bool = False,
    refresh_vendor_research: bool = False,
) -> StandaloneStrategyEstimate:
    """Estimate every model task the standalone runtime can start.

    AI strategy fan-out starts one generation call per platform. Standard AI
    and generic strategies use one Deep Research task per generated document.
    Lite AI generation uses the active Pro model, while an explicit vendor
    refresh remains a separate Deep Research task for each selected target.
    """
    normalized_type = strategy_type.strip().lower()
    if normalized_type not in SUPPORTED_STRATEGY_IDS:
        supported = ", ".join(sorted(SUPPORTED_STRATEGY_IDS))
        raise ValueError(
            f"Unsupported strategy type: {strategy_type}. Expected one of: {supported}"
        )

    normalized_platforms = tuple(dict.fromkeys(p.strip().lower() for p in platforms if p.strip()))
    if normalized_type in AI_STRATEGY_IDS:
        selected_platforms = normalized_platforms or ("agnostic",)
        strategy_calls = len(selected_platforms)
    else:
        selected_platforms = ("agnostic",)
        strategy_calls = 1
        lite_strategy = False

    vendor_refresh_tasks = 0
    if normalized_type in AI_STRATEGY_IDS and refresh_vendor_research:
        vendor_refresh_tasks = len(selected_platforms)

    # The engine choice (lite vs Deep Research) applies to BOTH the strategy and
    # the vendor AI-news refresh. Lite strategy generation uses one Pro-model
    # call; lite vendor news uses one grounded Google Search call per vendor.
    # Deep Research prices each as a flat Deep Research task.
    generation_dr_tasks = 0 if lite_strategy else strategy_calls
    vendor_refresh_dr_tasks = 0 if lite_strategy else vendor_refresh_tasks
    deep_research_tasks = generation_dr_tasks + vendor_refresh_dr_tasks
    deep_research_cost = deep_research_tasks * DEEP_RESEARCH_COST.standard_task_cost

    lite_cost = 0.0
    model_name = None
    if lite_strategy:
        from primr.ai.routing import Role, pick_model_for_role

        model_name = pick_model_for_role(Role.REASONING)
        lite_cost = PrimrModels.calculate_cost_conservative(
            model_name,
            LITE_AI_STRATEGY_MAX_INPUT_TOKENS * strategy_calls,
            LITE_AI_STRATEGY_MAX_OUTPUT_TOKENS * strategy_calls,
        )
        if vendor_refresh_tasks:
            lite_cost += _lite_vendor_news_cost() * vendor_refresh_tasks

    if lite_strategy:
        generation_min = LITE_AI_STRATEGY_OVERHEAD["duration_min"] * strategy_calls
        generation_max = LITE_AI_STRATEGY_OVERHEAD["duration_max"] * strategy_calls
        refresh_min = LITE_AI_STRATEGY_OVERHEAD["duration_min"] * vendor_refresh_tasks
        refresh_max = LITE_AI_STRATEGY_OVERHEAD["duration_max"] * vendor_refresh_tasks
    else:
        generation_min = AI_STRATEGY_OVERHEAD["duration_min"] * strategy_calls
        generation_max = AI_STRATEGY_OVERHEAD["duration_max"] * strategy_calls
        refresh_min = AI_STRATEGY_OVERHEAD["duration_min"] * vendor_refresh_tasks
        refresh_max = AI_STRATEGY_OVERHEAD["duration_max"] * vendor_refresh_tasks

    estimated_cost = round(deep_research_cost + lite_cost, 6)
    cost_basis = (
        "Conservative planning estimate for the exact strategy fan-out. "
        "Deep Research tasks use the configured flat planning cost; lite strategy "
        "and lite vendor AI-news calls use the active reasoning / Pro model's "
        "highest applicable token tier plus a grounded-search surcharge; "
        "actual token and tool usage varies."
    )

    return StandaloneStrategyEstimate(
        strategy_type=normalized_type,
        platforms=selected_platforms,
        lite_strategy=lite_strategy,
        strategy_calls=strategy_calls,
        deep_research_tasks=deep_research_tasks,
        vendor_refresh_tasks=vendor_refresh_tasks,
        model_name=model_name,
        estimated_cost_usd=estimated_cost,
        estimated_time_min_minutes=generation_min + refresh_min,
        estimated_time_max_minutes=generation_max + refresh_max,
        cost_basis=cost_basis,
    )


__all__ = [
    "AI_STRATEGY_IDS",
    "GENERIC_STRATEGY_IDS",
    "SUPPORTED_STRATEGY_IDS",
    "StandaloneStrategyEstimate",
    "estimate_standalone_strategy",
]
