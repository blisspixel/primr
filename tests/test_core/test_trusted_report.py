"""Security contracts for stable, root-bound report snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest

from primr.core.trusted_report import (
    ReportSnapshotError,
    stable_report_snapshot,
    validate_trusted_report,
)


@pytest.mark.parametrize("swap_call", [2, 3])
def test_validation_rechecks_resolved_containment_around_hashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap_call: int,
) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    report = (allowed_root / "report.md").absolute()
    report.write_text("trusted report", encoding="utf-8")
    outside = (tmp_path / "outside.md").absolute()
    outside.write_text("outside content", encoding="utf-8")

    original_resolve = Path.resolve
    report_resolves = 0

    def swapped_resolve(path: Path, strict: bool = False) -> Path:
        nonlocal report_resolves
        if path.absolute() == report:
            report_resolves += 1
            if report_resolves >= swap_call:
                return outside
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", swapped_resolve)

    with pytest.raises(ReportSnapshotError, match=r"allowed roots|changed"):
        validate_trusted_report(report, allowed_roots=(allowed_root,))


def test_validation_rejects_a_report_outside_allowed_roots(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    report = tmp_path / "outside.md"
    report.write_text("outside content", encoding="utf-8")

    with pytest.raises(ReportSnapshotError, match="outside the allowed roots"):
        validate_trusted_report(report, allowed_roots=(allowed_root,))


def test_snapshot_rechecks_root_containment_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    report = (allowed_root / "report.md").absolute()
    report.write_text("trusted report", encoding="utf-8")
    outside = (tmp_path / "outside.md").absolute()
    outside.write_text("outside content", encoding="utf-8")
    trusted = validate_trusted_report(report, allowed_roots=(allowed_root,))
    original_resolve = Path.resolve

    def swapped_resolve(path: Path, strict: bool = False) -> Path:
        if path.absolute() == report:
            return outside
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", swapped_resolve)

    with (
        pytest.raises(ReportSnapshotError, match="outside the allowed roots"),
        stable_report_snapshot(trusted, tmp_path / "snapshots"),
    ):
        pytest.fail("an out-of-root source must not reach provider context")
