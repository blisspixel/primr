"""Tests for calibration baseline readiness artifacts."""

import json
from pathlib import Path

import pytest

from primr.qa.artifact_fingerprints import artifact_fingerprint
from primr.qa.calibration_baseline import (
    build_calibration_baseline,
    default_baseline_json_path,
    default_baseline_markdown_path,
    inspect_calibration_baseline,
    read_calibration_baseline,
    write_calibration_baseline,
)


def _sidecar(
    *,
    include_agreement: bool = True,
    include_evidence: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "judge": {"kind": "cloud", "model": "fast-tier"},
        "per_label": {
            "Confirmed": {
                "sampled": 1,
                "traceable": 1,
                "untraceable": 0,
                "no_source": 0,
                "unfetchable": 0,
                "exempt": 0,
                "source_copied": 0,
            },
            "Reported": {
                "sampled": 1,
                "traceable": 0,
                "untraceable": 1,
                "no_source": 0,
                "unfetchable": 0,
                "exempt": 0,
                "source_copied": 0,
            },
            "Estimated": {
                "sampled": 1,
                "traceable": 0,
                "untraceable": 0,
                "no_source": 0,
                "unfetchable": 0,
                "exempt": 0,
                "source_copied": 1,
            },
        },
        "validation_rubric": {},
    }
    if include_evidence:
        payload["validation_rubric"] = {
            "claims_with_reviews": 2,
            "source_reviews": 2,
            "support": {"supported": 1, "unsupported": 1},
            "contradiction": {"none": 1, "partial": 1, "direct": 0, "unknown": 0},
            "source_independence": {"independent": 1, "first_party": 1, "unknown": 0},
            "source_authority": {"high": 1, "medium": 1, "low": 0, "unknown": 0},
            "reasoning_strength": {"strong": 1, "partial": 1, "weak": 0, "unknown": 0},
            "uncertainty_honesty": {"honest": 2, "overstated": 0, "understated": 0, "unknown": 0},
            "business_relevance": {"high": 1, "medium": 1, "low": 0, "unknown": 0},
        }
    if include_agreement:
        payload["judge_agreement"] = {
            "scope": "report",
            "local_model": "qwen2.5:14b",
            "compared": 2,
            "agreed": 2,
            "agreement": 1.0,
        }
    return payload


def _manifest(
    report_count: int,
    *,
    include_agreement: bool = True,
    include_evidence: bool = True,
    include_sidecars: bool = True,
    required_tags: list[str] | None = None,
    present_tags: list[str] | None = None,
) -> dict[str, object]:
    present = present_tags or []
    required = required_tags or []
    missing = [tag for tag in required if tag not in set(present)]
    reports = []
    for index in range(report_count):
        report: dict[str, object] = {
            "report_path": f"output/Company{index}_Strategic_Overview.md",
            "report_file": f"Company{index}_Strategic_Overview.md",
            "sidecar_path": f"output/Company{index}_Strategic_Overview.md.calibration.json",
            "sidecar_exists": include_sidecars,
            "claims_sampled": 2,
            "judgeable_claims": 2,
            "estimated_judge_calls": 2,
            "error": None,
            "coverage_tags": [present[index % len(present)]] if present else [],
        }
        if include_sidecars:
            report["sidecar"] = _sidecar(
                include_agreement=include_agreement,
                include_evidence=include_evidence,
            )
        reports.append(report)

    return {
        "manifest_format": "primr.calibration_pack.v1",
        "created_at_utc": "2026-06-27T00:00:00+00:00",
        "max_per_label": 10,
        "judge": {"kind": "cloud", "model": "fast-tier"},
        "totals": {
            "reports": report_count,
            "claims_sampled": report_count * 2,
            "judgeable_claims": report_count * 2,
            "estimated_judge_calls": report_count * 2,
            "estimated_cloud_cost_usd": round(report_count * 0.001, 4),
            "failures": 0,
            "sidecars_present": report_count if include_sidecars else 0,
        },
        "per_label": {},
        "existing_sidecar_per_label": {
            "Confirmed": {
                "sampled": report_count,
                "traceable": report_count,
                "untraceable": 0,
                "no_source": 0,
                "unfetchable": 0,
                "exempt": 0,
                "source_copied": 0,
            },
            "Reported": {
                "sampled": report_count,
                "traceable": 0,
                "untraceable": report_count,
                "no_source": 0,
                "unfetchable": 0,
                "exempt": 0,
                "source_copied": 0,
            },
            "Estimated": {
                "sampled": report_count,
                "traceable": 0,
                "untraceable": 0,
                "no_source": 0,
                "unfetchable": 0,
                "exempt": 0,
                "source_copied": report_count,
            },
        },
        "judge_agreement": None,
        "representation": {
            "selection_format": "primr.calibration_pack_selection.v1" if required else None,
            "selection_path": ".agent/calibration-selection.json" if required else None,
            "required_tags": required,
            "present_tags": present,
            "missing_tags": missing,
        },
        "reports": reports,
    }


