"""Stable binding between a primary research artifact and its owning run state."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

from primr.utils.fs_safety import (
    path_contains_link_or_reparse_point,
    path_is_linked_or_nonregular_file,
)

_HASH_CHUNK_BYTES = 1024 * 1024


def bind_primary_artifact(folder_path: str | None, result_path: str | None) -> bool:
    """Persist a stable primary-artifact fingerprint for later resume decisions."""

    if not folder_path or not result_path:
        return False
    fingerprint = _stable_artifact_fingerprint(Path(result_path))
    if fingerprint is None:
        return False

    from primr.core.run_state_io import _update_run_state

    _update_run_state(folder_path, **fingerprint)
    return True


def primary_artifact_matches_state(payload: object, result_path: str) -> bool:
    """Return whether an artifact still matches one canonical persisted binding."""

    if not isinstance(payload, dict):
        return False
    expected_path = payload.get("primary_artifact_path")
    expected_size = payload.get("primary_artifact_size_bytes")
    expected_sha256 = payload.get("primary_artifact_sha256")
    if (
        not isinstance(expected_path, str)
        or isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size < 0
        or not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
    ):
        return False

    fingerprint = _stable_artifact_fingerprint(Path(result_path))
    if fingerprint is None:
        return False
    return (
        os.path.normcase(expected_path)
        == os.path.normcase(str(fingerprint["primary_artifact_path"]))
        and expected_size == fingerprint["primary_artifact_size_bytes"]
        and expected_sha256 == fingerprint["primary_artifact_sha256"]
    )


def _stable_artifact_fingerprint(path: Path) -> dict[str, Any] | None:
    """Hash one unchanged, singly linked regular file without following a leaf link."""

    try:
        if path_contains_link_or_reparse_point(path) or path_is_linked_or_nonregular_file(path):
            return None
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
    except OSError:
        return None

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            return None
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, _HASH_CHUNK_BYTES):
            digest.update(chunk)
        after = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(after):
            return None
        return {
            "primary_artifact_path": str(Path(os.path.abspath(path))),
            "primary_artifact_size_bytes": after.st_size,
            "primary_artifact_sha256": digest.hexdigest(),
        }
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _file_identity(file_stat: os.stat_result) -> tuple[int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
    )


__all__ = ["bind_primary_artifact", "primary_artifact_matches_state"]
