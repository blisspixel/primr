"""Standalone strategy catalog cost and dispatch parity."""

from primr.config.models import DEEP_RESEARCH_COST
from primr.mcp_server.strategy_catalog import (
    GENERIC_STRATEGY_YAMLS,
    get_strategy_catalog,
)


def test_catalog_matches_dispatch_and_canonical_cost() -> None:
    catalog = get_strategy_catalog()
    ids = {str(item["id"]) for item in catalog}

    assert ids == {"ai_strategy", *GENERIC_STRATEGY_YAMLS}
    assert all(
        item["estimated_cost_usd"] == DEEP_RESEARCH_COST.standard_task_cost for item in catalog
    )
    assert all("actual token and tool usage varies" in str(item["cost_basis"]) for item in catalog)
