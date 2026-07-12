"""Cross-platform signaling and cleanup for supervised worker process trees."""

from __future__ import annotations

import asyncio
import os
import signal

from primr.mcp_server.windows_job import WindowsJobObject
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


async def cleanup_process_tree(
    process: asyncio.subprocess.Process,
    windows_job: WindowsJobObject | None,
) -> tuple[WindowsJobObject | None, str | None]:
    """Remove worker descendants after the retained parent exits."""
    if os.name == "nt":
        if windows_job is not None:
            try:
                windows_job.close()
            except OSError as exc:
                # CloseHandle failure means kill-on-close has not been proven.
                # Preserve the owner so the controller can retry and must keep
                # its journal lease while descendants may still be alive.
                return windows_job, f"Worker process-tree cleanup failed: {exc}"
        return None, None

    try:
        kill_group = getattr(os, "killpg")  # noqa: B009 - absent from Windows stubs
        kill_signal = getattr(signal, "SIGKILL")  # noqa: B009 - absent from Windows stubs
        kill_group(process.pid, kill_signal)
    except ProcessLookupError:
        return windows_job, None
    except (AttributeError, OSError) as exc:
        return windows_job, f"Worker process-tree cleanup failed: {exc}"
    return windows_job, None


async def signal_process_tree(
    process: asyncio.subprocess.Process,
    windows_job: WindowsJobObject | None,
    *,
    current_method: str | None,
    force: bool,
) -> str:
    """Signal an owned worker tree, falling back to its retained parent."""
    if process.returncode is not None:
        return current_method or "already_exited"

    if os.name == "nt":
        if not force:
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                return "ctrl_break"
            except (AttributeError, OSError, ProcessLookupError):
                pass
        if windows_job is not None:
            try:
                windows_job.terminate()
                return "terminate_job_object"
            except OSError:
                logger.exception("Windows Job Object termination failed")
        return _signal_direct_process(process, force=True)

    try:
        kill_group = getattr(os, "killpg")  # noqa: B009 - absent from Windows stubs
        kill_signal = (
            getattr(signal, "SIGKILL")  # noqa: B009 - absent from Windows stubs
            if force
            else signal.SIGTERM
        )
        kill_group(process.pid, kill_signal)
    except ProcessLookupError:
        return "already_exited"
    except (AttributeError, OSError):
        logger.exception("POSIX process-group signal failed")
        return _signal_direct_process(process, force=force)
    return "sigkill_group" if force else "sigterm_group"


def _signal_direct_process(process: asyncio.subprocess.Process, *, force: bool) -> str:
    if process.returncode is not None:
        return "already_exited"
    try:
        if force:
            process.kill()
            return "kill_process_fallback"
        process.terminate()
        return "terminate_process_fallback"
    except ProcessLookupError:
        return "already_exited"
    except OSError:
        logger.exception("Direct worker signal failed")
        return "signal_failed"


__all__ = ["cleanup_process_tree", "signal_process_tree"]
