"""
Property-based tests for State Machine implementations.

This module contains property tests that verify universal correctness properties
of the StateMachine, TierStateMachine, and JobStateMachine implementations.

**Feature: phd-level-excellence**
**Validates: Requirements 9.1-9.6, 10.1-10.6**
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from primr.utils.state_machine import (
    InvalidTransitionError,
    JobState,
    JobStateMachine,
    StateChangeEvent,
    StateMachine,
    TierState,
    Transition,
    create_job_state_machine,
    create_tier_state_machine,
)

# =============================================================================
# STRATEGIES FOR GENERATING TEST DATA
# =============================================================================

# Strategy for generating job IDs
job_id_strategy = st.from_regex(r"job-[a-z0-9]{6,12}", fullmatch=True)

# Strategy for tier state triggers
tier_trigger_strategy = st.sampled_from(
    [
        "start_scrape",
        "scrape_success",
        "soft_block",
        "all_tiers_exhausted",
        "hard_block",
        "try_next_tier",
        "no_more_tiers",
        "reset",
    ]
)

# Strategy for job state triggers
job_trigger_strategy = st.sampled_from(["start", "cancel", "pause", "complete", "fail", "resume"])

# Strategy for invalid triggers
invalid_trigger_strategy = st.text(min_size=1, max_size=20).filter(
    lambda x: (
        x
        not in [
            "start_scrape",
            "scrape_success",
            "soft_block",
            "all_tiers_exhausted",
            "hard_block",
            "try_next_tier",
            "no_more_tiers",
            "reset",
            "start",
            "cancel",
            "pause",
            "complete",
            "fail",
            "resume",
        ]
    )
)


# =============================================================================
# PROPERTY 22: VALID TRANSITION ACCEPTANCE
# =============================================================================


class TestValidTransitionAcceptance:
    """
    **Property 22: Valid Transition Acceptance**

    For any state machine and any transition defined in its transition table,
    calling `transition()` with the correct trigger from the correct state
    SHALL succeed and update the state.

    **Validates: Requirements 9.2, 10.2**
    """

    def test_tier_idle_to_attempting(self):
        """IDLE -> ATTEMPTING via start_scrape should succeed."""
        # Feature: phd-level-excellence, Property 22: Valid Transition Acceptance
        sm = create_tier_state_machine()
        assert sm.state == TierState.IDLE

        event = sm.transition("start_scrape")

        assert sm.state == TierState.ATTEMPTING
        assert event.from_state == TierState.IDLE
        assert event.to_state == TierState.ATTEMPTING
        assert event.trigger == "start_scrape"

    def test_tier_attempting_to_succeeded(self):
        """ATTEMPTING -> SUCCEEDED via scrape_success should succeed."""
        # Feature: phd-level-excellence, Property 22: Valid Transition Acceptance
        sm = create_tier_state_machine()
        sm.transition("start_scrape")

        event = sm.transition("scrape_success")

        assert sm.state == TierState.SUCCEEDED
        assert event.from_state == TierState.ATTEMPTING
        assert event.to_state == TierState.SUCCEEDED

    def test_tier_attempting_to_escalating(self):
        """ATTEMPTING -> ESCALATING via soft_block should succeed."""
        # Feature: phd-level-excellence, Property 22: Valid Transition Acceptance
        sm = create_tier_state_machine()
        sm.transition("start_scrape")

        event = sm.transition("soft_block")

        assert sm.state == TierState.ESCALATING
        assert event.trigger == "soft_block"

    def test_tier_escalating_to_attempting(self):
        """ESCALATING -> ATTEMPTING via try_next_tier should succeed."""
        # Feature: phd-level-excellence, Property 22: Valid Transition Acceptance
        sm = create_tier_state_machine()
        sm.transition("start_scrape")
        sm.transition("soft_block")

        event = sm.transition("try_next_tier")

        assert sm.state == TierState.ATTEMPTING
        assert event.from_state == TierState.ESCALATING

    def test_job_pending_to_running(self):
        """PENDING -> RUNNING via start should succeed."""
        # Feature: phd-level-excellence, Property 22: Valid Transition Acceptance
        sm = create_job_state_machine("job-123")
        assert sm.state == JobState.PENDING

        event = sm.transition("start")

        assert sm.state == JobState.RUNNING
        assert event.from_state == JobState.PENDING
        assert event.to_state == JobState.RUNNING

    def test_job_running_to_completed(self):
        """RUNNING -> COMPLETED via complete should succeed."""
        # Feature: phd-level-excellence, Property 22: Valid Transition Acceptance
        sm = create_job_state_machine("job-123")
        sm.transition("start")

        sm.transition("complete")

        assert sm.state == JobState.COMPLETED
        assert sm.is_terminal

    def test_job_running_to_paused_to_running(self):
        """RUNNING -> PAUSED -> RUNNING should succeed."""
        # Feature: phd-level-excellence, Property 22: Valid Transition Acceptance
        sm = create_job_state_machine("job-123")
        sm.transition("start")
        sm.transition("pause")
        assert sm.state == JobState.PAUSED

        sm.transition("resume")
        assert sm.state == JobState.RUNNING

    @given(job_id=job_id_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_job_transitions_from_pending(self, job_id: str):
        """All valid transitions from PENDING should succeed."""
        # Feature: phd-level-excellence, Property 22: Valid Transition Acceptance
        create_job_state_machine(job_id)

        # Valid triggers from PENDING
        valid_triggers = ["start", "cancel"]

        for trigger in valid_triggers:
            sm_copy = create_job_state_machine(job_id)
            event = sm_copy.transition(trigger)
            assert event.from_state == JobState.PENDING

    @given(job_id=job_id_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_job_transitions_from_running(self, job_id: str):
        """All valid transitions from RUNNING should succeed."""
        # Feature: phd-level-excellence, Property 22: Valid Transition Acceptance

        # Valid triggers from RUNNING
        valid_triggers = ["pause", "complete", "fail", "cancel"]

        for trigger in valid_triggers:
            sm = create_job_state_machine(job_id)
            sm.transition("start")
            event = sm.transition(trigger)
            assert event.from_state == JobState.RUNNING


# =============================================================================
# PROPERTY 23: INVALID TRANSITION REJECTION
# =============================================================================


class TestInvalidTransitionRejection:
    """
    **Property 23: Invalid Transition Rejection**

    For any state machine and any (state, trigger) pair NOT in its transition
    table, calling `transition()` SHALL raise `InvalidTransitionError` with
    the attempted from_state and trigger.

    **Validates: Requirements 9.6**
    """

    def test_tier_idle_invalid_triggers(self):
        """Invalid triggers from IDLE should raise InvalidTransitionError."""
        # Feature: phd-level-excellence, Property 23: Invalid Transition Rejection
        sm = create_tier_state_machine()

        invalid_triggers = ["scrape_success", "soft_block", "try_next_tier", "reset"]

        for trigger in invalid_triggers:
            with pytest.raises(InvalidTransitionError) as exc_info:
                sm.transition(trigger)

            assert exc_info.value.from_state == TierState.IDLE
            assert exc_info.value.trigger == trigger

    def test_tier_succeeded_invalid_triggers(self):
        """Invalid triggers from SUCCEEDED should raise InvalidTransitionError."""
        # Feature: phd-level-excellence, Property 23: Invalid Transition Rejection
        sm = create_tier_state_machine()
        sm.transition("start_scrape")
        sm.transition("scrape_success")

        invalid_triggers = ["start_scrape", "soft_block", "try_next_tier"]

        for trigger in invalid_triggers:
            with pytest.raises(InvalidTransitionError) as exc_info:
                sm.transition(trigger)

            assert exc_info.value.from_state == TierState.SUCCEEDED

    def test_job_pending_invalid_triggers(self):
        """Invalid triggers from PENDING should raise InvalidTransitionError."""
        # Feature: phd-level-excellence, Property 23: Invalid Transition Rejection
        sm = create_job_state_machine("job-123")

        invalid_triggers = ["pause", "complete", "fail", "resume"]

        for trigger in invalid_triggers:
            with pytest.raises(InvalidTransitionError) as exc_info:
                sm.transition(trigger)

            assert exc_info.value.from_state == JobState.PENDING
            assert exc_info.value.trigger == trigger

    def test_job_completed_no_transitions(self):
        """No transitions should be valid from COMPLETED (terminal state)."""
        # Feature: phd-level-excellence, Property 23: Invalid Transition Rejection
        sm = create_job_state_machine("job-123")
        sm.transition("start")
        sm.transition("complete")

        all_triggers = ["start", "cancel", "pause", "complete", "fail", "resume"]

        for trigger in all_triggers:
            with pytest.raises(InvalidTransitionError):
                sm.transition(trigger)

    @given(invalid_trigger=invalid_trigger_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_completely_invalid_triggers_rejected(self, invalid_trigger: str):
        """Completely invalid triggers should be rejected."""
        # Feature: phd-level-excellence, Property 23: Invalid Transition Rejection
        sm = create_tier_state_machine()

        with pytest.raises(InvalidTransitionError) as exc_info:
            sm.transition(invalid_trigger)

        assert exc_info.value.trigger == invalid_trigger

    def test_error_contains_from_state(self):
        """InvalidTransitionError should contain the from_state."""
        # Feature: phd-level-excellence, Property 23: Invalid Transition Rejection
        sm = create_job_state_machine("job-123")

        with pytest.raises(InvalidTransitionError) as exc_info:
            sm.transition("complete")

        error = exc_info.value
        assert error.from_state == JobState.PENDING
        assert "PENDING" in str(error).upper() or "pending" in str(error)


# =============================================================================
# PROPERTY 24: TRANSITION EVENT EMISSION
# =============================================================================


class TestTransitionEventEmission:
    """
    **Property 24: Transition Event Emission**

    For any successful state transition, all registered listeners SHALL receive
    a `StateChangeEvent` with correct `from_state`, `to_state`, `trigger`, and
    `timestamp` values.

    **Validates: Requirements 9.5, 10.5**
    """

    def test_listener_receives_event(self):
        """Registered listener should receive state change event."""
        # Feature: phd-level-excellence, Property 24: Transition Event Emission
        events_received = []

        def listener(event: StateChangeEvent):
            events_received.append(event)

        sm = create_tier_state_machine()
        sm.add_listener(listener)

        sm.transition("start_scrape")

        assert len(events_received) == 1
        event = events_received[0]
        assert event.from_state == TierState.IDLE
        assert event.to_state == TierState.ATTEMPTING
        assert event.trigger == "start_scrape"

    def test_multiple_listeners_all_receive_event(self):
        """All registered listeners should receive the event."""
        # Feature: phd-level-excellence, Property 24: Transition Event Emission
        events_1 = []
        events_2 = []
        events_3 = []

        sm = create_job_state_machine("job-123")
        sm.add_listener(lambda e: events_1.append(e))
        sm.add_listener(lambda e: events_2.append(e))
        sm.add_listener(lambda e: events_3.append(e))

        sm.transition("start")

        assert len(events_1) == 1
        assert len(events_2) == 1
        assert len(events_3) == 1

        # All should have same event data
        assert events_1[0].trigger == events_2[0].trigger == events_3[0].trigger

    def test_event_has_timestamp(self):
        """Event should have a timestamp."""
        # Feature: phd-level-excellence, Property 24: Transition Event Emission
        events = []

        sm = create_tier_state_machine()
        sm.add_listener(lambda e: events.append(e))

        sm.transition("start_scrape")

        assert events[0].timestamp is not None

    @given(job_id=job_id_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_event_sequence_matches_transitions(self, job_id: str):
        """Event sequence should match transition sequence."""
        # Feature: phd-level-excellence, Property 24: Transition Event Emission
        events = []

        sm = create_job_state_machine(job_id)
        sm.add_listener(lambda e: events.append(e))

        # Perform sequence of transitions
        sm.transition("start")
        sm.transition("pause")
        sm.transition("resume")
        sm.transition("complete")

        assert len(events) == 4

        # Verify sequence
        assert events[0].trigger == "start"
        assert events[1].trigger == "pause"
        assert events[2].trigger == "resume"
        assert events[3].trigger == "complete"

        # Verify state chain
        assert events[0].to_state == events[1].from_state
        assert events[1].to_state == events[2].from_state
        assert events[2].to_state == events[3].from_state

    def test_remove_listener_stops_events(self):
        """Removed listener should not receive events."""
        # Feature: phd-level-excellence, Property 24: Transition Event Emission
        events = []

        def listener(event):
            events.append(event)

        sm = create_tier_state_machine()
        sm.add_listener(listener)

        sm.transition("start_scrape")
        assert len(events) == 1

        sm.remove_listener(listener)
        sm.transition("scrape_success")

        # Should still be 1 (no new event)
        assert len(events) == 1

    def test_event_context_is_passed(self):
        """Context passed to transition should be in event."""
        # Feature: phd-level-excellence, Property 24: Transition Event Emission
        events = []

        sm = create_tier_state_machine()
        sm.add_listener(lambda e: events.append(e))

        sm.transition("start_scrape", url="https://example.com", tier=1)

        assert events[0].context["url"] == "https://example.com"
        assert events[0].context["tier"] == 1


# =============================================================================
# PROPERTY 25: STATE PERSISTENCE ROUND-TRIP
# =============================================================================


class TestStatePersistenceRoundTrip:
    """
    **Property 25: State Persistence Round-Trip**

    For any job state machine state, persisting the state and then recovering
    it SHALL produce a state machine in the same state with the same transition
    history.

    **Validates: Requirements 10.6**
    """

    @given(job_id=job_id_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_pending_state_round_trip(self, job_id: str):
        """PENDING state should survive round-trip."""
        # Feature: phd-level-excellence, Property 25: State Persistence Round-Trip
        sm = create_job_state_machine(job_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "job.json"
            sm.save(path)

            recovered = JobStateMachine.load(path)

            assert recovered.job_id == job_id
            assert recovered.state == JobState.PENDING
            assert len(recovered.history) == 0

    @given(job_id=job_id_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_running_state_round_trip(self, job_id: str):
        """RUNNING state should survive round-trip."""
        # Feature: phd-level-excellence, Property 25: State Persistence Round-Trip
        sm = create_job_state_machine(job_id)
        sm.transition("start")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "job.json"
            sm.save(path)

            recovered = JobStateMachine.load(path)

            assert recovered.job_id == job_id
            assert recovered.state == JobState.RUNNING
            assert len(recovered.history) == 1
            assert recovered.history[0].trigger == "start"

    @given(job_id=job_id_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_completed_state_round_trip(self, job_id: str):
        """COMPLETED state should survive round-trip."""
        # Feature: phd-level-excellence, Property 25: State Persistence Round-Trip
        sm = create_job_state_machine(job_id)
        sm.transition("start")
        sm.transition("complete")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "job.json"
            sm.save(path)

            recovered = JobStateMachine.load(path)

            assert recovered.state == JobState.COMPLETED
            assert recovered.is_terminal
            assert len(recovered.history) == 2

    @given(job_id=job_id_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_history_preserved_on_round_trip(self, job_id: str):
        """Full transition history should be preserved."""
        # Feature: phd-level-excellence, Property 25: State Persistence Round-Trip
        sm = create_job_state_machine(job_id)
        sm.transition("start")
        sm.transition("pause")
        sm.transition("resume")
        sm.transition("fail")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "job.json"
            sm.save(path)

            recovered = JobStateMachine.load(path)

            assert len(recovered.history) == 4
            assert recovered.history[0].trigger == "start"
            assert recovered.history[1].trigger == "pause"
            assert recovered.history[2].trigger == "resume"
            assert recovered.history[3].trigger == "fail"

    def test_to_dict_from_dict_round_trip(self):
        """to_dict/from_dict should be inverse operations."""
        # Feature: phd-level-excellence, Property 25: State Persistence Round-Trip
        sm = create_job_state_machine("job-abc123")
        sm.transition("start")
        sm.transition("pause")

        data = sm.to_dict()
        recovered = JobStateMachine.from_dict(data)

        assert recovered.job_id == sm.job_id
        assert recovered.state == sm.state
        assert len(recovered.history) == len(sm.history)

    @given(job_id=job_id_strategy)
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_multiple_save_load_cycles(self, job_id: str):
        """Multiple save/load cycles should be idempotent."""
        # Feature: phd-level-excellence, Property 25: State Persistence Round-Trip
        sm = create_job_state_machine(job_id)
        sm.transition("start")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "job.json"

            # Save and load multiple times
            for _ in range(3):
                sm.save(path)
                sm = JobStateMachine.load(path)

            assert sm.job_id == job_id
            assert sm.state == JobState.RUNNING


# =============================================================================
# ADDITIONAL STATE MACHINE TESTS
# =============================================================================


class TestStateMachineHelpers:
    """Tests for state machine helper methods."""

    def test_can_transition_returns_true_for_valid(self):
        """can_transition should return True for valid transitions."""
        sm = create_tier_state_machine()

        assert sm.can_transition("start_scrape")
        assert not sm.can_transition("scrape_success")

    def test_get_available_triggers(self):
        """get_available_triggers should return valid triggers."""
        sm = create_tier_state_machine()

        triggers = sm.get_available_triggers()
        assert "start_scrape" in triggers
        assert "scrape_success" not in triggers

    def test_history_tracking(self):
        """History should track all transitions."""
        sm = create_tier_state_machine()

        sm.transition("start_scrape")
        sm.transition("scrape_success")
        sm.transition("reset")

        assert len(sm.history) == 3
        assert sm.history[0].trigger == "start_scrape"
        assert sm.history[1].trigger == "scrape_success"
        assert sm.history[2].trigger == "reset"

    def test_reset_clears_history(self):
        """reset() should clear history."""
        sm = create_tier_state_machine()
        sm.transition("start_scrape")

        sm.reset(TierState.IDLE)

        assert sm.state == TierState.IDLE
        assert len(sm.history) == 0

    def test_job_is_terminal_property(self):
        """is_terminal should correctly identify terminal states."""
        sm = create_job_state_machine("job-123")

        assert not sm.is_terminal

        sm.transition("start")
        assert not sm.is_terminal

        sm.transition("complete")
        assert sm.is_terminal

    def test_job_is_active_property(self):
        """is_active should correctly identify running state."""
        sm = create_job_state_machine("job-123")

        assert not sm.is_active

        sm.transition("start")
        assert sm.is_active

        sm.transition("pause")
        assert not sm.is_active


class TestGuardFunctions:
    """Tests for transition guard functions."""

    def test_guard_prevents_transition(self):
        """Guard returning False should prevent transition."""
        from enum import Enum

        class TestState(Enum):
            A = "a"
            B = "b"

        def guard_requires_value(**context):
            return context.get("value", 0) > 10

        transitions = [
            Transition(TestState.A, TestState.B, "go", guard=guard_requires_value),
        ]

        sm = StateMachine(TestState.A, transitions)

        # Should fail without sufficient value
        with pytest.raises(InvalidTransitionError):
            sm.transition("go", value=5)

        # Should succeed with sufficient value
        sm.transition("go", value=15)
        assert sm.state == TestState.B

    def test_guard_receives_context(self):
        """Guard should receive context kwargs."""
        from enum import Enum

        class TestState(Enum):
            A = "a"
            B = "b"

        received_context = {}

        def capture_guard(**context):
            received_context.update(context)
            return True

        transitions = [
            Transition(TestState.A, TestState.B, "go", guard=capture_guard),
        ]

        sm = StateMachine(TestState.A, transitions)
        sm.transition("go", foo="bar", num=42)

        assert received_context["foo"] == "bar"
        assert received_context["num"] == 42
