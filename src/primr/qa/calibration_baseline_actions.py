"""Next-action guidance for calibration baseline readiness artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_AGENT_SELECTION_PATH = ".agent/calibration-selection.json"


def calibration_baseline_next_actions(
    *,
    reasons: list[str],
    manifest_path: Path | None,
    report_count: int,
    minimum_reports: int,
    reports_with_payloads: int,
    failures: int,
    reports_with_evidence_reviews: int,
    reports_with_judge_agreement: int,
    representative_selection_ready: bool,
    representation_missing_tags: list[str],
    selection_path: Any,
) -> dict[str, Any]:
    """Return remediation guidance for baseline readiness blockers."""
    manifest_ref = manifest_path.as_posix() if manifest_path is not None else "<pack-manifest.json>"
    baseline_md_ref = _default_markdown_ref(manifest_ref)
    target_report_count = max(report_count, minimum_reports)
    missing_reports = max(0, minimum_reports - report_count)
    missing_sidecars = max(0, report_count - reports_with_payloads)
    missing_evidence_reviews = max(0, report_count - reports_with_evidence_reviews)
    missing_judge_agreement = max(0, report_count - reports_with_judge_agreement)
    selection_ref = selection_path if isinstance(selection_path, str) and selection_path else None
    selection_command = (
        f"--pack-selection {selection_ref}"
        if selection_ref
        else f"--calibrate-recent {target_report_count}"
    )
    spend_preview_required = any(
        reason
        in {
            "missing_calibration_sidecars",
            "calibration_failures",
            "missing_evidence_reviews",
            "missing_judge_agreement",
        }
        for reason in reasons
    )
    items: list[dict[str, Any]] = []

    if "empty_pack" in reasons:
        items.append(
            {
                "reason": "empty_pack",
                "action": (
                    "Select current-format Strategic Overview reports before building a "
                    "baseline pack."
                ),
            }
        )
    if "insufficient_reports" in reasons:
        items.append(
            {
                "reason": "insufficient_reports",
                "missing_reports": missing_reports,
                "action": (
                    f"Add {missing_reports} more current-format Strategic Overview "
                    f"report(s) to reach the minimum of {minimum_reports}."
                ),
            }
        )
    if "missing_calibration_sidecars" in reasons:
        items.append(
            {
                "reason": "missing_calibration_sidecars",
                "missing_sidecars": missing_sidecars,
                "action": (
                    "Run calibration for every selected report so each pack entry has a "
                    "sidecar payload."
                ),
            }
        )
    if "calibration_failures" in reasons:
        items.append(
            {
                "reason": "calibration_failures",
                "failures": failures,
                "action": (
                    "Fix each failed report or judge failure, then rebuild the pack "
                    "without calibration errors."
                ),
            }
        )
    if "missing_evidence_reviews" in reasons:
        items.append(
            {
                "reason": "missing_evidence_reviews",
                "missing_reports": missing_evidence_reviews,
                "action": (
                    "Regenerate calibration sidecars with evidence-review-capable "
                    "judging so every selected report has source review dimensions."
                ),
            }
        )
    if "missing_judge_agreement" in reasons:
        items.append(
            {
                "reason": "missing_judge_agreement",
                "missing_reports": missing_judge_agreement,
                "action": (
                    "Run cloud-vs-local judge comparison on the same sampled claims "
                    "so every selected report has an agreement record before trusting "
                    "the baseline."
                ),
            }
        )
    if "missing_representative_selection" in reasons:
        items.append(
            {
                "reason": "missing_representative_selection",
                "action": (
                    "Create a curated calibration pack selection with non-empty required "
                    "representative tags before treating the pack as a baseline."
                ),
            }
        )
    if "missing_representative_coverage" in reasons:
        items.append(
            {
                "reason": "missing_representative_coverage",
                "missing_tags": representation_missing_tags,
                "action": (
                    "Add selected reports tagged for the missing representative "
                    "coverage dimensions, then rebuild the pack manifest."
                ),
            }
        )

    if not items:
        items.append(
            {
                "reason": "ready",
                "action": (
                    "Review the measured floor with the pack context before selecting "
                    "any hard threshold."
                ),
            }
        )

    commands = []
    if not representative_selection_ready:
        commands.append(
            {
                "purpose": "Create representative selection template",
                "command": (
                    "primr calibrate "
                    f"--calibrate-recent {target_report_count} "
                    f"--pack-selection-template {DEFAULT_AGENT_SELECTION_PATH}"
                ),
            }
        )
    commands.extend(
        [
            {
                "purpose": "Preview report selection and judge-call cost",
                "command": (
                    f"primr calibrate {selection_command} --dry-run --pack-manifest {manifest_ref}"
                ),
            },
            {
                "purpose": "Build agreement-validated pack",
                "command": (
                    f"primr calibrate {selection_command} --judge-compare "
                    f"--pack-manifest {manifest_ref}"
                ),
            },
            {
                "purpose": "Rebuild readiness summary",
                "command": (
                    f"primr calibrate --baseline-from {manifest_ref} "
                    f"--baseline-md {baseline_md_ref}"
                ),
            },
        ]
    )

    return {
        "missing_reports": missing_reports,
        "missing_sidecars": missing_sidecars,
        "missing_evidence_review_reports": missing_evidence_reviews,
        "missing_judge_agreement_reports": missing_judge_agreement,
        "missing_representative_selection": not representative_selection_ready,
        "missing_representative_tags": representation_missing_tags,
        "spend_preview_required": spend_preview_required,
        "gate_policy": (
            "Keep PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY unset until this artifact "
            "is ready and the measured floor has been reviewed."
        ),
        "items": items,
        "commands": commands,
    }


def _default_markdown_ref(manifest_ref: str) -> str:
    if manifest_ref == "<pack-manifest.json>":
        return "<baseline.md>"
    manifest_path = Path(manifest_ref)
    return manifest_path.with_name(f"{manifest_path.stem}.baseline.md").as_posix()