def test_build_baseline_flags_small_unvalidated_pack() -> None:
    baseline = build_calibration_baseline(
        _manifest(1, include_agreement=False, include_evidence=False),
        minimum_reports=5,
    )

    assert baseline["ready"] is False
    assert baseline["status"] == "insufficient_reports"
    assert "insufficient_reports" in baseline["reasons"]
    assert "missing_evidence_reviews" in baseline["reasons"]
    assert "missing_judge_agreement" in baseline["reasons"]
    assert "missing_representative_selection" in baseline["reasons"]
    actions = baseline["next_actions"]
    assert actions["missing_reports"] == 4
    assert actions["missing_sidecars"] == 0
    assert actions["spend_preview_required"] is True
    assert "PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY" in actions["gate_policy"]
    assert {item["reason"] for item in actions["items"]} == {
        "insufficient_reports",
        "missing_evidence_reviews",
        "missing_judge_agreement",
        "missing_representative_selection",
    }
    assert actions["items"][0]["missing_reports"] == 4
    assert actions["commands"][0]["command"].startswith(
        "primr calibrate --calibrate-recent 5 --pack-selection-template"
    )
    assert actions["commands"][1]["command"].startswith(
        "primr calibrate --calibrate-recent 5 --dry-run"
    )
    assert "--judge-compare" in actions["commands"][2]["command"]


def test_build_baseline_ready_when_pack_has_required_evidence() -> None:
    baseline = build_calibration_baseline(
        _manifest(
            5,
            required_tags=["clean", "blocked_origin", "strategy_module"],
            present_tags=["clean", "blocked_origin", "strategy_module"],
        ),
        minimum_reports=5,
    )

    assert baseline["ready"] is True
    assert baseline["status"] == "ready"
    assert baseline["representation"]["selection_ready"] is True
    assert baseline["totals"]["reports_with_evidence_reviews"] == 5
    assert baseline["totals"]["reports_with_judge_agreement"] == 5
    assert baseline["traceability"]["Confirmed"]["traceability_rate"] == 1.0
    assert baseline["traceability"]["Reported"]["traceability_rate"] == 0.0
    assert baseline["inference_label_checks"]["estimated_source_copied"] == 5
    assert baseline["inference_label_checks"]["total_source_copied"] == 5
    assert baseline["evidence_review"]["source_reviews"] == 10
    assert baseline["evidence_review"]["support_rate"] == 0.5
    assert baseline["judge_agreement"]["compared"] == 10
    assert baseline["judge_agreement"]["agreement_rate"] == 1.0
    assert baseline["reports"][0]["evidence_source_reviews"] == 2
    assert baseline["reports"][0]["has_evidence_reviews"] is True
    assert baseline["reports"][0]["judge_agreement_compared"] == 2
    assert baseline["reports"][0]["has_judge_agreement"] is True
    assert baseline["reports"][0]["inference_source_copied"] == 1
    assert baseline["next_actions"]["spend_preview_required"] is False
    assert baseline["next_actions"]["items"] == [
        {
            "reason": "ready",
            "action": (
                "Review the measured floor with the pack context before selecting "
                "any hard threshold."
            ),
        }
    ]


