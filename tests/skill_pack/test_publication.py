"""Failure-path coverage for atomic skill-pack publication."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from primr.skill_pack import publication
from primr.skill_pack.schema import SkillPackArtifacts


def _owned_output(tmp_path: Path, company_name: str = "Acme Corp") -> Path:
    output_dir = tmp_path / "Acme_Corp_Skills_Pack_20260713"
    output_dir.mkdir()
    publication.write_output_marker(output_dir, company_name)
    return output_dir


@pytest.mark.parametrize(
    "marker_text",
    [
        "not-json",
        "[]",
        json.dumps(
            {
                "format": "primr-skill-pack-output",
                "version": 1,
                "company_name": "Acme Corp",
                "output_name": "Acme_Corp_Skills_Pack_20260713",
                "publication_warnings": [1],
            }
        ),
    ],
)
def test_replace_rejects_malformed_ownership_markers(tmp_path: Path, marker_text: str):
    output_dir = _owned_output(tmp_path)
    (output_dir / publication.OUTPUT_MARKER_NAME).write_text(marker_text, encoding="utf-8")

    with pytest.raises(ValueError, match="without Primr ownership proof"):
        publication.validate_replace_target(tmp_path, output_dir, "Acme Corp", "Acme_Corp")


def test_replace_rejects_oversized_ownership_marker(tmp_path: Path):
    output_dir = _owned_output(tmp_path)
    (output_dir / publication.OUTPUT_MARKER_NAME).write_text(" " * 4097, encoding="utf-8")

    with pytest.raises(ValueError, match="without Primr ownership proof"):
        publication.validate_replace_target(tmp_path, output_dir, "Acme Corp", "Acme_Corp")


def test_replace_accepts_only_the_narrow_legacy_signature(tmp_path: Path):
    output_dir = tmp_path / "Acme_Corp_Skills_Pack_20260713"
    output_dir.mkdir()
    report = output_dir / "Acme_Corp_Skills_Pack_Report.md"
    report.write_text("# Skills Pack - Acme Corp\n\nLegacy report.\n", encoding="utf-8")
    (output_dir / "roles").mkdir()

    publication.validate_replace_target(tmp_path, output_dir, "Acme Corp", "Acme_Corp")

    report.write_text("# Unrelated report\n", encoding="utf-8")
    with pytest.raises(ValueError, match="without Primr ownership proof"):
        publication.validate_replace_target(tmp_path, output_dir, "Acme Corp", "Acme_Corp")


@pytest.mark.skipif(os.name != "nt", reason="requires a case-insensitive Windows filesystem")
def test_case_variant_collision_recognizes_the_existing_marker_owner(tmp_path: Path):
    canonical = tmp_path / "Foo_Skills_Pack_20260714"
    canonical.mkdir()
    publication.write_output_marker(canonical, "Foo")

    resolved = publication.resolve_output_name(tmp_path, "foo", "foo", "20260714")

    assert resolved != "foo_Skills_Pack_20260714"
    assert resolved.startswith("foo-")
    assert resolved.endswith("_Skills_Pack_20260714")


def test_replace_rejects_wrong_parent_and_reparse_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output_dir = _owned_output(tmp_path)
    outside = tmp_path.parent / output_dir.name

    with pytest.raises(ValueError, match="direct child"):
        publication.validate_replace_target(tmp_path, outside, "Acme Corp", "Acme_Corp")

    monkeypatch.setattr(publication, "_is_reparse_point", lambda path: path == output_dir)
    with pytest.raises(ValueError, match="symlink, junction, or mounted"):
        publication.validate_replace_target(tmp_path, output_dir, "Acme Corp", "Acme_Corp")

    monkeypatch.setattr(publication, "_is_reparse_point", lambda _path: False)
    monkeypatch.setattr(publication, "_tree_contains_reparse_point", lambda _path: True)
    with pytest.raises(ValueError, match="containing links or mount points"):
        publication.validate_replace_target(tmp_path, output_dir, "Acme Corp", "Acme_Corp")


def test_failed_publish_restores_previous_complete_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output_dir = tmp_path / "published"
    staged_output = tmp_path / "staged"
    output_dir.mkdir()
    staged_output.mkdir()
    (output_dir / "old.txt").write_text("old", encoding="utf-8")
    (staged_output / "new.txt").write_text("new", encoding="utf-8")
    original_rename = Path.rename

    def fail_staged_rename(path: Path, destination: Path):
        if path == staged_output:
            raise OSError("simulated publication failure")
        return original_rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail_staged_rename)

    with pytest.raises(OSError, match="simulated publication failure"):
        publication.publish_staged_output(staged_output, output_dir)

    assert (output_dir / "old.txt").read_text(encoding="utf-8") == "old"
    assert (staged_output / "new.txt").read_text(encoding="utf-8") == "new"


def test_failed_publish_surfaces_restore_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output_dir = tmp_path / "published"
    staged_output = tmp_path / "staged"
    output_dir.mkdir()
    staged_output.mkdir()
    original_rename = Path.rename

    def fail_publish_and_restore(path: Path, destination: Path):
        if path == staged_output:
            raise OSError("simulated publication failure")
        if path.name.startswith(".primr-backup-"):
            raise PermissionError("simulated restore failure")
        return original_rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail_publish_and_restore)
    monkeypatch.setattr(publication.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="previous output could not be restored"):
        publication.publish_staged_output(staged_output, output_dir)

    assert list(tmp_path.glob(".primr-backup-*"))


def test_publication_warning_persistence_failures_remain_nonfatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    output_dir = _owned_output(tmp_path)
    artifacts = SkillPackArtifacts(
        output_dir=str(output_dir),
        report_md_path=str(tmp_path / "missing" / "report.md"),
    )

    def fail_marker_write(*_args, **_kwargs):
        raise OSError("marker unavailable")

    monkeypatch.setattr(publication, "atomic_write_text", fail_marker_write)

    publication.record_publication_warning(artifacts, output_dir, "cleanup incomplete")

    assert artifacts.publication_warnings == ["cleanup incomplete"]
    assert "Could not persist publication warning in output marker" in caplog.text
    assert "Could not persist publication warning in pack report" in caplog.text


def test_rebase_artifact_paths_preserves_optional_outputs(tmp_path: Path):
    staged = tmp_path / "staged"
    published = tmp_path / "published"
    artifacts = SkillPackArtifacts(
        output_dir=str(staged),
        claude_tree_root=str(staged / "roles"),
        cowork_zip_path=None,
        report_md_path=str(staged / "report.md"),
        skill_md_paths=[str(staged / "roles" / "checking" / "SKILL.md")],
    )

    publication.rebase_artifact_paths(artifacts, staged, published)

    assert artifacts.output_dir == str(published)
    assert artifacts.claude_tree_root == str(published / "roles")
    assert artifacts.cowork_zip_path is None
    assert artifacts.report_md_path == str(published / "report.md")
    assert artifacts.skill_md_paths == [str(published / "roles" / "checking" / "SKILL.md")]
