"""Artifact integrity inspection for calibration baseline readiness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from primr.qa.artifact_fingerprints import artifact_fingerprint

ARTIFACT_FIELDS = (
    ("report", "report_path", "report_size_bytes", "report_content_hash"),
    ("sidecar", "sidecar_path", "sidecar_size_bytes", "sidecar_content_hash"),
)


def artifact_integrity_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare current local files against frozen report and sidecar fingerprints."""

    checked = 0
    unfingerprinted = 0
    missing: list[dict[str, Any]] = []
    mismatched: list[dict[str, Any]] = []

    for report in reports:
        for artifact_kind, path_key, size_key, hash_key in ARTIFACT_FIELDS:
            expected_size = _optional_int(report.get(size_key))
            expected_hash = _optional_string(report.get(hash_key))
            if expected_size is None and expected_hash is None:
                unfingerprinted += 1
                continue

            path_text = _optional_string(report.get(path_key))
            if path_text is None:
                missing.append(
                    _artifact_blocker(report, artifact_kind=artifact_kind, artifact_path=None)
                )
                continue

            current = artifact_fingerprint(Path(path_text))
            actual_size = _optional_int(current.get("size_bytes"))
            actual_hash = _optional_string(current.get("content_hash"))
            if actual_size is None and actual_hash is None:
                missing.append(
                    _artifact_blocker(report, artifact_kind=artifact_kind, artifact_path=path_text)
                )
                continue

            checked += 1
            if expected_size != actual_size or expected_hash != actual_hash:
                mismatched.append(
                    {
                        **_artifact_blocker(
                            report,
                            artifact_kind=artifact_kind,
                            artifact_path=path_text,
                        ),
                        "expected_size_bytes": expected_size,
                        "actual_size_bytes": actual_size,
                        "expected_content_hash": expected_hash,
                        "actual_content_hash": actual_hash,
                    }
                )

    return {
        "counts": {
            "checked": checked,
            "unfingerprinted": unfingerprinted,
            "missing": len(missing),
            "mismatched": len(mismatched),
        },
        "missing": missing,
        "mismatched": mismatched,
    }


def inspection_status(original_status: Any, artifact_integrity: dict[str, Any]) -> Any:
    """Return the inspection status, giving artifact integrity failures priority."""

    if artifact_integrity["missing"]:
        return "fingerprinted_artifact_missing"
    if artifact_integrity["mismatched"]:
        return "artifact_fingerprint_mismatch"
    return original_status


def _artifact_blocker(
    report: dict[str, Any],
    *,
    artifact_kind: str,
    artifact_path: str | None,
) -> dict[str, Any]:
    return {
        "artifact": artifact_kind,
        "path": artifact_path,
        "report_file": report.get("report_file"),
        "report_path": report.get("report_path"),
        "coverage_tags": _string_list(report.get("coverage_tags")),
    }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]
