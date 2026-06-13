"""Top-level CLI error and interrupt handling.

Turns an unexpected failure into actionable guidance (route to ``primr doctor``,
offer ``--verbose`` for the traceback, link the issue tracker) instead of a bare
stack trace, and makes Ctrl-C exit cleanly. Lives in its own module so
``cli.py`` (pinned by the file-size ratchet) stays lean: the guarded command
dispatch and the post-run update notice live here, not inline in ``main``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from primr.utils.console import console

if TYPE_CHECKING:
    from primr.core.cli import CLIConfig

ISSUES_URL = "https://github.com/blisspixel/primr/issues"
# 128 + SIGINT(2): the conventional shell exit code for a Ctrl-C interrupt.
EXIT_INTERRUPTED = 130


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


def guard_dispatch(handler: Callable[[CLIConfig], int], config: CLIConfig) -> int:
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
        console.blank()
        console.info("Cancelled.")
        return EXIT_INTERRUPTED
    except Exception as exc:
        if getattr(config, "verbose", False):
            raise
        return report_unexpected_error(exc)

    if rc == 0 and getattr(config.command, "name", "") == "RESEARCH" and not config.quiet:
        from primr.core.cli_update import notify_if_update_available

        notify_if_update_available()
    return rc
