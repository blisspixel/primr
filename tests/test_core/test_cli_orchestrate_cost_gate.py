"""Cost-gate tests for experimental ``primr orchestrate``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.cli import CLIConfig, Command
from primr.core.cli_orchestrate import handle_orchestrate
from primr.utils.cost_estimator import CostEstimate


def _config(**overrides):
    defaults = {
        "command": Command.ORCHESTRATE,
        "company_name": "Acme",
        "website": "https://acme.example",
        "dry_run_requested": False,
        "orchestrate_max_cost": None,
        "verify": False,
        "grok_tier": "hybrid",
    }
    defaults.update(overrides)
    return CLIConfig(**defaults)


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


@pytest.fixture
def estimate_seam(monkeypatch):
    printed = []
    monkeypatch.setattr(
        "primr.utils.cost_display.print_cost_estimate",
        lambda *a, **k: printed.append((a, k)) or _estimate(),
    )
    return printed


class TestOrchestrateCostGate:
    def test_dry_run_prices_and_does_not_launch(self, monkeypatch, estimate_seam):
        launch = MagicMock()
        monkeypatch.setattr(
            "primr.agentic.orchestrator.ResearchOrchestrator",
            launch,
        )
        code = handle_orchestrate(_config(dry_run_requested=True))
        assert code == 0
        assert estimate_seam
        launch.assert_not_called()

    def test_max_cost_below_estimate_refuses(self, monkeypatch, estimate_seam):
        monkeypatch.setattr(
            "primr.utils.cost_display.print_cost_estimate",
            lambda *a, **k: _estimate(5.0),
        )
        code = handle_orchestrate(_config(orchestrate_max_cost=1.0))
        assert code == 1

    def test_max_cost_allows_launch_with_cost_guard(self, monkeypatch, estimate_seam):
        result_obj = MagicMock()
        result_obj.is_success = True
        result_obj.duration_seconds = 1.0
        result_obj.report_path = None
        result_obj.hypotheses = []
        result_obj.completed_stages = ["a"]
        result_obj.errors = []

        hooks_holder = {}

        class FakeHookSystem:
            def __init__(self):
                self.hooks = []

            def register(self, hook):
                self.hooks.append(hook)
                hooks_holder["hooks"] = self.hooks

        orchestrator = MagicMock()
        seen_budget = {}

        async def fake_research(**kwargs):
            from primr.utils.run_budget import get_run_budget

            budget = get_run_budget()
            seen_budget["max"] = None if budget is None else budget.max_cost
            seen_budget["hook"] = None if budget is None else budget.as_hook()
            return result_obj

        orchestrator.research = fake_research
        monkeypatch.setattr(
            "primr.agentic.orchestrator.ResearchOrchestrator",
            MagicMock(return_value=orchestrator),
        )
        monkeypatch.setattr("primr.agentic.memory.ResearchMemory", MagicMock())
        monkeypatch.setattr("primr.agentic.orchestrator.OrchestratorConfig", MagicMock())
        monkeypatch.setattr("primr.agentic.HookSystem", FakeHookSystem)
        monkeypatch.setattr(
            "primr.utils.cost_display.print_cost_estimate",
            lambda *a, **k: _estimate(0.76),
        )

        from primr.utils.run_budget import get_run_budget

        code = handle_orchestrate(_config(orchestrate_max_cost=5.0))
        assert code == 0
        assert seen_budget["max"] == 5.0
        assert seen_budget["hook"] is not None
        assert any(h is seen_budget["hook"] for h in hooks_holder.get("hooks", []))
        assert get_run_budget() is None

    def test_interactive_decline_cancels(self, monkeypatch, estimate_seam):
        monkeypatch.setattr(
            "primr.utils.cost_display.print_cost_estimate",
            lambda *a, **k: _estimate(0.76),
        )
        monkeypatch.setattr("builtins.input", MagicMock(return_value="n"))
        launch = MagicMock()
        monkeypatch.setattr(
            "primr.agentic.orchestrator.ResearchOrchestrator",
            launch,
        )
        code = handle_orchestrate(_config(orchestrate_max_cost=None))
        assert code == 1
        launch.assert_not_called()

    def test_interactive_yes_launches(self, monkeypatch, estimate_seam):
        result_obj = MagicMock()
        result_obj.is_success = True
        result_obj.duration_seconds = 2.0
        result_obj.report_path = "out.md"
        result_obj.hypotheses = [1]
        result_obj.completed_stages = ["scrape"]
        result_obj.errors = []

        orchestrator = MagicMock()

        async def fake_research(**kwargs):
            return result_obj

        orchestrator.research = fake_research
        monkeypatch.setattr(
            "primr.agentic.orchestrator.ResearchOrchestrator",
            MagicMock(return_value=orchestrator),
        )
        monkeypatch.setattr("primr.agentic.memory.ResearchMemory", MagicMock())
        monkeypatch.setattr("primr.agentic.orchestrator.OrchestratorConfig", MagicMock())
        monkeypatch.setattr(
            "primr.utils.cost_display.print_cost_estimate",
            lambda *a, **k: _estimate(0.5),
        )
        monkeypatch.setattr("builtins.input", MagicMock(return_value="yes"))

        code = handle_orchestrate(_config(orchestrate_max_cost=None))
        assert code == 0
