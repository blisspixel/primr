"""Baseline readiness artifacts for calibration packs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from primr.core.eval_calibration import calibration_counts_from_payload, percent_or_dash

BASELINE_FORMAT = "primr.calibration_baseline.v1"
PACK_FORMAT = "primr.calibration_pack.v1"
DEFAULT_MINIMUM_REPORTS = 5

_COUNT_KEYS = (
    "confirmed_traceable",
    "confirmed_decidable",
    "reported_traceable",
    "reported_decidable",
    "evidence_source_reviews",
    "evidence_supported_reviews",
    "evidence_contradicted_reviews",
    "evidence_independent_reviews",
    "evidence_high_authority_reviews",
    "evidence_strong_reasoning_reviews",
    "evidence_honest_uncertainty_reviews",
    "evidence_high_relevance_reviews",
    "judge_agreement_compared",
    "judge_agreement_agreed",
)


def default_baseline_json_path(manifest_path: Path) -> Path:
    """Default baseline artifact path for a calibration pack manifest."""
    return manifest_path.with_name(f"{manifest_path.stem}.baseline.json")


def default_baseline_markdown_path(manifest_path: Path) -> Path:
    """Default Markdown summary path for a calibration pack manifest."""
    return manifest_path.with_name(f"{manifest_path.stem}.baseline.md")


def write_calibration_baseline(
    baseline_path: Path,
    manifest_path: Path,
    *,
    markdown_path: Path | None = None,
    minimum_reports: int = DEFAULT_MINIMUM_REPORTS,
) -> dict[str, Any]:
    """Build and write a calibration baseline readiness artifact."""
    manifest = _read_json_object(manifest_path)
    baseline = build_calibration_baseline(
        manifest,
        manifest_path=manifest_path,
        minimum_reports=minimum_reports,
    )
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_calibration_baseline_markdown(baseline), encoding="utf-8")
    return baseline


def build_calibration_baseline(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    minimum_reports: int = DEFAULT_MINIMUM_REPORTS,
) -> dict[str, Any]:
    """Summarize whether a calibration pack is ready to support gates."""
    if minimum_reports < 1:
        raise ValueError("minimum_reports must be at least 1")
    if manifest.get("manifest_format") != PACK_FORMAT:
        raise ValueError(f"Expected {PACK_FORMAT} manifest")

    reports = _report_entries(manifest)
    totals = manifest.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}

    report_count = _safe_int(totals.get("reports"), default=len(reports))
    reports_with_payloads = sum(1 for report in reports if isinstance(report.get("sidecar"), dict))
    sidecars_present = _safe_int(totals.get("sidecars_present"), default=reports_with_payloads)
    failures = _safe_int(totals.get("failures"))
    sidecar_counts = _aggregate_sidecar_counts(reports)
    coverage_counts = _sidecar_coverage_counts(reports)
    label_totals = _label_totals(manifest)
    label_summary = _label_summary(label_totals)
    evidence_summary = _evidence_summary(sidecar_counts)
    judge_agreement = _judge_agreement_summary(manifest, sidecar_counts)
    representation = _representation_summary(manifest, reports)
    reasons = _readiness_reasons(
        report_count=report_count,
        minimum_reports=minimum_reports,
        reports_with_payloads=reports_with_payloads,
        failures=failures,
        reports_with_evidence_reviews=coverage_counts["reports_with_evidence_reviews"],
        reports_with_judge_agreement=coverage_counts["reports_with_judge_agreement"],
        representation_missing_tags=representation["missing_tags"],
    )
    next_actions = _next_actions(
        reasons=reasons,
        manifest_path=manifest_path,
        report_count=report_count,
        minimum_reports=minimum_reports,
        reports_with_payloads=reports_with_payloads,
        failures=failures,
        reports_with_evidence_reviews=coverage_counts["reports_with_evidence_reviews"],
        reports_with_judge_agreement=coverage_counts["reports_with_judge_agreement"],
        representation_missing_tags=representation["missing_tags"],
        selection_path=representation.get("selection_path"),
    )

    return {
        "baseline_format": BASELINE_FORMAT,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "pack_manifest": manifest_path.as_posix() if manifest_path is not None else None,
        "pack_created_at_utc": manifest.get("created_at_utc"),
        "minimum_reports": minimum_reports,
        "ready": not reasons,
        "status": "ready" if not reasons else reasons[0],
        "reasons": reasons,
        "next_actions": next_actions,
        "judge": manifest.get("judge"),
        "max_per_label": manifest.get("max_per_label"),
        "totals": {
            "reports": report_count,
            "reports_with_sidecar_payloads": reports_with_payloads,
            "sidecars_present": sidecars_present,
            "claims_sampled": _safe_int(totals.get("claims_sampled")),
            "judgeable_claims": _safe_int(totals.get("judgeable_claims")),
            "estimated_judge_calls": _safe_int(totals.get("estimated_judge_calls")),
            "estimated_cloud_cost_usd": _safe_float(totals.get("estimated_cloud_cost_usd")),
            "failures": failures,
            **coverage_counts,
        },
        "traceability": label_summary,
        "representation": representation,
        "evidence_review": evidence_summary,
        "judge_agreement": judge_agreement,
        "reports": [_report_summary(report) for report in reports],
    }


def render_calibration_baseline_markdown(baseline: dict[str, Any]) -> str:
    """Render a compact human-readable readiness summary."""
    totals = _dict_value(baseline, "totals")
    evidence = _dict_value(baseline, "evidence_review")
    agreement = _dict_value(baseline, "judge_agreement")
    representation = _dict_value(baseline, "representation")
    traceability = _dict_value(baseline, "traceability")
    reasons = baseline.get("reasons", [])
    reason_text = ", ".join(str(reason) for reason in reasons) if reasons else "none"
    lines = [
        "# Calibration Baseline",
        "",
        f"Status: {baseline.get('status')}",
        f"Ready: {'yes' if baseline.get('ready') else 'no'}",
        f"Reasons: {reason_text}",
        f"Reports: {totals.get('reports', 0)} / minimum {baseline.get('minimum_reports')}",
        (
            "Sidecar payloads: "
            f"{totals.get('reports_with_sidecar_payloads', 0)} / {totals.get('reports', 0)}"
        ),
        f"Evidence source reviews: {evidence.get('source_reviews', 0)}",
        (
            "Evidence-reviewed reports: "
            f"{totals.get('reports_with_evidence_reviews', 0)} / {totals.get('reports', 0)}"
        ),
        (
            "Representative coverage: "
            f"{len(representation.get('present_tags', []))} / "
            f"{len(representation.get('required_tags', []))} required tags"
        ),
        (
            "Judge agreement: "
            f"{agreement.get('agreed', 0)} / {agreement.get('compared', 0)} "
            f"({percent_or_dash(agreement.get('agreement_rate'))})"
        ),
        (
            "Judge-agreement reports: "
            f"{totals.get('reports_with_judge_agreement', 0)} / {totals.get('reports', 0)}"
        ),
        "",
        "## Traceability",
        "",
        "| Label | Traceable | Decidable | Rate |",
        "|---|---:|---:|---:|",
    ]
    for label in ("Confirmed", "Reported"):
        stats = _dict_value(traceability, label)
        lines.append(
            f"| {label} | {stats.get('traceable', 0)} | {stats.get('decidable', 0)} | "
            f"{percent_or_dash(stats.get('traceability_rate'))} |"
        )

    if representation.get("required_tags"):
        missing_tags = ", ".join(str(tag) for tag in representation.get("missing_tags", []))
        lines.extend(
            [
                "",
                "## Representative Coverage",
                "",
                "| Required Tags | Present Tags | Missing Tags |",
                "|---|---|---|",
                (
                    f"| {', '.join(str(tag) for tag in representation.get('required_tags', []))} | "
                    f"{', '.join(str(tag) for tag in representation.get('present_tags', []))} | "
                    f"{missing_tags or 'none'} |"
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Evidence Review",
            "",
            "| Dimension | Count | Rate |",
            "|---|---:|---:|",
            _rate_row(evidence, "Supported", "supported_reviews", "support_rate"),
            _rate_row(evidence, "Contradicted", "contradicted_reviews", "contradiction_rate"),
            _rate_row(evidence, "Independent", "independent_reviews", "independence_rate"),
            _rate_row(evidence, "High Authority", "high_authority_reviews", "high_authority_rate"),
            _rate_row(
                evidence,
                "Strong Reasoning",
                "strong_reasoning_reviews",
                "strong_reasoning_rate",
            ),
            _rate_row(
                evidence,
                "Honest Uncertainty",
                "honest_uncertainty_reviews",
                "honest_uncertainty_rate",
            ),
            _rate_row(evidence, "High Relevance", "high_relevance_reviews", "high_relevance_rate"),
            "",
            "## Next Actions",
            "",
        ]
    )
    next_actions = baseline.get("next_actions", {})
    if isinstance(next_actions, dict):
        action_items = next_actions.get("items", [])
        if isinstance(action_items, list) and action_items:
            lines.extend(["| Reason | Action |", "|---|---|"])
            for item in action_items:
                if not isinstance(item, dict):
                    continue
                lines.append(f"| {item.get('reason', '')} | {item.get('action', '')} |")
        gate_policy = next_actions.get("gate_policy")
        if gate_policy:
            lines.extend(["", f"Gate policy: {gate_policy}"])
        commands = next_actions.get("commands", [])
        if isinstance(commands, list) and commands:
            lines.extend(
                [
                    "",
                    "## Suggested Commands",
                    "",
                    "| Purpose | Command |",
                    "|---|---|",
                ]
            )
            for command in commands:
                if not isinstance(command, dict):
                    continue
                lines.append(f"| {command.get('purpose', '')} | `{command.get('command', '')}` |")
            if next_actions.get("spend_preview_required"):
                lines.append(
                    "| Cost control | Preview spend and get operator approval before live judge calls. |"
                )

    lines.extend(
        [
            "",
            "## Reports",
            "",
            "| Report | Sidecar | Evidence Reviews | Judge Agreement | Claims | Judgeable | Tags |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for report in baseline.get("reports", []):
        if not isinstance(report, dict):
            continue
        tags = ", ".join(str(tag) for tag in report.get("coverage_tags", []))
        evidence_reviews = _safe_int(report.get("evidence_source_reviews"))
        agreement_compared = _safe_int(report.get("judge_agreement_compared"))
        lines.append(
            f"| {report.get('report_file', '')} | "
            f"{'yes' if report.get('sidecar_exists') else 'no'} | "
            f"{evidence_reviews if evidence_reviews else 'missing'} | "
            f"{agreement_compared if agreement_compared else 'missing'} | "
            f"{report.get('claims_sampled', 0)} | {report.get('judgeable_claims', 0)} | "
            f"{tags} |"
        )
    return "\n".join(lines) + "\n"


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Calibration pack manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Calibration pack manifest is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Calibration pack manifest must be a JSON object: {path}")
    return payload


def _report_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    reports = manifest.get("reports", [])
    if not isinstance(reports, list):
        return []
    return [report for report in reports if isinstance(report, dict)]


def _aggregate_sidecar_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    totals = dict.fromkeys(_COUNT_KEYS, 0)
    for report in reports:
        sidecar = report.get("sidecar")
        if not isinstance(sidecar, dict):
            continue
        counts = calibration_counts_from_payload(sidecar)
        for key in _COUNT_KEYS:
            totals[key] += _safe_int(counts.get(key))
    return totals


def _sidecar_coverage_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    reports_with_evidence = 0
    reports_with_agreement = 0
    for report in reports:
        sidecar = report.get("sidecar")
        if not isinstance(sidecar, dict):
            continue
        counts = calibration_counts_from_payload(sidecar)
        if _safe_int(counts.get("evidence_source_reviews")) > 0:
            reports_with_evidence += 1
        if _safe_int(counts.get("judge_agreement_compared")) > 0:
            reports_with_agreement += 1
    return {
        "reports_with_evidence_reviews": reports_with_evidence,
        "reports_with_judge_agreement": reports_with_agreement,
    }


def _label_totals(manifest: dict[str, Any]) -> dict[str, dict[str, int]]:
    preferred = manifest.get("existing_sidecar_per_label")
    if not isinstance(preferred, dict) or not preferred:
        preferred = manifest.get("per_label")
    if not isinstance(preferred, dict):
        return {}
    return {
        str(label): {str(key): _safe_int(value) for key, value in stats.items()}
        for label, stats in preferred.items()
        if isinstance(stats, dict)
    }


def _label_summary(label_totals: dict[str, dict[str, int]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for label in ("Confirmed", "Reported"):
        stats = label_totals.get(label, {})
        traceable = _safe_int(stats.get("traceable"))
        decidable = (
            traceable + _safe_int(stats.get("untraceable")) + _safe_int(stats.get("no_source"))
        )
        summary[label] = {
            "sampled": _safe_int(stats.get("sampled")),
            "traceable": traceable,
            "decidable": decidable,
            "untraceable": _safe_int(stats.get("untraceable")),
            "no_source": _safe_int(stats.get("no_source")),
            "unfetchable": _safe_int(stats.get("unfetchable")),
            "traceability_rate": _rate(traceable, decidable),
        }
    return summary


def _evidence_summary(counts: dict[str, int]) -> dict[str, Any]:
    source_reviews = _safe_int(counts.get("evidence_source_reviews"))

    def rate(key: str) -> float | None:
        return _rate(_safe_int(counts.get(key)), source_reviews)

    return {
        "source_reviews": source_reviews,
        "supported_reviews": _safe_int(counts.get("evidence_supported_reviews")),
        "contradicted_reviews": _safe_int(counts.get("evidence_contradicted_reviews")),
        "independent_reviews": _safe_int(counts.get("evidence_independent_reviews")),
        "high_authority_reviews": _safe_int(counts.get("evidence_high_authority_reviews")),
        "strong_reasoning_reviews": _safe_int(counts.get("evidence_strong_reasoning_reviews")),
        "honest_uncertainty_reviews": _safe_int(counts.get("evidence_honest_uncertainty_reviews")),
        "high_relevance_reviews": _safe_int(counts.get("evidence_high_relevance_reviews")),
        "support_rate": rate("evidence_supported_reviews"),
        "contradiction_rate": rate("evidence_contradicted_reviews"),
        "independence_rate": rate("evidence_independent_reviews"),
        "high_authority_rate": rate("evidence_high_authority_reviews"),
        "strong_reasoning_rate": rate("evidence_strong_reasoning_reviews"),
        "honest_uncertainty_rate": rate("evidence_honest_uncertainty_reviews"),
        "high_relevance_rate": rate("evidence_high_relevance_reviews"),
    }


def _judge_agreement_summary(
    manifest: dict[str, Any],
    counts: dict[str, int],
) -> dict[str, Any]:
    compared = _safe_int(counts.get("judge_agreement_compared"))
    agreed = _safe_int(counts.get("judge_agreement_agreed"))
    source = "sidecars" if compared else "none"
    if compared == 0:
        manifest_agreement = manifest.get("judge_agreement")
        if isinstance(manifest_agreement, dict):
            compared = _safe_int(manifest_agreement.get("compared"))
            agreed = _safe_int(manifest_agreement.get("agreed"))
            if compared:
                source = "manifest"
    return {
        "compared": compared,
        "agreed": agreed,
        "agreement_rate": _rate(agreed, compared),
        "source": source,
    }


def _representation_summary(
    manifest: dict[str, Any],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    representation = manifest.get("representation")
    if not isinstance(representation, dict):
        representation = {}
    required_tags = _string_list(representation.get("required_tags"))
    present_tags = _string_list(representation.get("present_tags"))
    if not present_tags:
        present_tags = sorted(
            {tag for report in reports for tag in _string_list(report.get("coverage_tags"))}
        )
    missing_tags = _string_list(representation.get("missing_tags"))
    if required_tags and not missing_tags:
        present = set(present_tags)
        missing_tags = [tag for tag in required_tags if tag not in present]
    return {
        "selection_format": representation.get("selection_format"),
        "selection_path": representation.get("selection_path"),
        "required_tags": required_tags,
        "present_tags": present_tags,
        "missing_tags": missing_tags,
    }


def _readiness_reasons(
    *,
    report_count: int,
    minimum_reports: int,
    reports_with_payloads: int,
    failures: int,
    reports_with_evidence_reviews: int,
    reports_with_judge_agreement: int,
    representation_missing_tags: list[str],
) -> list[str]:
    reasons: list[str] = []
    if report_count == 0:
        reasons.append("empty_pack")
    if report_count < minimum_reports:
        reasons.append("insufficient_reports")
    if reports_with_payloads < report_count:
        reasons.append("missing_calibration_sidecars")
    if failures:
        reasons.append("calibration_failures")
    if report_count > 0 and reports_with_evidence_reviews < report_count:
        reasons.append("missing_evidence_reviews")
    if report_count > 0 and reports_with_judge_agreement < report_count:
        reasons.append("missing_judge_agreement")
    if representation_missing_tags:
        reasons.append("missing_representative_coverage")
    return reasons


def _next_actions(
    *,
    reasons: list[str],
    manifest_path: Path | None,
    report_count: int,
    minimum_reports: int,
    reports_with_payloads: int,
    failures: int,
    reports_with_evidence_reviews: int,
    reports_with_judge_agreement: int,
    representation_missing_tags: list[str],
    selection_path: Any,
) -> dict[str, Any]:
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

    return {
        "missing_reports": missing_reports,
        "missing_sidecars": missing_sidecars,
        "missing_evidence_review_reports": missing_evidence_reviews,
        "missing_judge_agreement_reports": missing_judge_agreement,
        "missing_representative_tags": representation_missing_tags,
        "spend_preview_required": spend_preview_required,
        "gate_policy": (
            "Keep PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY unset until this artifact "
            "is ready and the measured floor has been reviewed."
        ),
        "items": items,
        "commands": [
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
        ],
    }


def _default_markdown_ref(manifest_ref: str) -> str:
    if manifest_ref == "<pack-manifest.json>":
        return "<baseline.md>"
    return str(default_baseline_markdown_path(Path(manifest_ref)).as_posix())


def _report_summary(report: dict[str, Any]) -> dict[str, Any]:
    sidecar = report.get("sidecar")
    sidecar_payload = sidecar if isinstance(sidecar, dict) else {}
    counts = calibration_counts_from_payload(sidecar_payload) if sidecar_payload else {}
    evidence_source_reviews = _safe_int(counts.get("evidence_source_reviews"))
    judge_agreement_compared = _safe_int(counts.get("judge_agreement_compared"))
    return {
        "report_file": report.get("report_file"),
        "report_path": report.get("report_path"),
        "sidecar_exists": bool(report.get("sidecar_exists")),
        "claims_sampled": _safe_int(report.get("claims_sampled")),
        "judgeable_claims": _safe_int(report.get("judgeable_claims")),
        "evidence_source_reviews": evidence_source_reviews,
        "has_evidence_reviews": evidence_source_reviews > 0,
        "judge_agreement_compared": judge_agreement_compared,
        "has_judge_agreement": judge_agreement_compared > 0,
        "confirmed_traceability": _rate(
            _safe_int(counts.get("confirmed_traceable")),
            _safe_int(counts.get("confirmed_decidable")),
        ),
        "reported_traceability": _rate(
            _safe_int(counts.get("reported_traceable")),
            _safe_int(counts.get("reported_decidable")),
        ),
        "coverage_tags": _string_list(report.get("coverage_tags")),
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 3)


def _rate_row(evidence: dict[str, Any], label: str, count_key: str, rate_key: str) -> str:
    return f"| {label} | {evidence.get(count_key, 0)} | {percent_or_dash(evidence.get(rate_key))} |"


def _dict_value(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key, {})
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
