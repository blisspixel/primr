"""Tests for shared Deep Research execution/polling behavior."""

from __future__ import annotations

import pytest

from primr.ai.deep_research_execution import poll_interaction_until_terminal


class _Interaction:
    def __init__(self, status: str):
        self.status = status


@pytest.mark.asyncio
async def test_poll_interaction_terminal_canceled_returns_immediately():
    interaction, elapsed = await poll_interaction_until_terminal(
        get_interaction=lambda _id: _Interaction("canceled"),
        interaction_id="job-1",
        timeout_seconds=10.0,
        max_poll_errors=0,
        poll_interval_for_elapsed=lambda _elapsed: 5.0,
        on_poll=None,
        on_transient_retry=None,
        build_timeout_error=lambda elapsed_s: TimeoutError(f"timeout: {elapsed_s}"),
        build_poll_error=lambda e: RuntimeError(str(e)),
    )
    assert interaction.status == "canceled"
    assert elapsed >= 0.0


@pytest.mark.asyncio
async def test_poll_interaction_terminal_expired_case_insensitive():
    interaction, _ = await poll_interaction_until_terminal(
        get_interaction=lambda _id: _Interaction("EXPIRED"),
        interaction_id="job-2",
        timeout_seconds=10.0,
        max_poll_errors=0,
        poll_interval_for_elapsed=lambda _elapsed: 5.0,
        on_poll=None,
        on_transient_retry=None,
        build_timeout_error=lambda elapsed_s: TimeoutError(f"timeout: {elapsed_s}"),
        build_poll_error=lambda e: RuntimeError(str(e)),
    )
    assert interaction.status == "EXPIRED"
