"""
Property-based tests for Pipeline Resilience Patterns.

This module validates the correctness properties of the pipeline resilience
implementation using the Hypothesis library. Each test corresponds to a
formal property from the design document.

Properties tested:
- Property 1: Table and Classification Completeness
- Property 2: Cost Ordering Invariant
- Property 3: Recovery Table Serialization Round-Trip

**Feature: pipeline-resilience**
**Validates: Requirements 1.1, 1.2, 1.3, 8.3, 14.1**
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.config.models import PrimrModels
from primr.pipeline.recovery import (
    RecoveryActionType,
    build_default_recovery_table,
)
from primr.pipeline.stages import (
    STAGE_CLASSIFICATIONS,
    PipelineStage,
    StageClass,
)

# =============================================================================
# STRATEGIES
# =============================================================================

# Strategy for sampling pipeline stages
pipeline_stages = st.sampled_from(list(PipelineStage))


# =============================================================================
# PROPERTY 1: TABLE AND CLASSIFICATION COMPLETENESS
# =============================================================================


# Feature: pipeline-resilience, Property 1: Table and Classification Completeness
class TestTableAndClassificationCompleteness:
    """
    **Property 1: Table and Classification Completeness**

    For any PipelineStage enum member, STAGE_CLASSIFICATIONS SHALL contain
    a StageClass entry for that stage.

    **Validates: Requirements 1.1, 8.3**
    """

    @given(stage=pipeline_stages)
    @settings(max_examples=100, deadline=None)
    def test_every_stage_has_classification(self, stage: PipelineStage) -> None:
        """Every PipelineStage member has an entry in STAGE_CLASSIFICATIONS."""
        assert stage in STAGE_CLASSIFICATIONS, (
            f"PipelineStage.{stage.name} missing from STAGE_CLASSIFICATIONS"
        )

    @given(stage=pipeline_stages)
    @settings(max_examples=100, deadline=None)
    def test_classification_is_valid_stage_class(self, stage: PipelineStage) -> None:
        """Every classification value is a valid StageClass member."""
        classification = STAGE_CLASSIFICATIONS[stage]
        assert isinstance(classification, StageClass), (
            f"STAGE_CLASSIFICATIONS[{stage.name}] is {type(classification)}, expected StageClass"
        )

    def test_classifications_cover_all_stages(self) -> None:
        """STAGE_CLASSIFICATIONS keys exactly match PipelineStage members."""
        assert set(STAGE_CLASSIFICATIONS.keys()) == set(PipelineStage)


# =============================================================================
# PROPERTY 2: COST ORDERING INVARIANT
# =============================================================================


# Feature: pipeline-resilience, Property 2: Cost Ordering Invariant
class TestCostOrderingInvariant:
    """
    **Property 2: Cost Ordering Invariant**

    For any RecoveryHierarchy in the RecoveryTable, the cost_rank values
    of its actions SHALL be strictly monotonically increasing.

    **Validates: Requirements 1.2**
    """

    @given(stage=pipeline_stages)
    @settings(max_examples=100, deadline=None)
    def test_cost_ranks_strictly_increasing(self, stage: PipelineStage) -> None:
        """cost_rank values are strictly monotonically increasing per hierarchy."""
        table = build_default_recovery_table()
        hierarchy = table.get_hierarchy(stage)
        ranks = [a.cost_rank for a in hierarchy.actions]
        for i in range(1, len(ranks)):
            assert ranks[i] > ranks[i - 1], (
                f"Stage {stage.name}: cost_rank {ranks[i]} at index {i} "
                f"is not greater than {ranks[i - 1]} at index {i - 1}"
            )

    @given(stage=pipeline_stages)
    @settings(max_examples=100, deadline=None)
    def test_hierarchy_has_at_least_one_action(self, stage: PipelineStage) -> None:
        """Every hierarchy has at least one recovery action."""
        table = build_default_recovery_table()
        hierarchy = table.get_hierarchy(stage)
        assert len(hierarchy.actions) >= 1, f"Stage {stage.name} has no recovery actions"


# =============================================================================
# PROPERTY 3: RECOVERY TABLE SERIALIZATION ROUND-TRIP
# =============================================================================


# Feature: pipeline-resilience, Property 3: Recovery Table Serialization Round-Trip
class TestRecoveryTableSerializationRoundTrip:
    """
    **Property 3: Recovery Table Serialization Round-Trip**

    Serialize table via to_json(), parse back, verify equivalence with to_dict().

    **Validates: Requirements 1.3, 14.1**
    """

    def test_json_round_trip_matches_to_dict(self) -> None:
        """Serializing to JSON and parsing back produces the same dict as to_dict()."""
        table = build_default_recovery_table()
        json_str = table.to_json()
        parsed: dict[str, object] = json.loads(json_str)
        expected = table.to_dict()
        assert parsed == expected

    @given(stage=pipeline_stages)
    @settings(max_examples=100, deadline=None)
    def test_per_stage_round_trip(self, stage: PipelineStage) -> None:
        """Each stage's hierarchy survives the JSON round-trip."""
        table = build_default_recovery_table()
        json_str = table.to_json()
        parsed: dict[str, object] = json.loads(json_str)
        hierarchy_dict = table.get_hierarchy(stage).to_dict()
        assert parsed[stage.value] == hierarchy_dict, f"Round-trip mismatch for stage {stage.name}"


