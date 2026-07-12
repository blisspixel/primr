"""Shared strategy operation for MCP jobs and direct tool requests."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from typing import Any

from primr.mcp_server.strategy_catalog import AI_STRATEGY_TYPES, GENERIC_STRATEGY_YAMLS

logger = logging.getLogger(__name__)


async def run_strategy_generation(
    report_path: str,
    strategy_type: str,
    platform: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Generate one strategy artifact from an existing report."""
    started_at = time.monotonic()
    filename = os.path.splitext(os.path.basename(report_path))[0]
    match = re.match(
        r"^(.+?)_(?:Strategic_Overview|AI_Strategy|Customer_Experience|Security|Data_Fabric)",
        filename,
    )
    if match:
        company_name = match.group(1).replace("_", " ")
    else:
        company_name = filename.replace("_", " ")

    if strategy_type in AI_STRATEGY_TYPES:
        from primr.core.ai_strategy import Platform, generate_ai_strategy

        vendor = Platform.from_string(platform) if platform else Platform.AGNOSTIC
        result = await generate_ai_strategy(
            company_name=company_name,
            platform=vendor,
            company_research_path=report_path,
            allow_vendor_refresh=False,
            on_progress=on_progress,
        )
        if result.error:
            raise RuntimeError(result.error)
        output_path = result.md_path or result.docx_path or result.txt_path
    elif strategy_type in GENERIC_STRATEGY_YAMLS:
        from primr.core.strategy_generation import generate_generic_strategy

        output_path = await asyncio.to_thread(
            generate_generic_strategy,
            strategy_name=strategy_type,
            strategy_yaml=GENERIC_STRATEGY_YAMLS[strategy_type],
            company_name=company_name,
            company_research_path=report_path,
        )
    else:
        supported = sorted({"ai_strategy", *GENERIC_STRATEGY_YAMLS})
        raise ValueError(
            f"Unsupported strategy type: {strategy_type}. Expected one of: {', '.join(supported)}"
        )

    if not output_path:
        raise RuntimeError(f"{strategy_type} strategy generation produced no output artifact")

    if strategy_type in GENERIC_STRATEGY_YAMLS:
        try:
            from primr.config.models import DEEP_RESEARCH_COST
            from primr.utils.usage_tracker import get_usage_tracker

            tracker = get_usage_tracker()
            tracker.record_usage(
                mode=f"standalone_strategy_{strategy_type}",
                company=company_name,
                input_tokens=0,
                output_tokens=0,
                duration_seconds=max(0.0, time.monotonic() - started_at),
                deep_research_cost=DEEP_RESEARCH_COST.standard_task_cost,
            )
            tracker.save()
        except Exception as exc:
            logger.debug("Standalone strategy usage tracking skipped: %s", exc)

    return {
        "output_path": output_path,
        "strategy_type": strategy_type,
        "qa_score": None,
    }


__all__ = ["run_strategy_generation"]
