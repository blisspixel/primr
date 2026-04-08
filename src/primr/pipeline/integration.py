"""
Pipeline resilience integration helpers for research_agent.py.

This module provides thin wrappers that connect the RecoveryExecutor
to the existing pipeline stages. Each wrapper preserves existing behavior
on successful runs (NFR 1) and adds recovery logic only on failure.

**Feature: pipeline-resilience**
**Validates: Requirements 2.1-2.4, 3.1-3.4, 4.1-4.4, 5.1-5.4, 6.1-6.3, 7.1-7.4, 9.1-9.4, NFR 4**
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from primr.pipeline.executor import (
    BackgroundAbort,
    RecoveryContext,
    RecoveryEvent,
    RecoveryExecutor,
    StageResult,
)
from primr.pipeline.recovery import build_default_recovery_table
from primr.pipeline.stages import PipelineStage

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("research_agent.resilience")


# =============================================================================
# SCRAPING STAGE WRAPPER (per-page granularity)
# =============================================================================


def scrape_page_with_recovery(
    executor: RecoveryExecutor,
    scrape_fn: Callable[[], dict],
    url: str,
    folder_path: str,
    budget_stressed: bool = False,
) -> StageResult:
    """Wrap a single page scrape call with the recovery executor.

    Preserves existing sticky-tier optimization — the ESCALATE_TIER action
    delegates to the existing tier logic inside *scrape_fn*.

    **Validates: Requirements 2.1-2.4, NFR 4**
    """
    ctx = RecoveryContext(
        stage=PipelineStage.SCRAPING,
        folder_path=folder_path,
        attempt=0,
        last_error=None,
        budget_stressed=budget_stressed,
    )
    return executor.execute(PipelineStage.SCRAPING, scrape_fn, context=ctx)


# =============================================================================
# EXTERNAL SEARCH STAGE WRAPPER (per-query granularity)
# =============================================================================


def search_query_with_recovery(
    executor: RecoveryExecutor,
    search_fn: Callable[[], list[dict]],
    folder_path: str,
    budget_stressed: bool = False,
) -> StageResult:
    """Wrap a single search query call with the recovery executor.

    **Validates: Requirements 3.1-3.4, NFR 4**
    """
    ctx = RecoveryContext(
        stage=PipelineStage.EXTERNAL_SEARCH,
        folder_path=folder_path,
        attempt=0,
        last_error=None,
        budget_stressed=budget_stressed,
    )
    return executor.execute(PipelineStage.EXTERNAL_SEARCH, search_fn, context=ctx)


# =============================================================================
# ANALYSIS STAGE WRAPPER (per-stage granularity)
# =============================================================================


def analysis_with_recovery(
    executor: RecoveryExecutor,
    analysis_fn: Callable[[], str],
    folder_path: str,
    budget_stressed: bool = False,
) -> StageResult:
    """Wrap the analysis workbook generation with the recovery executor.

    **Validates: Requirements 4.1-4.4, NFR 4**
    """
    ctx = RecoveryContext(
        stage=PipelineStage.ANALYSIS,
        folder_path=folder_path,
        attempt=0,
        last_error=None,
        budget_stressed=budget_stressed,
    )
    return executor.execute(PipelineStage.ANALYSIS, analysis_fn, context=ctx)


# =============================================================================
# SECTION WRITING STAGE WRAPPER (per-section granularity)
# =============================================================================


def write_section_with_recovery(
    executor: RecoveryExecutor,
    write_fn: Callable[[], dict[str, Any] | None],
    folder_path: str,
    budget_stressed: bool = False,
) -> StageResult:
    """Wrap a single section writing call with the recovery executor.

    **Validates: Requirements 5.1-5.4, NFR 4**
    """
    ctx = RecoveryContext(
        stage=PipelineStage.SECTION_WRITING,
        folder_path=folder_path,
        attempt=0,
        last_error=None,
        budget_stressed=budget_stressed,
    )
    return executor.execute(PipelineStage.SECTION_WRITING, write_fn, context=ctx)


# =============================================================================
# CROSS-VALIDATION STAGE WRAPPER (per-stage, background)
# =============================================================================


def cross_validate_with_recovery(
    executor: RecoveryExecutor,
    validate_fn: Callable[[], dict],
    folder_path: str,
    budget_stressed: bool = False,
) -> StageResult:
    """Wrap cross-validation with the recovery executor (background stage).

    Bails immediately on 429 or budget stress.

    **Validates: Requirements 6.1-6.3, 9.1-9.4, NFR 4**
    """
    ctx = RecoveryContext(
        stage=PipelineStage.CROSS_VALIDATION,
        folder_path=folder_path,
        attempt=0,
        last_error=None,
        budget_stressed=budget_stressed,
    )
    return executor.execute(PipelineStage.CROSS_VALIDATION, validate_fn, context=ctx)


# =============================================================================
# STRATEGY GENERATION STAGE WRAPPER (per-stage, background)
# =============================================================================


def strategy_with_recovery(
    executor: RecoveryExecutor,
    strategy_fn: Callable[[], str],
    folder_path: str,
    budget_stressed: bool = False,
) -> StageResult:
    """Wrap strategy generation with the recovery executor (background stage).

    Bails immediately on 429 or budget stress.

    **Validates: Requirements 7.1-7.4, 9.1-9.4, NFR 4**
    """
    ctx = RecoveryContext(
        stage=PipelineStage.STRATEGY_GENERATION,
        folder_path=folder_path,
        attempt=0,
        last_error=None,
        budget_stressed=budget_stressed,
    )
    return executor.execute(PipelineStage.STRATEGY_GENERATION, strategy_fn, context=ctx)


# =============================================================================
# EXECUTOR FACTORY
# =============================================================================


def create_pipeline_executor(
    folder_path: str,
    event_listener: Callable[[RecoveryEvent | BackgroundAbort], None] | None = None,
) -> RecoveryExecutor:
    """Create a RecoveryExecutor with the default recovery table.

    **Validates: Requirements 1.1, 1.2**
    """
    return RecoveryExecutor(
        recovery_table=build_default_recovery_table(),
        event_listener=event_listener,
    )
