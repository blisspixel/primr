"""
Pipeline stage definitions and foreground/background classification.

This module provides:
- PipelineStage enum for the six pipeline stages
- StageClass enum for foreground/background classification
- STAGE_CLASSIFICATIONS dict mapping stages to their class
- is_foreground() / is_background() helper functions

The stage classifier is a declarative data structure — inspectable
and queryable without executing any pipeline logic.

**Feature: pipeline-resilience**
**Validates: Requirements 8.1, 8.2, 8.3, 8.4**
"""

from __future__ import annotations

from enum import Enum

# =============================================================================
# PIPELINE STAGE ENUM
# =============================================================================


class PipelineStage(Enum):
    """The six pipeline stages that declare recovery hierarchies."""

    SCRAPING = "scraping"
    EXTERNAL_SEARCH = "external_search"
    ANALYSIS = "analysis"
    SECTION_WRITING = "section_writing"
    CROSS_VALIDATION = "cross_validation"
    STRATEGY_GENERATION = "strategy_generation"


# =============================================================================
# STAGE CLASSIFICATION
# =============================================================================


class StageClass(Enum):
    """Foreground stages retry aggressively; background stages bail on overload."""

    FOREGROUND = "foreground"
    BACKGROUND = "background"


# Declarative classification — the single source of truth.
# Foreground stages must complete for a useful artifact.
# Background stages are additive quality, not core.
STAGE_CLASSIFICATIONS: dict[PipelineStage, StageClass] = {
    PipelineStage.SCRAPING: StageClass.FOREGROUND,
    PipelineStage.EXTERNAL_SEARCH: StageClass.FOREGROUND,
    PipelineStage.ANALYSIS: StageClass.FOREGROUND,
    PipelineStage.SECTION_WRITING: StageClass.FOREGROUND,
    PipelineStage.CROSS_VALIDATION: StageClass.BACKGROUND,
    PipelineStage.STRATEGY_GENERATION: StageClass.BACKGROUND,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def is_foreground(stage: PipelineStage) -> bool:
    """Return True if the stage must complete for a useful artifact."""
    return STAGE_CLASSIFICATIONS[stage] == StageClass.FOREGROUND


def is_background(stage: PipelineStage) -> bool:
    """Return True if the stage is additive quality, not core."""
    return STAGE_CLASSIFICATIONS[stage] == StageClass.BACKGROUND
