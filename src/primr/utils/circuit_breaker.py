"""
Circuit Breaker pattern for external API resilience.

Prevents cascading failures by failing fast when an external service
is experiencing issues, allowing it time to recover.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Service is down, requests fail immediately
- HALF_OPEN: Testing if service has recovered

Usage:
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60)

    if breaker.can_execute():
        try:
            result = call_external_api()
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise
    else:
        # Circuit is open, skip the call
        return None
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from primr.utils.logging_config import get_logger

logger = get_logger("utils.circuit_breaker")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for external API calls.

    Tracks failures and opens the circuit when threshold is reached,
    preventing further calls until the reset timeout expires.

    Args:
        name: Identifier for this circuit (for logging)
        failure_threshold: Number of failures before opening circuit
        reset_timeout: Seconds to wait before testing recovery
        success_threshold: Successes needed in half-open to close circuit
    """
    name: str = "default"
    failure_threshold: int = 3
    reset_timeout: int = 60
    success_threshold: int = 1

    # Internal state
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: datetime | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing fast)."""
        return self.state == CircuitState.OPEN

    def can_execute(self) -> bool:
        """
        Check if a request can be executed.

        Returns:
            True if request should proceed, False if circuit is open
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if reset timeout has passed
                if self._last_failure_time is not None:
                    elapsed = (datetime.now() - self._last_failure_time).total_seconds()
                    if elapsed >= self.reset_timeout:
                        # Transition to half-open
                        self._state = CircuitState.HALF_OPEN
                        self._success_count = 0
                        logger.info(f"Circuit '{self.name}' transitioning to HALF_OPEN")
                        return True
                return False

            # HALF_OPEN: allow request to test recovery
            return True

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    # Service recovered, close circuit
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(f"Circuit '{self.name}' CLOSED (service recovered)")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()

            if self._state == CircuitState.HALF_OPEN:
                # Failed during recovery test, reopen circuit
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit '{self.name}' OPEN (recovery failed)")
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    # Threshold reached, open circuit
                    self._state = CircuitState.OPEN
                    logger.warning(
                        f"Circuit '{self.name}' OPEN after {self._failure_count} failures"
                    )

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            logger.debug(f"Circuit '{self.name}' reset to CLOSED")

    def get_status(self) -> dict:
        """Get current circuit status for monitoring."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "last_failure": self._last_failure_time.isoformat() if self._last_failure_time else None,
            }
