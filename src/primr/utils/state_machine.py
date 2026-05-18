"""
State Machine Specifications for Primr.

This module provides formal state machine implementations for tier escalation
and job lifecycle management, with transition validation and event emission.

**Feature: phd-level-excellence**
**Validates: Requirements 9.1-9.6, 10.1-10.6**

Components:
- StateMachine: Generic state machine with transition validation
- TierState: States for scraping tier escalation
- TierStateMachine: State machine for tier escalation
- JobState: States for job lifecycle
- JobStateMachine: State machine for job lifecycle with persistence
- InvalidTransitionError: Exception for invalid state transitions
- StateChangeEvent: Event emitted on state transitions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# =============================================================================
# EXCEPTIONS
# =============================================================================


class InvalidTransitionError(Exception):
    """
    Raised when an invalid state transition is attempted.

    Attributes:
        from_state: The current state
        to_state: The attempted target state (may be None if unknown)
        trigger: The trigger that caused the invalid transition
    """

    def __init__(
        self,
        from_state: Enum,
        to_state: Enum | None,
        trigger: str,
        message: str | None = None,
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.trigger = trigger

        if message is None:
            if to_state:
                message = (
                    f"Invalid transition: {from_state.value} -> {to_state.value} via '{trigger}'"
                )
            else:
                message = f"No transition defined from {from_state.value} via '{trigger}'"

        super().__init__(message)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class Transition:
    """
    Definition of a state transition.

    Attributes:
        from_state: Source state
        to_state: Target state
        trigger: Event that triggers this transition
        guard: Optional function that must return True for transition to proceed
    """

    from_state: Enum
    to_state: Enum
    trigger: str
    guard: Callable[..., bool] | None = None


@dataclass
class StateChangeEvent:
    """
    Event emitted when a state transition occurs.

    Attributes:
        from_state: Previous state
        to_state: New state
        trigger: Event that caused the transition
        timestamp: When the transition occurred
        context: Additional context data
    """

    from_state: Enum
    to_state: Enum
    trigger: str
    timestamp: datetime = field(default_factory=datetime.now)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "trigger": self.trigger,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
        }


# =============================================================================
# GENERIC STATE MACHINE
# =============================================================================


class StateMachine:
    """
    Generic state machine with transition validation and event emission.

    Supports:
    - Defined transitions with optional guards
    - State invariant assertions
    - Event listeners for state changes
    - Transition history tracking

    Example:
        transitions = [
            Transition(State.A, State.B, "go"),
            Transition(State.B, State.C, "finish"),
        ]

        sm = StateMachine(State.A, transitions)
        sm.transition("go")  # Now in State.B
        sm.transition("finish")  # Now in State.C
    """

    def __init__(
        self,
        initial_state: Enum,
        transitions: list[Transition],
        invariants: dict[Enum, Callable[..., bool]] | None = None,
    ):
        """
        Initialize the state machine.

        Args:
            initial_state: Starting state
            transitions: List of valid transitions
            invariants: Optional dict mapping states to invariant functions
        """
        self._state = initial_state
        self._transitions: dict[tuple[Enum, str], Transition] = {
            (t.from_state, t.trigger): t for t in transitions
        }
        self._invariants = invariants or {}
        self._listeners: list[Callable[[StateChangeEvent], None]] = []
        self._history: list[StateChangeEvent] = []

    @property
    def state(self) -> Enum:
        """Get current state."""
        return self._state

    @property
    def history(self) -> list[StateChangeEvent]:
        """Get transition history."""
        return self._history.copy()

    def can_transition(self, trigger: str, **context: Any) -> bool:
        """
        Check if a transition is valid from the current state.

        Args:
            trigger: The trigger event
            **context: Context passed to guard function

        Returns:
            True if transition is valid, False otherwise
        """
        key = (self._state, trigger)
        if key not in self._transitions:
            return False

        transition = self._transitions[key]
        return not (transition.guard and not transition.guard(**context))

    def get_available_triggers(self) -> list[str]:
        """Get list of valid triggers from current state."""
        return [trigger for (state, trigger) in self._transitions if state == self._state]

    def transition(self, trigger: str, **context: Any) -> StateChangeEvent:
        """
        Execute a state transition.

        Args:
            trigger: The trigger event
            **context: Context passed to guard and invariant functions

        Returns:
            StateChangeEvent describing the transition

        Raises:
            InvalidTransitionError: If transition is not valid
        """
        key = (self._state, trigger)

        if key not in self._transitions:
            raise InvalidTransitionError(self._state, None, trigger)

        transition = self._transitions[key]

        # Check guard
        if transition.guard and not transition.guard(**context):
            raise InvalidTransitionError(
                self._state,
                transition.to_state,
                trigger,
                f"Guard failed for transition {self._state.value} -> {transition.to_state.value}",
            )

        old_state = self._state
        new_state = transition.to_state

        # Check invariant for new state
        if new_state in self._invariants and not self._invariants[new_state](**context):
            raise InvalidTransitionError(
                old_state,
                new_state,
                trigger,
                f"Invariant failed for state {new_state.value}",
            )

        # Perform transition
        self._state = new_state

        # Create and record event
        event = StateChangeEvent(
            from_state=old_state,
            to_state=new_state,
            trigger=trigger,
            context=context,
        )
        self._history.append(event)

        # Notify listeners
        for listener in self._listeners:
            listener(event)

        return event

    def add_listener(self, listener: Callable[[StateChangeEvent], None]) -> None:
        """Add a listener for state change events."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[StateChangeEvent], None]) -> None:
        """Remove a state change listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def reset(self, initial_state: Enum | None = None) -> None:
        """
        Reset the state machine.

        Args:
            initial_state: State to reset to (uses original if not provided)
        """
        if initial_state is not None:
            self._state = initial_state
        self._history.clear()


# =============================================================================
# TIER ESCALATION STATE MACHINE
# =============================================================================


class TierState(Enum):
    """
    States for scraping tier escalation.

    State Diagram:
    ```
    IDLE --> ATTEMPTING --> SUCCEEDED --> IDLE
              |    ^
              v    |
         ESCALATING
              |
              v
           FAILED --> IDLE
              |
              v
          BLOCKED --> IDLE
    ```
    """

    IDLE = "idle"
    ATTEMPTING = "attempting"
    ESCALATING = "escalating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


# Tier escalation transitions
TIER_TRANSITIONS = [
    Transition(TierState.IDLE, TierState.ATTEMPTING, "start_scrape"),
    Transition(TierState.ATTEMPTING, TierState.SUCCEEDED, "scrape_success"),
    Transition(TierState.ATTEMPTING, TierState.ESCALATING, "soft_block"),
    Transition(TierState.ATTEMPTING, TierState.FAILED, "all_tiers_exhausted"),
    Transition(TierState.ATTEMPTING, TierState.BLOCKED, "hard_block"),
    Transition(TierState.ESCALATING, TierState.ATTEMPTING, "try_next_tier"),
    Transition(TierState.ESCALATING, TierState.FAILED, "no_more_tiers"),
    Transition(TierState.SUCCEEDED, TierState.IDLE, "reset"),
    Transition(TierState.FAILED, TierState.IDLE, "reset"),
    Transition(TierState.BLOCKED, TierState.IDLE, "reset"),
]


def create_tier_state_machine() -> StateMachine:
    """
    Create a state machine for tier escalation.

    Returns:
        StateMachine configured for tier escalation
    """
    return StateMachine(TierState.IDLE, TIER_TRANSITIONS)


# =============================================================================
# JOB LIFECYCLE STATE MACHINE
# =============================================================================


class JobState(Enum):
    """
    States for job lifecycle.

    State Diagram:
    ```
    PENDING --> RUNNING --> COMPLETED
        |          |
        |          +--> PAUSED --> RUNNING
        |          |       |
        |          +--> FAILED
        |          |
        |          +--> CANCELLED
        |
        +--> CANCELLED
    ```
    """

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Job lifecycle transitions
JOB_TRANSITIONS = [
    Transition(JobState.PENDING, JobState.RUNNING, "start"),
    Transition(JobState.PENDING, JobState.CANCELLED, "cancel"),
    Transition(JobState.RUNNING, JobState.PAUSED, "pause"),
    Transition(JobState.RUNNING, JobState.COMPLETED, "complete"),
    Transition(JobState.RUNNING, JobState.FAILED, "fail"),
    Transition(JobState.RUNNING, JobState.CANCELLED, "cancel"),
    Transition(JobState.PAUSED, JobState.RUNNING, "resume"),
    Transition(JobState.PAUSED, JobState.CANCELLED, "cancel"),
]


class JobStateMachine(StateMachine):
    """
    State machine for job lifecycle with persistence support.

    Extends StateMachine with:
    - Job ID tracking
    - State persistence to file
    - State recovery from file

    Example:
        sm = JobStateMachine("job-123")
        sm.transition("start")
        sm.save("jobs/job-123.json")

        # Later...
        sm2 = JobStateMachine.load("jobs/job-123.json")
        assert sm2.state == JobState.RUNNING
    """

    def __init__(
        self,
        job_id: str,
        initial_state: JobState = JobState.PENDING,
        transitions: list[Transition] | None = None,
    ):
        """
        Initialize job state machine.

        Args:
            job_id: Unique identifier for the job
            initial_state: Starting state (default: PENDING)
            transitions: Custom transitions (default: JOB_TRANSITIONS)
        """
        super().__init__(
            initial_state,
            transitions or JOB_TRANSITIONS,
        )
        self.job_id = job_id
        self._created_at = datetime.now()

    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self._state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED)

    @property
    def is_active(self) -> bool:
        """Check if job is actively running."""
        return self._state == JobState.RUNNING

    def to_dict(self) -> dict[str, Any]:
        """Serialize state machine to dictionary."""
        return {
            "job_id": self.job_id,
            "state": self._state.value,
            "created_at": self._created_at.isoformat(),
            "history": [event.to_dict() for event in self._history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobStateMachine:
        """
        Deserialize state machine from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored JobStateMachine
        """
        sm = cls(data["job_id"], JobState(data["state"]))
        sm._created_at = datetime.fromisoformat(data["created_at"])

        # Restore history
        for event_data in data.get("history", []):
            event = StateChangeEvent(
                from_state=JobState(event_data["from_state"]),
                to_state=JobState(event_data["to_state"]),
                trigger=event_data["trigger"],
                timestamp=datetime.fromisoformat(event_data["timestamp"]),
                context=event_data.get("context", {}),
            )
            sm._history.append(event)

        return sm

    def save(self, path: Path | str) -> None:
        """
        Save state machine to file.

        Args:
            path: File path to save to
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path | str) -> JobStateMachine:
        """
        Load state machine from file.

        Args:
            path: File path to load from

        Returns:
            Restored JobStateMachine
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


def create_job_state_machine(job_id: str) -> JobStateMachine:
    """
    Create a state machine for job lifecycle.

    Args:
        job_id: Unique identifier for the job

    Returns:
        JobStateMachine configured for job lifecycle
    """
    return JobStateMachine(job_id)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "JOB_TRANSITIONS",
    "TIER_TRANSITIONS",
    # Exceptions
    "InvalidTransitionError",
    # Job lifecycle
    "JobState",
    "JobStateMachine",
    "StateChangeEvent",
    # Generic state machine
    "StateMachine",
    # Tier escalation
    "TierState",
    # Data classes
    "Transition",
    "create_job_state_machine",
    "create_tier_state_machine",
]
