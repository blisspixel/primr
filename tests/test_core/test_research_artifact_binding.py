from __future__ import annotations

import json
import os

import pytest

from primr.core.research_artifact_binding import (
    bind_primary_artifact,
    primary_artifact_matches_state,
)


def _state(folder):
    return json.loads((folder / "_run_state.json").read_text(encoding="utf-8"))


def test_binding_matches_only_unchanged_primary_artifact(tmp_path):
    folder = tmp_path / "run"
    artifact = tmp_path / "report.docx"
    artifact.write_bytes(b"durable report")

    assert bind_primary_artifact(str(folder), str(artifact)) is True
    payload = _state(folder)
    assert primary_artifact_matches_state(payload, str(artifact)) is True

    artifact.write_bytes(b"changed report")
    assert primary_artifact_matches_state(payload, str(artifact)) is False


def test_binding_rejects_directory_and_malformed_state(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()

    assert bind_primary_artifact(str(folder), str(tmp_path)) is False
    assert primary_artifact_matches_state({}, str(tmp_path / "missing.docx")) is False


def test_binding_rejects_multiply_linked_artifact(tmp_path):
    folder = tmp_path / "run"
    artifact = tmp_path / "report.docx"
    linked = tmp_path / "report-copy.docx"
    artifact.write_bytes(b"durable report")
    os.link(artifact, linked)

    assert bind_primary_artifact(str(folder), str(artifact)) is False


def test_binding_rejects_artifact_beneath_linked_parent(tmp_path):
    real_parent = tmp_path / "real"
    linked_parent = tmp_path / "linked"
    real_parent.mkdir()
    artifact = real_parent / "report.docx"
    artifact.write_bytes(b"durable report")
    try:
        linked_parent.symlink_to(real_parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory links unavailable: {type(exc).__name__}")

    assert bind_primary_artifact(str(tmp_path / "run"), str(linked_parent / artifact.name)) is False