def test_build_baseline_preserves_manifest_artifact_fingerprints() -> None:
    manifest = _manifest(
        5,
        required_tags=["clean"],
        present_tags=["clean"],
    )
    reports = manifest["reports"]
    assert isinstance(reports, list)
    first_report = reports[0]
    assert isinstance(first_report, dict)
    first_report.update(
        {
            "report_size_bytes": 123,
            "report_content_hash": "sha256:report",
            "sidecar_size_bytes": 456,
            "sidecar_content_hash": "sha256:sidecar",
        }
    )

    baseline = build_calibration_baseline(manifest, minimum_reports=5)
    inspection = inspect_calibration_baseline(baseline)

    assert baseline["reports"][0]["report_size_bytes"] == 123
    assert baseline["reports"][0]["report_content_hash"] == "sha256:report"
    assert baseline["reports"][0]["sidecar_size_bytes"] == 456
    assert baseline["reports"][0]["sidecar_content_hash"] == "sha256:sidecar"
    assert inspection["blockers"]["missing_sidecars"] == []


def test_inspect_baseline_flags_mutated_fingerprinted_artifacts(tmp_path: Path) -> None:
    report_path = tmp_path / "Acme_Strategic_Overview.md"
    sidecar_path = tmp_path / "Acme_Strategic_Overview.md.calibration.json"
    report_path.write_text("original report", encoding="utf-8")
    sidecar_path.write_text("{}", encoding="utf-8")
    report_fingerprint = artifact_fingerprint(report_path)
    sidecar_fingerprint = artifact_fingerprint(sidecar_path)

    manifest = _manifest(
        5,
        required_tags=["clean"],
        present_tags=["clean"],
    )
    reports = manifest["reports"]
    assert isinstance(reports, list)
    first_report = reports[0]
    assert isinstance(first_report, dict)
    first_report.update(
        {
            "report_path": report_path.as_posix(),
            "report_size_bytes": report_fingerprint["size_bytes"],
            "report_content_hash": report_fingerprint["content_hash"],
            "sidecar_path": sidecar_path.as_posix(),
            "sidecar_size_bytes": sidecar_fingerprint["size_bytes"],
            "sidecar_content_hash": sidecar_fingerprint["content_hash"],
        }
    )
    report_path.write_text("mutated report", encoding="utf-8")
    sidecar_path.unlink()

    baseline = build_calibration_baseline(manifest, minimum_reports=5)
    inspection = inspect_calibration_baseline(baseline)

    assert baseline["ready"] is True
    assert inspection["ready"] is False
    assert inspection["status"] == "fingerprinted_artifact_missing"
    assert "fingerprinted_artifact_missing" in inspection["reasons"]
    assert "artifact_fingerprint_mismatch" in inspection["reasons"]
    assert inspection["artifact_integrity"] == {
        "checked": 1,
        "unfingerprinted": 8,
        "missing": 1,
        "mismatched": 1,
    }
    assert inspection["blockers"]["fingerprinted_artifacts_missing"][0]["artifact"] == "sidecar"
    mismatch = inspection["blockers"]["artifact_fingerprint_mismatches"][0]
    assert mismatch["artifact"] == "report"
    assert mismatch["expected_content_hash"] == report_fingerprint["content_hash"]
    assert mismatch["actual_content_hash"] != report_fingerprint["content_hash"]


def test_build_baseline_requires_explicit_representative_selection() -> None:
    baseline = build_calibration_baseline(_manifest(5), minimum_reports=5)

    assert baseline["ready"] is False
    assert baseline["status"] == "missing_representative_selection"
    assert baseline["representation"]["selection_ready"] is False
    assert baseline["next_actions"]["missing_representative_selection"] is True
    assert any(
        item["reason"] == "missing_representative_selection"
        and "curated calibration pack selection" in item["action"]
        for item in baseline["next_actions"]["items"]
    )
    assert (
        "--pack-selection-template .agent/calibration-selection.json"
        in baseline["next_actions"]["commands"][0]["command"]
    )


