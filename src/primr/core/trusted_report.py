"""Stable report validation and snapshotting for provider-bound strategy input."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class TrustedReport:
    """A regular report whose identity and bytes were validated together."""

    path: Path
    device: int
    inode: int
    size: int
    modified_ns: int
    content_sha256: str
    allowed_roots: tuple[Path, ...] = ()


class ReportSnapshotError(RuntimeError):
    """Raised when report identity or stable snapshot guarantees fail."""


def _report_identity(report_stat: os.stat_result) -> tuple[int, int, int, int]:
    return (
        report_stat.st_dev,
        report_stat.st_ino,
        report_stat.st_size,
        report_stat.st_mtime_ns,
    )


def _is_link_or_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _contains_link_or_reparse_point(path: Path) -> bool:
    current = path.absolute()
    while True:
        if _is_link_or_reparse_point(current):
            return True
        if current == current.parent:
            return False
        current = current.parent


def _validate_opened_location(
    path: Path,
    opened_stat: os.stat_result,
    allowed_roots: tuple[Path, ...],
) -> None:
    """Bind an opened descriptor to its current resolved, allowed location."""
    current_target = path.resolve(strict=True)
    if allowed_roots and not any(current_target.is_relative_to(root) for root in allowed_roots):
        raise ReportSnapshotError("Report file moved outside the allowed roots")
    current_stat = current_target.lstat()
    if (current_stat.st_dev, current_stat.st_ino) != (
        opened_stat.st_dev,
        opened_stat.st_ino,
    ):
        raise ReportSnapshotError("Report file changed during validation")


def _validated_report_digest(
    path: Path,
    expected_stat: os.stat_result,
    allowed_roots: tuple[Path, ...],
) -> str:
    source_fd = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(path, flags)
        with os.fdopen(source_fd, "rb") as source:
            source_fd = -1
            opened_stat = os.fstat(source.fileno())
            current_path_stat = path.lstat()
            if (
                not stat.S_ISREG(opened_stat.st_mode)
                or _is_link_or_reparse_point(path)
                or opened_stat.st_nlink > 1
                or _report_identity(opened_stat) != _report_identity(expected_stat)
                or (current_path_stat.st_dev, current_path_stat.st_ino)
                != (opened_stat.st_dev, opened_stat.st_ino)
            ):
                raise ReportSnapshotError("Report file changed during validation")
            _validate_opened_location(path, opened_stat, allowed_roots)
            digest = hashlib.file_digest(source, "sha256").hexdigest()
            final_source_stat = os.fstat(source.fileno())

        _validate_opened_location(path, final_source_stat, allowed_roots)
        final_path_stat = path.lstat()
        if (
            _report_identity(final_source_stat) != _report_identity(expected_stat)
            or _is_link_or_reparse_point(path)
            or (final_path_stat.st_dev, final_path_stat.st_ino)
            != (expected_stat.st_dev, expected_stat.st_ino)
        ):
            raise ReportSnapshotError("Report file changed during validation")
        return digest
    finally:
        if source_fd >= 0:
            os.close(source_fd)


def validate_trusted_report(
    report_path: str | Path,
    *,
    allowed_roots: Iterable[str | Path] | None = None,
) -> TrustedReport:
    """Validate and hash one no-link, single-name regular report."""
    supplied = Path(report_path).expanduser()
    if _contains_link_or_reparse_point(supplied):
        raise ReportSnapshotError("Report path cannot contain links or reparse points")

    resolved = supplied.resolve(strict=True)
    roots: tuple[Path, ...] = ()
    if allowed_roots is not None:
        roots = tuple(Path(root).resolve() for root in allowed_roots)
        if not any(resolved.is_relative_to(root) for root in roots):
            raise ReportSnapshotError("Report file is outside the allowed roots")

    metadata = resolved.lstat()
    if _is_link_or_reparse_point(resolved) or not stat.S_ISREG(metadata.st_mode):
        raise ReportSnapshotError("Report path is not a regular file")
    if metadata.st_nlink > 1:
        raise ReportSnapshotError("Report file cannot be a hard link")

    digest = _validated_report_digest(resolved, metadata, roots)
    return TrustedReport(
        path=resolved,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        size=metadata.st_size,
        modified_ns=metadata.st_mtime_ns,
        content_sha256=digest,
        allowed_roots=roots,
    )


def _create_stable_snapshot(report: TrustedReport, destination_dir: Path) -> Path:
    snapshot_path: Path | None = None
    source_fd = -1
    try:
        if _contains_link_or_reparse_point(report.path):
            raise ReportSnapshotError("Report path changed after validation")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(report.path, flags)
        opened_stat = os.fstat(source_fd)
        _validate_opened_location(report.path, opened_stat, report.allowed_roots)
        expected_identity = (
            report.device,
            report.inode,
            report.size,
            report.modified_ns,
        )
        current_path_stat = report.path.lstat()
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or _is_link_or_reparse_point(report.path)
            or opened_stat.st_nlink > 1
            or _report_identity(opened_stat) != expected_identity
            or (current_path_stat.st_dev, current_path_stat.st_ino)
            != (opened_stat.st_dev, opened_stat.st_ino)
        ):
            raise ReportSnapshotError("Report file changed after validation")

        destination_dir.mkdir(parents=True, exist_ok=True)
        snapshot_fd, snapshot_name = tempfile.mkstemp(
            prefix=".primr-strategy-context-",
            suffix=report.path.suffix,
            dir=destination_dir,
        )
        snapshot_path = Path(snapshot_name)
        snapshot_digest = hashlib.sha256()
        with os.fdopen(snapshot_fd, "wb") as target, os.fdopen(source_fd, "rb") as source:
            source_fd = -1
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
                snapshot_digest.update(chunk)
            target.flush()
            os.fsync(target.fileno())
            final_source_stat = os.fstat(source.fileno())

        final_path_stat = report.path.lstat()
        _validate_opened_location(report.path, final_source_stat, report.allowed_roots)
        if (
            _report_identity(final_source_stat) != expected_identity
            or _is_link_or_reparse_point(report.path)
            or (final_path_stat.st_dev, final_path_stat.st_ino) != (report.device, report.inode)
            or snapshot_digest.hexdigest() != report.content_sha256
        ):
            raise ReportSnapshotError("Report file changed while it was copied")
        return snapshot_path
    except (OSError, ReportSnapshotError) as exc:
        if snapshot_path is not None:
            snapshot_path.unlink(missing_ok=True)
        if isinstance(exc, ReportSnapshotError):
            raise
        raise ReportSnapshotError("Could not create a stable report snapshot") from exc
    finally:
        if source_fd >= 0:
            os.close(source_fd)


@contextmanager
def stable_report_snapshot(
    report: TrustedReport,
    destination_dir: str | Path,
) -> Iterator[Path]:
    """Yield a private verified copy and remove it on every outcome."""
    snapshot = _create_stable_snapshot(report, Path(destination_dir))
    try:
        yield snapshot
    finally:
        try:
            snapshot.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove strategy context snapshot")


__all__ = [
    "ReportSnapshotError",
    "TrustedReport",
    "stable_report_snapshot",
    "validate_trusted_report",
]
