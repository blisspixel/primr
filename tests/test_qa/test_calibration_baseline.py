"""Tests for calibration baseline readiness artifacts."""

import json
from pathlib import Path

import pytest

from primr.qa.calibration_baseline import (
    build_calibration_baseline,
    default_baseline_json_path,
    default_baseline_markdown_path,
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
            },
            "Reported": {
                "sampled": 1,
                "traceable": 0,
                "untraceable": 1,
                "no_source": 0,
                "unfetchable": 0,
                "exempt": 0,
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
) -> dict[str, object]:
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
            },
            "Reported": {
                "sampled": report_count,
                "traceable": 0,
                "untraceable": report_count,
                "no_source": 0,
                "unfetchable": 0,
                "exempt": 0,
            },
        },
        "judge_agreement": None,
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


def test_build_baseline_ready_when_pack_has_required_evidence() -> None:
    baseline = build_calibration_baseline(_manifest(5), minimum_reports=5)

    assert baseline["ready"] is True
    assert baseline["status"] == "ready"
    assert baseline["traceability"]["Confirmed"]["traceability_rate"] == 1.0
    assert baseline["traceability"]["Reported"]["traceability_rate"] == 0.0
    assert baseline["evidence_review"]["source_reviews"] == 10
    assert baseline["evidence_review"]["support_rate"] == 0.5
    assert baseline["judge_agreement"]["compared"] == 10
    assert baseline["judge_agreement"]["agreement_rate"] == 1.0


def test_write_baseline_json_and_markdown(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pack.json"
    manifest_path.write_text(json.dumps(_manifest(5)), encoding="utf-8")
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
    assert "Judge agreement: 10 / 10 (100%)" in markdown


def test_rejects_wrong_manifest_format() -> None:
    with pytest.raises(ValueError, match=r"primr\.calibration_pack\.v1"):
        build_calibration_baseline({"manifest_format": "wrong"})