def test_build_baseline_requires_per_report_evidence_review_coverage() -> None:
    manifest = _manifest(5)
    reports = manifest["reports"]
    assert isinstance(reports, list)
    first_report = reports[0]
    assert isinstance(first_report, dict)
    first_report["sidecar"] = _sidecar(include_evidence=False)

    baseline = build_calibration_baseline(manifest, minimum_reports=5)

    assert baseline["ready"] is False
    assert "missing_evidence_reviews" in baseline["reasons"]
    assert baseline["totals"]["reports_with_evidence_reviews"] == 4
    assert baseline["reports"][0]["evidence_source_reviews"] == 0
    assert baseline["reports"][0]["has_evidence_reviews"] is False
    assert baseline["next_actions"]["missing_evidence_review_reports"] == 1
    assert any(
        item["reason"] == "missing_evidence_reviews"
        and item["missing_reports"] == 1
        and "every selected report" in item["action"]
        for item in baseline["next_actions"]["items"]
    )


def test_build_baseline_requires_per_report_judge_agreement_coverage() -> None:
    manifest = _manifest(5)
    reports = manifest["reports"]
    assert isinstance(reports, list)
    first_report = reports[0]
    assert isinstance(first_report, dict)
    first_report["sidecar"] = _sidecar(include_agreement=False)

    baseline = build_calibration_baseline(manifest, minimum_reports=5)

    assert baseline["ready"] is False
    assert "missing_judge_agreement" in baseline["reasons"]
    assert baseline["totals"]["reports_with_judge_agreement"] == 4
    assert baseline["reports"][0]["judge_agreement_compared"] == 0
    assert baseline["reports"][0]["has_judge_agreement"] is False
    assert baseline["next_actions"]["missing_judge_agreement_reports"] == 1
    assert any(
        item["reason"] == "missing_judge_agreement"
        and item["missing_reports"] == 1
        and "every selected report" in item["action"]
        for item in baseline["next_actions"]["items"]
    )


def test_build_baseline_names_missing_sidecar_remediation() -> None:
    baseline = build_calibration_baseline(_manifest(5, include_sidecars=False), minimum_reports=5)

    assert baseline["ready"] is False
    assert "missing_calibration_sidecars" in baseline["reasons"]
    assert baseline["next_actions"]["missing_sidecars"] == 5
    assert baseline["next_actions"]["spend_preview_required"] is True
    assert any(
        item["reason"] == "missing_calibration_sidecars"
        and item["missing_sidecars"] == 5
        and "sidecar payload" in item["action"]
        for item in baseline["next_actions"]["items"]
    )


def test_build_baseline_requires_declared_representative_coverage() -> None:
    baseline = build_calibration_baseline(
        _manifest(
            5,
            required_tags=["clean", "blocked_origin", "strategy_module"],
            present_tags=["clean", "strategy_module"],
        ),
        minimum_reports=5,
    )

    assert baseline["ready"] is False
    assert "missing_representative_coverage" in baseline["reasons"]
    assert baseline["representation"]["missing_tags"] == ["blocked_origin"]
    assert baseline["next_actions"]["spend_preview_required"] is False
    assert baseline["next_actions"]["missing_representative_tags"] == ["blocked_origin"]
    assert (
        "--pack-selection .agent/calibration-selection.json"
        in baseline["next_actions"]["commands"][0]["command"]
    )
    assert any(
        item["reason"] == "missing_representative_coverage"
        and item["missing_tags"] == ["blocked_origin"]
        for item in baseline["next_actions"]["items"]
    )


