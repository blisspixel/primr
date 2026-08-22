"""Unit tests for _handle_eval body branches in primr.core.cli."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core.cli import CLIConfig, Command, _handle_eval
from primr.core.local_stage_eval import WebsiteSummaryEvalRow, WebsiteSummarySemanticEvalRow


def _config(**overrides):
    defaults = {
        "command": Command.EVAL,
        "eval_id": "eval-2026-r1",
        "eval_baseline": "full",
        "eval_profiles": ("full", "lite"),
    }
    defaults.update(overrides)
    return CLIConfig(**defaults)


@pytest.fixture
def stub_eval_deps(monkeypatch, tmp_path):
    """Mock all the model_eval imports."""
    monkeypatch.setattr(
        "primr.core.model_eval.get_eval_profile",
        lambda p: MagicMock(estimated_cost_usd=1.5) if p in ("full", "lite", "fast") else None,
    )
    monkeypatch.setattr(
        "primr.core.model_eval.list_eval_profile_names",
        lambda: ["full", "lite", "fast"],
    )
    monkeypatch.setattr(
        "primr.core.model_eval._safe_eval_dir",
        lambda root, eid: Path(root) / eid,
    )
    monkeypatch.setattr(
        "primr.core.model_eval.auto_stage_existing_reports",
        MagicMock(return_value={}),
    )
    monkeypatch.setattr(
        "primr.core.model_eval.evaluate_outputs",
        MagicMock(
            return_value=MagicMock(
                missing_pairs=[],
                summary="",
            )
        ),
    )
    monkeypatch.setattr(
        "primr.core.model_eval.write_llm_judge_report",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "primr.core.model_eval.write_fast_feedback_guidance",
        MagicMock(return_value=None),
    )
    return tmp_path


class TestEvalBody:
    def test_runs_through_validation(self, stub_eval_deps, tmp_path):
        """Happy path: all validations pass and eval runs."""
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path),
            )
        )
        # Returns 0 if evaluation succeeded, 1 otherwise. Should be 0 for empty manifest path.
        assert result in (0, 1)

    def test_auto_stage_runs(self, stub_eval_deps, tmp_path, monkeypatch):
        stage_mock = MagicMock(return_value={"full": ["a", "b"]})
        monkeypatch.setattr(
            "primr.core.model_eval.auto_stage_existing_reports",
            stage_mock,
        )
        _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_auto_stage=True,
                eval_source_dir=str(tmp_path / "source"),
                eval_root=str(tmp_path),
            )
        )
        stage_mock.assert_called_once()

    def test_run_missing_without_manifest_returns_1(self, stub_eval_deps, tmp_path):
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_run_missing=True,
                eval_max_new_runs=5,
                eval_max_estimated_cost=10.0,
                eval_root=str(tmp_path),
                eval_manifest=None,
            )
        )
        assert result == 1

    def test_run_missing_zero_new_runs_returns_1(self, stub_eval_deps, tmp_path):
        manifest = tmp_path / "manifest.csv"
        manifest.write_text("company,website\nExampleCo,https://x.example\n")
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_run_missing=True,
                eval_max_new_runs=0,
                eval_max_estimated_cost=10.0,
                eval_root=str(tmp_path),
                eval_manifest=str(manifest),
            )
        )
        assert result == 1

    def test_run_missing_zero_max_cost_returns_1(self, stub_eval_deps, tmp_path):
        manifest = tmp_path / "manifest.csv"
        manifest.write_text("company,website\nExampleCo,https://x.example\n")
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_run_missing=True,
                eval_max_new_runs=5,
                eval_max_estimated_cost=0.0,
                eval_root=str(tmp_path),
                eval_manifest=str(manifest),
            )
        )
        assert result == 1

    @pytest.mark.parametrize("cap", [float("nan"), float("inf")])
    def test_run_missing_nonfinite_max_cost_returns_1(self, stub_eval_deps, tmp_path, cap):
        manifest = tmp_path / "manifest.csv"
        manifest.write_text("company,website\nExampleCo,https://x.example\n")

        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_run_missing=True,
                eval_max_new_runs=5,
                eval_max_estimated_cost=cap,
                eval_root=str(tmp_path),
                eval_manifest=str(manifest),
            )
        )

        assert result == 1

    @pytest.mark.parametrize("cap", [float("nan"), float("inf")])
    def test_grok_judge_nonfinite_max_cost_returns_1(self, stub_eval_deps, tmp_path, cap):
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_llm_judge=True,
                eval_judge_provider="grok",
                eval_judge_max_cost=cap,
                eval_root=str(tmp_path),
            )
        )

        assert result == 1

    def test_company_creates_manifest(self, stub_eval_deps, tmp_path):
        _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_company="ExampleCo",
                eval_root=str(tmp_path),
            )
        )
        # Should have written eval_company_manifest.csv
        manifest = tmp_path / "eval-r1" / "eval_company_manifest.csv"
        assert manifest.exists()
        assert "ExampleCo" in manifest.read_text(encoding="utf-8")

    def test_stage_scorecard_writes_review_only_artifacts(self, stub_eval_deps, tmp_path):
        working_root = tmp_path / "working"
        run_state = working_root / "ExampleCo" / "run-001" / "_run_state.json"
        run_state.parent.mkdir(parents=True)
        run_state.write_text(
            json.dumps(
                {
                    "report_body": "must not be copied",
                    "stage_routes": [
                        {
                            "stage_id": "fast.scrape_summary",
                            "backend_id": "gemini-flash",
                            "backend_kind": "cloud_api",
                            "billing_mode": "api_dollars",
                            "inference_profile": "cloud",
                            "outcome": "selected",
                            "duration_seconds": 1.25,
                            "actual_input_tokens": 50,
                            "actual_output_tokens": 20,
                            "actual_cost_usd": 0.0002,
                            "prompt": "must not be copied",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        quality_path = tmp_path / "quality.json"
        quality_path.write_text(
            json.dumps(
                {
                    "quality_evidence": [
                        {
                            "stage_id": "fast.scrape_summary",
                            "backend_id": "gemini-flash",
                            "quality_score": 91.0,
                            "sample_size": 2,
                            "source": "semantic-eval",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path / "evals"),
                eval_stage_scorecard=True,
                eval_stage_quality=str(quality_path),
                eval_stage_route_root=str(working_root),
                eval_stage_id="fast.scrape_summary",
            )
        )

        assert result == 0
        scorecard_path = tmp_path / "evals" / "eval-r1" / "stage_eval_scorecard.json"
        markdown_path = tmp_path / "evals" / "eval-r1" / "stage_eval_scorecard.md"
        payload = json.loads(scorecard_path.read_text(encoding="utf-8"))
        assert payload["decision_policy"] == "candidate_for_human_review_only"
        assert payload["rows"][0]["review_status"] == "candidate_for_human_review"
        assert "must not be copied" not in scorecard_path.read_text(encoding="utf-8")
        assert "must not be copied" not in markdown_path.read_text(encoding="utf-8")

    def test_stage_scorecard_requires_quality_evidence_path(self, stub_eval_deps, tmp_path):
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path),
                eval_stage_scorecard=True,
                eval_stage_quality=None,
            )
        )

        assert result == 1

    def test_source_relevance_fixture_generates_quality_evidence_for_scorecard(
        self, stub_eval_deps, tmp_path
    ):
        fixture = tmp_path / "source_relevance_fixture.json"
        fixture.write_text(
            json.dumps(
                {
                    "cases": [
                        {
                            "case_id": "case-001",
                            "company": "ExampleCo",
                            "source_count": 3,
                            "source_text": "must not be copied",
                            "expected_keep": [1, 3],
                            "candidates": [
                                {"backend_id": "codex-host", "kept": [1, 3]},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        working_root = tmp_path / "working"
        run_state = working_root / "ExampleCo" / "run-001" / "_run_state.json"
        run_state.parent.mkdir(parents=True)
        run_state.write_text(
            json.dumps(
                {
                    "stage_routes": [
                        {
                            "stage_id": "fast.source_relevance",
                            "backend_id": "codex-host",
                            "backend_kind": "host_agent",
                            "billing_mode": "host_plan",
                            "inference_profile": "agent",
                            "outcome": "selected",
                            "duration_seconds": 3.0,
                            "actual_cost_usd": 0.0,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path / "evals"),
                eval_source_relevance_fixture=str(fixture),
                eval_stage_scorecard=True,
                eval_stage_quality=None,
                eval_stage_route_root=str(working_root),
                eval_stage_id="fast.source_relevance",
            )
        )

        assert result == 0
        quality_path = (
            tmp_path
            / "evals"
            / "eval-r1"
            / "source_relevance_stage"
            / "source_relevance_stage_quality_evidence.json"
        )
        scorecard_path = tmp_path / "evals" / "eval-r1" / "stage_eval_scorecard.json"
        quality_text = quality_path.read_text(encoding="utf-8")
        assert "must not be copied" not in quality_text
        quality_payload = json.loads(quality_text)
        assert quality_payload["quality_evidence"][0]["quality_score"] == 100.0
        scorecard_payload = json.loads(scorecard_path.read_text(encoding="utf-8"))
        assert scorecard_payload["rows"][0]["stage_id"] == "fast.source_relevance"
        assert scorecard_payload["rows"][0]["review_status"] == "candidate_for_human_review"

    def test_page_access_fixture_generates_body_free_eval_artifacts(self, stub_eval_deps, tmp_path):
        fixture = tmp_path / "page_access_fixture.json"
        fixture.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "cases": [
                        {
                            "case_id": "real-about",
                            "expected_real_content": True,
                            "html": (
                                "<html><head><title>About ExampleCo</title>"
                                '<script type="application/ld+json">{"@type":"Organization"}</script>'
                                "</head><body><header><nav><a>About</a><a>Products</a>"
                                "<a>News</a><a>Contact</a></nav></header><main>"
                                "<h1>About ExampleCo</h1>"
                                "<p>ExampleCo builds practical field equipment for "
                                "industrial customers.</p>"
                                "<p>Our company operates service centers and a partner "
                                "network across North America.</p></main>"
                                "<footer><a>Careers</a><a>Support</a><a>Investors</a>"
                                "<a>Privacy</a></footer></body></html>"
                            ),
                            "url": "https://www.example.com/private/path?token=secret",
                            "http_status": 200,
                            "expected_markers": ["exampleco"],
                            "tags": ["sanitized-real-trace"],
                        },
                        {
                            "case_id": "trace-blocked",
                            "expected_real_content": False,
                            "access_assessment": {
                                "state": "soft_block",
                                "confidence": 0.96,
                                "reason": "Challenge/interstitial shell detected",
                            },
                            "tags": ["sanitized-protected-trace"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path / "evals"),
                eval_page_access_fixture=str(fixture),
            )
        )

        assert result == 0
        stage_root = tmp_path / "evals" / "eval-r1" / "page_access_stage"
        report_path = stage_root / "page_access_stage_eval.json"
        markdown_path = stage_root / "page_access_stage_eval.md"
        quality_path = stage_root / "page_access_stage_quality_evidence.json"
        report_text = report_path.read_text(encoding="utf-8")
        markdown_text = markdown_path.read_text(encoding="utf-8")
        quality_payload = json.loads(quality_path.read_text(encoding="utf-8"))

        assert "ExampleCo builds practical field equipment" not in report_text
        assert "https://www.example.com/private/path" not in report_text
        assert "token=secret" not in report_text
        assert "ExampleCo builds practical field equipment" not in markdown_text
        assert "token=secret" not in markdown_text
        report_payload = json.loads(report_text)
        assert report_payload["metrics"]["sample_count"] == 2
        assert report_payload["false_positive_case_ids"] == []
        assert report_payload["false_negative_case_ids"] == []
        assert quality_payload["quality_evidence"][0]["stage_id"] == "scraping.page_access"
        assert quality_payload["quality_evidence"][0]["sample_size"] == 2

    def test_page_access_fixture_invalid_file_returns_1(self, stub_eval_deps, tmp_path):
        fixture = tmp_path / "page_access_fixture.json"
        fixture.write_text('{"cases": [{"case_id": "missing-label"}]}', encoding="utf-8")

        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path / "evals"),
                eval_page_access_fixture=str(fixture),
            )
        )

        assert result == 1

    def test_local_stage_eval_generates_quality_evidence_for_scorecard(
        self, stub_eval_deps, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "primr.core.cli._resolve_local_judge_models",
            lambda config: (["qwen3:30b"], []),
        )
        monkeypatch.setattr(
            "primr.core.local_stage_eval.find_latest_website_summary_eval_inputs",
            MagicMock(return_value=[SimpleNamespace(company="ExampleCo")]),
        )
        stage_row = WebsiteSummaryEvalRow(
            company="ExampleCo",
            model="qwen3:30b",
            working_dir="working/ExampleCo/run-001",
            input_pages=2,
            local_summary_path="must-not-be-copied.local.txt",
            baseline_summary_path="must-not-be-copied.baseline.txt",
            baseline_words=100,
            local_words=90,
            baseline_source_sections=2,
            local_source_sections=2,
            baseline_source_citations=1,
            local_source_citations=1,
            baseline_open_questions=2,
            local_open_questions=2,
            baseline_has_synthesis=True,
            local_has_synthesis=True,
            source_section_ratio=100.0,
            citation_ratio=100.0,
            open_questions_ratio=100.0,
            word_ratio=90.0,
            completeness_score=96.0,
        )
        monkeypatch.setattr(
            "primr.core.local_stage_eval.run_local_website_summary_stage_eval",
            MagicMock(return_value=[stage_row]),
        )

        working_root = tmp_path / "working"
        run_state = working_root / "ExampleCo" / "run-001" / "_run_state.json"
        run_state.parent.mkdir(parents=True)
        run_state.write_text(
            json.dumps(
                {
                    "stage_routes": [
                        {
                            "stage_id": "fast.scrape_summary",
                            "backend_id": "qwen3:30b",
                            "backend_kind": "local",
                            "billing_mode": "local_runtime",
                            "inference_profile": "local",
                            "outcome": "selected",
                            "duration_seconds": 2.0,
                            "actual_cost_usd": 0.0,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path / "evals"),
                eval_company="ExampleCo",
                eval_local_stage="website-summary",
                eval_stage_scorecard=True,
                eval_stage_quality=None,
                eval_stage_route_root=str(working_root),
                eval_stage_id="fast.scrape_summary",
                eval_judge_models=("qwen3:30b",),
            )
        )

        assert result == 0
        quality_path = (
            tmp_path
            / "evals"
            / "eval-r1"
            / "website_summary_stage"
            / "website_summary_stage_quality_evidence.json"
        )
        scorecard_path = tmp_path / "evals" / "eval-r1" / "stage_eval_scorecard.json"
        quality_text = quality_path.read_text(encoding="utf-8")
        assert "must-not-be-copied" not in quality_text
        quality_payload = json.loads(quality_text)
        assert quality_payload["quality_evidence"][0]["quality_score"] == 96.0
        scorecard_payload = json.loads(scorecard_path.read_text(encoding="utf-8"))
        assert scorecard_payload["rows"][0]["review_status"] == "candidate_for_human_review"

    def test_local_stage_eval_uses_semantic_evidence_for_same_command_scorecard(
        self, stub_eval_deps, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "primr.core.cli._resolve_local_judge_models",
            lambda config: (["qwen3:30b"], []),
        )
        monkeypatch.setattr(
            "primr.core.local_stage_eval.find_latest_website_summary_eval_inputs",
            MagicMock(return_value=[SimpleNamespace(company="ExampleCo")]),
        )
        stage_row = WebsiteSummaryEvalRow(
            company="ExampleCo",
            model="qwen3:30b",
            working_dir="working/ExampleCo/run-001",
            input_pages=2,
            local_summary_path="must-not-be-copied.local.txt",
            baseline_summary_path="must-not-be-copied.baseline.txt",
            baseline_words=100,
            local_words=90,
            baseline_source_sections=2,
            local_source_sections=2,
            baseline_source_citations=1,
            local_source_citations=1,
            baseline_open_questions=2,
            local_open_questions=2,
            baseline_has_synthesis=True,
            local_has_synthesis=True,
            source_section_ratio=100.0,
            citation_ratio=100.0,
            open_questions_ratio=100.0,
            word_ratio=90.0,
            completeness_score=96.0,
        )
        monkeypatch.setattr(
            "primr.core.local_stage_eval.run_local_website_summary_stage_eval",
            MagicMock(return_value=[stage_row]),
        )
        semantic_calls = []

        def fake_semantic_eval(*, rows, judge_model, **_kwargs):
            assert rows == [stage_row]
            semantic_calls.append(judge_model)
            score = 91.0 if judge_model == "llama3.1:70b" else 89.0
            return [
                WebsiteSummarySemanticEvalRow(
                    company="ExampleCo",
                    model="qwen3:30b",
                    judge_model=judge_model,
                    working_dir="working/ExampleCo/run-001",
                    semantic_score=score,
                    aspects={
                        "strategic_coverage": score,
                        "factual_alignment": score,
                        "evidence_usefulness": score,
                        "uncertainty_calibration": score,
                    },
                    rationale="Candidate keeps the useful strategic evidence.",
                    response_valid=True,
                    input_tokens=120,
                    output_tokens=40,
                )
            ]

        monkeypatch.setattr(
            "primr.core.local_stage_eval.run_local_website_summary_semantic_eval",
            fake_semantic_eval,
        )

        working_root = tmp_path / "working"
        run_state = working_root / "ExampleCo" / "run-001" / "_run_state.json"
        run_state.parent.mkdir(parents=True)
        run_state.write_text(
            json.dumps(
                {
                    "stage_routes": [
                        {
                            "stage_id": "fast.scrape_summary",
                            "backend_id": "qwen3:30b",
                            "backend_kind": "local",
                            "billing_mode": "local_runtime",
                            "inference_profile": "local",
                            "outcome": "selected",
                            "duration_seconds": 2.0,
                            "actual_cost_usd": 0.0,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path / "evals"),
                eval_company="ExampleCo",
                eval_local_stage="website-summary",
                eval_stage_semantic_judge=True,
                eval_stage_semantic_judge_model="llama3.1:70b,qwen2.5:14b",
                eval_stage_scorecard=True,
                eval_stage_quality=None,
                eval_stage_route_root=str(working_root),
                eval_stage_id="fast.scrape_summary",
                eval_judge_models=("qwen3:30b",),
            )
        )

        assert result == 0
        assert semantic_calls == ["llama3.1:70b", "qwen2.5:14b"]
        quality_path = (
            tmp_path
            / "evals"
            / "eval-r1"
            / "website_summary_stage"
            / "website_summary_stage_semantic_quality_evidence.json"
        )
        report_path = (
            tmp_path
            / "evals"
            / "eval-r1"
            / "website_summary_stage"
            / "website_summary_stage_semantic_eval.json"
        )
        scorecard_path = tmp_path / "evals" / "eval-r1" / "stage_eval_scorecard.json"
        quality_text = quality_path.read_text(encoding="utf-8")
        assert "must-not-be-copied" not in quality_text
        quality_payload = json.loads(quality_text)
        assert quality_payload["quality_evidence"][0]["quality_score"] == 90.0
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert (
            report_payload["judge_policy"] == "local_judge_panel_review_signal_not_promotion_gate"
        )
        assert report_payload["agreement_summary"]["overall"]["avg_score_spread"] == 2.0
        scorecard_payload = json.loads(scorecard_path.read_text(encoding="utf-8"))
        assert scorecard_payload["rows"][0]["quality_score"] == 90.0
