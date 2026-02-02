"""
Circuit Breaker with Monitoring for fault tolerance.

This module provides:
- CircuitState enum for circuit breaker states
- CircuitBreakerConfig dataclass for configuration
- CircuitStats dataclass for monitoring statistics
- CircuitBreaker class for managing circuit breaker state
- CircuitOpenError for signaling open circuit

The circuit breaker pattern prevents repeated calls to a failing service
by tracking failure rates and temporarily blocking requests.

**Feature: phd-level-excellence**
**Validates: Requirements 3.1-3.7**
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from primr.utils.errors import PrimrError

logger = logging.getLogger(__name__)


# =============================================================================
# CIRCUIT STATE ENUM
# =============================================================================

class CircuitState(Enum):
    """
    States for the circuit breaker state machine.
    
    The circuit breaker has three states:
    - CLOSED: Normal operation, requests are allowed
    - OPEN: Circuit is tripped, requests are rejected
    - HALF_OPEN: Testing if service has recovered
    
    State transitions:
    - CLOSED -> OPEN: When failure_threshold is reached
    - OPEN -> HALF_OPEN: After timeout_seconds has elapsed
    - HALF_OPEN -> CLOSED: When success_threshold is reached
    - HALF_OPEN -> OPEN: When a failure occurs in half-open state
    
    **Validates: Requirements 3.5, 3.6**
    """
    
    CLOSED = "closed"      # Normal operation, requests allowed
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


# =============================================================================
# CIRCUIT BREAKER CONFIGURATION
# =============================================================================

@dataclass
class CircuitBreakerConfig:
    """
    Configuration for circuit breaker behavior.
    
    This dataclass defines the parameters that control how the circuit
    breaker operates, including thresholds for opening and closing the
    circuit, and timeout for transitioning from open to half-open.
    
    Attributes:
        failure_threshold: Number of consecutive failures to open the circuit
        success_threshold: Number of consecutive successes to close the circuit
        timeout_seconds: Time to wait before transitioning from OPEN to HALF_OPEN
        half_open_max_calls: Maximum calls allowed in HALF_OPEN state
    
    Example:
        config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            timeout_seconds=30.0,
            half_open_max_calls=3
        )
    
    **Validates: Requirements 3.5, 3.6**
    """
    
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 30.0
    half_open_max_calls: int = 3
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.success_threshold < 1:
            raise ValueError("success_threshold must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")


# =============================================================================
# CIRCUIT STATISTICS
# =============================================================================

@dataclass
class CircuitStats:
    """
    Statistics for circuit breaker monitoring.
    
    This dataclass provides a snapshot of the circuit breaker's current
    state and statistics for monitoring and debugging purposes.
    
    Attributes:
        state: Current circuit state (CLOSED, OPEN, HALF_OPEN)
        failure_count: Number of failures since last reset
        success_count: Number of successes since last reset
        last_failure_time: Timestamp of the last failure (None if no failures)
        last_state_change: Timestamp of the last state transition
        total_rejections: Total number of requests rejected due to open circuit
    
    **Validates: Requirements 3.3**
    """
    
    state: CircuitState
    failure_count: int
    success_count: int
    last_failure_time: datetime | None
    last_state_change: datetime
    total_rejections: int


# =============================================================================
# STATE CHANGE EVENT
# =============================================================================

@dataclass
class StateChangeEvent:
    """
    Event emitted when circuit breaker state changes.
    
    This dataclass captures information about a state transition for
    event listeners.
    
    Attributes:
        key: The circuit key (e.g., host name)
        from_state: The previous state
        to_state: The new state
        timestamp: When the transition occurred
        trigger: What triggered the transition (e.g., "failure", "success", "timeout")
    
    **Validates: Requirements 3.4**
    """
    
    key: str
    from_state: CircuitState
    to_state: CircuitState
    timestamp: datetime
    trigger: str


# =============================================================================
# CIRCUIT OPEN ERROR
# =============================================================================

@dataclass
class CircuitOpenError(PrimrError):
    """
    Raised when circuit breaker is open and rejecting requests.
    
    This error indicates that the circuit breaker is in the OPEN state
    and is rejecting requests to protect the system from cascading failures.
    
    Attributes:
        host: The host/key for which the circuit is open
        retry_after: Seconds until the circuit may transition to HALF_OPEN
        category: Always "circuit_open"
        recoverable: Always True (can retry after timeout)
    
    Example:
        try:
            circuit_breaker.check("api.example.com")
        except CircuitOpenError as e:
            print(f"Circuit open for {e.host}, retry after {e.retry_after}s")
    
    **Validates: Requirements 3.7**
    """
    
    message: str = ""
    host: str = ""
    category: str = "circuit_open"
    recoverable: bool = True
    
    def __post_init__(self) -> None:
        """Initialize the error with a descriptive message."""
        if not self.message:
            self.message = f"Circuit breaker open for {self.host}"
        super().__post_init__()


# =============================================================================
# INTERNAL CIRCUIT STATE TRACKING
# =============================================================================

@dataclass
class _CircuitStateData:
    """
    Internal state tracking for a single circuit.
    
    This class tracks the state and statistics for a single circuit key.
    """
    
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    half_open_calls: int = 0
    last_failure_time: datetime | None = None
    last_state_change: datetime = field(default_factory=datetime.now)
    total_rejections: int = 0
    
    def time_in_current_state(self) -> float:
        """Get time in seconds since last state change."""
        return (datetime.now() - self.last_state_change).total_seconds()
    
    def should_attempt_reset(self, config: CircuitBreakerConfig) -> bool:
        """Check if enough time has passed to attempt reset from OPEN state."""
        if self.state != CircuitState.OPEN:
            return False
        return self.time_in_current_state() >= config.timeout_seconds
    
    def transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state, resetting counters as appropriate."""
        self.state = new_state
        self.last_state_change = datetime.now()
        
        if new_state == CircuitState.CLOSED:
            # Reset counters when closing
            self.failure_count = 0
            self.success_count = 0
            self.half_open_calls = 0
        elif new_state == CircuitState.HALF_OPEN:
            # Reset counters for half-open testing
            self.success_count = 0
            self.half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            # Reset success count when opening
            self.success_count = 0
    
    def record_success(self, config: CircuitBreakerConfig) -> CircuitState | None:
        """
        Record a successful call and return new state if transition occurred.
        
        Returns:
            New state if a transition occurred, None otherwise
        """
        self.success_count += 1
        
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.success_count >= config.success_threshold:
                old_state = self.state
                self.transition_to(CircuitState.CLOSED)
                return CircuitState.CLOSED
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success in closed state
            self.failure_count = 0
        
        return None
    
    def record_failure(self, config: CircuitBreakerConfig) -> CircuitState | None:
        """
        Record a failed call and return new state if transition occurred.
        
        Returns:
            New state if a transition occurred, None otherwise
        """
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state opens the circuit
            self.transition_to(CircuitState.OPEN)
            return CircuitState.OPEN
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= config.failure_threshold:
                self.transition_to(CircuitState.OPEN)
                return CircuitState.OPEN
        
        return None


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

