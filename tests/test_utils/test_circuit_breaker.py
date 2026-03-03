"""
Tests for the Circuit Breaker pattern implementation.
"""

import threading
import time

import pytest

from primr.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    CircuitStats,
)


class TestCircuitBreakerBasics:
    """Basic circuit breaker functionality tests."""

    def test_initial_state_is_closed(self):
        """Circuit starts in closed state."""
        breaker = CircuitBreaker(name="test")

        assert breaker.get_state("test") == CircuitState.CLOSED
        assert breaker.can_execute("test") is True

    def test_success_keeps_circuit_closed(self):
        """Successful requests keep circuit closed."""
        breaker = CircuitBreaker(name="test")

        for _ in range(10):
            assert breaker.can_execute("test") is True
            breaker.record_success("test")

        assert breaker.get_state("test") == CircuitState.CLOSED

    def test_failures_below_threshold_keep_closed(self):
        """Failures below threshold don't open circuit."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        breaker.record_failure("test")
        breaker.record_failure("test")

        assert breaker.get_state("test") == CircuitState.CLOSED
        assert breaker.can_execute("test") is True

    def test_failures_at_threshold_open_circuit(self):
        """Failures at threshold open the circuit."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        breaker.record_failure("test")
        breaker.record_failure("test")
        breaker.record_failure("test")

        assert breaker.get_state("test") == CircuitState.OPEN
        assert breaker.can_execute("test") is False


class TestCircuitBreakerStateTransitions:
    """Tests for state transitions."""

    def test_open_to_half_open_after_timeout(self):
        """Circuit transitions to half-open after reset timeout."""
        breaker = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=1)

        # Open the circuit
        breaker.record_failure("test")
        assert breaker.get_state("test") == CircuitState.OPEN

        # Wait for timeout
        time.sleep(1.1)

        # Should transition to half-open on next check
        assert breaker.can_execute("test") is True
        assert breaker.get_state("test") == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        """Circuit closes after success in half-open state."""
        breaker = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0.001)

        # Open the circuit
        breaker.record_failure("test")

        # Wait briefly for timeout
        time.sleep(0.01)

        # Transition to half-open
        breaker.can_execute("test")
        assert breaker.get_state("test") == CircuitState.HALF_OPEN

        # Success should close it
        breaker.record_success("test")
        assert breaker.get_state("test") == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Circuit reopens after failure in half-open state."""
        breaker = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0.001)

        # Open the circuit
        breaker.record_failure("test")

        # Wait briefly for timeout
        time.sleep(0.01)

        # Transition to half-open
        breaker.can_execute("test")
        assert breaker.get_state("test") == CircuitState.HALF_OPEN

        # Failure should reopen it
        breaker.record_failure("test")
        assert breaker.get_state("test") == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        """Success in closed state resets failure count."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        # Two failures
        breaker.record_failure("test")
        breaker.record_failure("test")

        # Success resets count
        breaker.record_success("test")

        # Two more failures shouldn't open (count was reset)
        breaker.record_failure("test")
        breaker.record_failure("test")

        assert breaker.get_state("test") == CircuitState.CLOSED


class TestCircuitBreakerReset:
    """Tests for manual reset functionality."""

    def test_reset_closes_open_circuit(self):
        """Manual reset closes an open circuit."""
        breaker = CircuitBreaker(name="test", failure_threshold=1)

        breaker.record_failure("test")
        assert breaker.get_state("test") == CircuitState.OPEN

        breaker.reset("test")

        assert breaker.get_state("test") == CircuitState.CLOSED
        assert breaker.can_execute("test") is True

    def test_reset_clears_failure_count(self):
        """Reset transitions state to closed (failure count is reset on state transition)."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        # Record enough failures to open the circuit
        breaker.record_failure("test")
        breaker.record_failure("test")
        breaker.record_failure("test")

        # Verify circuit is open
        assert breaker.get_state("test") == CircuitState.OPEN

        breaker.reset("test")

        # Verify reset closed the circuit
        assert breaker.get_state("test") == CircuitState.CLOSED

        # After reset, should need 3 failures to open again
        breaker.record_failure("test")
        breaker.record_failure("test")
        assert breaker.get_state("test") == CircuitState.CLOSED

        breaker.record_failure("test")
        assert breaker.get_state("test") == CircuitState.OPEN


class TestCircuitBreakerStatus:
    """Tests for status reporting."""

    def test_get_stats_returns_circuit_stats(self):
        """get_stats returns a CircuitStats object with circuit info."""
        breaker = CircuitBreaker(name="test_circuit")

        stats = breaker.get_stats("test_circuit")

        assert isinstance(stats, CircuitStats)
        assert stats.state == CircuitState.CLOSED
        assert stats.failure_count == 0
        assert stats.last_failure_time is None

    def test_stats_reflects_failures(self):
        """Stats reflects failure count and time."""
        breaker = CircuitBreaker(name="test", failure_threshold=5)

        breaker.record_failure("test")
        breaker.record_failure("test")

        stats = breaker.get_stats("test")

        assert stats.failure_count == 2
        assert stats.last_failure_time is not None


class TestCircuitBreakerThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_access(self):
        """Circuit breaker handles concurrent access."""
        breaker = CircuitBreaker(name="test", failure_threshold=100)
        errors = []

        def record_failures():
            try:
                for _ in range(50):
                    breaker.record_failure("test")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_failures) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Should have recorded 200 failures total
        stats = breaker.get_stats("test")
        assert stats.failure_count >= 100  # At least threshold reached


class TestCircuitBreakerConfiguration:
    """Tests for configuration options."""

    def test_custom_failure_threshold(self):
        """Custom failure threshold is respected."""
        breaker = CircuitBreaker(name="test", failure_threshold=5)

        for _ in range(4):
            breaker.record_failure("test")

        assert breaker.get_state("test") == CircuitState.CLOSED

        breaker.record_failure("test")
        assert breaker.get_state("test") == CircuitState.OPEN

    def test_custom_config_success_threshold(self):
        """Custom success threshold for half-open recovery using config."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=0.001,
            success_threshold=3
        )
        breaker = CircuitBreaker(config)

        # Open and transition to half-open
        breaker.record_failure("test")
        time.sleep(0.01)
        breaker.can_execute("test")

        # Need 3 successes to close
        breaker.record_success("test")
        assert breaker.get_state("test") == CircuitState.HALF_OPEN

        breaker.record_success("test")
        assert breaker.get_state("test") == CircuitState.HALF_OPEN

        breaker.record_success("test")
        assert breaker.get_state("test") == CircuitState.CLOSED


class TestCircuitBreakerNewAPI:
    """Tests for the new API with check() method."""

    def test_check_raises_when_open(self):
        """check() raises CircuitOpenError when circuit is open."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=60.0)
        breaker = CircuitBreaker(config)

        breaker.record_failure("api.example.com")

        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.check("api.example.com")

        assert exc_info.value.host == "api.example.com"
        assert exc_info.value.recoverable is True

    def test_check_allows_when_closed(self):
        """check() allows requests when circuit is closed."""
        config = CircuitBreakerConfig(failure_threshold=5)
        breaker = CircuitBreaker(config)

        # Should not raise
        breaker.check("api.example.com")

    def test_state_change_listener(self):
        """State change listeners are notified on transitions."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker(config)

        events = []
        breaker.add_state_change_listener(lambda e: events.append(e))

        breaker.record_failure("test")

        assert len(events) == 1
        assert events[0].from_state == CircuitState.CLOSED
        assert events[0].to_state == CircuitState.OPEN
        assert events[0].key == "test"
