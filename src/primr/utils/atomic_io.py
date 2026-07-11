"""Atomic file-replace helper resilient to transient Windows file locks.

On Windows a sync client (e.g. OneDrive) or antivirus can hold a brief lock on
a file, making :func:`os.replace` raise ``PermissionError`` (WinError 32) even
though the rename would succeed a moment later. :func:`atomic_replace` retries
the rename a few times with a short backoff before giving up, so long-running
pipelines and persistence paths do not abort on transient contention.

On POSIX, ``os.replace`` does not hit this lock contention, so the first attempt
succeeds and the retry path is inert. Persistent failures still re-raise the
original ``PermissionError`` so callers keep their existing error semantics.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

__all__ = ["atomic_replace", "atomic_write_bytes", "atomic_write_text"]


def atomic_replace(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    *,
    retries: int = 5,
    base_delay: float = 0.05,
) -> None:
    """Atomically replace ``dst`` with ``src``, retrying on transient locks.

    Retries :func:`os.replace` on ``PermissionError`` (the Windows file-lock
    case), sleeping ``base_delay * attempt`` seconds between tries. Re-raises the
    last ``PermissionError`` if every attempt fails. Any other exception
    propagates immediately.
    """
    if retries < 1:
        raise ValueError("retries must be >= 1")

    src_s = os.fspath(src)
    dst_s = os.fspath(dst)
    last_error: PermissionError | None = None
    for attempt in range(1, retries + 1):
        try:
            os.replace(src_s, dst_s)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(base_delay * attempt)

    # Exhausted retries on a persistent lock; re-raise so the caller's existing
    # error handling runs unchanged.
    assert last_error is not None
    raise last_error


def atomic_write_bytes(path: str | os.PathLike[str], content: bytes) -> None:
    """Write bytes through a same-directory temporary file and atomic replace."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        atomic_replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(
    path: str | os.PathLike[str],
    content: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Write text atomically using the shared replace seam."""

    atomic_write_bytes(path, content.encode(encoding))