# =============================================================================
# STRATEGIES FOR MODEL CIRCUIT BREAKER TESTS
# =============================================================================

# All known model names from the registry
_ALL_MODEL_NAMES = list(PrimrModels.ALL_MODELS.keys())
model_names = st.sampled_from(_ALL_MODEL_NAMES)

# Pairs of distinct model names
distinct_model_pairs = st.tuples(model_names, model_names).filter(lambda pair: pair[0] != pair[1])


# =============================================================================
# PROPERTY 8: MODEL FAILURE INDEPENDENCE
# =============================================================================


# Feature: pipeline-resilience, Property 8: Model Failure Independence
class TestModelFailureIndependence:
    """
    **Property 8: Model Failure Independence**

    For any two distinct model names and any sequence of failures recorded
    against model A, model B's circuit state SHALL remain CLOSED (unaffected
    by model A's failures).

    **Validates: Requirements 11.1**
    """

    @given(
        pair=distinct_model_pairs,
        failure_count=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=100, deadline=None)
    def test_failures_on_model_a_do_not_affect_model_b(
        self,
        pair: tuple[str, str],
        failure_count: int,
    ) -> None:
        """Failures on model A must not change model B's circuit state."""
        from primr.pipeline.model_breaker import ModelCircuitBreaker
        from primr.utils.circuit_breaker import CircuitState

        model_a, model_b = pair
        breaker = ModelCircuitBreaker()

        # Record failures on model A
        for _ in range(failure_count):
            breaker.record_failure(model_a)

        # Model B must remain CLOSED
        assert breaker.get_state(model_b) == CircuitState.CLOSED, (
            f"Model B ({model_b}) state changed to {breaker.get_state(model_b)} "
            f"after {failure_count} failures on model A ({model_a})"
        )


# =============================================================================
# PROPERTY 9: CIRCUIT BREAKER STATE MACHINE
# =============================================================================


