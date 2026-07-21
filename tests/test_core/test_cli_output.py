"""Tests for machine-readable CLI output helpers (track C)."""

from __future__ import annotations

import json

from primr.core.cli_output import (
    cost_estimate_json,
    emit_json,
    research_result_json,
)
from primr.core.strategy_outcome import StrategyOutcomeTracker
from primr.core.vendor_refresh_outcome import VendorRefreshTracker
from primr.utils.cost_estimator import CostEstimate


def _estimate() -> CostEstimate:
    return CostEstimate(
        mode="fast",
        estimated_input_tokens=1000,
        estimated_output_tokens=2000,
        estimated_search_queries=5,
        input_cost=0.01,
        output_cost=0.02,
        search_cost=0.03,
        total_cost=0.06,
        duration_minutes="20-30",
        notes=["a note"],
    )


class TestCostEstimateJson:
    def test_includes_dataclass_fields_and_context(self):
        d = cost_estimate_json(_estimate(), mode_label="full (Grok)", ai_strategy=True)
        assert d["mode"] == "fast"
        assert d["total_cost"] == 0.06
        assert d["estimated_input_tokens"] == 1000
        assert d["notes"] == ["a note"]
        assert d["mode_label"] == "full (Grok)"
        assert d["includes_ai_strategy"] is True

    def test_is_json_serializable(self):
        d = cost_estimate_json(_estimate(), mode_label="x", ai_strategy=False)
        assert json.loads(json.dumps(d))["total_cost"] == 0.06

    def test_includes_budget_enforcement_when_supplied(self):
        budget = {
            "preflight": "refuses to start",
            "runtime_checkpoints": False,
            "runtime": "estimate-gated only",
            "checkpointed_stages": [],
        }
        d = cost_estimate_json(
            _estimate(),
            mode_label="x",
            ai_strategy=False,
            budget_enforcement=budget,
        )

        assert d["budget_enforcement"] == budget

    def test_includes_inference_metadata_when_supplied(self):
        inference = {
            "profile": "hybrid",
            "host_agent": {"billing_mode": "potentially_metered"},
        }

        d = cost_estimate_json(
            _estimate(),
            mode_label="x",
            ai_strategy=False,
            inference=inference,
        )

        assert d["inference"] == inference


class TestResearchResultJson:
    def test_failed_when_no_path(self):
        d = research_result_json(None, company="Acme", website="https://acme.example", mode="fast")
        assert d["status"] == "failed"
        assert d["report_path"] is None
        assert d["docx_path"] is None
        assert d["word_count"] is None
        assert d["company"] == "Acme"

    def test_completed_with_word_count(self, tmp_path):
        md = tmp_path / "report.md"
        md.write_text("one two three four five", encoding="utf-8")
        d = research_result_json(
            str(md), company="Acme", website="https://acme.example", mode="fast"
        )
        assert d["status"] == "completed"
        assert d["report_path"] == str(md.resolve())
        assert d["word_count"] == 5
        assert d["docx_path"] is None

    def test_detects_sibling_docx(self, tmp_path):
        md = tmp_path / "report.md"
        md.write_text("words here", encoding="utf-8")
        docx = tmp_path / "report.docx"
        docx.write_text("(binary placeholder)", encoding="utf-8")
        d = research_result_json(
            str(md), company="Acme", website="https://acme.example", mode="premium"
        )
        assert d["docx_path"] == str(docx.resolve())
        assert d["mode"] == "premium"

    def test_binary_docx_primary_is_not_decoded_as_text(self, tmp_path):
        docx = tmp_path / "report.docx"
        docx.write_bytes(b"PK\x03\x04\x80\xff\x00")

        payload = research_result_json(
            str(docx),
            company="ExampleCo",
            website="https://example.co",
            mode="complete",
            fulfillment_status="completed",
            outcome_state_status="available",
            run_state_path=str(tmp_path / "_run_state.json"),
        )

        assert payload["status"] == "completed"
        assert payload["fulfillment_status"] == "completed"
        assert payload["report_path"] == str(docx.resolve())
        assert payload["docx_path"] == str(docx.resolve())
        assert payload["word_count"] is None
        assert payload["outcome_state_status"] == "available"

    def test_preserves_completed_report_with_partial_strategy_status(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("base report", encoding="utf-8")
        tracker = StrategyOutcomeTracker(("ai:azure", "ai:aws"))
        tracker.mark_completed("ai:azure")

        payload = research_result_json(
            str(report),
            company="ExampleCo",
            website="https://example.co",
            mode="complete",
            strategy_outcome=tracker.snapshot(),
        )

        assert payload["status"] == "completed"
        assert payload["strategy_status"] == "partial"
        assert payload["strategy_failed_targets"] == ["ai:aws"]

    def test_includes_vendor_refresh_fulfillment(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("base report", encoding="utf-8")
        refresh = VendorRefreshTracker(("azure", "aws"))
        refresh.observe("azure", "started")
        refresh.observe("azure", "completed")
        refresh.mark_skipped("aws")

        payload = research_result_json(
            str(report),
            company="ExampleCo",
            website="https://example.co",
            mode="complete",
            vendor_refresh_outcome=refresh.snapshot(),
        )

        assert payload["status"] == "completed"
        assert payload["vendor_refresh_status"] == "partial"
        assert payload["vendor_refresh_completed"] == ["azure"]
        assert payload["vendor_refresh_skipped"] == ["aws"]


class TestEmitJson:
    def test_emits_parseable_json(self, capsys):
        emit_json({"status": "completed", "n": 1})
        out = capsys.readouterr().out
        assert json.loads(out) == {"status": "completed", "n": 1}
