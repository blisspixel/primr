"""Regression tests for bug-hunt round 3 correctness fixes."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.cli import CLIConfig, Command
from primr.core.cli_dryrun import (
    _NON_EXECUTABLE_FULL_NOTE,
    _annotate_non_executable_full_estimate,
    run_dry_run,
)
from primr.utils.cost_estimator import CostEstimate, estimate_cost, normalize_estimate_mode


def _estimate(total: float = 0.76) -> CostEstimate:
    return CostEstimate(
        mode="complete",
        estimated_input_tokens=1,
        estimated_output_tokens=1,
        estimated_search_queries=0,
        input_cost=0.0,
        output_cost=0.0,
        search_cost=0.0,
        total_cost=total,
        duration_minutes="30-45 min",
        notes=[],
    )


class TestUnknownEstimateModeFailsClosed:
    def test_normalize_rejects_typos(self):
        import pytest

        with pytest.raises(ValueError, match="Unknown estimate mode"):
            normalize_estimate_mode("compleet")

    def test_full_alias_maps_to_complete(self):
        assert normalize_estimate_mode("full") == "complete"
        est = estimate_cost("full", use_historical=False)
        assert est.mode == "complete"
        # Must not underprice as scrape-only.
        scrape = estimate_cost("scrape-only", use_historical=False)
        assert est.total_cost > scrape.total_cost


class TestDualProviderEstimateHonesty:
    def test_without_xai_gemini_gets_non_executable_note(self, monkeypatch):
        for key in ("XAI_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            monkeypatch.delenv(key, raising=False)
        est = _estimate()
        _annotate_non_executable_full_estimate(est, mode="complete")
        assert _NON_EXECUTABLE_FULL_NOTE in (est.notes or [])

    def test_xai_ready_skips_non_executable_note(self, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-" + "x" * 20)
        est = _estimate()
        _annotate_non_executable_full_estimate(est, mode="complete")
        assert _NON_EXECUTABLE_FULL_NOTE not in (est.notes or [])

    def test_openai_only_dry_run_json_marks_not_execution_ready(self, monkeypatch):
        for key in ("XAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 40)
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            lambda *a, **k: _estimate(),
        )
        monkeypatch.setattr(
            "primr.pipeline.recovery.build_default_recovery_table",
            MagicMock(return_value=MagicMock(hierarchies={}, to_json=lambda: "{}")),
        )
        monkeypatch.setattr("primr.pipeline.stages.STAGE_CLASSIFICATIONS", {})

        captured: dict = {}

        def fake_emit(payload):
            captured.update(payload)

        monkeypatch.setattr("primr.core.cli_output.emit_json", fake_emit)

        code = run_dry_run(
            CLIConfig(
                command=Command.DRY_RUN,
                company_name="Acme",
                website="https://acme.example",
                mode="complete",
                json_output=True,
            )
        )
        assert code == 0
        assert captured.get("execution_ready") is False
        notes = captured.get("notes") or []
        assert any("XAI/Gemini full-recipe" in str(n) for n in notes)
        assert "estimate only" in str(captured.get("mode_label", "")).lower() or (
            "provider keys required" in str(captured.get("mode_label", "")).lower()
        )

    def test_keyless_full_mode_label_not_raw_complete(self, monkeypatch):
        """No keys must still get the honest full label, not bare 'complete'."""
        for key in ("XAI_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            lambda *a, **k: _estimate(),
        )
        captured: dict = {}
        monkeypatch.setattr("primr.core.cli_output.emit_json", lambda p: captured.update(p))
        code = run_dry_run(
            CLIConfig(
                command=Command.DRY_RUN,
                company_name="Acme",
                website="https://acme.example",
                mode="complete",
                json_output=True,
            )
        )
        assert code == 0
        assert captured.get("execution_ready") is False
        assert captured.get("mode_label") != "complete"
        assert "provider keys required" in str(captured.get("mode_label", ""))
