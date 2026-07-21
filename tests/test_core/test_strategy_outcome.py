from __future__ import annotations

import json

from primr.core.strategy_outcome import (
    StrategyOutcomeTracker,
    expected_strategy_targets,
    load_strategy_outcome,
    persist_strategy_outcome,
    strategy_outcome_from_state,
    strategy_target,
)


def test_expected_targets_expand_ai_vendors_and_keep_strategy_order():
    assert expected_strategy_targets(["ai", "customer_experience"], ("azure", "aws")) == (
        "ai:azure",
        "ai:aws",
        "customer_experience",
    )
    assert strategy_target("AI", "GCP") == "ai:gcp"


def test_tracker_reports_completed_partial_failed_and_not_requested():
    empty = StrategyOutcomeTracker(()).snapshot()
    assert empty.status == "not_requested"
    assert empty.requires_nonzero_exit is False

    tracker = StrategyOutcomeTracker(("ai:azure", "ai:aws"))
    tracker.mark_completed("ai:azure")
    partial = tracker.snapshot()
    assert partial.status == "partial"
    assert partial.completed_targets == ("ai:azure",)
    assert partial.failed_targets == ("ai:aws",)
    assert partial.requires_nonzero_exit is True

    tracker.mark_completed("ai:aws")
    complete = tracker.snapshot()
    assert complete.status == "completed"
    assert complete.failed_targets == ()

    failed = StrategyOutcomeTracker(("data_fabric_strategy",)).snapshot()
    assert failed.status == "failed"
    assert failed.failed_targets == ("data_fabric_strategy",)


def test_skipped_targets_remain_distinct_and_all_skipped_is_failed():
    tracker = StrategyOutcomeTracker(("ai:azure", "ai:aws"))
    tracker.mark_skipped("ai:azure")
    tracker.mark_remaining_skipped()

    outcome = tracker.snapshot()

    assert outcome.status == "failed"
    assert outcome.failed_targets == ()
    assert outcome.skipped_targets == ("ai:azure", "ai:aws")


def test_persist_and_load_round_trip(tmp_path):
    tracker = StrategyOutcomeTracker(("ai:azure", "ai:aws"))
    tracker.mark_completed("ai:azure")
    tracker.mark_failed("ai:aws")
    outcome = tracker.snapshot()

    persist_strategy_outcome(str(tmp_path), outcome)

    assert load_strategy_outcome(str(tmp_path)) == outcome
    assert load_strategy_outcome(str(tmp_path / "missing")) is None


def test_load_rejects_inconsistent_completed_state(tmp_path):
    (tmp_path / "_run_state.json").write_text(
        json.dumps(
            {
                "strategy_status": "completed",
                "strategy_expected_targets": ["ai:azure"],
                "strategy_completed_targets": [],
                "strategy_failed_targets": [],
                "strategy_skipped_targets": [],
            }
        ),
        encoding="utf-8",
    )

    assert load_strategy_outcome(str(tmp_path)) is None


def test_state_parser_rejects_missing_or_malformed_partitions():
    valid = {
        "strategy_status": "completed",
        "strategy_expected_targets": ["ai:azure"],
        "strategy_completed_targets": ["ai:azure"],
        "strategy_failed_targets": [],
        "strategy_skipped_targets": [],
    }

    assert strategy_outcome_from_state(valid) is not None
    assert strategy_outcome_from_state([]) is None
    for key in (
        "strategy_expected_targets",
        "strategy_completed_targets",
        "strategy_failed_targets",
        "strategy_skipped_targets",
    ):
        missing = dict(valid)
        missing.pop(key)
        assert strategy_outcome_from_state(missing) is None

        malformed = dict(valid)
        malformed[key] = [1]
        assert strategy_outcome_from_state(malformed) is None
