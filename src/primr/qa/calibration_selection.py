"""Curated report selections for representative calibration packs."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SELECTION_FORMAT = "primr.calibration_pack_selection.v1"
DEFAULT_REPRESENTATIVE_TAGS = (
    "clean",
    "blocked_origin",
    "weak_citation",
    "strategy_module",
    "high_hiring_signal",
)

_TAG_PATTERN = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class CalibrationPackSelection:
    """Operator-curated report set and representative coverage requirements."""

    source_path: Path
    report_paths: tuple[Path, ...]
    required_tags: tuple[str, ...]
    tags_by_report: Mapping[str, tuple[str, ...]]

    def tags_for(self, report_path: Path) -> tuple[str, ...]:
        """Return coverage tags for a selected report path."""
        return self.tags_by_report.get(_path_key(report_path), ())

    @property
    def present_tags(self) -> tuple[str, ...]:
        """Sorted unique coverage tags present in this selection."""
        return tuple(sorted({tag for tags in self.tags_by_report.values() for tag in tags}))

    @property
    def missing_tags(self) -> tuple[str, ...]:
        """Required coverage tags that have no selected report."""
        present = set(self.present_tags)
        return tuple(tag for tag in self.required_tags if tag not in present)

    def to_manifest_representation(self) -> dict[str, Any]:
        """Serialize representative coverage metadata into a pack manifest."""
        return {
            "selection_format": SELECTION_FORMAT,
            "selection_path": self.source_path.as_posix(),
            "required_tags": list(self.required_tags),
            "present_tags": list(self.present_tags),
            "missing_tags": list(self.missing_tags),
        }


def load_calibration_pack_selection(selection_path: Path) -> CalibrationPackSelection:
    """Load an explicit calibration pack selection JSON file.

    The selection file deliberately records coverage tags supplied by the
    operator. Primr does not infer representativeness from prose, filenames, or
    ad-hoc content checks.
    """
    payload = _read_selection_payload(selection_path)
    if payload.get("selection_format") != SELECTION_FORMAT:
        raise ValueError(f"Expected {SELECTION_FORMAT} selection file")

    reports = payload.get("reports")
    if not isinstance(reports, list) or not reports:
        raise ValueError("Calibration pack selection must include at least one report")

    base_dir = _selection_base_dir(payload.get("base_dir"), selection_path)
    required_tags = _parse_tags(payload.get("required_tags", []), field="required_tags")
    report_paths: list[Path] = []
    tags_by_report: dict[str, tuple[str, ...]] = {}
    seen: set[str] = set()

    for index, entry in enumerate(reports):
        report_path, tags = _parse_report_entry(entry, index=index, base_dir=base_dir)
        key = _path_key(report_path)
        if key in seen:
            raise ValueError(f"Duplicate calibration report in selection: {report_path}")
        if not report_path.is_file():
            raise FileNotFoundError(f"Selected calibration report not found: {report_path}")
        seen.add(key)
        report_paths.append(report_path)
        tags_by_report[key] = tags

    return CalibrationPackSelection(
        source_path=selection_path,
        report_paths=tuple(report_paths),
        required_tags=required_tags,
        tags_by_report=tags_by_report,
    )


def write_calibration_pack_selection_template(
    selection_path: Path,
    report_paths: list[Path],
    *,
    required_tags: tuple[str, ...] = DEFAULT_REPRESENTATIVE_TAGS,
) -> dict[str, Any]:
    """Write an operator-curated selection template without inferring tags."""
    if not report_paths:
        raise ValueError("Calibration pack selection template requires at least one report")

    base_dir = selection_path.parent.resolve(strict=False)
    payload: dict[str, Any] = {
        "selection_format": SELECTION_FORMAT,
        "base_dir": ".",
        "required_tags": list(required_tags),
        "reports": [
            {
                "path": _template_report_path(report_path, base_dir),
                "tags": [],
            }
            for report_path in report_paths
        ],
    }
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _read_selection_payload(selection_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(selection_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Calibration pack selection not found: {selection_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Calibration pack selection is not valid JSON: {selection_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Calibration pack selection must be a JSON object: {selection_path}")
    return payload


def _selection_base_dir(raw_base_dir: Any, selection_path: Path) -> Path:
    if raw_base_dir is None:
        return Path.cwd()
    if not isinstance(raw_base_dir, str) or not raw_base_dir.strip():
        raise ValueError("Calibration pack selection base_dir must be a non-empty string")
    base_dir = Path(raw_base_dir)
    if not base_dir.is_absolute():
        base_dir = selection_path.parent / base_dir
    return base_dir


def _parse_report_entry(entry: Any, *, index: int, base_dir: Path) -> tuple[Path, tuple[str, ...]]:
    if isinstance(entry, str):
        raw_path = entry
        tags: tuple[str, ...] = ()
    elif isinstance(entry, dict):
        raw_path = entry.get("path")
        tags = _parse_tags(entry.get("tags", []), field=f"reports[{index}].tags")
    else:
        raise ValueError(f"reports[{index}] must be a path string or object")

    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"reports[{index}].path must be a non-empty string")

    report_path = Path(raw_path)
    if not report_path.is_absolute():
        report_path = base_dir / report_path
    return report_path.resolve(strict=False), tags


def _parse_tags(raw_tags: Any, *, field: str) -> tuple[str, ...]:
    if raw_tags is None:
        return ()
    if not isinstance(raw_tags, list):
        raise ValueError(f"{field} must be a list of tag strings")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_tags:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"{field} must contain non-empty tag strings")
        tag = raw.strip().lower().replace("-", "_").replace(" ", "_")
        if not _TAG_PATTERN.fullmatch(tag):
            raise ValueError(
                f"{field} contains invalid tag {raw!r}; use lowercase letters, digits, or '_'"
            )
        if tag not in seen:
            normalized.append(tag)
            seen.add(tag)
    return tuple(normalized)


def _path_key(path: Path) -> str:
    return str(path.resolve(strict=False))


def _template_report_path(report_path: Path, base_dir: Path) -> str:
    resolved = report_path.resolve(strict=False)
    try:
        return resolved.relative_to(base_dir).as_posix()
    except ValueError:
        return resolved.as_posix()
