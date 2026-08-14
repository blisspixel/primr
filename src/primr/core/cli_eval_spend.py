"""Approval helpers for billable ``primr --eval`` paths.

``--eval-max-estimated-cost`` and ``--eval-judge-max-cost`` are spend ceilings,
not approval. Paid eval work still quotes, honors ``--dry-run``, and requires
``--skip-confirm`` or an explicit yes. This module is the single confirm
seam for ``--eval-run-missing`` and ``--eval-llm-judge`` so those flags
cannot treat a cap as consent or ignore ``--dry-run``.
"""

from __future__ import annotations

from typing import Any

from primr.utils.console import console, prompt_yes_no


def approve_eval_spend(config: Any, estimated_total: float, label: str) -> int | None:
    """Return an exit code to stop, or ``None`` when spend is approved.

    The caller prints the planned work first. This helper repeats the dollar
    amount, refuses to launch on ``--dry-run``, and treats a cost cap as a
    ceiling rather than consent. Interactive decline is a hard stop (exit 1)
    so a cancelled eval cannot fall through into ``perform_research``.
    """
    console.info(f"{label}: estimated ${estimated_total:.2f}")
    if getattr(config, "dry_run_requested", False):
        console.info("Dry-run only; no eval spend started.")
        return 0
    # Caps such as --eval-max-estimated-cost are checked by the caller.
    # Approval is only --skip-confirm or an explicit yes.
    if getattr(config, "skip_confirm", False):
        console.info(f"Proceeding with {label} under --skip-confirm")
        return None
    if not prompt_yes_no(
        f"Proceed with {label} (~${estimated_total:.2f})?",
        default=False,
    ):
        console.info("Cancelled.")
        return 1
    return None
