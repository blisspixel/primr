"""Tests for the extracted strategy-generation stage (roadmap #23, Batch C).

Pins the stage orchestration: budget checkpoint, per-vendor AI strategy
pipeline (single + parallel dispatch), YAML strategy loop, QA trust-stat
assembly, and failure isolation. LLM-backed helpers are patched at the
research_agent seam (they are lazy-imported there until their own
extraction); the YAML loop reads the real strategy YAML from the package.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core.fast_run_strategy import StrategyPhaseResult, run_strategy_phase

CLEAN_QA = {
    "qa_gate_passed": True,
    "placeholder_refs": 0,
    "source_urls": 5,
    "citation_defs": 5,
    "missing_citations": 0,
    "invalid_source_urls": 0,
    "budget_inconsistent": False,
}


@pytest.fixture
def seams(monkeypatch, tmp_path):
    mocks = {
        "build_ai_prompt": MagicMock(return_value="ai strategy prompt"),
        "vendor_research": MagicMock(return_value=[]),
        "enrich": MagicMock(side_effect=lambda content, *a, **k: content),
        "prepare": MagicMock(side_effect=lambda content, *a, **k: (content, dict(CLEAN_QA), [])),
        "save": MagicMock(
            side_effect=lambda content, company, vendor, **k: str(tmp_path / f"{vendor}.docx")
        ),
        "build_yaml_prompt": MagicMock(return_value="yaml strategy prompt"),
        "session_cost": MagicMock(return_value=0.50),
        "failover": MagicMock(return_value="## Strategy\ncontent body"),
    }
    monkeypatch.setattr(
        "primr.core.research_agent._build_ai_strategy_prompt", mocks["build_ai_prompt"]
    )
    monkeypatch.setattr(
        "primr.core.research_agent._get_or_generate_vendor_research", mocks["vendor_research"]
    )
    monkeypatch.setattr("primr.core.research_agent._enrich_strategy_content", mocks["enrich"])
    monkeypatch.setattr("primr.core.research_agent._prepare_strategy_for_output", mocks["prepare"])
    monkeypatch.setattr("primr.core.research_agent._save_strategy_output", mocks["save"])
    monkeypatch.setattr(
        "primr.core.research_agent._build_strategy_prompt_from_yaml", mocks["build_yaml_prompt"]
    )
    monkeypatch.setattr(
        "primr.core.research_agent._compute_session_llm_cost", mocks["session_cost"]
    )
    monkeypatch.setattr(
        "primr.pipeline.integration.strategy_with_recovery",
        lambda executor, fn, folder: SimpleNamespace(success=True, output=fn(), skip_reason=None),
    )
    monkeypatch.setattr("primr.core.fast_run_strategy.call_with_failover", mocks["failover"])
    monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: None)
    mocks["tmp"] = tmp_path
    return mocks


def _call(seams, **overrides) -> StrategyPhaseResult:
    defaults = {
        "has_strategies": True,
        "ai_strategy": True,
        "platforms": ["azure"],
        "strategy_types": None,
        "company_label": "AcmeCo",
        "website": "https://acme.example",
        "report_content": "## Report\nbody",
        "analysis_workbook": "workbook",
        "validated_source_urls": ["https://acme.example/about"],
        "discovery_notes_content": None,
        "grok_reasoning": "reasoner-model",
        "grok_writing": "writer-model",
        "folder_path": str(seams["tmp"]),
        "output_dir": None,
        "diagnostics_dir": None,
        "write_txt": False,
        "recovery_executor": object(),
        "total_phases": 6,
    }
    defaults.update(overrides)
    return run_strategy_phase(**defaults)


class TestSkipPaths:
    def test_no_strategies_returns_empty(self, seams):
        result = _call(seams, has_strategies=False)
        assert result.strategy_paths == {}
        assert result.strategy_trust_stats == []
        seams["failover"].assert_not_called()

    def test_budget_exceeded_skips_generation(self, seams, monkeypatch):
        budget = MagicMock()
        budget.exceeded.return_value = True
        budget.max_cost = 1.50
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)
        result = _call(seams)
        assert result.strategy_paths == {}
        seams["failover"].assert_not_called()
        budget.sync_spend.assert_called_once_with(0.50)

    def test_budget_under_cap_proceeds(self, seams, monkeypatch):
        budget = MagicMock()
        budget.exceeded.return_value = False
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)
        result = _call(seams)
        assert "ai" in result.strategy_paths


class TestYAMLBudgetCheckpoint:
    """The strategy stage rechecks --budget between YAML strategy documents, so a
    multi-strategy run stops once the ceiling is reached (consistent with the
    Phase-2/5 checkpoints). Strategies already produced still ship."""

    _TYPES = ["customer_experience", "modern_security_compliance"]

    def test_skips_remaining_strategies_when_budget_exceeded_mid_loop(self, seams, monkeypatch):
        budget = MagicMock()
        budget.max_cost = 1.50
        # entry: under cap (proceed); first YAML type: under cap; second: over cap.
        budget.exceeded.side_effect = [False, False, True]
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)

        result = _call(seams, ai_strategy=False, platforms=None, strategy_types=self._TYPES)

        assert "customer_experience" in result.strategy_paths
        assert "modern_security_compliance" not in result.strategy_paths
        # Only the first strategy's writing call ran; the second was skipped.
        assert seams["failover"].call_count == 1

    def test_generates_all_strategies_with_headroom(self, seams, monkeypatch):
        budget = MagicMock()
        budget.exceeded.return_value = False
        monkeypatch.setattr("primr.utils.run_budget.get_run_budget", lambda: budget)

        result = _call(seams, ai_strategy=False, platforms=None, strategy_types=self._TYPES)

        assert "customer_experience" in result.strategy_paths
        assert "modern_security_compliance" in result.strategy_paths
        assert seams["failover"].call_count == 2


class TestAIStrategySingleVendor:
    def test_full_pipeline_saves_with_ai_key(self, seams):
        result = _call(seams)
        assert result.strategy_paths == {"ai": str(seams["tmp"] / "azure.docx")}
        seams["enrich"].assert_called_once()
        seams["prepare"].assert_called_once()

    def test_trust_stats_assembled(self, seams):
        result = _call(seams)
        assert len(result.strategy_trust_stats) == 1
        label, stats = result.strategy_trust_stats[0]
        assert label == "AI Strategy"
        assert dict(stats)["Gate"] == "PASS"
        assert dict(stats)["Sources"] == "5 valid"

    def test_vendor_research_skipped_for_agnostic(self, seams):
        _call(seams, platforms=["agnostic"])
        seams["vendor_research"].assert_not_called()

    def test_llm_failure_abandons_vendor_without_raising(self, seams):
        seams["failover"].side_effect = RuntimeError("API down")
        result = _call(seams)
        assert result.strategy_paths == {}
        seams["save"].assert_not_called()

    def test_enrich_failure_keeps_original_content(self, seams):
        seams["enrich"].side_effect = RuntimeError("enrich down")
        result = _call(seams)
        assert "ai" in result.strategy_paths  # still saved
        prepared_content = seams["prepare"].call_args.args[0]
        assert prepared_content.startswith("## Strategy")


class TestAIStrategyMultiVendor:
    def test_parallel_vendors_get_prefixed_keys(self, seams):
        result = _call(seams, platforms=["azure", "aws"])
        assert set(result.strategy_paths) == {"ai_azure", "ai_aws"}
        assert len(result.strategy_trust_stats) == 2
        labels = {label for label, _ in result.strategy_trust_stats}
        assert labels == {"AI Strategy (AZURE)", "AI Strategy (AWS)"}

    def test_one_vendor_failing_does_not_block_others(self, seams):
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if kwargs.get("max_tokens") and calls["n"] == 1:
                raise RuntimeError("first vendor died")
            return "## Strategy\ncontent body"

        seams["failover"].side_effect = flaky
        result = _call(seams, platforms=["azure", "aws"])
        assert len(result.strategy_paths) == 1


class TestYamlStrategies:
    def test_real_yaml_strategy_loads_and_saves(self, seams):
        result = _call(
            seams, ai_strategy=False, platforms=None, strategy_types=["customer_experience"]
        )
        assert "customer_experience" in result.strategy_paths
        seams["build_yaml_prompt"].assert_called_once()
        config = seams["build_yaml_prompt"].call_args.args[0]
        assert "meta" in config  # real YAML parsed from the package

    def test_unknown_yaml_skipped_cleanly(self, seams):
        result = _call(
            seams, ai_strategy=False, platforms=None, strategy_types=["nonexistent_strategy"]
        )
        assert result.strategy_paths == {}

    def test_ai_stype_skipped_in_yaml_loop(self, seams):
        result = _call(seams, ai_strategy=False, platforms=None, strategy_types=["ai"])
        assert result.strategy_paths == {}
        seams["build_yaml_prompt"].assert_not_called()
