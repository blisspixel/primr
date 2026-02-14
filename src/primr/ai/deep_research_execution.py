"""
Shared polling execution helpers for Deep Research interactions.
"""

from __future__ import annotations

import asyncio
import time
import typing
from typing import Any


def is_transient_poll_error(error: Exception | str) -> bool:
    """Classify transient polling errors that should be retried."""
    error_str = str(error).lower()
    return any(
        pattern in error_str
        for pattern in (
            "500",
            "internal server error",
            "503",
            "service unavailable",
            "connection",
            "timeout",
        )
    )


async def poll_interaction_until_terminal(
    *,
    get_interaction: typing.Callable[[str], Any],
    interaction_id: str,
    timeout_seconds: float,
    max_poll_errors: int,
    poll_interval_for_elapsed: typing.Callable[[float], float],
    on_poll: typing.Callable[[Any, float], None] | None = None,
    on_transient_retry: typing.Callable[[int, int, float, Exception], None] | None = None,
    build_timeout_error: typing.Callable[[float], Exception],
    build_poll_error: typing.Callable[[Exception], Exception],
) -> tuple[Any, float]:
    """
    Poll an interaction until a terminal status is reached.

    Returns:
        Tuple of (terminal_interaction, elapsed_seconds).
    """
    start_time = time.time()
    consecutive_poll_errors = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            raise build_timeout_error(elapsed)

        try:
            interaction = get_interaction(interaction_id)
            consecutive_poll_errors = 0
        except Exception as e:
            if is_transient_poll_error(e) and consecutive_poll_errors < max_poll_errors:
                consecutive_poll_errors += 1
                wait_time = 10 * consecutive_poll_errors
                if on_transient_retry:
                    on_transient_retry(consecutive_poll_errors, max_poll_errors, wait_time, e)
                await asyncio.sleep(wait_time)
                continue
            raise build_poll_error(e) from e

        if on_poll is not None:
            on_poll(interaction, elapsed)

        status = getattr(interaction, "status", "")
        if status in ("completed", "failed"):
            return interaction, elapsed

        await asyncio.sleep(poll_interval_for_elapsed(elapsed))
