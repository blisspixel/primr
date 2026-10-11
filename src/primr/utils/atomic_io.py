"""Atomic persistence and bounded locks for cooperating local processes.

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

import contextlib
import importlib
import os
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from primr.utils.logging_config import get_logger

__all__ = ["atomic_replace", "atomic_write_bytes", "atomic_write_text", "file_mutation_lock"]

logger = get_logger("utils.atomic_io")


def _try_lock(stream: BinaryIO) -> None:
    """Acquire the persistent lock without an operating-system wait."""
    stream.seek(0)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl = importlib.import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(stream: BinaryIO) -> None:
    """Release the same region acquired by :func:`_try_lock`."""
    stream.seek(0)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl = importlib.import_module("fcntl")
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def file_mutation_lock(
    path: str | os.PathLike[str], *, timeout: float = 10.0, poll_interval: float = 0.05
) -> Iterator[None]:
    """Serialize cooperating local processes through a persistent sibling lock.

    Hold this across the entire read-modify-write operation. The lock is
    advisory, is not reentrant, and must not be deleted when released: replacing
    its inode could let another process lock a different file at the same path.
    The OS releases ownership when the descriptor closes, including on a crash.
    Callers also serialize their own threads when sharing mutable session state.
    """
    if timeout < 0 or poll_interval <= 0:
        raise ValueError("timeout must be nonnegative and poll_interval must be positive")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f"{target.name}.lock")
    with open(lock_path, "a+b") as stream:
        acquired = False
        try:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            deadline = time.monotonic() + timeout
            while True:
                try:
                    _try_lock(stream)
                    acquired = True
                    break
                except OSError as exc:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Timed out waiting for file mutation lock: {lock_path}"
                        ) from exc
                    time.sleep(min(poll_interval, remaining))
            yield
        finally:
            if acquired:
                try:
                    _unlock(stream)
                except OSError as exc:
                    logger.warning("Failed to release file mutation lock at %s: %s", lock_path, exc)


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
