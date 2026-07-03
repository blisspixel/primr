"""Tests for the --budget pre-flight gate helpers in primr.core.cli_budget.

Pins the bug-hunt fix: --strategy-type documents are priced into the
estimate the gate approves against, so a run cannot be approved under a
ceiling its strategy documents will predictably exceed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from primr.core.cli_budget import (
    activate_run_budget,
    build_run_estimate,
    estimate_strategy_types,
    estimate_vendor_count,
)
from primr.utils.run_budget import clear_run_budget, get_run_budget


def _config(**overrides) -> SimpleNamespace:
    defaults = {
        "budget_usd": None,
        "mode": "complete",
        "ai_strategy": False,
        "cloud_vendors": [],
        "lite_strategy": False,
        "grok_tier": "hybrid",
        "strategy_type": "ai",
        "verify": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _clean_budget():
    clear_run_budget()
    yield
    clear_run_budget()


class TestEstimateStrategyTypes:
    def test_default_ai_type_prices_nothing_extra(self):
        assert estimate_strategy_types(_config()) == []

    def test_yaml_type_is_priced(self):
        assert estimate_strategy_types(_config(strategy_type="customer_experience")) == [
            "customer_experience"
        ]

    def test_missing_attribute_defaults_to_ai(self):
        config = _config()
        del config.strategy_type
        assert estimate_strategy_types(config) == []


class TestEstimateVendorCount:
    def test_no_ai_strategy_is_one(self):
        assert estimate_vendor_count(_config()) == 1

    def test_vendor_count_floors_at_one(self):
        assert estimate_vendor_count(_config(ai_strategy=True, cloud_vendors=[])) == 1
        assert estimate_vendor_count(_config(ai_strategy=True, cloud_vendors=["azure", "aws"])) == 2


class TestBuildRunEstimate:
    """The single estimate-shaping seam. Every surface that quotes a run -
    ``--dry-run``, the ``--budget`` gate, and (by mirroring these flags) the
    interactive confirm prompt - prices through here, so a shaping flag omitted
    here understates spend on every surface at once. These pin the forwarding.
    """

    def test_forwards_every_shaping_flag(self, monkeypatch):
        captured: dict = {}

        def fake_estimate_cost(mode, ai_strategy=False, **kwargs):
            captured["mode"] = mode
            captured["ai_strategy"] = ai_strategy
            captured.update(kwargs)
            return SimpleNamespace(total_cost=1.0)

        monkeypatch.setattr("primr.utils.cost_estimator.estimate_cost", fake_estimate_cost)
        config = _config(
            ai_strategy=True,
            cloud_vendors=["aws", "azure"],
            lite_strategy=True,
            grok_tier="max",
            strategy_type="customer_experience",
            verify=True,
        )
        build_run_estimate(config, fast_mode=True, premium_mode=False)

        assert captured["mode"] == "complete"
        assert captured["ai_strategy"] is True
        assert captured["fast_mode"] is True
        assert captured["premium_mode"] is False
        assert captured["lite_strategy"] is True
        assert captured["grok_tier"] == "max"
        assert captured["num_vendors"] == 2
        assert captured["strategy_types"] == ["customer_experience"]
        # The flag this cycle closed: verify was dropped by dry-run and the gate.
        assert captured["verify"] is True

    def test_verify_flag_is_forwarded_false_by_default(self, monkeypatch):
        captured: dict = {}

        def fake_estimate_cost(mode, ai_strategy=False, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(total_cost=1.0)

        monkeypatch.setattr("primr.utils.cost_estimator.estimate_cost", fake_estimate_cost)
        build_run_estimate(_config(), fast_mode=False, premium_mode=True)
        assert captured["verify"] is False
        assert captured["premium_mode"] is True


class TestActivateRunBudget:
    def test_no_budget_flag_is_inactive(self):
        result = activate_run_budget(_config(), fast_mode=True, premium_mode=False)
        assert result.ok
        assert not result.active
        assert get_run_budget() is None

    def test_non_positive_budget_rejected(self):
        result = activate_run_budget(_config(budget_usd=0.0), fast_mode=True, premium_mode=False)
        assert not result.ok
        assert get_run_budget() is None

    def test_strategy_type_cost_counts_against_the_gate(self, monkeypatch):
        """A ceiling that fits the base run but not the strategy doc refuses.

        The gate previously approved this run because the strategy document
        was invisible to the estimate; the runtime checkpoints then had to
        stop mid-run instead of the operator learning up front.
        """
        # Pin provider keys so fast-mode routing (and pricing) is deterministic.
        for key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("XAI_API_KEY", "fake-key-for-estimate-shape")

        from primr.utils.cost_estimator import estimate_cost

        base = estimate_cost(
            "complete", use_historical=False, fast_mode=True, grok_tier="hybrid"
        ).total_cost
        with_strategy = estimate_cost(
            "complete",
            use_historical=False,
            fast_mode=True,
            grok_tier="hybrid",
            strategy_types=["customer_experience"],
        ).total_cost
        assert with_strategy > base
        between = (base + with_strategy) / 2

        config = _config(budget_usd=between, strategy_type="customer_experience")
        result = activate_run_budget(config, fast_mode=True, premium_mode=False)
        assert not result.ok
        assert get_run_budget() is None

    def test_sufficient_budget_activates(self):
        config = _config(budget_usd=100.0, strategy_type="customer_experience")
        result = activate_run_budget(config, fast_mode=True, premium_mode=False)
        assert result.ok
        assert result.active
        budget = get_run_budget()
        assert budget is not None
        assert budget.max_cost == 100.0
