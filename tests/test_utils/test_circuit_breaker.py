"""
Tests for the Circuit Breaker pattern implementation.
"""

import pytest
import time
from unittest.mock import patch
from datetime import datetime, timedelta

from primr.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)


class TestCircuitBreakerBasics:
    """Basic circuit breaker functionality tests."""
    
    def test_initial_state_is_closed(self):
        """Circuit starts in closed state."""
        breaker = CircuitBreaker(name="test")
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True
        assert breaker.is_open is False
    
    def test_success_keeps_circuit_closed(self):
        """Successful requests keep circuit closed."""
        breaker = CircuitBreaker(name="test")
        
        for _ in range(10):
            assert breaker.can_execute() is True
            breaker.record_success()
        
        assert breaker.state == CircuitState.CLOSED
    
    def test_failures_below_threshold_keep_closed(self):
        """Failures below threshold don't open circuit."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        
        breaker.record_failure()
        breaker.record_failure()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True
    
    def test_failures_at_threshold_open_circuit(self):
        """Failures at threshold open the circuit."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open is True
        assert breaker.can_execute() is False


class TestCircuitBreakerStateTransitions:
    """Tests for state transitions."""
    
    def test_open_to_half_open_after_timeout(self):
        """Circuit transitions to half-open after reset timeout."""
        breaker = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=1)
        
        # Open the circuit
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        
        # Wait for timeout
        time.sleep(1.1)
        
        # Should transition to half-open on next check
        assert breaker.can_execute() is True
        assert breaker.state == CircuitState.HALF_OPEN
    
    def test_half_open_to_closed_on_success(self):
        """Circuit closes after success in half-open state."""
        breaker = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0)
        
        # Open the circuit
        breaker.record_failure()
        
        # Transition to half-open
        breaker.can_execute()
        assert breaker.state == CircuitState.HALF_OPEN
        
        # Success should close it
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
    
    def test_half_open_to_open_on_failure(self):
        """Circuit reopens after failure in half-open state."""
        breaker = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0)
        
        # Open the circuit
        breaker.record_failure()
        
        # Transition to half-open
        breaker.can_execute()
        assert breaker.state == CircuitState.HALF_OPEN
        
        # Failure should reopen it
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
    
    def test_success_resets_failure_count(self):
        """Success in closed state resets failure count."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        
        # Two failures
        breaker.record_failure()
        breaker.record_failure()
        
        # Success resets count
        breaker.record_success()
        
        # Two more failures shouldn't open (count was reset)
        breaker.record_failure()
        breaker.record_failure()
        
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerReset:
    """Tests for manual reset functionality."""
    
    def test_reset_closes_open_circuit(self):
        """Manual reset closes an open circuit."""
        breaker = CircuitBreaker(name="test", failure_threshold=1)
        
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True
    
    def test_reset_clears_failure_count(self):
        """Reset clears the failure count."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        
        breaker.record_failure()
        breaker.record_failure()
        breaker.reset()
        
        # Should need 3 more failures to open
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerStatus:
    """Tests for status reporting."""
    
    def test_get_status_returns_dict(self):
        """get_status returns a dictionary with circuit info."""
        breaker = CircuitBreaker(name="test_circuit")
        
        status = breaker.get_status()
        
        assert status["name"] == "test_circuit"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["last_failure"] is None
    
    def test_status_reflects_failures(self):
        """Status reflects failure count and time."""
        breaker = CircuitBreaker(name="test", failure_threshold=5)
        
        breaker.record_failure()
        breaker.record_failure()
        
        status = breaker.get_status()
        
        assert status["failure_count"] == 2
        assert status["last_failure"] is not None


class TestCircuitBreakerThreadSafety:
    """Tests for thread safety."""
    
    def test_concurrent_access(self):
        """Circuit breaker handles concurrent access."""
        import threading
        
        breaker = CircuitBreaker(name="test", failure_threshold=100)
        errors = []
        
        def record_failures():
            try:
                for _ in range(50):
                    breaker.record_failure()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=record_failures) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        # Should have recorded 200 failures total
        status = breaker.get_status()
        assert status["failure_count"] >= 100  # At least threshold reached


class TestCircuitBreakerConfiguration:
    """Tests for configuration options."""
    
    def test_custom_failure_threshold(self):
        """Custom failure threshold is respected."""
        breaker = CircuitBreaker(name="test", failure_threshold=5)
        
        for _ in range(4):
            breaker.record_failure()
        
        assert breaker.state == CircuitState.CLOSED
        
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
    
    def test_custom_success_threshold(self):
        """Custom success threshold for half-open recovery."""
        breaker = CircuitBreaker(
            name="test", 
            failure_threshold=1, 
            reset_timeout=0,
            success_threshold=3
        )
        
        # Open and transition to half-open
        breaker.record_failure()
        breaker.can_execute()
        
        # Need 3 successes to close
        breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN
        
        breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN
        
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
