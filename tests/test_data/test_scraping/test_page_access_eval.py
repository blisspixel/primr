"""Tests for offline page-access classifier eval helpers."""

import base64
import json

import pytest

from primr.data.scraping.models import PageAccessAssessment, PageAccessState
from primr.data.scraping.page_access_eval import (
    PageAccessEvalCase,
    PageAccessPrediction,
    evaluate_page_access_cases,
    evaluate_page_access_fixture_file,
    page_access_eval_payload,
    prediction_from_access_assessment,
    score_page_access_predictions,
    write_page_access_eval_json,
    write_page_access_eval_markdown,
)
from primr.data.scraping.page_snapshots import compare_render_snapshots

REAL_ABOUT_PAGE = b"""<!doctype html>
<html>
<head>
  <title>About ExampleCo</title>
  <script type="application/ld+json">{"@type":"Organization"}</script>
</head>
<body>
  <header><nav><a>About</a><a>Products</a><a>News</a><a>Contact</a></nav></header>
  <main>
    <h1>About ExampleCo</h1>
    <p>ExampleCo builds practical field equipment for industrial customers.</p>
    <p>Our company operates service centers and a partner network across North America.</p>
  </main>
  <footer><a>Careers</a><a>Support</a><a>Investors</a><a>Privacy</a></footer>
</body>
</html>"""


PROTECTED_INTERSTITIAL = b"""<!doctype html>
<html>
<head><title>Please wait</title></head>
<body>
  <script>window.KPSDK={};</script>
  <script src="/challenge/ips.js?x-kpsdk-im=test"></script>
  <iframe src="javascript:;" style="display:none"></iframe>
  Please wait while we verify your browser.
</body>
</html>"""


def test_evaluate_page_access_cases_scores_fixture_confusion_matrix():
    snapshot = compare_render_snapshots(
        initial_html="<html><body>Checking your browser</body></html>",
        final_html="<html><body>" + ("ExampleCo product support details. " * 30) + "</body></html>",
    )
    report = evaluate_page_access_cases(
        [
            PageAccessEvalCase(
                case_id="real-about",
                expected_real_content=True,
                html=REAL_ABOUT_PAGE,
                url="https://www.example.com/about",
                http_status=200,
                expected_markers=("exampleco",),
                tags=("protected-site", "real"),
            ),
            PageAccessEvalCase(
                case_id="protected-shell",
                expected_real_content=False,
                html=PROTECTED_INTERSTITIAL,
                url="https://www.example.com/",
                http_status=200,
                tags=("protected-site", "blocked"),
            ),
            PageAccessEvalCase(
                case_id="browser-cleared",
                expected_real_content=True,
                html=b"<html><body><main><h1>ExampleCo</h1></main></body></html>",
                url="https://www.example.com/",
                http_status=200,
                expected_markers=("exampleco",),
                render_snapshot=snapshot,
                tags=("protected-site", "browser"),
            ),
        ]
    )

    assert report.metrics.sample_count == 3
    assert report.metrics.true_positive == 2
    assert report.metrics.true_negative == 1
    assert report.metrics.false_positive == 0
    assert report.metrics.false_negative == 0
    assert report.metrics.false_positive_rate == 0.0
    assert report.metrics.false_negative_rate == 0.0
    assert report.by_tag["protected-site"].sample_count == 3
    assert report.false_positive_case_ids == ()
    assert report.false_negative_case_ids == ()


def test_score_page_access_predictions_reports_false_positive_and_false_negative():
    report = score_page_access_predictions(
        [
            PageAccessPrediction(
                case_id="tp",
                expected_real_content=True,
                predicted_state=PageAccessState.SUCCESS,
                confidence=0.8,
                tags=("protected",),
            ),
            PageAccessPrediction(
                case_id="tn",
                expected_real_content=False,
                predicted_state=PageAccessState.SOFT_BLOCK,
                confidence=0.9,
                tags=("protected",),
            ),
            PageAccessPrediction(
                case_id="fp",
                expected_real_content=False,
                predicted_state=PageAccessState.SUCCESS,
                confidence=0.7,
                tags=("protected",),
            ),
            PageAccessPrediction(
                case_id="fn",
                expected_real_content=True,
                predicted_state=PageAccessState.UNKNOWN,
                confidence=0.4,
                tags=("protected",),
            ),
        ]
    )

    assert report.metrics.true_positive == 1
    assert report.metrics.true_negative == 1
    assert report.metrics.false_positive == 1
    assert report.metrics.false_negative == 1
    assert report.metrics.accuracy == 0.5
    assert report.metrics.false_positive_rate == 0.5
    assert report.metrics.false_negative_rate == 0.5
    assert report.false_positive_case_ids == ("fp",)
    assert report.false_negative_case_ids == ("fn",)


