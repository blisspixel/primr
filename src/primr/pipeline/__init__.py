"""
Pipeline module - Recovery hierarchies, stage classification, and model circuit breaking.

This package provides the resilience layer for Primr's research pipeline:
- Stage definitions and foreground/background classification
- Cost-ordered recovery hierarchies per stage
- Model-level circuit breaking with provider-aware fallback
- Recovery executor that orchestrates retry/fallback/skip logic

**Feature: pipeline-resilience**
"""

from primr.pipeline.errors import (
    ErrorCategory,
    classify_error,
    is_rate_limited,
)
from primr.pipeline.executor import (
    RecoveryContext,
    RecoveryExecutor,
    StageResult,
    compute_backoff,
    reduce_queries,
)
from primr.pipeline.model_breaker import (
    ANALYSIS_FALLBACK_CHAIN,
    PREMIUM_FALLBACK_CHAIN,
    FallbackChain,
    ModelCircuitBreaker,
    ModelHealthEvent,
)
from primr.pipeline.recovery import (
    RecoveryAction,
    RecoveryActionType,
    RecoveryHierarchy,
    RecoveryTable,
    build_default_recovery_table,
)
from primr.pipeline.stages import (
    STAGE_CLASSIFICATIONS,
    PipelineStage,
    StageClass,
    is_background,
    is_foreground,
)

__all__ = [
    "ANALYSIS_FALLBACK_CHAIN",
    "PREMIUM_FALLBACK_CHAIN",
    "STAGE_CLASSIFICATIONS",
    "ErrorCategory",
    "FallbackChain",
    "ModelCircuitBreaker",
    "ModelHealthEvent",
    "PipelineStage",
    "RecoveryAction",
    "RecoveryActionType",
    "RecoveryContext",
    "RecoveryExecutor",
    "RecoveryHierarchy",
    "RecoveryTable",
    "StageClass",
    "StageResult",
    "build_default_recovery_table",
    "classify_error",
    "compute_backoff",
    "is_background",
    "is_foreground",
    "is_rate_limited",
    "reduce_queries",
]