# Feature: pipeline-resilience, Property 9: Circuit Breaker State Machine
class TestCircuitBreakerStateMachine:
    """
    **Property 9: Circuit Breaker State Machine**

    - After exactly failure_threshold (3) consecutive failures -> OPEN
    - While OPEN, after timeout_seconds elapses -> HALF_OPEN on next check
    - In HALF_OPEN, a single success -> CLOSED
    - In HALF_OPEN, a single failure -> OPEN

    **Validates: Requirements 11.2, 11.4, 11.5, 11.6**
    """

    @given(model=model_names)
    @settings(max_examples=100, deadline=None)
    def test_opens_after_failure_threshold(self, model: str) -> None:
        """After exactly 3 consecutive failures, state transitions to OPEN."""
        from primr.pipeline.model_breaker import ModelCircuitBreaker
        from primr.utils.circuit_breaker import CircuitState

        breaker = ModelCircuitBreaker(failure_threshold=3)

        # First 2 failures: still CLOSED
        breaker.record_failure(model)
        assert breaker.get_state(model) == CircuitState.CLOSED
        breaker.record_failure(model)
        assert breaker.get_state(model) == CircuitState.CLOSED

        # 3rd failure: transitions to OPEN
        breaker.record_failure(model)
        assert breaker.get_state(model) == CircuitState.OPEN

    @given(model=model_names)
    @settings(max_examples=100, deadline=None)
    def test_half_open_after_timeout(self, model: str) -> None:
        """After timeout elapses in OPEN state, transitions to HALF_OPEN."""

        from primr.pipeline.model_breaker import ModelCircuitBreaker
        from primr.utils.circuit_breaker import CircuitState

        # Use a very short timeout for testing
        breaker = ModelCircuitBreaker(failure_threshold=3, recovery_timeout=0.01)

        # Trip the breaker
        for _ in range(3):
            breaker.record_failure(model)
        assert breaker.get_state(model) == CircuitState.OPEN

        # Simulate timeout by manipulating the internal state
        import time

        time.sleep(0.02)

        # The next health check should transition to HALF_OPEN
        # can_execute triggers the timeout check
        breaker.is_healthy(model)
        assert breaker.get_state(model) == CircuitState.HALF_OPEN

    @given(model=model_names)
    @settings(max_examples=100, deadline=None)
    def test_half_open_success_closes(self, model: str) -> None:
        """A single success in HALF_OPEN transitions to CLOSED."""
        import time

        from primr.pipeline.model_breaker import ModelCircuitBreaker
        from primr.utils.circuit_breaker import CircuitState

        breaker = ModelCircuitBreaker(failure_threshold=3, recovery_timeout=0.01)

        # Trip to OPEN
        for _ in range(3):
            breaker.record_failure(model)

        # Wait for timeout, trigger HALF_OPEN
        time.sleep(0.02)
        breaker.is_healthy(model)
        assert breaker.get_state(model) == CircuitState.HALF_OPEN

        # Single success closes
        breaker.record_success(model)
        assert breaker.get_state(model) == CircuitState.CLOSED

    @given(model=model_names)
    @settings(max_examples=100, deadline=None)
    def test_half_open_failure_reopens(self, model: str) -> None:
        """A single failure in HALF_OPEN transitions back to OPEN."""
        import time

        from primr.pipeline.model_breaker import ModelCircuitBreaker
        from primr.utils.circuit_breaker import CircuitState

        breaker = ModelCircuitBreaker(failure_threshold=3, recovery_timeout=0.01)

        # Trip to OPEN
        for _ in range(3):
            breaker.record_failure(model)

        # Wait for timeout, trigger HALF_OPEN
        time.sleep(0.02)
        breaker.is_healthy(model)
        assert breaker.get_state(model) == CircuitState.HALF_OPEN

        # Single failure reopens
        breaker.record_failure(model)
        assert breaker.get_state(model) == CircuitState.OPEN


# =============================================================================
# PROPERTY 11: PROVIDER-AWARE MODEL SELECTION
# =============================================================================


