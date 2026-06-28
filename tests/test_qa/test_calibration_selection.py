"""Tests for curated calibration pack selections."""

import json
from pathlib import Path

import pytest

from primr.qa.calibration_selection import (
    DEFAULT_REPRESENTATIVE_TAGS,
    SELECTION_FORMAT,
    SELECTION_INSPECTION_FORMAT,
    inspect_calibration_pack_selection,
    load_calibration_pack_selection,
    write_calibration_pack_selection_template,
)


def _report(path: Path, name: str = "Acme_Strategic_Overview_01-01-2026.md") -> Path:
    report = path / name
    report.write_text("# Report\n\nRevenue grew. (Confirmed) [cite: 1]\n", encoding="utf-8")
    return report


def test_load_selection_resolves_reports_and_tags_from_cwd(tmp_path: Path, monkeypatch):
    report = _report(tmp_path)
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_format": SELECTION_FORMAT,
                "required_tags": ["clean", "high-hiring-signal"],
                "reports": [
                    {
                        "path": report.name,
                        "tags": ["Clean", "high hiring signal"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    selection = load_calibration_pack_selection(selection_path)

    assert selection.report_paths == (report,)
    assert selection.required_tags == ("clean", "high_hiring_signal")
    assert selection.tags_for(report) == ("clean", "high_hiring_signal")
    assert selection.present_tags == ("clean", "high_hiring_signal")
    assert selection.missing_tags == ()
    assert selection.to_manifest_representation()["missing_tags"] == []


def test_load_selection_reports_missing_required_tags(tmp_path: Path, monkeypatch):
    report = _report(tmp_path)
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_format": SELECTION_FORMAT,
                "required_tags": ["clean", "blocked_origin"],
                "reports": [{"path": report.name, "tags": ["clean"]}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    selection = load_calibration_pack_selection(selection_path)

    assert selection.present_tags == ("clean",)
    assert selection.missing_tags == ("blocked_origin",)


def test_inspect_selection_reports_representative_coverage(tmp_path: Path, monkeypatch):
    report = _report(tmp_path)
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_format": SELECTION_FORMAT,
                "required_tags": ["clean", "blocked_origin"],
                "reports": [{"path": report.name, "tags": ["clean"]}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    inspection = inspect_calibration_pack_selection(load_calibration_pack_selection(selection_path))

    assert inspection["inspection_format"] == SELECTION_INSPECTION_FORMAT
    assert inspection["representative_coverage_complete"] is False
    assert inspection["counts"] == {
        "reports": 1,
        "required_tags": 2,
        "present_tags": 1,
        "missing_tags": 1,
    }
    assert inspection["missing_tags"] == ["blocked_origin"]
    assert inspection["reports"] == [
        {
            "path": report.as_posix(),
            "tags": ["clean"],
        }
    ]
    assert inspection["next_actions"][0]["spend_preview_required"] is False


def test_load_selection_honors_base_dir_relative_to_selection_file(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    report = _report(reports_dir)
    selection_dir = tmp_path / "state"
    selection_dir.mkdir()
    selection_path = selection_dir / "selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_format": SELECTION_FORMAT,
                "base_dir": "../reports",
                "reports": [{"path": report.name, "tags": ["strategy_module"]}],
            }
        ),
        encoding="utf-8",
    )

    selection = load_calibration_pack_selection(selection_path)

    assert selection.report_paths == (report,)
    assert selection.tags_for(report) == ("strategy_module",)


def test_load_selection_rejects_invalid_format(tmp_path: Path):
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps({"selection_format": "wrong", "reports": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"primr\.calibration_pack_selection\.v1"):
        load_calibration_pack_selection(selection_path)


def test_load_selection_rejects_duplicate_reports(tmp_path: Path, monkeypatch):
    report = _report(tmp_path)
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_format": SELECTION_FORMAT,
                "reports": [report.name, report.name],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="Duplicate calibration report"):
        load_calibration_pack_selection(selection_path)


def test_load_selection_rejects_invalid_tag(tmp_path: Path):
    report = _report(tmp_path)
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_format": SELECTION_FORMAT,
                "base_dir": ".",
                "reports": [{"path": report.name, "tags": ["needs/review"]}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid tag"):
        load_calibration_pack_selection(selection_path)


def test_write_selection_template_leaves_tags_empty(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    report = _report(reports_dir)
    selection_path = tmp_path / "selection.json"

    payload = write_calibration_pack_selection_template(selection_path, [report])

    assert json.loads(selection_path.read_text(encoding="utf-8")) == payload
    assert payload["selection_format"] == SELECTION_FORMAT
    assert payload["required_tags"] == list(DEFAULT_REPRESENTATIVE_TAGS)
    assert payload["reports"] == [
        {
            "path": "reports/Acme_Strategic_Overview_01-01-2026.md",
            "tags": [],
        }
    ]
