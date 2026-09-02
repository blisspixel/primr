"""Shared research execution policy for MCP and A2A entry points."""

from __future__ import annotations

import math
import os
from typing import Any

from primr.mcp_server.cost_caps import is_cost_cap_enforced
from primr.mcp_server.platforms import normalize_platforms
from primr.mcp_server.types import MCPErrorCode


def parse_max_duration(duration_str: str, default: int = 30) -> int:
    """Parse the max minutes from a duration string like ``5-10 min``."""
    try:
        parts = duration_str.split("-")
        if len(parts) >= 2:
            return int(parts[1].split()[0])
        return int(parts[0].split()[0])
    except (ValueError, IndexError):
        return default


def build_research_estimate(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return the normalized estimate payload for a research execution shape.

    Mirrors CLI ``build_run_estimate`` cost-shaping kwargs so MCP/A2A approval
    tokens cannot understate spend relative to the run that will execute.
    Authorization uses the higher of planning defaults and historical averages
    (never a historical-only floor that can under-approve after cheap samples).
    """
    from primr.core.budget_policy import describe_budget_enforcement
    from primr.utils.cost_estimator import estimate_cost

    mode = arguments.get("mode", "full")
    mode_mapping = {
        "scrape": "scrape-only",
        "deep": "deep-research",
        "full": "complete",
        "premium": "complete",
    }
    estimator_mode = mode_mapping.get(mode, "complete")
    verify = bool(arguments.get("verify", False))
    premium_mode = mode == "premium"
    # Match CLI resolve: full mode uses the routed fast pipeline when xAI is
    # available or OpenRouter was separately enabled for paid routing.
    from primr.ai.providers.openrouter import openrouter_routing_ready

    fast_mode = mode == "full" and bool(os.environ.get("XAI_API_KEY") or openrouter_routing_ready())
    # Extra JSON fields are not worker inputs. Pricing only the default
    # hybrid/full shape prevents under-approval via unbound kwargs.
    grok_tier = "hybrid"
    lite_strategy = False

    no_ai_strategy = arguments.get("no_ai_strategy", False)
    include_ai_strategy = not no_ai_strategy and mode in ("full", "premium")
    platforms = arguments.get("platforms")
    if platforms is None and arguments.get("platform"):
        platforms = [arguments["platform"]]
    if platforms is None:
        platforms = ["agnostic"]
    if isinstance(platforms, str):
        platforms = [platforms]
    platforms = normalize_platforms(platforms)
    num_vendors = len(platforms) if include_ai_strategy else 0

    estimate_kwargs = {
        "include_ai_strategy": include_ai_strategy,
        "verify": verify,
        "premium_mode": premium_mode,
        "fast_mode": fast_mode,
        "num_vendors": max(num_vendors, 1) if include_ai_strategy else 1,
        "lite_strategy": lite_strategy,
        "grok_tier": grok_tier,
    }
    # Planning floor is the approval baseline; historical can only raise it.
    planning = estimate_cost(estimator_mode, use_historical=False, **estimate_kwargs)
    historical = estimate_cost(estimator_mode, use_historical=True, **estimate_kwargs)
    if historical.total_cost > planning.total_cost:
        cost_estimate = historical
        if "Based on" not in " ".join(cost_estimate.notes or []):
            cost_estimate.notes = list(cost_estimate.notes or [])
            cost_estimate.notes.append(
                f"Authorization floor raised by historical average "
                f"(planning was ${planning.total_cost:.2f})"
            )
    else:
        cost_estimate = planning
    pages = 20 if mode in ("scrape", "full", "premium") else 0
    max_duration = parse_max_duration(cost_estimate.duration_minutes)
    result: dict[str, Any] = {
        "estimated_cost_usd": round(cost_estimate.total_cost, 2),
        "estimated_time_minutes": max_duration,
        "estimated_time_range": cost_estimate.duration_minutes,
        "planned_pages": pages,
        "mode": mode,
        "budget_enforcement": describe_budget_enforcement(
            mode=estimator_mode,
            fast_mode=fast_mode,
            premium_mode=premium_mode,
        ).as_dict(),
    }
    if include_ai_strategy:
        result["ai_strategy"] = True
        result["platforms"] = platforms
        result["strategy_type"] = arguments.get("strategy_type", "ai")
    else:
        result["ai_strategy"] = False
    return result


def enforce_cost_cap(
    estimated_cost: float,
    max_estimated_cost_usd: Any,
    operation_name: str,
) -> dict[str, Any] | None:
    """Return a structured error when a research cost cap is missing or exceeded."""
    if max_estimated_cost_usd is None:
        if is_cost_cap_enforced():
            return {
                "error": True,
                "error_type": "cost_cap_required",
                "error_code": MCPErrorCode.COST_CAP_REQUIRED,
                "message": (
                    f"{operation_name} requires max_estimated_cost_usd; call the "
                    "matching estimate tool and obtain explicit approval first"
                ),
            }
        return None

    cap = coerce_budget_usd(max_estimated_cost_usd)
    if cap is None:
        return {
            "error": True,
            "error_type": "invalid_cost_cap",
            "error_code": MCPErrorCode.INVALID_PARAMS,
            "message": (
                f"max_estimated_cost_usd must be a finite, non-negative number for "
                f"{operation_name}, got {max_estimated_cost_usd!r}"
            ),
        }

    if estimated_cost > cap:
        return {
            "error": True,
            "error_type": "cost_cap_exceeded",
            "error_code": MCPErrorCode.COST_CAP_EXCEEDED,
            "message": (
                f"Estimated cost ${estimated_cost:.2f} exceeds approved cap "
                f"${cap:.2f} for {operation_name}"
            ),
            "estimated_cost_usd": estimated_cost,
            "max_estimated_cost_usd": cap,
        }
    return None


def coerce_budget_usd(max_estimated_cost_usd: Any) -> float | None:
    """Return a finite non-negative budget, or ``None`` when no cap is present."""
    if max_estimated_cost_usd is None:
        return None
    try:
        cap = float(max_estimated_cost_usd)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(cap) or cap < 0:
        return None
    return cap
