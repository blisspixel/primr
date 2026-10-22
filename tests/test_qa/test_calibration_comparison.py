"""Comparison measurements must describe the saved cloud report snapshot."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from primr.qa import label_calibration
from primr.qa.calibration_judge_agreement import compare_calibration_reports
from primr.qa.calibration_runner import JudgeSelection, compare_judges, sidecar_path_for
from primr.qa.label_calibration import CalibrationReport, calibrate_claims, extract_labeled_claims

REPORT = """## Executive Summary
Revenue reached $50M in 2025. (Confirmed) [cite: 1]

## Sources
[cite: 1] https://news.example/revenue
"""


@pytest.fixture(autouse=True)
def _no_default_egress(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Tests require injected fetch and judge functions")

    for name in ("_default_fetch", "_default_judge", "_default_review"):
        monkeypatch.setattr(label_calibration, name, blocked)
    return


def _report(root: Path, name: str = "Acme") -> Path:
    path = root / f"{name}_Strategic_Overview.md"
    path.write_text(REPORT, encoding="utf-8")
    return path


def test_failed_cloud_pass_is_not_retried_or_compared(tmp_path: Path) -> None:
    path = _report(tmp_path)
    cloud = Mock(side_effect=[RuntimeError("cloud unavailable"), True])
    local = Mock(return_value=True)

    outcomes, agreement = compare_judges(
        [path],
        local_selection=JudgeSelection(kind="local", model="example-local", judge_fn=local),
        fetch_fn=lambda _url: "Revenue reached $50M in 2025.",
        cloud_judge_fn=cloud,
    )

    assert cloud.call_count == 1
    local.assert_not_called()
    assert outcomes[0].error is not None
    assert "cloud unavailable" in outcomes[0].error
    assert agreement.compared == 0
    assert agreement.agreement is None
    assert not sidecar_path_for(path).exists()


def test_report_changed_by_local_judge_is_not_counted(tmp_path: Path) -> None:
    path = _report(tmp_path)

    def local(_claim: str, _source: str) -> bool:
        path.write_text(REPORT.replace("$50M", "$900M"), encoding="utf-8")
        return True

    outcomes, agreement = compare_judges(
        [path],
        local_selection=JudgeSelection(kind="local", model="example-local", judge_fn=local),
        fetch_fn=lambda _url: "Revenue reached $50M in 2025.",
        cloud_judge_fn=lambda _claim, _source: True,
    )

    assert outcomes[0].error == "comparison_artifact_changed"
    assert agreement.compared == 0
    payload = json.loads(sidecar_path_for(path).read_text(encoding="utf-8"))
    assert "judge_agreement" not in payload


def test_local_failure_keeps_cloud_result_and_continues_batch(tmp_path: Path) -> None:
    paths = [_report(tmp_path, name) for name in ("Acme", "ExampleCo")]
    local = Mock(side_effect=[RuntimeError("local unavailable"), True])
    cloud = Mock(return_value=True)

    outcomes, agreement = compare_judges(
        paths,
        local_selection=JudgeSelection(kind="local", model="example-local", judge_fn=local),
        fetch_fn=lambda _url: "Revenue reached $50M in 2025.",
        cloud_judge_fn=cloud,
    )

    assert len(outcomes) == 2
    assert outcomes[0].error is not None
    assert "local unavailable" in outcomes[0].error
    assert outcomes[1].error is None
    assert agreement.compared == agreement.agreed == 1
    failed = json.loads(sidecar_path_for(paths[0]).read_text(encoding="utf-8"))
    assert failed["per_label"]["Confirmed"]["traceable"] == 1
    assert "judge_agreement" not in failed


@pytest.mark.parametrize(
    "local",
    [
        JudgeSelection(kind="local", model="example-local"),
        JudgeSelection(kind="cloud", model="example-local", judge_fn=lambda _c, _s: True),
        JudgeSelection(kind="local", model="", judge_fn=lambda _c, _s: True),
    ],
)
def test_invalid_local_plan_fails_before_cloud_calls(tmp_path: Path, local: JudgeSelection) -> None:
    cloud = Mock(return_value=True)
    with pytest.raises(ValueError, match="local judge"):
        compare_judges(
            [_report(tmp_path)],
            local_selection=local,
            fetch_fn=lambda _url: "text",
            cloud_judge_fn=cloud,
        )
    cloud.assert_not_called()


def test_unreadable_report_does_not_abort_comparison_batch(tmp_path: Path) -> None:
    bad = tmp_path / "Invalid_Strategic_Overview.md"
    bad.write_bytes(b"\xff\xfe")
    good = _report(tmp_path)
    _, agreement = compare_judges(
        [bad, good],
        local_selection=JudgeSelection(
            kind="local", model="example-local", judge_fn=lambda _claim, _source: True
        ),
        fetch_fn=lambda _url: "text",
        cloud_judge_fn=lambda _claim, _source: True,
    )
    assert agreement.compared == agreement.agreed == 1


def test_local_judge_uses_full_original_claim_and_frozen_capture(tmp_path: Path) -> None:
    path = _report(tmp_path)
    full_claim = "Revenue " + "grew steadily " * 40 + "to $50M in 2025."
    path.write_text(REPORT.replace("Revenue reached $50M in 2025.", full_claim), encoding="utf-8")
    original_source = "Revenue reached $50M in 2025."
    captures = {"https://news.example/revenue": original_source}
    local_calls: list[tuple[str, str]] = []

    def cloud(_claim: str, _source: str) -> bool:
        captures["https://news.example/revenue"] = "Revenue reached $900M in 2025."
        return True

    def local(claim: str, source: str) -> bool:
        local_calls.append((claim, source))
        return True

    _, agreement = compare_judges(
        [path],
        local_selection=JudgeSelection(kind="local", model="example-local", judge_fn=local),
        cloud_judge_fn=cloud,
        captured_sources=captures,
    )

    assert agreement.compared == agreement.agreed == 1
    assert len(local_calls) == 1
    assert full_claim in local_calls[0][0]
    assert local_calls[0][1] == original_source


def test_sidecar_changed_by_local_judge_is_not_overwritten(tmp_path: Path) -> None:
    path = _report(tmp_path)
    replacement = ""

    def local(_claim: str, _source: str) -> bool:
        nonlocal replacement
        payload = json.loads(sidecar_path_for(path).read_text(encoding="utf-8"))
        payload["judge"]["model"] = "different-run"
        replacement = json.dumps(payload)
        sidecar_path_for(path).write_text(replacement, encoding="utf-8")
        return True

    outcomes, agreement = compare_judges(
        [path],
        local_selection=JudgeSelection(kind="local", model="example-local", judge_fn=local),
        fetch_fn=lambda _url: "text",
        cloud_judge_fn=lambda _claim, _source: True,
    )

    assert outcomes[0].error == "comparison_artifact_changed"
    assert agreement.compared == 0
    assert sidecar_path_for(path).read_text(encoding="utf-8") == replacement


def test_comparison_fetches_once_and_judges_cloud_once_per_pair(tmp_path: Path) -> None:
    path = _report(tmp_path)
    fetch = Mock(return_value="Revenue reached $50M in 2025.")
    cloud = Mock(return_value=True)
    local = Mock(return_value=False)
    _, agreement = compare_judges(
        [path],
        local_selection=JudgeSelection(kind="local", model="example-local", judge_fn=local),
        fetch_fn=fetch,
        cloud_judge_fn=cloud,
    )
    fetch.assert_called_once_with("https://news.example/revenue")
    assert cloud.call_count == local.call_count == 1
    assert cloud.call_args == local.call_args
    assert agreement.compared == 1
    assert agreement.agreed == 0


@pytest.mark.parametrize("different_length", [False, True])
def test_verdict_comparison_rejects_different_claim_samples(different_length: bool) -> None:
    claims = extract_labeled_claims(REPORT)
    cloud = calibrate_claims(claims, fetch_fn=lambda _url: "text", judge_fn=lambda _c, _s: True)
    local = CalibrationReport(
        results=[]
        if different_length
        else [replace(cloud.results[0], claim=replace(claims[0], sentence="Different claim"))]
    )
    with pytest.raises(ValueError):
        compare_calibration_reports(cloud, local, local_model="example-local")
