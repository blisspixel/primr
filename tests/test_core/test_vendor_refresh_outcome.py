from __future__ import annotations

import json

from primr.core.vendor_refresh_outcome import (
    VendorRefreshTracker,
    load_vendor_refresh_outcome,
    persist_vendor_refresh_outcome,
    vendor_refresh_outcome_from_state,
)


def test_tracker_reports_completed_partial_and_failed_outcomes():
    complete = VendorRefreshTracker(("azure",))
    observer = complete.observer("azure")
    observer("started")
    observer("completed")
    assert complete.snapshot().status == "completed"
    assert complete.snapshot().started_count == 1

    partial = VendorRefreshTracker(("azure", "aws"))
    partial.observe("azure", "started")
    partial.observe("azure", "completed")
    partial.observe("aws", "started")
    partial.observe("aws", "failed")
    result = partial.snapshot()
    assert result.status == "partial"
    assert result.completed_vendors == ("azure",)
    assert result.failed_vendors == ("aws",)
    assert result.requires_nonzero_exit is True

    failed = VendorRefreshTracker(("gcp",))
    assert failed.snapshot().status == "failed"
    assert failed.snapshot().failed_vendors == ("gcp",)


def test_budget_skips_are_distinct_and_not_requested_is_successful():
    empty = VendorRefreshTracker(()).snapshot()
    assert empty.status == "not_requested"
    assert empty.requires_nonzero_exit is False

    skipped = VendorRefreshTracker(("azure", "aws"))
    skipped.mark_skipped("azure")
    skipped.mark_remaining_skipped()
    result = skipped.snapshot()
    assert result.status == "failed"
    assert result.skipped_vendors == ("azure", "aws")
    assert result.started_vendors == ()


def test_persist_and_load_round_trip(tmp_path):
    tracker = VendorRefreshTracker(("private",))
    tracker.observe("private", "started")
    tracker.observe("private", "completed")
    outcome = tracker.snapshot()

    persist_vendor_refresh_outcome(str(tmp_path), outcome)

    assert load_vendor_refresh_outcome(str(tmp_path)) == outcome
    assert load_vendor_refresh_outcome(str(tmp_path / "missing")) is None


def test_load_rejects_inconsistent_completed_state(tmp_path):
    (tmp_path / "_run_state.json").write_text(
        json.dumps(
            {
                "vendor_refresh_status": "completed",
                "vendor_refresh_expected": ["azure"],
                "vendor_refresh_started": [],
                "vendor_refresh_completed": [],
                "vendor_refresh_failed": [],
                "vendor_refresh_skipped": [],
            }
        ),
        encoding="utf-8",
    )

    assert load_vendor_refresh_outcome(str(tmp_path)) is None


def test_state_parser_rejects_missing_or_malformed_partitions():
    valid = {
        "vendor_refresh_status": "completed",
        "vendor_refresh_expected": ["azure"],
        "vendor_refresh_started": ["azure"],
        "vendor_refresh_completed": ["azure"],
        "vendor_refresh_failed": [],
        "vendor_refresh_skipped": [],
    }

    assert vendor_refresh_outcome_from_state(valid) is not None
    assert vendor_refresh_outcome_from_state([]) is None
    for key in (
        "vendor_refresh_expected",
        "vendor_refresh_started",
        "vendor_refresh_completed",
        "vendor_refresh_failed",
        "vendor_refresh_skipped",
    ):
        missing = dict(valid)
        missing.pop(key)
        assert vendor_refresh_outcome_from_state(missing) is None

        malformed = dict(valid)
        malformed[key] = [1]
        assert vendor_refresh_outcome_from_state(malformed) is None
