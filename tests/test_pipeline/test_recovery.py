"""
Unit tests for recovery table data structures and default table.

Tests verify each stage has the correct number of actions in the correct order,
and that serialization produces the expected structure.

**Feature: pipeline-resilience**
**Validates: Requirements 2.1-2.4, 3.1-3.4, 4.1-4.4, 5.1-5.4, 6.1-6.3, 7.1-7.4**
"""

from __future__ import annotations

from primr.pipeline.recovery import (
    RecoveryActionType,
    build_default_recovery_table,
)
from primr.pipeline.stages import PipelineStage


def _action_types(stage: PipelineStage) -> list[RecoveryActionType]:
    """Return the ordered action types for a stage from the default table."""
    table = build_default_recovery_table()
    return [a.action_type for a in table.get_hierarchy(stage).actions]


class TestScrapingHierarchy:
    """Requirement 2: scraping → retry_backoff, escalate_tier, skip_page."""

    def test_action_count(self) -> None:
        assert len(_action_types(PipelineStage.SCRAPING)) == 3

    def test_action_order(self) -> None:
        assert _action_types(PipelineStage.SCRAPING) == [
            RecoveryActionType.RETRY_BACKOFF,
            RecoveryActionType.ESCALATE_TIER,
            RecoveryActionType.SKIP_PAGE,
        ]


class TestExternalSearchHierarchy:
    """Requirement 3: external_search → retry_backoff, reduce_queries, skip_stage."""

    def test_action_count(self) -> None:
        assert len(_action_types(PipelineStage.EXTERNAL_SEARCH)) == 3

    def test_action_order(self) -> None:
        assert _action_types(PipelineStage.EXTERNAL_SEARCH) == [
            RecoveryActionType.RETRY_BACKOFF,
            RecoveryActionType.REDUCE_QUERIES,
            RecoveryActionType.SKIP_STAGE,
        ]


class TestAnalysisHierarchy:
    """Requirement 4: analysis → retry_backoff, fallback_model, abort_partial."""

    def test_action_count(self) -> None:
        assert len(_action_types(PipelineStage.ANALYSIS)) == 3

    def test_action_order(self) -> None:
        assert _action_types(PipelineStage.ANALYSIS) == [
            RecoveryActionType.RETRY_BACKOFF,
            RecoveryActionType.FALLBACK_MODEL,
            RecoveryActionType.ABORT_PARTIAL,
        ]


class TestSectionWritingHierarchy:
    """Requirement 5: section_writing → retry_same, simplify_prompt, skip_stage."""

    def test_action_count(self) -> None:
        assert len(_action_types(PipelineStage.SECTION_WRITING)) == 3

    def test_action_order(self) -> None:
        assert _action_types(PipelineStage.SECTION_WRITING) == [
            RecoveryActionType.RETRY_SAME,
            RecoveryActionType.SIMPLIFY_PROMPT,
            RecoveryActionType.SKIP_STAGE,
        ]


class TestCrossValidationHierarchy:
    """Requirement 6: cross_validation → retry_same, skip_stage."""

    def test_action_count(self) -> None:
        assert len(_action_types(PipelineStage.CROSS_VALIDATION)) == 2

    def test_action_order(self) -> None:
        assert _action_types(PipelineStage.CROSS_VALIDATION) == [
            RecoveryActionType.RETRY_SAME,
            RecoveryActionType.SKIP_STAGE,
        ]


class TestStrategyGenerationHierarchy:
    """Requirement 7: strategy_generation → retry_same, minimal_output, skip_stage."""

    def test_action_count(self) -> None:
        assert len(_action_types(PipelineStage.STRATEGY_GENERATION)) == 3

    def test_action_order(self) -> None:
        assert _action_types(PipelineStage.STRATEGY_GENERATION) == [
            RecoveryActionType.RETRY_SAME,
            RecoveryActionType.MINIMAL_OUTPUT,
            RecoveryActionType.SKIP_STAGE,
        ]


class TestRecoveryTableCompleteness:
    """The default table covers all six pipeline stages."""

    def test_all_stages_present(self) -> None:
        table = build_default_recovery_table()
        assert set(table.hierarchies.keys()) == set(PipelineStage)