def test_write_baseline_json_and_markdown(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pack.json"
    manifest_path.write_text(
        json.dumps(
            _manifest(
                5,
                required_tags=["clean", "blocked_origin"],
                present_tags=["clean", "blocked_origin"],
            )
        ),
        encoding="utf-8",
    )
    baseline_path = default_baseline_json_path(manifest_path)
    markdown_path = default_baseline_markdown_path(manifest_path)

    payload = write_calibration_baseline(
        baseline_path,
        manifest_path,
        markdown_path=markdown_path,
        minimum_reports=5,
    )

    assert json.loads(baseline_path.read_text(encoding="utf-8")) == payload
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Status: ready" in markdown
    assert "## Evidence Review" in markdown
    assert "## Inference Label Checks" in markdown
    assert "## Representative Coverage" in markdown
    assert "## Next Actions" in markdown
    assert "## Suggested Commands" in markdown
    assert "Judge agreement: 10 / 10 (100%)" in markdown
    assert "Evidence-reviewed reports: 5 / 5" in markdown
    assert "Judge-agreement reports: 5 / 5" in markdown
    assert "Representative selection: ready" in markdown
    assert (
        "| Report | Sidecar | Evidence Reviews | Judge Agreement | Claims | Judgeable | Tags |"
        in markdown
    )
    assert "| Company0_Strategic_Overview.md | yes | 2 | 2 | 2 | 2 | clean |" in markdown
    assert "Representative coverage: 2 / 2 required tags" in markdown
    assert "--pack-selection .agent/calibration-selection.json" in markdown
    assert "PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY" in markdown


def test_inspect_baseline_lists_report_level_blockers() -> None:
    manifest = _manifest(
        5,
        required_tags=["clean", "blocked_origin"],
        present_tags=["clean"],
    )
    reports = manifest["reports"]
    assert isinstance(reports, list)
    missing_sidecar = reports[0]
    missing_evidence = reports[1]
    missing_agreement = reports[2]
    failed = reports[3]
    assert isinstance(missing_sidecar, dict)
    assert isinstance(missing_evidence, dict)
    assert isinstance(missing_agreement, dict)
    assert isinstance(failed, dict)
    missing_sidecar["sidecar_exists"] = False
    missing_sidecar.pop("sidecar")
    missing_evidence["sidecar"] = _sidecar(include_evidence=False)
    missing_agreement["sidecar"] = _sidecar(include_agreement=False)
    failed["error"] = "calibration_failed: judge unavailable"
    manifest["totals"]["sidecars_present"] = 4
    manifest["totals"]["failures"] = 1

    baseline = build_calibration_baseline(manifest, minimum_reports=5)
    inspection = inspect_calibration_baseline(baseline)

    assert inspection["inspection_format"] == "primr.calibration_readiness_inspection.v1"
    assert inspection["ready"] is False
    assert inspection["counts"] == {
        "reports": 5,
        "minimum_reports": 5,
        "missing_reports": 0,
        "missing_sidecars": 1,
        "calibration_failures": 1,
        "missing_evidence_review_reports": 2,
        "missing_judge_agreement_reports": 2,
        "missing_representative_selection": False,
        "missing_representative_tags": 1,
    }
    assert inspection["blockers"]["missing_sidecars"][0]["report_file"] == (
        "Company0_Strategic_Overview.md"
    )
    assert inspection["blockers"]["missing_evidence_reviews"][0]["evidence_source_reviews"] == 0
    assert inspection["blockers"]["missing_judge_agreement"][0]["judge_agreement_compared"] == 0
    assert inspection["blockers"]["calibration_failures"][0]["error"] == (
        "calibration_failed: judge unavailable"
    )
    assert inspection["blockers"]["missing_representative_tags"] == ["blocked_origin"]
    assert "--dry-run" in inspection["commands"][0]["command"]


def test_read_calibration_baseline_rejects_wrong_artifact(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"baseline_format": "wrong"}), encoding="utf-8")

    with pytest.raises(ValueError, match=r"primr\.calibration_baseline\.v1"):
        read_calibration_baseline(path)


def test_rejects_wrong_manifest_format() -> None:
    with pytest.raises(ValueError, match=r"primr\.calibration_pack\.v1"):
        build_calibration_baseline({"manifest_format": "wrong"})
