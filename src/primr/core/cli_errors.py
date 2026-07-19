"""Top-level CLI error and interrupt handling.

Turns an unexpected failure into actionable guidance (route to ``primr doctor``,
offer ``--verbose`` for the traceback, link the issue tracker) instead of a bare
stack trace, and makes Ctrl-C exit cleanly. Lives in its own module so
``cli.py`` (pinned by the file-size ratchet) stays lean: the guarded command
dispatch and the post-run update notice live here, not inline in ``main``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from primr.core.cli_command_output import report_command_error
from primr.utils.console import console

ISSUES_URL = "https://github.com/blisspixel/primr/issues"
# 128 + SIGINT(2): the conventional shell exit code for a Ctrl-C interrupt.
EXIT_INTERRUPTED = 130
_ConfigT = TypeVar("_ConfigT")


def report_unexpected_error(exc: Exception) -> int:
    """Show actionable guidance for an unexpected CLI failure; return exit 1.

    Used for exceptions that reached the top of the CLI without a more specific
    handler. Points the user at ``primr doctor`` and ``--verbose`` rather than
    dumping a raw traceback they can't act on.
    """
    console.blank()
    console.error(f"Unexpected error: {exc}")
    console.info("Run 'primr doctor' to check your setup (keys, browsers, paths).")
    console.info("Re-run with --verbose for the full traceback.")
    console.info(f"If this looks like a bug, please report it: {ISSUES_URL}")
    return 1


def guard_dispatch(handler: Callable[[_ConfigT], int], config: _ConfigT) -> int:
    """Run a command handler with top-level interrupt + error handling.

    - ``KeyboardInterrupt`` (Ctrl-C) exits cleanly with code 130, no traceback.
    - In ``--verbose`` mode an unexpected exception is re-raised so the full
      traceback surfaces for debugging; otherwise it becomes actionable guidance.
    - On a clean, non-quiet research run, emits the passive update notice (moved
      here from ``main`` so the success-tail logic lives with the dispatch).
    """
    try:
        rc = handler(config)
    except KeyboardInterrupt:
        if getattr(config, "json_output", False):
            command = getattr(config, "command", None)
            return report_command_error(
                json_output=True,
                operation=str(getattr(command, "name", "command")).lower(),
                error_type="interrupted",
                message="The command was cancelled.",
                exit_code=EXIT_INTERRUPTED,
            )
        console.blank()
        console.info("Cancelled.")
        return EXIT_INTERRUPTED
    except Exception as exc:
        if getattr(config, "json_output", False):
            command = getattr(config, "command", None)
            return report_command_error(
                json_output=True,
                operation=str(getattr(command, "name", "command")).lower(),
                error_type="unexpected_error",
                message="The command failed unexpectedly.",
                hints=(
                    "Run 'primr doctor' to check the local setup.",
                    f"Report reproducible failures at {ISSUES_URL}.",
                ),
            )
        if getattr(config, "verbose", False):
            raise
        return report_unexpected_error(exc)

    command = getattr(config, "command", None)
    if (
        rc == 0
        and getattr(command, "name", "") == "RESEARCH"
        and not getattr(config, "quiet", False)
    ):
        from primr.core.cli_update import notify_if_update_available

        notify_if_update_available()
    return rc