# Feature: pipeline-resilience, Property 11: Provider-Aware Model Selection
class TestProviderAwareModelSelection:
    """
    **Property 11: Provider-Aware Model Selection**

    - select_model returns the first healthy model with valid API key
    - If no such model exists, raises RuntimeError
    - Models without API key are never returned

    **Validates: Requirements 13.1, 13.2, 13.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_select_model_returns_first_healthy_with_key(
        self,
        data: st.DataObject,
    ) -> None:
        """select_model returns the first healthy model with a valid API key."""
        from unittest.mock import patch

        from primr.pipeline.model_breaker import (
            PROVIDER_API_KEY_ENV,
            FallbackChain,
            ModelCircuitBreaker,
        )

        # Pick a chain with at least 2 models
        chain_models = data.draw(st.lists(model_names, min_size=2, max_size=5, unique=True))
        chain = FallbackChain(name="test", models=tuple(chain_models))

        # Decide which providers have API keys (provider-level, not model-level)
        all_providers = list(PROVIDER_API_KEY_ENV.keys())
        provider_has_key: dict[str, bool] = {}
        for provider in all_providers:
            provider_has_key[provider] = data.draw(st.booleans())

        # Decide which models are healthy
        model_healthy = data.draw(
            st.lists(
                st.booleans(),
                min_size=len(chain_models),
                max_size=len(chain_models),
            )
        )

        # Find expected result: first model that is both healthy and has provider key
        expected_model = None
        for i, m in enumerate(chain_models):
            config = PrimrModels.get_model_config(m)
            if config is None:
                continue
            has_key = provider_has_key.get(config.provider, False)
            if has_key and model_healthy[i]:
                expected_model = m
                break

        breaker = ModelCircuitBreaker(failure_threshold=3, recovery_timeout=3600.0)

        # Trip unhealthy models
        for i, m in enumerate(chain_models):
            if not model_healthy[i]:
                for _ in range(3):
                    breaker.record_failure(m)

        def mock_has_api_key(provider: str) -> bool:
            return provider_has_key.get(provider, False)

        with patch(
            "primr.pipeline.model_breaker._has_api_key",
            side_effect=mock_has_api_key,
        ):
            if expected_model is not None:
                result = breaker.select_model(chain)
                assert result == expected_model, f"Expected {expected_model}, got {result}"
            else:
                import pytest

                with pytest.raises(RuntimeError):
                    breaker.select_model(chain)

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_model_without_api_key_never_returned(
        self,
        data: st.DataObject,
    ) -> None:
        """Models whose provider lacks a configured API key are never returned."""
        from unittest.mock import patch

        from primr.pipeline.model_breaker import FallbackChain, ModelCircuitBreaker

        chain_models = data.draw(st.lists(model_names, min_size=1, max_size=5, unique=True))
        chain = FallbackChain(name="test", models=tuple(chain_models))

        breaker = ModelCircuitBreaker()

        # No API keys available at all
        with patch(
            "primr.pipeline.model_breaker._has_api_key",
            return_value=False,
        ):
            import pytest

            with pytest.raises(RuntimeError):
                breaker.select_model(chain)


# =============================================================================
# PROPERTY 10: HEALTH EVENT EMISSION
# =============================================================================


# Feature: pipeline-resilience, Property 10: Health Event Emission
class TestHealthEventEmission:
    """
    **Property 10: Health Event Emission**

    Every state transition emits a ModelHealthEvent with non-empty timestamp,
    correct model name, correct from_state and to_state, non-negative failure_count.

    **Validates: Requirements 12.1**
    """

    @given(model=model_names)
    @settings(max_examples=100, deadline=None)
    def test_health_event_emitted_on_state_transition(self, model: str) -> None:
        """State transitions emit ModelHealthEvent with correct fields."""
        from primr.pipeline.model_breaker import ModelCircuitBreaker, ModelHealthEvent

        events: list[ModelHealthEvent] = []
        breaker = ModelCircuitBreaker(
            failure_threshold=3,
            health_listener=events.append,
        )

        # Trip the breaker: CLOSED -> OPEN
        for _ in range(3):
            breaker.record_failure(model)

        # Should have emitted at least one event (CLOSED -> OPEN)
        assert len(events) >= 1, "No health event emitted on CLOSED -> OPEN transition"

        event = events[-1]
        assert event.timestamp, "Timestamp must be non-empty"
        assert event.model == model, f"Expected model {model}, got {event.model}"
        assert event.from_state == "closed", f"Expected from_state 'closed', got {event.from_state}"
        assert event.to_state == "open", f"Expected to_state 'open', got {event.to_state}"
        assert event.failure_count >= 0, (
            f"failure_count must be non-negative, got {event.failure_count}"
        )

    @given(model=model_names)
    @settings(max_examples=100, deadline=None)
    def test_health_event_on_recovery(self, model: str) -> None:
        """HALF_OPEN -> CLOSED transition emits correct health event."""
        import time

        from primr.pipeline.model_breaker import ModelCircuitBreaker, ModelHealthEvent

        events: list[ModelHealthEvent] = []
        breaker = ModelCircuitBreaker(
            failure_threshold=3,
            recovery_timeout=0.01,
            health_listener=events.append,
        )

        # Trip to OPEN
        for _ in range(3):
            breaker.record_failure(model)

        # Wait for timeout, trigger HALF_OPEN
        time.sleep(0.02)
        breaker.is_healthy(model)

        # Record success to close
        events.clear()
        breaker.record_success(model)

        # Should have emitted HALF_OPEN -> CLOSED event
        assert len(events) >= 1, "No health event emitted on HALF_OPEN -> CLOSED"
        event = events[-1]
        assert event.model == model
        assert event.from_state == "half_open"
        assert event.to_state == "closed"
        assert event.failure_count >= 0


# =============================================================================
# STRATEGIES FOR EXECUTOR TESTS
# =============================================================================

# Background stages only
background_stages = st.sampled_from(
    [
        PipelineStage.CROSS_VALIDATION,
        PipelineStage.STRATEGY_GENERATION,
    ]
)

# Foreground stages only
foreground_stages = st.sampled_from(
    [
        PipelineStage.SCRAPING,
        PipelineStage.EXTERNAL_SEARCH,
        PipelineStage.ANALYSIS,
        PipelineStage.SECTION_WRITING,
    ]
)


# =============================================================================
# PROPERTY 6: BACKGROUND STAGE IMMEDIATE ABORT
# =============================================================================


# Feature: pipeline-resilience, Property 6: Background Stage Immediate Abort
class TestBackgroundStageImmediateAbort:
    """
    **Property 6: Background Stage Immediate Abort**

    Background stages abort immediately on 429 or budget_stressed without
    attempting recovery actions.

    **Validates: Requirements 9.1, 9.2, 9.3**
    """

    @given(stage=background_stages)
    @settings(max_examples=100, deadline=None)
    def test_background_aborts_on_rate_limit(self, stage: PipelineStage) -> None:
        """Background stage aborts immediately on HTTP 429 without recovery."""
        from primr.pipeline.executor import (
            RecoveryContext,
            RecoveryExecutor,
        )

        handler_called = False

        def failing_callable() -> None:
            raise Exception("429 rate limit exceeded")

        def should_not_be_called(ctx: RecoveryContext) -> Any:
            nonlocal handler_called
            handler_called = True

        # Register handlers for all action types in this stage's hierarchy
        from primr.pipeline.recovery import build_default_recovery_table

        table = build_default_recovery_table()
        hierarchy = table.get_hierarchy(stage)
        handlers: dict[
            tuple[PipelineStage, RecoveryActionType], Callable[[RecoveryContext], Any]
        ] = {}
        for action in hierarchy.actions:
            handlers[(stage, action.action_type)] = should_not_be_called

        executor = RecoveryExecutor(
            recovery_table=table,
            action_handlers=handlers,
        )

        ctx = RecoveryContext(
            stage=stage,
            folder_path="/tmp/test",
            attempt=0,
            last_error=None,
            budget_stressed=False,
        )

        result = executor.execute(stage, failing_callable, ctx)

        assert result.skipped is True, "Background stage should be skipped on 429"
        assert result.skip_reason is not None, "skip_reason must not be None"
        assert len(result.skip_reason) > 0, "skip_reason must be non-empty"
        assert not handler_called, "Recovery handlers should not be called for background 429"

    @given(stage=background_stages)
    @settings(max_examples=100, deadline=None)
    def test_background_aborts_on_budget_stress(self, stage: PipelineStage) -> None:
        """Background stage aborts immediately when budget_stressed=True."""
        from primr.pipeline.executor import (
            RecoveryContext,
            RecoveryExecutor,
        )

        call_count = 0

        def should_not_be_called() -> None:
            nonlocal call_count
            call_count += 1

        executor = RecoveryExecutor()
        ctx = RecoveryContext(
            stage=stage,
            folder_path="/tmp/test",
            attempt=0,
            last_error=None,
            budget_stressed=True,
        )

        result = executor.execute(stage, should_not_be_called, ctx)

        assert result.skipped is True, "Background stage should be skipped on budget stress"
        assert result.skip_reason is not None, "skip_reason must not be None"
        assert len(result.skip_reason) > 0, "skip_reason must be non-empty"
        assert call_count == 0, "Callable should not be invoked when budget_stressed=True"


# =============================================================================
# PROPERTY 4: FOREGROUND STAGE EXHAUSTION
# =============================================================================


# Feature: pipeline-resilience, Property 4: Foreground Stage Exhaustion
class TestForegroundStageExhaustion:
    """
    **Property 4: Foreground Stage Exhaustion**

    For any foreground stage with all-failing callable, executor attempts
    every action in hierarchy before terminating.

    **Validates: Requirements 1.4, 10.1**
    """

    @given(stage=foreground_stages)
    @settings(max_examples=100, deadline=None)
    def test_foreground_exhausts_all_actions(self, stage: PipelineStage) -> None:
        """Foreground stage attempts every action in hierarchy before terminating."""
        from primr.pipeline.executor import (
            RecoveryContext,
            RecoveryExecutor,
        )
        from primr.pipeline.recovery import build_default_recovery_table

        table = build_default_recovery_table()
        hierarchy = table.get_hierarchy(stage)

        # Register always-failing handlers for every action
        handlers = {}
        for action in hierarchy.actions:
            handlers[(stage, action.action_type)] = lambda ctx: (_ for _ in ()).throw(
                Exception("handler failed")
            )

        executor = RecoveryExecutor(
            recovery_table=table,
            action_handlers=handlers,
        )

        def always_fail() -> None:
            raise Exception("initial call failed")

        ctx = RecoveryContext(
            stage=stage,
            folder_path="/tmp/test",
            attempt=0,
            last_error=None,
            budget_stressed=False,
        )

        result = executor.execute(stage, always_fail, ctx)

        # All actions should have been attempted
        assert len(result.actions_taken) == len(hierarchy.actions), (
            f"Expected {len(hierarchy.actions)} actions attempted, got {len(result.actions_taken)}"
        )
        assert result.success is False, "Should not succeed when all actions fail"


# =============================================================================
# PROPERTY 5: QUERY REDUCTION BOUND
# =============================================================================


# Feature: pipeline-resilience, Property 5: Query Reduction Bound
class TestQueryReductionBound:
    """
    **Property 5: Query Reduction Bound**

    For any positive initial count, reduced count <= original // 2,
    and reduced >= 1 when original >= 2.

    **Validates: Requirements 3.2**
    """

    @given(original=st.integers(min_value=1, max_value=10000))
    @settings(max_examples=100, deadline=None)
    def test_reduced_at_most_half(self, original: int) -> None:
        """Reduced count is at most 50% of original."""
        from primr.pipeline.executor import reduce_queries

        reduced = reduce_queries(original)
        assert reduced <= max(original // 2, 1), (
            f"reduce_queries({original}) = {reduced}, expected <= {original // 2}"
        )

    @given(original=st.integers(min_value=2, max_value=10000))
    @settings(max_examples=100, deadline=None)
    def test_reduced_at_least_one_when_original_ge_2(self, original: int) -> None:
        """Reduced count is at least 1 when original >= 2."""
        from primr.pipeline.executor import reduce_queries

        reduced = reduce_queries(original)
        assert reduced >= 1, f"reduce_queries({original}) = {reduced}, expected >= 1"

    @given(original=st.integers(min_value=1, max_value=10000))
    @settings(max_examples=100, deadline=None)
    def test_reduced_is_positive(self, original: int) -> None:
        """Reduced count is always positive."""
        from primr.pipeline.executor import reduce_queries

        reduced = reduce_queries(original)
        assert reduced >= 1, f"reduce_queries({original}) = {reduced}, expected >= 1"


# =============================================================================
# PROPERTY 7: BACKOFF DELAY MONOTONICITY
# =============================================================================


# Feature: pipeline-resilience, Property 7: Backoff Delay Monotonicity
class TestBackoffDelayMonotonicity:
    """
    **Property 7: Backoff Delay Monotonicity**

    Backoff delays are monotonically non-decreasing (ignoring jitter),
    within expected range with jitter, capped at max.

    **Validates: Requirements 10.3**
    """

    @given(
        max_attempt=st.integers(min_value=1, max_value=10),
        base=st.floats(min_value=0.1, max_value=5.0),
        max_delay=st.floats(min_value=10.0, max_value=120.0),
    )
    @settings(max_examples=100, deadline=None)
    def test_delays_within_expected_range(
        self,
        max_attempt: int,
        base: float,
        max_delay: float,
    ) -> None:
        """Each delay falls within [base * 2^attempt, base * 2^attempt * 1.2], capped."""
        from primr.pipeline.executor import compute_backoff

        for attempt in range(max_attempt + 1):
            delay = compute_backoff(attempt, base=base, max_delay=max_delay)
            raw_min = base * (2**attempt)
            raw_max = raw_min * 1.2
            expected_min = min(raw_min, max_delay)
            expected_max = min(raw_max, max_delay)
            assert delay >= expected_min - 1e-9, (
                f"attempt={attempt}: delay {delay} < expected min {expected_min}"
            )
            assert delay <= expected_max + 1e-9, (
                f"attempt={attempt}: delay {delay} > expected max {expected_max}"
            )

    @given(max_attempt=st.integers(min_value=1, max_value=10))
    @settings(max_examples=100, deadline=None)
    def test_delays_capped_at_max(self, max_attempt: int) -> None:
        """Delays never exceed max_delay."""
        from primr.pipeline.executor import compute_backoff

        max_delay = 60.0
        for attempt in range(max_attempt + 1):
            delay = compute_backoff(attempt, max_delay=max_delay)
            assert delay <= max_delay + 1e-9, (
                f"attempt={attempt}: delay {delay} exceeds max_delay {max_delay}"
            )
