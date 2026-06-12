"""Tests for the extracted fast-run setup stage (roadmap #23, Batch A)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.core.fast_run_setup import FastRunSetup, resolve_fast_run_setup


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """Keep setup hermetic: no session leak, no real folder creation."""
    monkeypatch.delenv("PRIMR_CONTINUOUS_REASONING", raising=False)
    monkeypatch.setattr("primr.ai.grok_client.reset_grok_session", lambda: None)
    monkeypatch.setattr(
        "primr.core.research_agent.create_working_folder",
        lambda company, website: str(tmp_path / "run"),
    )


def _resolve(**overrides) -> FastRunSetup:
    defaults = {
        "company_name": "AcmeCo",
        "website": "https://acme.example",
        "ai_strategy": False,
        "strategy_types": None,
        "grok_tier": "hybrid",
        "continuous_reasoning": True,
        "folder_path": None,
    }
    defaults.update(overrides)
    return resolve_fast_run_setup(**defaults)


class TestModelResolution:
    def test_resolves_tier_models(self):
        setup = _resolve()
        assert setup.grok_reasoning
        assert setup.grok_writing

    def test_max_tier_skips_cross_provider_routing(self, monkeypatch):
        routed = MagicMock()
        monkeypatch.setattr("primr.ai.routing.pick_model_for_role", routed)
        _resolve(grok_tier="max")
        routed.assert_not_called()

    def test_routing_override_applies_for_hybrid(self, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.routing.pick_model_for_role", lambda role: "gemini-3.1-flash-lite"
        )
        setup = _resolve(grok_tier="hybrid")
        assert setup.grok_writing == "gemini-3.1-flash-lite"

    def test_routing_failure_falls_back_to_tier_writer(self, monkeypatch):
        def boom(role):
            raise RuntimeError("routing down")

        monkeypatch.setattr("primr.ai.routing.pick_model_for_role", boom)
        setup = _resolve(grok_tier="hybrid")
        assert setup.grok_writing  # tier default survived

    def test_eval_recipe_writing_wins(self, monkeypatch):
        recipe = MagicMock()
        recipe.writing = "recipe-writer-model"
        recipe.reasoning = "recipe-reasoner"
        monkeypatch.setattr("primr.ai.routing.get_active_eval_recipe", lambda: recipe)
        setup = _resolve()
        assert setup.grok_writing == "recipe-writer-model"

    def test_fast_tier_uses_low_reasoning_effort(self):
        assert _resolve(grok_tier="fast").grok_reasoning_effort == "low"
        assert _resolve(grok_tier="hybrid").grok_reasoning_effort is None


class TestContinuousReasoningFlag:
    def test_env_off_overrides_parameter(self, monkeypatch):
        monkeypatch.setenv("PRIMR_CONTINUOUS_REASONING", "0")
        assert _resolve(continuous_reasoning=True).continuous_reasoning is False

    def test_env_on_overrides_parameter(self, monkeypatch):
        monkeypatch.setenv("PRIMR_CONTINUOUS_REASONING", "yes")
        assert _resolve(continuous_reasoning=False).continuous_reasoning is True

    def test_parameter_used_when_env_unset(self):
        assert _resolve(continuous_reasoning=False).continuous_reasoning is False


class TestRunIdentity:
    def test_display_name_from_company(self):
        assert _resolve().display_name == "AcmeCo"

    def test_display_name_falls_back_to_domain(self):
        setup = _resolve(company_name=None)
        assert setup.display_name == "acme.example"

    def test_existing_folder_path_preserved(self, tmp_path):
        existing = str(tmp_path / "resume-folder")
        assert _resolve(folder_path=existing).folder_path == existing

    def test_folder_created_when_absent(self, tmp_path):
        assert _resolve(folder_path=None).folder_path == str(tmp_path / "run")


class TestPhasePlan:
    def test_no_strategies_five_phases(self):
        setup = _resolve(ai_strategy=False, strategy_types=None)
        assert setup.has_strategies is False
        assert setup.total_phases == 5

    def test_ai_strategy_six_phases(self):
        setup = _resolve(ai_strategy=True)
        assert setup.has_strategies is True
        assert setup.total_phases == 6

    def test_yaml_strategies_six_phases(self):
        setup = _resolve(strategy_types=["customer_experience"])
        assert setup.has_strategies is True
        assert setup.total_phases == 6


class TestSessionReset:
    def test_grok_session_reset_called(self, monkeypatch):
        reset = MagicMock()
        monkeypatch.setattr("primr.ai.grok_client.reset_grok_session", reset)
        _resolve()
        reset.assert_called_once()


class TestRecipeBanner:
    def test_active_recipe_printed(self, monkeypatch):
        recipe = MagicMock()
        recipe.writing = "recipe-writer"
        recipe.reasoning = "recipe-reasoner"
        monkeypatch.setattr("primr.ai.routing.get_active_eval_recipe", lambda: recipe)
        with patch("primr.utils.console.console.info") as info:
            _resolve()
        printed = " ".join(str(c.args[0]) for c in info.call_args_list)
        assert "recipe-writer" in printed
