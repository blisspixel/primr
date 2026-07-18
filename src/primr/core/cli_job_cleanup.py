"""Operator-facing pending-job cleanup workflow."""

from __future__ import annotations

from typing import Protocol

from primr.utils.console import console


class ConfirmationPrompt(Protocol):
    """Callable shape for an operator confirmation prompt."""

    def __call__(self, prompt: str, *, default: bool) -> bool:
        """Return whether the operator confirmed the requested action."""
        raise NotImplementedError


def run_clear_pending_jobs(*, assume_yes: bool, confirm: ConfirmationPrompt) -> int:
    """Confirm and remove only the recovery records shown to the operator."""
    from primr.ai.job_persistence import get_pending_jobs_with_status, remove_pending_jobs

    read_success, jobs = get_pending_jobs_with_status()
    if not read_success:
        console.error(
            "Pending-job cleanup could not read the recovery registry. No records were changed."
        )
        return 1
    if not jobs:
        console.info("No pending jobs to clear.")
        return 0

    count = len(jobs)
    console.warn(
        f"This will remove {count} pending recovery record(s). "
        "Primr will no longer be able to resume them."
    )
    if not assume_yes and not confirm(
        f"Clear these {count} pending recovery record(s)?", default=False
    ):
        console.info("Pending-job cleanup cancelled. No records were changed.")
        return 0

    success, removed = remove_pending_jobs(jobs)
    if not success:
        console.error("Pending-job cleanup failed. Recovery records were left unchanged.")
        return 1

    console.ok(f"Cleared {removed} pending recovery record(s).")
    if removed < count:
        console.info(f"{count - removed} record(s) changed before cleanup and were not removed.")
    return 0
