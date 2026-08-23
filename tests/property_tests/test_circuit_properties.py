"""
Property-based tests for the circuit breaker.

This module contains property tests that verify universal correctness properties
of the circuit breaker implementation as specified in the PhD-Level Excellence spec.

**Feature: phd-level-excellence**
**Validates: Requirements 3.1-3.7**
"""

from __future__ import annotations

import time
from datetime import datetime

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from primr.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    StateChangeEvent,
)

# =============================================================================
# STRATEGIES FOR GENERATING TEST DATA
# =============================================================================

# Strategy for generating circuit keys (host names, operation types)
key_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=50
).map(lambda x: x.lower() + ".example.com")

# Strategy for generating circuit breaker configurations
config_strategy = st.builds(
    CircuitBreakerConfig,
    failure_threshold=st.integers(min_value=1, max_value=20),
    success_threshold=st.integers(min_value=1, max_value=10),
    timeout_seconds=st.floats(
        min_value=0.01, max_value=60.0, allow_nan=False, allow_infinity=False
    ),
    half_open_max_calls=st.integers(min_value=1, max_value=10),
)


# Strategy for generating failure counts
failure_count_strategy = st.integers(min_value=0, max_value=50)

# Strategy for generating success counts
success_count_strategy = st.integers(min_value=0, max_value=50)


# =============================================================================
# PROPERTY 7: FAILURE COUNT TRACKING
# =============================================================================