# Type alias for state change listener
StateChangeListener = Callable[[StateChangeEvent], None]


class CircuitBreaker:
    """
    Circuit breaker with monitoring interface.
    
    The circuit breaker tracks failures per key (e.g., host, operation type)
    and automatically transitions between states based on configured thresholds.
    
    Key features:
    - Per-key state tracking with failure/success counts
    - Automatic state transitions based on thresholds
    - Timeout-based transition from OPEN to HALF_OPEN
    - Monitoring interface for state and statistics
    - Event emission for state changes
    
    Example (new API):
        breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            timeout_seconds=30.0
        ))
        
        # Check before making a call
        try:
            breaker.check("api.example.com")
            result = make_api_call()
            breaker.record_success("api.example.com")
        except CircuitOpenError:
            # Circuit is open, handle gracefully
            pass
        except Exception:
            breaker.record_failure("api.example.com")
            raise
    
    Example (legacy API - backward compatible):
        breaker = CircuitBreaker(
            name="google_search",
            failure_threshold=3,
            reset_timeout=60
        )
        
        if breaker.is_open("https://api.example.com"):
            # Circuit is open, skip request
            pass
    
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.7**
    """
    
    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        *,
        # Legacy parameters for backward compatibility
        name: str | None = None,
        failure_threshold: int | None = None,
        reset_timeout: float | None = None,
        half_open_requests: int | None = None,
    ):
        """
        Initialize CircuitBreaker.
        
        Args:
            config: Circuit breaker configuration (uses defaults if None)
            name: Legacy parameter - circuit breaker name (stored for reference)
            failure_threshold: Legacy parameter - failures before opening
            reset_timeout: Legacy parameter - seconds before trying again
            half_open_requests: Legacy parameter - requests allowed in half-open
        """
        # Handle legacy parameters
        if name is not None or failure_threshold is not None or reset_timeout is not None:
            # Legacy mode - create config from individual parameters
            self.config = CircuitBreakerConfig(
                failure_threshold=failure_threshold if failure_threshold is not None else 5,
                success_threshold=1,  # Legacy behavior: single success closes
                timeout_seconds=reset_timeout if reset_timeout is not None else 30.0,
                half_open_max_calls=half_open_requests if half_open_requests is not None else 3,
            )
            self._name = name
            self._legacy_mode = True
        else:
            self.config = config or CircuitBreakerConfig()
            self._name = None
            self._legacy_mode = False
        
        self._circuits: dict[str, _CircuitStateData] = {}
        self._listeners: list[StateChangeListener] = []
    
    def _get_or_create(self, key: str) -> _CircuitStateData:
        """Get or create circuit state for a key."""
        if key not in self._circuits:
            self._circuits[key] = _CircuitStateData()
        return self._circuits[key]
    
    def _notify_state_change(
        self,
        key: str,
        from_state: CircuitState,
        to_state: CircuitState,
        trigger: str
    ) -> None:
        """Notify all listeners of a state change."""
        event = StateChangeEvent(
            key=key,
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.now(),
            trigger=trigger
        )
        
        logger.info(
            f"Circuit breaker state change: {key} {from_state.value} -> {to_state.value} "
            f"(trigger: {trigger})"
        )
        
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                # Don't let listener errors affect circuit breaker operation
                logger.warning(f"State change listener error: {e}")
    
    def get_state(self, key: str) -> CircuitState:
        """
        Get current circuit state for a key.
        
        Args:
            key: The circuit key (e.g., host name, operation type)
        
        Returns:
            Current circuit state
        
        **Validates: Requirements 3.2**
        """
        circuit = self._get_or_create(key)
        return circuit.state
    
    def get_stats(self, key: str) -> CircuitStats:
        """
        Get circuit statistics for monitoring.
        
        Args:
            key: The circuit key
        
        Returns:
            CircuitStats with current state and counts
        
        **Validates: Requirements 3.3**
        """
        circuit = self._get_or_create(key)
        return CircuitStats(
            state=circuit.state,
            failure_count=circuit.failure_count,
            success_count=circuit.success_count,
            last_failure_time=circuit.last_failure_time,
            last_state_change=circuit.last_state_change,
            total_rejections=circuit.total_rejections,
        )
    
    def get_all_stats(self) -> dict[str, CircuitStats]:
        """
        Get stats for all tracked circuits.
        
        Returns:
            Dictionary mapping keys to their CircuitStats
        
        **Validates: Requirements 3.3**
        """
        return {key: self.get_stats(key) for key in self._circuits}
    
    def record_success(self, key: str | None = None) -> None:
        """
        Record a successful call.
        
        This should be called after a successful operation to update
        the circuit breaker state.
        
        Args:
            key: The circuit key (uses name if in legacy mode and key is None)
        
        **Validates: Requirements 3.1, 3.2**
        """
        circuit_key = key or self._name or "default"
        circuit = self._get_or_create(circuit_key)
        old_state = circuit.state
        new_state = circuit.record_success(self.config)
        
        if new_state is not None:
            self._notify_state_change(circuit_key, old_state, new_state, "success")
    
    def record_failure(self, key: str | None = None) -> None:
        """
        Record a failed call.
        
        This should be called after a failed operation to update
        the circuit breaker state.
        
        Args:
            key: The circuit key (uses name if in legacy mode and key is None)
        
        **Validates: Requirements 3.1, 3.2**
        """
        circuit_key = key or self._name or "default"
        circuit = self._get_or_create(circuit_key)
        old_state = circuit.state
        new_state = circuit.record_failure(self.config)
        
        if new_state is not None:
            self._notify_state_change(circuit_key, old_state, new_state, "failure")
    
    def check(self, key: str) -> None:
        """
        Check if circuit allows requests.
        
        This should be called before making a request. If the circuit
        is open, it will raise CircuitOpenError. If the circuit is open
        but the timeout has elapsed, it will transition to half-open.
        
        Args:
            key: The circuit key
        
        Raises:
            CircuitOpenError: If the circuit is open and timeout hasn't elapsed
        
        **Validates: Requirements 3.7**
        """
        circuit = self._get_or_create(key)
        
        if circuit.state == CircuitState.OPEN:
            # Check if timeout has passed
            if circuit.should_attempt_reset(self.config):
                old_state = circuit.state
                circuit.transition_to(CircuitState.HALF_OPEN)
                self._notify_state_change(key, old_state, CircuitState.HALF_OPEN, "timeout")
            else:
                # Still in open state, reject request
                circuit.total_rejections += 1
                retry_after = self.config.timeout_seconds - circuit.time_in_current_state()
                raise CircuitOpenError(
                    host=key,
                    retry_after=max(0.0, retry_after)
                )
        elif circuit.state == CircuitState.HALF_OPEN:
            # Check if we've exceeded max calls in half-open state
            if circuit.half_open_calls >= self.config.half_open_max_calls:
                circuit.total_rejections += 1
                raise CircuitOpenError(
                    message=f"Circuit breaker half-open limit reached for {key}",
                    host=key,
                    retry_after=1.0  # Short retry for half-open limit
                )
    
    def add_state_change_listener(self, listener: StateChangeListener) -> None:
        """
        Add listener for state change events.
        
        The listener will be called whenever the circuit breaker
        transitions between states.
        
        Args:
            listener: Callable that receives StateChangeEvent
        
        **Validates: Requirements 3.4**
        """
        self._listeners.append(listener)
    
    def remove_state_change_listener(self, listener: StateChangeListener) -> None:
        """
        Remove a state change listener.
        
        Args:
            listener: The listener to remove
        """
        if listener in self._listeners:
            self._listeners.remove(listener)
    
    def reset(self, key: str) -> None:
        """
        Reset a circuit to closed state.
        
        This can be used for manual intervention or testing.
        
        Args:
            key: The circuit key to reset
        """
        if key in self._circuits:
            circuit = self._circuits[key]
            old_state = circuit.state
            if old_state != CircuitState.CLOSED:
                circuit.transition_to(CircuitState.CLOSED)
                self._notify_state_change(key, old_state, CircuitState.CLOSED, "manual_reset")
    
    def reset_all(self) -> None:
        """Reset all circuits to closed state."""
        for key in list(self._circuits.keys()):
            self.reset(key)
    
    # =========================================================================
    # LEGACY API METHODS (Backward Compatibility)
    # =========================================================================
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL for legacy API."""
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() if parsed.netloc else url
        except Exception:
            return url
    
    def is_open(self, url: str) -> bool:
        """
        Legacy API: Check if circuit is open (blocking requests).
        
        Note: This method has inverted semantics from the new API.
        Returns True if requests SHOULD be made (circuit is closed or half-open).
        Returns False if requests should NOT be made (circuit is open).
        
        Args:
            url: URL to check
        
        Returns:
            True if requests should be made, False if circuit is open
        """
        key = self._extract_domain(url) if self._legacy_mode else url
        circuit = self._get_or_create(key)
        
        if circuit.state == CircuitState.OPEN:
            # Check if timeout has passed
            if circuit.should_attempt_reset(self.config):
                old_state = circuit.state
                circuit.transition_to(CircuitState.HALF_OPEN)
                self._notify_state_change(key, old_state, CircuitState.HALF_OPEN, "timeout")
                return True  # Allow request in half-open
            return False  # Block request
        
        return True  # Allow request (closed or half-open)
    
    def can_execute(self, key: str | None = None) -> bool:
        """
        Legacy API: Check if circuit allows execution.
        
        Args:
            key: Optional circuit key (uses name if in legacy mode)
        
        Returns:
            True if requests can be made, False if circuit is open
        """
        circuit_key = key or self._name or "default"
        circuit = self._get_or_create(circuit_key)
        
        if circuit.state == CircuitState.OPEN:
            # Check if timeout has passed
            if circuit.should_attempt_reset(self.config):
                old_state = circuit.state
                circuit.transition_to(CircuitState.HALF_OPEN)
                self._notify_state_change(circuit_key, old_state, CircuitState.HALF_OPEN, "timeout")
                return True  # Allow request in half-open
            return False  # Block request
        
        return True  # Allow request (closed or half-open)
    
    # Legacy properties for test compatibility
    @property
    def _failure_count(self) -> int:
        """Legacy property: Get failure count for default circuit."""
        key = self._name or "default"
        if key in self._circuits:
            return self._circuits[key].failure_count
        return 0
    
    @_failure_count.setter
    def _failure_count(self, value: int) -> None:
        """Legacy property: Set failure count for default circuit."""
        key = self._name or "default"
        circuit = self._get_or_create(key)
        circuit.failure_count = value
    
    @property
    def _state(self) -> str:
        """Legacy property: Get state as string for default circuit."""
        key = self._name or "default"
        if key in self._circuits:
            return self._circuits[key].state.value
        return "closed"
    
    @_state.setter
    def _state(self, value: str) -> None:
        """Legacy property: Set state from string for default circuit."""
        key = self._name or "default"
        circuit = self._get_or_create(key)
        state_map = {
            "closed": CircuitState.CLOSED,
            "open": CircuitState.OPEN,
            "half_open": CircuitState.HALF_OPEN,
        }
        if value in state_map:
            circuit.state = state_map[value]
    
    @property
    def _last_failure_time(self) -> datetime | None:
        """Legacy property: Get last failure time for default circuit."""
        key = self._name or "default"
        if key in self._circuits:
            return self._circuits[key].last_failure_time
        return None
    
    @_last_failure_time.setter
    def _last_failure_time(self, value: datetime | None) -> None:
        """Legacy property: Set last failure time for default circuit."""
        key = self._name or "default"
        circuit = self._get_or_create(key)
        circuit.last_failure_time = value
