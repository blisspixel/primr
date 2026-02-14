"""Tests for shared Deep Research polling helpers."""

from primr.ai.deep_research_polling import (
    phase_name_for_elapsed,
    poll_interval_for_elapsed,
)


def test_phase_name_for_elapsed_thresholds():
    assert phase_name_for_elapsed(0) == "Initializing"
    assert phase_name_for_elapsed(120) == "Searching sources"
    assert phase_name_for_elapsed(240) == "Analyzing findings"
    assert phase_name_for_elapsed(480) == "Generating report"
    assert phase_name_for_elapsed(900) == "Finalizing"


def test_poll_interval_for_elapsed_schedule():
    schedule = (
        (60.0, 5.0),
        (180.0, 10.0),
        (360.0, 20.0),
    )
    assert poll_interval_for_elapsed(30, schedule, 30.0) == 5.0
    assert poll_interval_for_elapsed(100, schedule, 30.0) == 10.0
    assert poll_interval_for_elapsed(250, schedule, 30.0) == 20.0
    assert poll_interval_for_elapsed(500, schedule, 30.0) == 30.0
