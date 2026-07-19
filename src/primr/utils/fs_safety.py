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
import stat
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_trusted_darwin_root_alias(path: Path, metadata: os.stat_result) -> bool:
    """Recognize macOS root aliases that are outside user control.

    macOS exposes ``/var`` and ``/tmp`` as root-owned links into ``/private``.
    Rejecting those aliases makes normal temporary directories unusable.  The
    exception stays narrow: the link and its parent must be root-owned, the
    parent must not be group- or world-writable, and the destination must be
    the matching standard location.
    """
    if (
        sys.platform != "darwin"
        or path.parent != Path("/")
        or path.name not in {"tmp", "var"}
        or getattr(metadata, "st_uid", -1) != 0
    ):
        return False
    try:
        root_metadata = path.parent.stat()
        destination = os.readlink(path)
    except OSError:
        return False
    return (
        getattr(root_metadata, "st_uid", -1) == 0
        and stat.S_IMODE(root_metadata.st_mode) & 0o022 == 0
        and destination in {f"private/{path.name}", f"/private/{path.name}"}
    )


def path_contains_link_or_reparse_point(path: Path) -> bool:
    """Return true when any existing path component redirects traversal."""
    current = path.absolute()
    while True:
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            pass
        except OSError:
            return True
        else:
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            attributes = getattr(metadata, "st_file_attributes", 0)
            is_link = stat.S_ISLNK(metadata.st_mode)
            if (is_link and not _is_trusted_darwin_root_alias(current, metadata)) or bool(
                reparse_flag and attributes & reparse_flag
            ):
                return True
        if current == current.parent:
            return False
        current = current.parent


def path_is_linked_or_nonregular_file(path: Path) -> bool:
    """Reject linked, multiply named, reparse, and nonregular state files."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink > 1
        or bool(reparse_flag and attributes & reparse_flag)
    )


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


def check_dir_atomic_writable(path: Path) -> tuple[bool, str | None]:
    """Probe the same-directory atomic write path used by durable state."""
    writable, error = check_dir_writable(path)
    if not writable:
        return False, error

    from primr.utils.atomic_io import atomic_write_bytes

    candidate = path / f".primr_atomic_test_{secrets.token_hex(8)}"
    try:
        atomic_write_bytes(candidate, b"ok")
    except OSError as exc:
        return False, f"Atomic write failed: {exc}"
    try:
        candidate.unlink(missing_ok=True)
    except OSError as exc:
        return False, f"Atomic cleanup failed: {exc.__class__.__name__}"
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
