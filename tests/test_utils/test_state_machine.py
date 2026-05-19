"""Tests for primr.utils.state_machine.

Covers the generic StateMachine, the tier-escalation specialization,
and the JobStateMachine with persistence. Adds coverage to a previously
0%-covered module that's actively imported by agentic/integration.py.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from primr.utils.state_machine import (
    JOB_TRANSITIONS,
    TIER_TRANSITIONS,
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


class DemoState(Enum):
    A = "a"
    B = "b"
    C = "c"


# ---------------------------------------------------------------------------
# InvalidTransitionError
# ---------------------------------------------------------------------------


class TestInvalidTransitionError:
    def test_message_with_target_state(self):
        err = InvalidTransitionError(DemoState.A, DemoState.B, "trigger_x")
        assert "a" in str(err)
        assert "b" in str(err)
        assert "trigger_x" in str(err)
        assert err.from_state is DemoState.A
        assert err.to_state is DemoState.B
        assert err.trigger == "trigger_x"

    def test_message_without_target_state(self):
        err = InvalidTransitionError(DemoState.A, None, "trigger_x")
        assert "a" in str(err)
        assert "trigger_x" in str(err)

    def test_custom_message_used(self):
        err = InvalidTransitionError(
            DemoState.A, DemoState.B, "trigger", message="custom failure text"
        )
        assert str(err) == "custom failure text"


# ---------------------------------------------------------------------------
# Transition + StateChangeEvent dataclasses
# ---------------------------------------------------------------------------


class TestStateChangeEvent:
    def test_to_dict_round_trip_fields(self):
        evt = StateChangeEvent(
            from_state=DemoState.A,
            to_state=DemoState.B,
            trigger="go",
            context={"foo": "bar"},
        )
        d = evt.to_dict()
        assert d["from_state"] == "a"
        assert d["to_state"] == "b"
        assert d["trigger"] == "go"
        assert d["context"] == {"foo": "bar"}
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# Generic StateMachine
# ---------------------------------------------------------------------------


@pytest.fixture
def demo_machine() -> StateMachine:
    transitions = [
        Transition(DemoState.A, DemoState.B, "go"),
        Transition(DemoState.B, DemoState.C, "finish"),
        Transition(DemoState.C, DemoState.A, "reset"),
    ]
    return StateMachine(DemoState.A, transitions)


class TestStateMachineHappyPath:
    def test_initial_state(self, demo_machine):
        assert demo_machine.state is DemoState.A

    def test_basic_transition(self, demo_machine):
        evt = demo_machine.transition("go")
        assert demo_machine.state is DemoState.B
        assert evt.from_state is DemoState.A
        assert evt.to_state is DemoState.B

    def test_chained_transitions(self, demo_machine):
        demo_machine.transition("go")
        demo_machine.transition("finish")
        demo_machine.transition("reset")
        assert demo_machine.state is DemoState.A

    def test_history_records_each_transition(self, demo_machine):
        demo_machine.transition("go")
        demo_machine.transition("finish")
        history = demo_machine.history
        assert len(history) == 2
        # history returned should be a copy
        history.clear()
        assert len(demo_machine.history) == 2

    def test_can_transition(self, demo_machine):
        assert demo_machine.can_transition("go") is True
        assert demo_machine.can_transition("nonexistent") is False

    def test_get_available_triggers(self, demo_machine):
        assert demo_machine.get_available_triggers() == ["go"]
        demo_machine.transition("go")
        assert demo_machine.get_available_triggers() == ["finish"]


class TestStateMachineErrors:
    def test_unknown_trigger_raises(self, demo_machine):
        with pytest.raises(InvalidTransitionError):
            demo_machine.transition("bogus")

    def test_trigger_invalid_from_current_state(self, demo_machine):
        # "finish" is valid from B, not from A
        with pytest.raises(InvalidTransitionError):
            demo_machine.transition("finish")


class TestStateMachineGuards:
    def test_guard_allows_transition_when_true(self):
        transitions = [Transition(DemoState.A, DemoState.B, "go", guard=lambda **kw: True)]
        sm = StateMachine(DemoState.A, transitions)
        sm.transition("go")
        assert sm.state is DemoState.B

    def test_guard_blocks_when_false(self):
        transitions = [Transition(DemoState.A, DemoState.B, "go", guard=lambda **kw: False)]
        sm = StateMachine(DemoState.A, transitions)
        with pytest.raises(InvalidTransitionError, match="Guard"):
            sm.transition("go")
        assert sm.state is DemoState.A

    def test_guard_can_use_context(self):
        transitions = [
            Transition(DemoState.A, DemoState.B, "go", guard=lambda value=0, **kw: value > 5)
        ]
        sm = StateMachine(DemoState.A, transitions)
        with pytest.raises(InvalidTransitionError):
            sm.transition("go", value=3)
        sm.transition("go", value=10)
        assert sm.state is DemoState.B

    def test_can_transition_reflects_guard(self):
        transitions = [Transition(DemoState.A, DemoState.B, "go", guard=lambda **kw: False)]
        sm = StateMachine(DemoState.A, transitions)
        assert sm.can_transition("go") is False


class TestStateMachineInvariants:
    def test_invariant_failure_blocks(self):
        transitions = [Transition(DemoState.A, DemoState.B, "go")]
        invariants = {DemoState.B: lambda **kw: False}
        sm = StateMachine(DemoState.A, transitions, invariants=invariants)
        with pytest.raises(InvalidTransitionError, match="Invariant"):
            sm.transition("go")

    def test_invariant_passes(self):
        transitions = [Transition(DemoState.A, DemoState.B, "go")]
        invariants = {DemoState.B: lambda **kw: True}
        sm = StateMachine(DemoState.A, transitions, invariants=invariants)
        sm.transition("go")
        assert sm.state is DemoState.B


class TestStateMachineListeners:
    def test_listener_invoked_on_transition(self, demo_machine):
        events: list[StateChangeEvent] = []
        demo_machine.add_listener(events.append)
        demo_machine.transition("go")
        assert len(events) == 1
        assert events[0].from_state is DemoState.A

    def test_remove_listener(self, demo_machine):
        events: list[StateChangeEvent] = []
        demo_machine.add_listener(events.append)
        demo_machine.remove_listener(events.append)
        demo_machine.transition("go")
        assert events == []

    def test_remove_listener_not_registered_is_noop(self, demo_machine):
        # Should not raise.
        demo_machine.remove_listener(lambda evt: None)


class TestStateMachineReset:
    def test_reset_clears_history(self, demo_machine):
        demo_machine.transition("go")
        demo_machine.reset()
        assert demo_machine.history == []

    def test_reset_to_specific_state(self, demo_machine):
        demo_machine.transition("go")
        demo_machine.reset(DemoState.C)
        assert demo_machine.state is DemoState.C

    def test_reset_default_keeps_current_state(self, demo_machine):
        demo_machine.transition("go")
        demo_machine.reset()
        # Default reset doesn't change state, just clears history
        assert demo_machine.state is DemoState.B


# ---------------------------------------------------------------------------
# Tier escalation specialization
# ---------------------------------------------------------------------------


class TestTierStateMachine:
    def test_factory_yields_idle_state(self):
        sm = create_tier_state_machine()
        assert sm.state is TierState.IDLE

    def test_full_tier_escalation_sequence(self):
        sm = create_tier_state_machine()
        sm.transition("start_scrape")
        assert sm.state is TierState.ATTEMPTING
        sm.transition("soft_block")
        assert sm.state is TierState.ESCALATING
        sm.transition("try_next_tier")
        assert sm.state is TierState.ATTEMPTING
        sm.transition("scrape_success")
        assert sm.state is TierState.SUCCEEDED
        sm.transition("reset")
        assert sm.state is TierState.IDLE

    def test_failure_path_to_idle(self):
        sm = create_tier_state_machine()
        sm.transition("start_scrape")
        sm.transition("all_tiers_exhausted")
        assert sm.state is TierState.FAILED
        sm.transition("reset")
        assert sm.state is TierState.IDLE

    def test_hard_block_path(self):
        sm = create_tier_state_machine()
        sm.transition("start_scrape")
        sm.transition("hard_block")
        assert sm.state is TierState.BLOCKED

    def test_tier_transitions_module_constant_populated(self):
        assert len(TIER_TRANSITIONS) > 0


# ---------------------------------------------------------------------------
# JobStateMachine
# ---------------------------------------------------------------------------


class TestJobStateMachine:
    def test_default_starts_pending(self):
        sm = create_job_state_machine("job-1")
        assert sm.state is JobState.PENDING
        assert sm.job_id == "job-1"

    def test_is_terminal_for_completed(self):
        sm = JobStateMachine("job-1")
        sm.transition("start")
        sm.transition("complete")
        assert sm.is_terminal is True

    def test_is_terminal_for_failed(self):
        sm = JobStateMachine("job-1")
        sm.transition("start")
        sm.transition("fail")
        assert sm.is_terminal is True

    def test_is_terminal_for_cancelled(self):
        sm = JobStateMachine("job-1")
        sm.transition("cancel")
        assert sm.is_terminal is True

    def test_is_active_only_when_running(self):
        sm = JobStateMachine("job-1")
        assert sm.is_active is False
        sm.transition("start")
        assert sm.is_active is True
        sm.transition("pause")
        assert sm.is_active is False

    def test_pause_resume_cycle(self):
        sm = JobStateMachine("job-1")
        sm.transition("start")
        sm.transition("pause")
        assert sm.state is JobState.PAUSED
        sm.transition("resume")
        assert sm.state is JobState.RUNNING

    def test_cancel_from_paused(self):
        sm = JobStateMachine("job-1")
        sm.transition("start")
        sm.transition("pause")
        sm.transition("cancel")
        assert sm.state is JobState.CANCELLED

    def test_custom_initial_state(self):
        sm = JobStateMachine("job-1", initial_state=JobState.RUNNING)
        assert sm.state is JobState.RUNNING

    def test_job_transitions_module_constant_populated(self):
        assert len(JOB_TRANSITIONS) > 0


class TestJobStateMachineSerialization:
    def test_to_dict_includes_fields(self):
        sm = JobStateMachine("job-99")
        sm.transition("start")
        d = sm.to_dict()
        assert d["job_id"] == "job-99"
        assert d["state"] == "running"
        assert "created_at" in d
        assert isinstance(d["history"], list)
        assert len(d["history"]) == 1

    def test_from_dict_round_trip(self):
        sm = JobStateMachine("job-77")
        sm.transition("start")
        sm.transition("complete")
        restored = JobStateMachine.from_dict(sm.to_dict())
        assert restored.job_id == "job-77"
        assert restored.state is JobState.COMPLETED
        assert len(restored.history) == 2

    def test_save_load_round_trip(self, tmp_path: Path):
        sm = JobStateMachine("job-disk")
        sm.transition("start")
        path = tmp_path / "nested" / "job.json"
        sm.save(path)
        assert path.exists()
        loaded = JobStateMachine.load(path)
        assert loaded.job_id == "job-disk"
        assert loaded.state is JobState.RUNNING

    def test_save_creates_parent_directories(self, tmp_path: Path):
        sm = JobStateMachine("job-x")
        deep = tmp_path / "a" / "b" / "c" / "job.json"
        sm.save(deep)
        assert deep.parent.is_dir()

    def test_save_is_valid_json(self, tmp_path: Path):
        sm = JobStateMachine("job-x")
        sm.transition("start")
        path = tmp_path / "job.json"
        sm.save(path)
        with path.open() as f:
            data = json.load(f)
        assert data["job_id"] == "job-x"

    def test_save_accepts_string_path(self, tmp_path: Path):
        sm = JobStateMachine("job-x")
        path = str(tmp_path / "job.json")
        sm.save(path)
        loaded = JobStateMachine.load(path)
        assert loaded.job_id == "job-x"
