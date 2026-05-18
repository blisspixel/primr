"""Filesystem safety helpers.

Centralizes operations that have repeatedly turned up in security findings:
- symlink-safe writability checks (the prior ``test_file.write_text("test")``
  pattern followed any symlink the directory's owner had placed at the
  predictable name and clobbered the target).
- owner-only file permissions on POSIX.

Use ``check_dir_writable(path)`` for startup/config validators and the
``write_text_secure``/``write_bytes_secure`` helpers when persisting
secrets.
"""

from __future__ import annotations

import errno
import logging
import os
import secrets
from pathlib import Path  # noqa: TC003 - used at runtime in helpers below

logger = logging.getLogger(__name__)


def check_dir_writable(path: Path) -> tuple[bool, str | None]:
    """Return ``(ok, error)`` for whether ``path`` is writable for the
    current process, without following or creating symlinks.

    Strategy: create a randomly named file with ``O_CREAT | O_EXCL`` and,
    where supported, ``O_NOFOLLOW`` so a same-named symlink cannot be
    targeted via TOCTOU. Unlink on success. Avoid the previous predictable
    ``.primr_write_test`` filename, which made symlink-clobbering trivial
    for an attacker with write access to a shared output directory.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"Cannot create directory: {e}"

    name = f".primr_write_test_{secrets.token_hex(8)}"
    candidate = path / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow

    try:
        fd = os.open(str(candidate), flags, 0o600)
    except OSError as e:
        if e.errno == errno.ELOOP:
            return False, "Symlink detected at writability probe path"
        return False, f"Not writable: {e}"

    try:
        os.write(fd, b"ok")
    finally:
        os.close(fd)
    try:
        candidate.unlink()
    except OSError:
        # Leave probe file behind rather than failing — operator can clean it.
        pass
    return True, None


def write_bytes_secure(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    """Write ``data`` to ``path`` with restrictive permissions on POSIX.

    Uses ``os.open(O_WRONLY | O_CREAT | O_TRUNC, mode)`` so the file is
    created with the requested mode in a single syscall — there is no
    window where another local user could read it before chmod runs.
    On non-POSIX hosts (Windows/NTFS), permissions are inherited from
    the parent directory's ACL and the mode argument is ignored.
    """
    if os.name == "posix":
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        try:
            path.chmod(mode)
        except OSError as e:
            logger.debug("Could not chmod %s to 0o%o: %s", path, mode, e)
    else:
        path.write_bytes(data)


def write_text_secure(path: Path, text: str, *, mode: int = 0o600) -> None:
    """UTF-8 wrapper around ``write_bytes_secure``."""
    write_bytes_secure(path, text.encode("utf-8"), mode=mode)
