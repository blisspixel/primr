"""
Recovery table data structures and default table factory.

This module provides:
- RecoveryActionType enum for all recovery action kinds
- RecoveryAction frozen dataclass for a single recovery step
- RecoveryHierarchy frozen dataclass for an ordered sequence of actions per stage
- RecoveryTable frozen dataclass for the full stage→hierarchy mapping
- build_default_recovery_table() factory for the six-stage default table

The recovery table is a pure data structure — serializable to JSON,
inspectable via ``--dry-run``, and testable without executing any I/O.

**Feature: pipeline-resilience**
**Validates: Requirements 1.1, 1.3, 14.1**
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from primr.pipeline.stages import (
    STAGE_CLASSIFICATIONS,
    PipelineStage,
)

# =============================================================================
# RECOVERY ACTION TYPE ENUM
# =============================================================================


class RecoveryActionType(Enum):
    """The kind of recovery action to attempt."""

    RETRY_SAME = "retry_same"
    RETRY_BACKOFF = "retry_backoff"
    ESCALATE_TIER = "escalate_tier"
    REDUCE_QUERIES = "reduce_queries"
    FALLBACK_MODEL = "fallback_model"
    SIMPLIFY_PROMPT = "simplify_prompt"
    SKIP_PAGE = "skip_page"
    SKIP_STAGE = "skip_stage"
    ABORT_PARTIAL = "abort_partial"
    MINIMAL_OUTPUT = "minimal_output"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True)
class RecoveryAction:
    """A single step in a recovery hierarchy."""

    action_type: RecoveryActionType
    description: str
    cost_rank: int  # 1 = cheapest, higher = more expensive

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "action_type": self.action_type.value,
            "description": self.description,
            "cost_rank": self.cost_rank,
        }


@dataclass(frozen=True)
class RecoveryHierarchy:
    """Ordered sequence of recovery actions for a pipeline stage."""

    stage: PipelineStage
    actions: tuple[RecoveryAction, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary including stage classification."""
        return {
            "stage": self.stage.value,
            "classification": STAGE_CLASSIFICATIONS[self.stage].value,
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass(frozen=True)
class RecoveryTable:
    """Declarative mapping from pipeline stages to recovery hierarchies.

    Pure data structure — serializable to JSON, inspectable without
    executing any recovery actions.
    """

    hierarchies: dict[PipelineStage, RecoveryHierarchy]

    def get_hierarchy(self, stage: PipelineStage) -> RecoveryHierarchy:
        """Return the recovery hierarchy for *stage*."""
        return self.hierarchies[stage]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full table to a plain dictionary."""
        return {
            stage.value: h.to_dict()
            for stage, h in self.hierarchies.items()
        }

    def to_json(self) -> str:
        """Serialize the full table to a JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# =============================================================================
# DEFAULT TABLE FACTORY
# =============================================================================


def build_default_recovery_table() -> RecoveryTable:
    """Build the default recovery table for all six pipeline stages.

    Each hierarchy's actions have strictly increasing cost_rank values.
    """
    scraping = RecoveryHierarchy(
        stage=PipelineStage.SCRAPING,
        actions=(
            RecoveryAction(
                action_type=RecoveryActionType.RETRY_BACKOFF,
                description="Retry same tier with jitter",
                cost_rank=1,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.ESCALATE_TIER,
                description="Escalate to next scrape tier",
                cost_rank=2,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP_PAGE,
                description="Skip page, log as failed",
                cost_rank=3,
            ),
        ),
    )

    external_search = RecoveryHierarchy(
        stage=PipelineStage.EXTERNAL_SEARCH,
        actions=(
            RecoveryAction(
                action_type=RecoveryActionType.RETRY_BACKOFF,
                description="Retry query with backoff",
                cost_rank=1,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.REDUCE_QUERIES,
                description="Reduce query count by 50%+",
                cost_rank=2,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP_STAGE,
                description="Skip search, proceed scrape-only",
                cost_rank=3,
            ),
        ),
    )

    analysis = RecoveryHierarchy(
        stage=PipelineStage.ANALYSIS,
        actions=(
            RecoveryAction(
                action_type=RecoveryActionType.RETRY_BACKOFF,
                description="Retry same model with backoff",
                cost_rank=1,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.FALLBACK_MODEL,
                description="Try next model in chain",
                cost_rank=2,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.ABORT_PARTIAL,
                description="Abort with partial output",
                cost_rank=3,
            ),
        ),
    )

    section_writing = RecoveryHierarchy(
        stage=PipelineStage.SECTION_WRITING,
        actions=(
            RecoveryAction(
                action_type=RecoveryActionType.RETRY_SAME,
                description="Retry with original prompt",
                cost_rank=1,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SIMPLIFY_PROMPT,
                description="Regenerate with simpler prompt",
                cost_rank=2,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP_STAGE,
                description="Skip section, insert gap marker",
                cost_rank=3,
            ),
        ),
    )

    cross_validation = RecoveryHierarchy(
        stage=PipelineStage.CROSS_VALIDATION,
        actions=(
            RecoveryAction(
                action_type=RecoveryActionType.RETRY_SAME,
                description="Retry validation call",
                cost_rank=1,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP_STAGE,
                description="Skip validation, flag as unvalidated",
                cost_rank=2,
            ),
        ),
    )

    strategy_generation = RecoveryHierarchy(
        stage=PipelineStage.STRATEGY_GENERATION,
        actions=(
            RecoveryAction(
                action_type=RecoveryActionType.RETRY_SAME,
                description="Retry strategy generation",
                cost_rank=1,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.MINIMAL_OUTPUT,
                description="Generate minimal strategy",
                cost_rank=2,
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP_STAGE,
                description="Skip strategy, deliver report only",
                cost_rank=3,
            ),
        ),
    )

    return RecoveryTable(
        hierarchies={
            PipelineStage.SCRAPING: scraping,
            PipelineStage.EXTERNAL_SEARCH: external_search,
            PipelineStage.ANALYSIS: analysis,
            PipelineStage.SECTION_WRITING: section_writing,
            PipelineStage.CROSS_VALIDATION: cross_validation,
            PipelineStage.STRATEGY_GENERATION: strategy_generation,
        }
    )
