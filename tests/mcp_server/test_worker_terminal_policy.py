"""Terminal compatibility contracts for supervised research workers."""

from datetime import datetime, timezone

import pytest

from primr.mcp_server.job_store import ResearchJobState
from primr.mcp_server.types import ResearchStage
from primr.mcp_server.worker_terminal_policy import (
    is_cancel_return_code,
    terminal_event_is_compatible,
)


def _terminal(stage: ResearchStage, error_type: str | None = None) -> ResearchJobState:
    job = ResearchJobState(
        job_id="job-1",
        company_name="Acme",
        mode="full",
        start_time=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )
    job.current_stage = stage
    job.error_type = error_type
    return job


@pytest.mark.parametrize(
    ("return_code", "exit_reason", "expected"),
    [(0, "completed", True), (0, "wrong", False), (1, "completed", False)],
)
def test_completed_requires_success_code_and_reason(return_code, exit_reason, expected):
    assert (
        terminal_event_is_compatible(
            _terminal(ResearchStage.COMPLETED),
            exit_reason=exit_reason,
            return_code=return_code,
            cancel_reason=None,
            termination_method=None,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("return_code", "exit_reason", "expected"),
    [(1, "pipeline_error", True), (0, "pipeline_error", False), (1, "wrong", False)],
)
def test_failed_requires_failure_code_and_matching_reason(return_code, exit_reason, expected):
    assert (
        terminal_event_is_compatible(
            _terminal(ResearchStage.FAILED, "pipeline_error"),
            exit_reason=exit_reason,
            return_code=return_code,
            cancel_reason=None,
            termination_method=None,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("cancel_reason", "return_code", "exit_reason", "expected"),
    [
        ("user_cancelled", 130, "user_cancelled", True),
        (None, 130, "user_cancelled", False),
        ("server_shutdown", 130, "user_cancelled", False),
        ("user_cancelled", 0, "user_cancelled", False),
        ("user_cancelled", 130, "wrong", False),
    ],
)
def test_cancelled_requires_parent_intent_code_and_reason(
    cancel_reason,
    return_code,
    exit_reason,
    expected,
):
    assert (
        terminal_event_is_compatible(
            _terminal(ResearchStage.CANCELLED, "user_cancelled"),
            exit_reason=exit_reason,
            return_code=return_code,
            cancel_reason=cancel_reason,
            termination_method=None,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("return_code", "method", "expected"),
    [
        (130, None, True),
        (-15, "sigterm_group", True),
        (-9, "sigkill_group", True),
        (1, "sigterm_group", False),
        (2, "kill_process_fallback", False),
        (1, "kill_process_fallback", True),
        (0xC000013A, "ctrl_break", True),
        (0xC000013A - (1 << 32), "ctrl_break", True),
        (1, "ctrl_break", False),
    ],
)
def test_cancel_return_codes_are_known_platform_outcomes(return_code, method, expected):
    assert is_cancel_return_code(return_code, method) is expected
