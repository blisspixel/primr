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
    def test_openai_only_label_gets_non_executable_note(self):
        est = _estimate()
        _annotate_non_executable_full_estimate(
            est,
            mode_label="full (OpenAI estimate only; execution needs XAI or Gemini)",
        )
        assert _NON_EXECUTABLE_FULL_NOTE in (est.notes or [])

    def test_xai_label_does_not_get_non_executable_note(self):
        est = _estimate()
        _annotate_non_executable_full_estimate(
            est,
            mode_label="full (Grok 4.3 hybrid)",
        )
        assert _NON_EXECUTABLE_FULL_NOTE not in (est.notes or [])

    def test_openai_only_dry_run_json_marks_not_execution_ready(self, monkeypatch, capsys):
        for key in ("XAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 40)
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            lambda *a, **k: _estimate(),
        )
        # Avoid recovery import side effects
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
