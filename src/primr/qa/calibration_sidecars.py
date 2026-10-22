"""Calibration sidecar naming, report binding, and usability rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from primr.qa.artifact_fingerprints import artifact_bytes_fingerprint, artifact_fingerprint

SIDECAR_SUFFIX = ".calibration.json"


def sidecar_path_for(report_path: Path) -> Path:
    """Return the sidecar path paired with a report file."""
    return report_path.with_name(report_path.name + SIDECAR_SUFFIX)


def report_path_for_sidecar(sidecar_path: Path) -> Path:
    """Return the report path named by a calibration sidecar filename."""
    if not sidecar_path.name.endswith(SIDECAR_SUFFIX):
        raise ValueError(f"Not a calibration sidecar path: {sidecar_path}")
    return sidecar_path.with_name(sidecar_path.name[: -len(SIDECAR_SUFFIX)])


def calibration_sidecar_matches_artifact(
    report_artifact: dict[str, Any], payload: dict[str, Any]
) -> bool:
    """Return whether a sidecar is bound to one captured report snapshot."""
    return (
        report_artifact.get("size_bytes") is not None
        and report_artifact.get("content_hash") is not None
        and isinstance(payload.get("report_artifact"), dict)
        and payload["report_artifact"] == report_artifact
    )


def calibration_sidecar_matches_report(report_path: Path, payload: dict[str, Any]) -> bool:
    """Return whether a sidecar payload is bound to the report's current bytes."""
    return calibration_sidecar_matches_artifact(artifact_fingerprint(report_path), payload)


def usable_sidecar_payload(report: dict[str, Any]) -> dict[str, Any] | None:
    """Return a manifest sidecar only when its report binding is valid."""
    sidecar = report.get("sidecar")
    if report.get("sidecar_matches_report") is not True or not isinstance(sidecar, dict):
        return None
    return sidecar


def has_usable_sidecar(report: dict[str, Any]) -> bool:
    """Return whether a manifest or baseline summary has a usable sidecar."""
    if not report.get("sidecar_exists") or report.get("sidecar_matches_report") is not True:
        return False
    return "sidecar" not in report or isinstance(report.get("sidecar"), dict)


def read_sidecar_payload(
    report_path: Path,
    *,
    report_artifact: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Read the sidecar bound to the current or supplied report snapshot."""
    payload, _fingerprint = read_sidecar_snapshot(
        report_path,
        report_artifact=report_artifact,
    )
    return payload


def read_sidecar_snapshot(
    report_path: Path,
    *,
    report_artifact: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Read, validate, and fingerprint a sidecar from one byte snapshot."""

    sidecar = sidecar_path_for(report_path)
    try:
        content = sidecar.read_bytes()
    except OSError:
        return None, {"size_bytes": None, "content_hash": None}
    fingerprint = artifact_bytes_fingerprint(content)
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, fingerprint
    if not isinstance(payload, dict):
        return None, fingerprint
    expected_artifact = report_artifact or artifact_fingerprint(report_path)
    if not calibration_sidecar_matches_artifact(expected_artifact, payload):
        return None, fingerprint
    return payload, fingerprint