class TestFailureCountTracking:
    """
    **Property 7: Failure Count Tracking**

    For any sequence of `record_failure()` calls for a given key,
    `get_stats().failure_count` SHALL equal the number of failures
    recorded since the last reset or state change.

    **Validates: Requirements 3.1, 3.3**
    """

    @given(
        key=key_strategy,
        num_failures=st.integers(min_value=1, max_value=20),
        config=config_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_failure_count_equals_recorded_failures(
        self, key: str, num_failures: int, config: CircuitBreakerConfig
    ):
        """Failure count should equal the number of recorded failures."""
        # Ensure we don't trigger state transition
        assume(num_failures < config.failure_threshold)

        breaker = CircuitBreaker(config)

        # Record failures
        for _ in range(num_failures):
            breaker.record_failure(key)

        stats = breaker.get_stats(key)

        # Failure count should match
        assert stats.failure_count == num_failures

    @given(key=key_strategy, config=config_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_failure_count_resets_on_success_in_closed_state(
        self, key: str, config: CircuitBreakerConfig
    ):
        """Failure count should reset to 0 after a success in closed state."""
        # Ensure we have room to record failures without opening
        assume(config.failure_threshold >= 2)

        breaker = CircuitBreaker(config)

        # Record some failures (but not enough to open)
        failures_to_record = config.failure_threshold - 1
        for _ in range(failures_to_record):
            breaker.record_failure(key)

        # Verify failures were recorded and circuit is still closed
        assert breaker.get_stats(key).failure_count == failures_to_record
        assert breaker.get_state(key) == CircuitState.CLOSED

        # Record a success
        breaker.record_success(key)

        # Failure count should be reset
        assert breaker.get_stats(key).failure_count == 0

    @given(key=key_strategy, config=config_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_failure_count_resets_on_state_transition_to_closed(
        self, key: str, config: CircuitBreakerConfig
    ):
        """Failure count should reset when transitioning to CLOSED state."""
        # Use short timeout for testing
        config = CircuitBreakerConfig(
            failure_threshold=config.failure_threshold,
            success_threshold=1,  # Single success to close
            timeout_seconds=0.01,  # Very short timeout
            half_open_max_calls=config.half_open_max_calls,
        )
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        assert breaker.get_state(key) == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.02)

        # Check to transition to half-open
        breaker.check(key)
        assert breaker.get_state(key) == CircuitState.HALF_OPEN

        # Record success to close
        breaker.record_success(key)
        assert breaker.get_state(key) == CircuitState.CLOSED

        # Failure count should be reset
        assert breaker.get_stats(key).failure_count == 0

    @given(key=key_strategy, num_failures=st.integers(min_value=1, max_value=10))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_last_failure_time_updated_on_failure(self, key: str, num_failures: int):
        """Last failure time should be updated on each failure."""
        config = CircuitBreakerConfig(failure_threshold=num_failures + 5)
        breaker = CircuitBreaker(config)

        before = datetime.now()

        for _ in range(num_failures):
            breaker.record_failure(key)

        after = datetime.now()

        stats = breaker.get_stats(key)

        # Last failure time should be set and within bounds
        assert stats.last_failure_time is not None
        assert before <= stats.last_failure_time <= after


# =============================================================================
# PROPERTY 8: STATE TRANSITION EVENTS
# =============================================================================


class TestStateTransitionEvents:
    """
    **Property 8: State Transition Events**

    For any circuit breaker state transition (closed→open, open→half-open,
    half-open→closed), all registered listeners SHALL receive a `StateChangeEvent`
    with correct `from_state`, `to_state`, and `trigger` values.

    **Validates: Requirements 3.4**
    """

    @given(key=key_strategy, config=config_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_listener_receives_closed_to_open_event(self, key: str, config: CircuitBreakerConfig):
        """Listener should receive event when circuit opens."""
        breaker = CircuitBreaker(config)

        events: list[StateChangeEvent] = []
        breaker.add_state_change_listener(lambda e: events.append(e))

        # Trigger transition to OPEN
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Should have received exactly one event
        assert len(events) == 1
        event = events[0]

        assert event.key == key
        assert event.from_state == CircuitState.CLOSED
        assert event.to_state == CircuitState.OPEN
        assert event.trigger == "failure"
        assert isinstance(event.timestamp, datetime)

    @given(key=key_strategy, config=config_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_listener_receives_open_to_half_open_event(
        self, key: str, config: CircuitBreakerConfig
    ):
        """Listener should receive event when circuit transitions to half-open."""
        # Use short timeout for testing
        config = CircuitBreakerConfig(
            failure_threshold=config.failure_threshold,
            success_threshold=config.success_threshold,
            timeout_seconds=0.01,
            half_open_max_calls=config.half_open_max_calls,
        )
        breaker = CircuitBreaker(config)

        events: list[StateChangeEvent] = []
        breaker.add_state_change_listener(lambda e: events.append(e))

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Wait for timeout
        time.sleep(0.02)

        # Check to trigger transition
        breaker.check(key)

        # Should have two events: CLOSED->OPEN and OPEN->HALF_OPEN
        assert len(events) == 2

        half_open_event = events[1]
        assert half_open_event.from_state == CircuitState.OPEN
        assert half_open_event.to_state == CircuitState.HALF_OPEN
        assert half_open_event.trigger == "timeout"

    @given(key=key_strategy, config=config_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_listener_receives_half_open_to_closed_event(
        self, key: str, config: CircuitBreakerConfig
    ):
        """Listener should receive event when circuit closes from half-open."""
        # Use short timeout and single success threshold
        config = CircuitBreakerConfig(
            failure_threshold=config.failure_threshold,
            success_threshold=1,
            timeout_seconds=0.01,
            half_open_max_calls=config.half_open_max_calls,
        )
        breaker = CircuitBreaker(config)

        events: list[StateChangeEvent] = []
        breaker.add_state_change_listener(lambda e: events.append(e))

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Wait and transition to half-open
        time.sleep(0.02)
        breaker.check(key)

        # Record success to close
        breaker.record_success(key)

        # Should have three events
        assert len(events) == 3

        close_event = events[2]
        assert close_event.from_state == CircuitState.HALF_OPEN
        assert close_event.to_state == CircuitState.CLOSED
        assert close_event.trigger == "success"

    @given(key=key_strategy, config=config_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_listener_receives_half_open_to_open_event(
        self, key: str, config: CircuitBreakerConfig
    ):
        """Listener should receive event when circuit reopens from half-open."""
        config = CircuitBreakerConfig(
            failure_threshold=config.failure_threshold,
            success_threshold=config.success_threshold,
            timeout_seconds=0.01,
            half_open_max_calls=config.half_open_max_calls,
        )
        breaker = CircuitBreaker(config)

        events: list[StateChangeEvent] = []
        breaker.add_state_change_listener(lambda e: events.append(e))

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Wait and transition to half-open
        time.sleep(0.02)
        breaker.check(key)

        # Record failure to reopen
        breaker.record_failure(key)

        # Should have three events
        assert len(events) == 3

        reopen_event = events[2]
        assert reopen_event.from_state == CircuitState.HALF_OPEN
        assert reopen_event.to_state == CircuitState.OPEN
        assert reopen_event.trigger == "failure"

    @given(key=key_strategy, num_listeners=st.integers(min_value=1, max_value=5))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_listeners_receive_events(self, key: str, num_listeners: int):
        """All registered listeners should receive state change events."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(config)

        # Register multiple listeners
        all_events: list[list[StateChangeEvent]] = [[] for _ in range(num_listeners)]
        for i in range(num_listeners):
            breaker.add_state_change_listener(lambda e, idx=i: all_events[idx].append(e))

        # Trigger a state change
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # All listeners should have received the event
        for listener_events in all_events:
            assert len(listener_events) == 1
            assert listener_events[0].to_state == CircuitState.OPEN

    @given(key=key_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_listener_error_does_not_affect_circuit(self, key: str):
        """Listener errors should not affect circuit breaker operation."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(config)

        def failing_listener(event: StateChangeEvent):
            raise RuntimeError("Listener error")

        good_events: list[StateChangeEvent] = []

        breaker.add_state_change_listener(failing_listener)
        breaker.add_state_change_listener(lambda e: good_events.append(e))

        # Should not raise despite failing listener
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Circuit should still be open
        assert breaker.get_state(key) == CircuitState.OPEN

        # Good listener should still receive event
        assert len(good_events) == 1


# =============================================================================
# PROPERTY 9: THRESHOLD-BASED STATE TRANSITIONS
# =============================================================================


class TestThresholdBasedStateTransitions:
    """
    **Property 9: Threshold-Based State Transitions**

    For any circuit breaker with `failure_threshold=N`, the circuit SHALL
    transition from CLOSED to OPEN after exactly N consecutive failures.
    For any circuit with `success_threshold=M`, the circuit SHALL transition
    from HALF_OPEN to CLOSED after exactly M consecutive successes.

    **Validates: Requirements 3.5, 3.6**
    """

    @given(key=key_strategy, failure_threshold=st.integers(min_value=1, max_value=20))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_circuit_opens_after_exactly_n_failures(self, key: str, failure_threshold: int):
        """Circuit should open after exactly failure_threshold failures."""
        config = CircuitBreakerConfig(failure_threshold=failure_threshold)
        breaker = CircuitBreaker(config)

        # Record N-1 failures - should still be closed
        for _ in range(failure_threshold - 1):
            breaker.record_failure(key)
            assert breaker.get_state(key) == CircuitState.CLOSED

        # Record Nth failure - should now be open
        breaker.record_failure(key)
        assert breaker.get_state(key) == CircuitState.OPEN

    @given(key=key_strategy, success_threshold=st.integers(min_value=1, max_value=10))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_circuit_closes_after_exactly_m_successes(self, key: str, success_threshold: int):
        """Circuit should close after exactly success_threshold successes in half-open."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=success_threshold,
            timeout_seconds=0.01,
            half_open_max_calls=success_threshold + 5,
        )
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Wait and transition to half-open
        time.sleep(0.02)
        breaker.check(key)
        assert breaker.get_state(key) == CircuitState.HALF_OPEN

        # Record M-1 successes - should still be half-open
        for _ in range(success_threshold - 1):
            breaker.record_success(key)
            assert breaker.get_state(key) == CircuitState.HALF_OPEN

        # Record Mth success - should now be closed
        breaker.record_success(key)
        assert breaker.get_state(key) == CircuitState.CLOSED

    @given(key=key_strategy, failure_threshold=st.integers(min_value=2, max_value=10))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_success_resets_failure_count_before_threshold(self, key: str, failure_threshold: int):
        """Success should reset failure count, preventing circuit from opening."""
        config = CircuitBreakerConfig(failure_threshold=failure_threshold)
        breaker = CircuitBreaker(config)

        # Record N-1 failures
        for _ in range(failure_threshold - 1):
            breaker.record_failure(key)

        # Record a success - should reset failure count
        breaker.record_success(key)

        # Record N-1 more failures - should still be closed
        for _ in range(failure_threshold - 1):
            breaker.record_failure(key)

        assert breaker.get_state(key) == CircuitState.CLOSED

    @given(key=key_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_single_failure_in_half_open_reopens_circuit(self, key: str):
        """Any failure in half-open state should immediately reopen the circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=5,  # High threshold
            timeout_seconds=0.01,
        )
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Wait and transition to half-open
        time.sleep(0.02)
        breaker.check(key)
        assert breaker.get_state(key) == CircuitState.HALF_OPEN

        # Record some successes (but not enough to close)
        for _ in range(config.success_threshold - 2):
            breaker.record_success(key)

        # Single failure should reopen
        breaker.record_failure(key)
        assert breaker.get_state(key) == CircuitState.OPEN

    @given(key=key_strategy, config=config_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_successes_in_closed_state_do_not_change_state(
        self, key: str, config: CircuitBreakerConfig
    ):
        """Successes in closed state should not change the state."""
        breaker = CircuitBreaker(config)

        # Record many successes
        for _ in range(20):
            breaker.record_success(key)

        # Should still be closed
        assert breaker.get_state(key) == CircuitState.CLOSED


# =============================================================================
# PROPERTY 10: OPEN CIRCUIT REJECTION
# =============================================================================


class TestOpenCircuitRejection:
    """
    **Property 10: Open Circuit Rejection**

    For any circuit in OPEN state (before timeout), calling `check()` SHALL
    raise `CircuitOpenError` with a `retry_after` value equal to the remaining
    timeout duration.

    **Validates: Requirements 3.7**
    """

    @given(
        key=key_strategy,
        timeout_seconds=st.floats(
            min_value=1.0, max_value=60.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_check_raises_circuit_open_error_when_open(self, key: str, timeout_seconds: float):
        """check() should raise CircuitOpenError when circuit is open."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=timeout_seconds)
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # check() should raise CircuitOpenError
        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check(key)

        error = exc_info.value
        assert error.host == key
        assert error.recoverable is True
        assert error.category == "circuit_open"

    @given(
        key=key_strategy,
        timeout_seconds=st.floats(
            min_value=1.0, max_value=60.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_retry_after_equals_remaining_timeout(self, key: str, timeout_seconds: float):
        """retry_after should equal the remaining timeout duration."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=timeout_seconds)
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Immediately check - retry_after should be close to timeout_seconds
        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check(key)

        error = exc_info.value

        # retry_after should be approximately timeout_seconds (within 0.1s tolerance)
        assert error.retry_after is not None
        assert abs(error.retry_after - timeout_seconds) < 0.1

    @given(key=key_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_retry_after_decreases_over_time(self, key: str):
        """retry_after should decrease as time passes."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=1.0,  # 1 second timeout
        )
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Get initial retry_after
        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check(key)
        initial_retry_after = exc_info.value.retry_after

        # Wait a bit
        time.sleep(0.2)

        # Get retry_after again
        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check(key)
        later_retry_after = exc_info.value.retry_after

        # Should have decreased
        assert later_retry_after < initial_retry_after

    @given(key=key_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_check_succeeds_after_timeout(self, key: str):
        """check() should succeed after timeout has elapsed."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=0.01,  # Very short timeout
        )
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Wait for timeout
        time.sleep(0.02)

        # check() should succeed (no exception)
        breaker.check(key)

        # Should now be in half-open state
        assert breaker.get_state(key) == CircuitState.HALF_OPEN

    @given(key=key_strategy, config=config_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_check_succeeds_when_closed(self, key: str, config: CircuitBreakerConfig):
        """check() should succeed when circuit is closed."""
        breaker = CircuitBreaker(config)

        # check() should not raise when closed
        breaker.check(key)  # Should not raise

        assert breaker.get_state(key) == CircuitState.CLOSED

    @given(key=key_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_total_rejections_incremented_on_open_check(self, key: str):
        """total_rejections should increment when check() is called on open circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=60.0,  # Long timeout
        )
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        initial_rejections = breaker.get_stats(key).total_rejections

        # Try to check multiple times
        num_checks = 5
        for _ in range(num_checks):
            with pytest.raises(CircuitOpenError):
                breaker.check(key)

        # total_rejections should have increased
        final_rejections = breaker.get_stats(key).total_rejections
        assert final_rejections == initial_rejections + num_checks

    @given(key=key_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_circuit_open_error_is_primr_error(self, key: str):
        """CircuitOpenError should be a PrimrError subclass."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check(key)

        error = exc_info.value

        # Should be a PrimrError
        from primr.utils.errors import PrimrError

        assert isinstance(error, PrimrError)

        # Should have all PrimrError attributes
        assert hasattr(error, "message")
        assert hasattr(error, "category")
        assert hasattr(error, "recoverable")
        assert hasattr(error, "retry_after")
        assert hasattr(error, "correlation_id")

    @given(key=key_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_retry_after_is_non_negative(self, key: str):
        """retry_after should always be non-negative."""
        # The property concerns the error value, not timeout transition timing.
        # Keep the circuit open long enough for coverage and loaded CI runners.
        config = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=60.0)
        breaker = CircuitBreaker(config)

        # Open the circuit
        for _ in range(config.failure_threshold):
            breaker.record_failure(key)

        # Check immediately
        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check(key)

        assert exc_info.value.retry_after >= 0
