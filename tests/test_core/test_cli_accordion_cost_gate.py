"""Cost-gate tests for experimental ``primr --test-accordion``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.cli import CLIConfig, Command
from primr.core.cli_accordion import handle_test_accordion
from primr.utils.cost_estimator import CostEstimate


def _config(**overrides):
    defaults = {
        "command": Command.TEST_ACCORDION,
        "test_accordion_topic": "Oceanography 2026",
        "test_accordion_pages": 50,
        "dry_run_requested": False,
        "skip_confirm": False,
        "budget_usd": None,
    }
    defaults.update(overrides)
    return CLIConfig(**defaults)


def _estimate(total: float = 2.5) -> CostEstimate:
    return CostEstimate(
        mode="deep-research",
        estimated_input_tokens=1,
        estimated_output_tokens=1,
        estimated_search_queries=0,
        input_cost=0.0,
        output_cost=0.0,
        search_cost=0.0,
        total_cost=total,
        duration_minutes="8-15 min",
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


class TestAccordionCostGate:
    def test_dry_run_prices_and_does_not_launch(self, monkeypatch, estimate_seam):
        launch = MagicMock()
        monkeypatch.setattr("primr.ai.accordion_test.run_accordion_test", launch)
        code = handle_test_accordion(_config(dry_run_requested=True))
        assert code == 0
        assert estimate_seam
        launch.assert_not_called()

    def test_budget_below_estimate_refuses(self, monkeypatch, estimate_seam):
        monkeypatch.setattr(
            "primr.utils.cost_display.print_cost_estimate",
            lambda *a, **k: _estimate(5.0),
        )
        launch = MagicMock()
        monkeypatch.setattr("primr.ai.accordion_test.run_accordion_test", launch)
        code = handle_test_accordion(_config(budget_usd=1.0, skip_confirm=True))
        assert code == 1
        launch.assert_not_called()

    def test_skip_confirm_launches_after_quote(self, monkeypatch, estimate_seam):
        result = MagicMock()
        result.success = True
        result.page_estimate = 12.0
        result.output_path = "out.md"
        launch = MagicMock(return_value=result)
        monkeypatch.setattr("primr.ai.accordion_test.run_accordion_test", launch)
        code = handle_test_accordion(_config(skip_confirm=True))
        assert code == 0
        launch.assert_called_once()

    def test_decline_does_not_launch(self, monkeypatch, estimate_seam):
        launch = MagicMock()
        monkeypatch.setattr("primr.ai.accordion_test.run_accordion_test", launch)
        monkeypatch.setattr("primr.core.cli_accordion.prompt_yes_no", lambda *a, **k: False)
        code = handle_test_accordion(_config(skip_confirm=False))
        assert code == 1
        launch.assert_not_called()
