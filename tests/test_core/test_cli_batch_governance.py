"""Regression tests for batch and enrichment cost governance."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from primr.core.cli_batch import _ColumnMap
from primr.core.cli_batch_runtime import (
    BatchCompany,
    BatchPlan,
    enrich_batch,
    process_batch,
)
from primr.utils.cost_estimator import CostEstimate
from primr.utils.run_budget import get_run_budget


def _estimate(cost: float = 1.25) -> CostEstimate:
    return CostEstimate(
        mode="complete",
        estimated_input_tokens=100,
        estimated_output_tokens=50,
        estimated_search_queries=0,
        input_cost=0.25,
        output_cost=cost - 0.25,
        search_cost=0.0,
        total_cost=cost,
        duration_minutes="10-20",
        notes=[],
    )


def _company(
    name: str = "Example Labs",
    website: str | None = "https://example.test",
) -> BatchCompany:
    return BatchCompany(name=name, website=website, industry="Services", context={})


def _plan(*companies: BatchCompany) -> BatchPlan:
    pending = tuple(company for company in companies if company.website)
    missing = tuple(company for company in companies if not company.website)
    return BatchPlan(
        companies=tuple(companies),
        pending=pending,
        missing_websites=missing,
        invalid_rows=(),
        existing=(),
    )


def test_batch_json_dry_run_is_one_local_plan(monkeypatch, tmp_path):
    emitted: list[dict[str, object]] = []
    research = MagicMock()
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.build_batch_plan",
        MagicMock(return_value=_plan(_company())),
    )
    monkeypatch.setattr("primr.core.cli_batch_runtime._emit_json", emitted.append)
    monkeypatch.setattr("primr.core.research_agent.perform_research", research)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=AssertionError("no prompt")))

    result = process_batch(
        str(tmp_path / "batch.csv"),
        dry_run=True,
        json_output=True,
        per_company_estimate=_estimate(),
        mode_label="full",
        ai_strategy=False,
    )

    assert result == 0
    research.assert_not_called()
    assert len(emitted) == 1
    assert emitted[0]["schema_version"] == "primr.batch-plan.v1"
    assert emitted[0]["operation"] == "batch_research"
    assert emitted[0]["eligible_company_count"] == 1
    assert emitted[0]["estimated_batch_cost_usd"] == 1.25
    assert emitted[0]["budget_scope"] == "batch"
    assert emitted[0]["batch_within_budget"] is None
    assert emitted[0]["automatic_retries"] == 0
    assert emitted[0]["approval_required"] is True


def test_declined_batch_starts_no_research(monkeypatch, tmp_path):
    research = MagicMock()
    preflight = MagicMock(return_value=(True, []))
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.build_batch_plan",
        MagicMock(return_value=_plan(_company())),
    )
    monkeypatch.setattr("primr.core.research_agent.perform_research", research)
    monkeypatch.setattr("builtins.input", MagicMock(return_value="n"))

    result = process_batch(
        str(tmp_path / "batch.csv"),
        skip_confirm=False,
        per_company_estimate=_estimate(),
        ai_strategy=False,
        execution_preflight=preflight,
    )

    assert result == 0
    preflight.assert_not_called()
    research.assert_not_called()


def test_approved_batch_preflight_failure_starts_no_research(monkeypatch, tmp_path):
    research = MagicMock()
    preflight = MagicMock(return_value=(False, ["provider unavailable"]))
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.build_batch_plan",
        MagicMock(return_value=_plan(_company())),
    )
    monkeypatch.setattr("primr.core.research_agent.perform_research", research)

    result = process_batch(
        str(tmp_path / "batch.csv"),
        per_company_estimate=_estimate(),
        ai_strategy=False,
        execution_preflight=preflight,
    )

    assert result == 1
    preflight.assert_called_once_with()
    research.assert_not_called()


def test_missing_website_blocks_batch_without_hidden_lookup(monkeypatch, tmp_path):
    research = MagicMock()
    lookup = MagicMock(side_effect=AssertionError("batch must not look up websites"))
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.build_batch_plan",
        MagicMock(return_value=_plan(_company(website=None))),
    )
    monkeypatch.setattr("primr.core.research_agent.perform_research", research)
    monkeypatch.setattr("primr.data.search_utils.lookup_company_website", lookup)

    result = process_batch(
        str(tmp_path / "batch.csv"),
        per_company_estimate=_estimate(),
        ai_strategy=False,
        research_runner=research,
    )

    assert result == 1
    research.assert_not_called()
    lookup.assert_not_called()


def test_batch_budget_applies_to_quoted_batch_total(monkeypatch, tmp_path):
    research = MagicMock()
    preflight = MagicMock(return_value=(True, []))
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.build_batch_plan",
        MagicMock(
            return_value=_plan(
                _company("Example Labs", "https://one.example"),
                _company("Sample Works", "https://two.example"),
            )
        ),
    )
    monkeypatch.setattr("primr.core.research_agent.perform_research", research)

    result = process_batch(
        str(tmp_path / "batch.csv"),
        per_company_estimate=_estimate(0.75),
        budget_usd=1.0,
        ai_strategy=False,
        execution_preflight=preflight,
    )

    assert result == 1
    preflight.assert_not_called()
    research.assert_not_called()


def test_batch_forwards_flags_and_clears_per_company_budget(monkeypatch, tmp_path):
    report = tmp_path / "report.md"
    report.write_text("report " * 1_000, encoding="utf-8")
    observed_budget: list[float | None] = []

    def _research(*args, **kwargs):
        from primr.core.strategy_outcome import StrategyOutcomeTracker, persist_strategy_outcome
        from primr.core.vendor_refresh_outcome import (
            VendorRefreshTracker,
            persist_vendor_refresh_outcome,
        )

        budget = get_run_budget()
        observed_budget.append(None if budget is None else budget.max_cost)
        state_path = tmp_path / "run-state"
        state_path.mkdir()
        kwargs["run_context"]["working_folder"] = str(state_path)
        persist_strategy_outcome(str(state_path), StrategyOutcomeTracker(()).snapshot())
        persist_vendor_refresh_outcome(str(state_path), VendorRefreshTracker(()).snapshot())
        return str(report)

    research = MagicMock(side_effect=_research)
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.build_batch_plan",
        MagicMock(return_value=_plan(_company())),
    )
    monkeypatch.setattr("primr.core.research_agent.perform_research", research)

    result = process_batch(
        str(tmp_path / "batch.csv"),
        mode="deep",
        citation_style="footnoted",
        ai_strategy=False,
        platforms=("gcp",),
        skip_confirm=True,
        per_company_estimate=_estimate(0.75),
        output_dir=tmp_path,
        strategies=["data_strategy"],
        no_qa=True,
        max_scrape_time=120,
        lite_strategy=True,
        fast_mode=True,
        premium_mode=False,
        skip_scrape_validation=True,
        verify=True,
        grok_tier="premium",
        skip_recon=True,
        continuous_reasoning=False,
        budget_usd=1.0,
        research_runner=research,
    )

    assert result == 0
    assert observed_budget == [1.0]
    assert get_run_budget() is None
    kwargs = research.call_args.kwargs
    assert kwargs == {
        "mode": "deep",
        "citation_style": "footnoted",
        "ai_strategy": False,
        "platforms": ("gcp",),
        "output_dir": str(tmp_path),
        "skip_confirm": True,
        "refresh_vendor_research": False,
        "strategies": ["data_strategy"],
        "no_qa": True,
        "max_scrape_time": 120,
        "lite_strategy": True,
        "fast_mode": True,
        "premium_mode": False,
        "skip_scrape_validation": True,
        "resume_local": False,
        "verify": True,
        "grok_tier": "premium",
        "skip_recon": True,
        "continuous_reasoning": False,
        "run_context": {"working_folder": str(tmp_path / "run-state")},
    }


@pytest.mark.parametrize("budget", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_batch_budget_starts_no_research(monkeypatch, tmp_path, budget):
    planning = MagicMock()
    research = MagicMock()
    monkeypatch.setattr("primr.core.cli_batch_runtime.build_batch_plan", planning)
    monkeypatch.setattr("primr.core.research_agent.perform_research", research)

    result = process_batch(
        str(tmp_path / "batch.csv"),
        budget_usd=budget,
        per_company_estimate=_estimate(),
        ai_strategy=False,
        research_runner=research,
    )

    assert result == 1
    planning.assert_not_called()
    research.assert_not_called()


def test_failed_company_is_not_retried(monkeypatch, tmp_path):
    research = MagicMock(side_effect=RuntimeError("provider failure"))
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.build_batch_plan",
        MagicMock(return_value=_plan(_company())),
    )
    monkeypatch.setattr("primr.core.research_agent.perform_research", research)

    result = process_batch(
        str(tmp_path / "batch.csv"),
        per_company_estimate=_estimate(),
        ai_strategy=False,
        research_runner=research,
    )

    assert result == 1
    research.assert_called_once()


def _enrich_frame():
    return (
        pd.DataFrame([{"Company": "Example Labs", "Website": "", "Industry": "Services"}]),
        _ColumnMap(
            company="Company",
            website="Website",
            industry="Industry",
            context=[],
        ),
    )


def test_enrich_decline_has_zero_search_model_calls_and_no_output(monkeypatch, tmp_path):
    output = tmp_path / "batch_enriched.csv"
    lookup = MagicMock()
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime._prepare_batch_df",
        MagicMock(return_value=_enrich_frame()),
    )
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.estimate_website_lookup",
        MagicMock(
            return_value={
                "lookup_count": 1,
                "estimated_cost_usd": 0.01,
            }
        ),
    )
    monkeypatch.setattr("primr.data.search_utils.lookup_company_website", lookup)
    monkeypatch.setattr("builtins.input", MagicMock(return_value="n"))

    result = enrich_batch(
        str(tmp_path / "batch.csv"),
        skip_confirm=False,
        output_dir=tmp_path,
    )

    assert result == 0
    lookup.assert_not_called()
    assert not output.exists()


def test_enrich_json_dry_run_has_stable_contract_and_no_lookup(monkeypatch, tmp_path):
    emitted: list[dict[str, object]] = []
    lookup = MagicMock()
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime._prepare_batch_df",
        MagicMock(return_value=_enrich_frame()),
    )
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.estimate_website_lookup",
        MagicMock(
            return_value={
                "lookup_count": 1,
                "model_name": "utility-model",
                "estimated_cost_usd": 0.01,
            }
        ),
    )
    monkeypatch.setattr("primr.core.cli_batch_runtime._emit_json", emitted.append)
    monkeypatch.setattr("primr.data.search_utils.lookup_company_website", lookup)

    result = enrich_batch(
        str(tmp_path / "batch.csv"),
        dry_run=True,
        json_output=True,
        output_dir=tmp_path,
    )

    assert result == 0
    lookup.assert_not_called()
    assert len(emitted) == 1
    assert emitted[0]["schema_version"] == "primr.batch-enrich-plan.v1"
    assert emitted[0]["operation"] == "batch_enrich"
    assert emitted[0]["lookup_count"] == 1
    assert emitted[0]["estimated_cost_usd"] == 0.01
    assert emitted[0]["automatic_retries"] == 0
    assert emitted[0]["provider_failover"] is False
    assert emitted[0]["approval_required"] is True
    assert not Path(str(emitted[0]["output_path"])).exists()


def test_enrich_uses_exact_model_once_without_failover_and_clears_budget(
    monkeypatch,
    tmp_path,
):
    observed_budget: list[float | None] = []

    def _lookup(*args, **kwargs):
        budget = get_run_budget()
        observed_budget.append(None if budget is None else budget.max_cost)
        return "https://example.test/"

    lookup = MagicMock(side_effect=_lookup)
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime._prepare_batch_df",
        MagicMock(return_value=_enrich_frame()),
    )
    monkeypatch.setattr(
        "primr.core.cli_batch_runtime.estimate_website_lookup",
        MagicMock(
            return_value={
                "lookup_count": 1,
                "model_name": "utility-model",
                "estimated_cost_usd": 0.01,
            }
        ),
    )
    monkeypatch.setattr("primr.data.search_utils.lookup_company_website", lookup)

    result = enrich_batch(
        str(tmp_path / "batch.csv"),
        skip_confirm=True,
        budget_usd=1.0,
        output_dir=tmp_path,
    )

    assert result == 0
    lookup.assert_called_once_with(
        "Example Labs",
        context={},
        model="utility-model",
        retries=0,
        allow_failover=False,
    )
    assert observed_budget == [1.0]
    assert get_run_budget() is None