def test_prediction_from_access_assessment_accepts_trace_dicts_and_missing_entries():
    success = prediction_from_access_assessment(
        case_id="trace-success",
        expected_real_content=True,
        access_assessment={"state": "success", "confidence": 0.88, "reason": "Observed real page"},
        tags=("trace",),
    )
    missing = prediction_from_access_assessment(
        case_id="trace-missing",
        expected_real_content=False,
        access_assessment=None,
        tags=("trace",),
    )
    invalid = prediction_from_access_assessment(
        case_id="trace-invalid",
        expected_real_content=False,
        access_assessment={"state": "not-a-state", "confidence": "high"},
        tags=("trace",),
    )
    dataclass_input = prediction_from_access_assessment(
        case_id="trace-dataclass",
        expected_real_content=False,
        access_assessment=PageAccessAssessment(
            state=PageAccessState.SOFT_BLOCK,
            confidence=0.92,
            reason="Challenge/interstitial shell detected",
        ),
    )

    assert success.predicted_state == PageAccessState.SUCCESS
    assert missing.predicted_state == PageAccessState.UNKNOWN
    assert missing.reason == "missing_access_assessment"
    assert invalid.predicted_state == PageAccessState.UNKNOWN
    assert invalid.confidence == 0.0
    assert dataclass_input.predicted_state == PageAccessState.SOFT_BLOCK


def test_page_access_eval_artifacts_are_body_free(tmp_path):
    report = evaluate_page_access_cases(
        [
            PageAccessEvalCase(
                case_id="real-about",
                expected_real_content=True,
                html=REAL_ABOUT_PAGE,
                url="https://www.example.com/private/path?token=abc",
                http_status=200,
                expected_markers=("exampleco",),
                tags=("fixture",),
            )
        ]
    )

    json_path = tmp_path / "page_access_eval.json"
    md_path = tmp_path / "page_access_eval.md"
    write_page_access_eval_json(json_path, report)
    write_page_access_eval_markdown(md_path, report)

    payload_text = json_path.read_text(encoding="utf-8")
    markdown_text = md_path.read_text(encoding="utf-8")
    payload = json.loads(payload_text)

    assert payload["schema_version"] == 1
    assert payload["metrics"]["sample_count"] == 1
    assert "ExampleCo builds practical field equipment" not in payload_text
    assert "https://www.example.com/private/path" not in payload_text
    assert "token=abc" not in payload_text
    assert "ExampleCo builds practical field equipment" not in markdown_text
    assert "https://www.example.com/private/path" not in markdown_text
    assert "token=abc" not in markdown_text


def test_page_access_eval_payload_includes_case_ids_not_raw_inputs():
    report = score_page_access_predictions(
        [
            PageAccessPrediction(
                case_id="fp",
                expected_real_content=False,
                predicted_state=PageAccessState.SUCCESS,
            ),
            PageAccessPrediction(
                case_id="fn",
                expected_real_content=True,
                predicted_state=PageAccessState.THIN_CONTENT,
            ),
        ]
    )

    payload = page_access_eval_payload(report)

    assert payload["false_positive_case_ids"] == ["fp"]
    assert payload["false_negative_case_ids"] == ["fn"]
    assert "rows" in payload


def test_evaluate_page_access_fixture_file_scores_html_and_trace_predictions(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "base64-real",
                        "expected_real_content": True,
                        "html_base64": base64.b64encode(REAL_ABOUT_PAGE).decode("ascii"),
                        "url": "https://www.example.com/about?token=secret",
                        "http_status": 200,
                        "expected_markers": ["exampleco"],
                        "tags": ["protected-site", "real"],
                    },
                    {
                        "case_id": "trace-block",
                        "expected_real_content": False,
                        "access_assessment": {
                            "state": "soft_block",
                            "confidence": 0.91,
                            "reason": "Challenge/interstitial shell detected",
                        },
                        "tags": ["protected-site", "trace"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_page_access_fixture_file(fixture)
    payload_text = json.dumps(page_access_eval_payload(report))

    assert report.metrics.sample_count == 2
    assert report.metrics.false_positive == 0
    assert report.metrics.false_negative == 0
    assert report.by_tag["protected-site"].sample_count == 2
    assert "ExampleCo builds practical field equipment" not in payload_text
    assert "token=secret" not in payload_text


def test_evaluate_page_access_fixture_file_rejects_missing_labels(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text('{"cases": [{"case_id": "missing-label"}]}', encoding="utf-8")

    with pytest.raises(ValueError, match="expected_real_content"):
        evaluate_page_access_fixture_file(fixture)
