"""``primr update`` — self-upgrade to the latest published release.

Detects whether primr was installed via pipx or pip and runs the matching
upgrade command, reporting the before/after version. This is the explicit
counterpart to the passive "update available" notice: the notice tells you a
new version exists; this command installs it in one step.
"""

from __future__ import annotations

import subprocess
import sys

from primr import __version__
from primr.utils.console import console
from primr.utils.version_check import (
    check_for_update,
    detect_install_method,
    get_latest_version,
)


def notify_if_update_available() -> None:
    """Print a one-line "update available" notice when a newer release exists.

    Cached (~24h) and opt-out aware via ``check_for_update``; swallows every
    failure so it can never disrupt the surrounding command. Safe to call at
    the tail of any command.
    """
    try:
        latest = check_for_update(__version__)
    except Exception:  # pragma: no cover - check_for_update is already safe
        return
    if not latest:
        return
    console.blank()
    console.info(f"Update available: v{__version__} -> v{latest}. Run 'primr update'.")


def run_update(*, check_only: bool = False, yes: bool = False) -> int:
    """Upgrade primr to the latest PyPI release.

    Args:
        check_only: Only report whether an update is available; do not install.
        yes: Skip the confirmation prompt and upgrade immediately.

    Returns:
        Process exit code (0 on success / already-current, non-zero on failure).
    """
    console.banner("Primr Update")
    console.blank()
    console.detail("Installed", __version__)

    console.status("Checking PyPI for the latest release")
    latest = get_latest_version(force=True)
    console.status_line_done()

    if latest is None:
        console.warn("Could not reach PyPI to check for updates.")
        console.info("Check your connection, or upgrade manually:")
        console.info("  pipx upgrade primr   (or)   pip install --upgrade primr")
        return 1

    console.detail("Latest", latest)
    console.blank()

    from primr.utils.version_check import is_newer

    if not is_newer(latest, __version__):
        console.ok(f"primr is already up to date (v{__version__}).")
        return 0

    console.info(f"A newer version is available: v{__version__} -> v{latest}")

    if check_only:
        console.blank()
        console.info("Run 'primr update' to install it.")
        return 0

    if not yes and not sys.stdin.isatty():
        console.error("Non-interactive updates require explicit confirmation.")
        console.info("Re-run with 'primr update --yes', or use '--check' to inspect only.")
        return 1

    method = detect_install_method()
    console.detail("Method", method.kind)
    console.detail("Command", " ".join(method.upgrade_command))
    console.blank()

    if not yes:
        try:
            answer = input(f"Upgrade primr to v{latest} now? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.blank()
            console.info("Update cancelled.")
            return 1
        if answer in {"n", "no"}:
            console.info("Update cancelled.")
            return 0

    console.blank()
    console.status(f"Upgrading primr to v{latest}")
    try:
        result = subprocess.run(
            method.upgrade_command,
            check=False,
        )
    except FileNotFoundError:
        console.status_line_done()
        console.error(f"Could not run: {method.upgrade_command[0]} (not found on PATH).")
        if method.kind == "pipx":
            console.info("Install pipx, or upgrade with: pip install --upgrade primr")
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        console.status_line_done()
        console.error(f"Update failed: {exc}")
        return 1

    console.status_line_done()
    console.blank()

    if result.returncode != 0:
        console.error("Upgrade command exited with a non-zero status.")
        console.info("You can retry manually:")
        console.info(f"  {' '.join(method.upgrade_command)}")
        return result.returncode

    console.ok(f"primr upgraded to v{latest}.")
    console.info("Open a new terminal (or re-run) to use the updated version.")
    return 0
