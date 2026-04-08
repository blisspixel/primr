"""
Unit tests for pipeline stage classifications.

Tests verify the declarative stage classifier behaves correctly
for foreground/background classification without executing pipeline logic.

**Feature: pipeline-resilience**
**Validates: Requirements 8.1, 8.2, 8.3, 8.4**
"""

from __future__ import annotations

from primr.pipeline.stages import (
    STAGE_CLASSIFICATIONS,
    PipelineStage,
    StageClass,
    is_background,
    is_foreground,
)


class TestForegroundClassification:
    """Requirement 8.1: scraping, external_search, analysis, section_writing are foreground."""

    def test_scraping_is_foreground(self) -> None:
        assert is_foreground(PipelineStage.SCRAPING) is True

    def test_external_search_is_foreground(self) -> None:
        assert is_foreground(PipelineStage.EXTERNAL_SEARCH) is True

    def test_analysis_is_foreground(self) -> None:
        assert is_foreground(PipelineStage.ANALYSIS) is True

    def test_section_writing_is_foreground(self) -> None:
        assert is_foreground(PipelineStage.SECTION_WRITING) is True


class TestBackgroundClassification:
    """Requirement 8.2: cross_validation, strategy_generation are background."""

    def test_cross_validation_is_background(self) -> None:
        assert is_background(PipelineStage.CROSS_VALIDATION) is True

    def test_strategy_generation_is_background(self) -> None:
        assert is_background(PipelineStage.STRATEGY_GENERATION) is True


class TestForegroundBackgroundExclusivity:
    """Foreground and background are mutually exclusive for every stage."""

    def test_foreground_stages_are_not_background(self) -> None:
        for stage in PipelineStage:
            if is_foreground(stage):
                assert not is_background(stage), f"{stage.name} is both foreground and background"

    def test_background_stages_are_not_foreground(self) -> None:
        for stage in PipelineStage:
            if is_background(stage):
                assert not is_foreground(stage), f"{stage.name} is both background and foreground"


class TestDeclarativeClassification:
    """Requirement 8.3, 8.4: STAGE_CLASSIFICATIONS is a declarative dict inspectable
    without executing pipeline logic."""

    def test_classifications_is_a_dict(self) -> None:
        assert isinstance(STAGE_CLASSIFICATIONS, dict)

    def test_classifications_keys_are_pipeline_stages(self) -> None:
        for key in STAGE_CLASSIFICATIONS:
            assert isinstance(key, PipelineStage)

    def test_classifications_values_are_stage_classes(self) -> None:
        for value in STAGE_CLASSIFICATIONS.values():
            assert isinstance(value, StageClass)

    def test_classifications_inspectable_without_pipeline_logic(self) -> None:
        """The dict can be read and iterated as pure data — no I/O or side effects."""
        entries = list(STAGE_CLASSIFICATIONS.items())
        assert len(entries) == len(PipelineStage)
        for stage, cls in entries:
            assert stage.value  # enum value is a non-empty string
            assert cls.value in ("foreground", "background")
