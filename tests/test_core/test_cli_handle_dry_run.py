"""Unit tests for the dry-run handler (run_dry_run in primr.core.cli_dryrun).

Mocks the cost estimator and recovery table builder to exercise each
flag-combination branch and exit code without printing real estimates.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.cli import CLIConfig, Command
from primr.core.cli_dryrun import run_dry_run


def _config(**overrides):
    defaults = {"command": Command.DRY_RUN, "mode": "complete"}
    defaults.update(overrides)
    return CLIConfig(**defaults)


@pytest.fixture
def mocks(monkeypatch):
    estimate = MagicMock()
    estimate.__str__ = lambda self: "ESTIMATE STRING"
    monkeypatch.setattr(
        "primr.utils.cost_estimator.estimate_cost",
        MagicMock(return_value=estimate),
    )
    # recovery table builder used at the end of dry-run
    recovery_table = MagicMock()
    recovery_table.hierarchies = {}
    recovery_table.to_json.return_value = "{}"
    monkeypatch.setattr(
        "primr.pipeline.recovery.build_default_recovery_table",
        MagicMock(return_value=recovery_table),
    )
    monkeypatch.setattr("primr.pipeline.stages.STAGE_CLASSIFICATIONS", {})
    return estimate


class TestDryRunFlags:
    def test_fast_and_premium_together_fails(self, mocks):
        result = run_dry_run(_config(fast_mode=True, premium_mode=True))
        assert result == 1

    def test_fast_with_invalid_mode_fails(self, mocks):
        result = run_dry_run(_config(fast_mode=True, mode="scrape"))
        assert result == 1

    def test_premium_with_invalid_mode_fails(self, mocks):
        result = run_dry_run(_config(premium_mode=True, mode="scrape"))
        assert result == 1

    def test_premium_with_complete_mode_succeeds(self, mocks):
        result = run_dry_run(_config(premium_mode=True, mode="complete"))
        assert result == 0

    def test_fast_with_complete_mode_succeeds(self, mocks):
        result = run_dry_run(_config(fast_mode=True, mode="complete"))
        assert result == 0

    def test_auto_fast_mode_when_xai_key_set(self, mocks, monkeypatch):
        # Without --fast or --premium, complete mode auto-promotes to fast when XAI key is set.
        monkeypatch.setenv("XAI_API_KEY", "x" * 30)
        result = run_dry_run(_config(mode="complete"))
        assert result == 0

    @pytest.mark.parametrize(
        ("env_name", "expected_label"),
        [
            ("OPENAI_API_KEY", "standard (OpenAI routed)"),
            ("ANTHROPIC_API_KEY", "standard (Anthropic routed)"),
        ],
    )
    def test_auto_standard_estimate_when_opt_in_provider_key_set(
        self, monkeypatch, capsys, env_name, expected_label
    ):
        import json

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv(env_name, "provider-key-" + "x" * 20)

        result = run_dry_run(_config(mode="complete", json_output=True))

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["mode_label"] == expected_label

    def test_skip_recon_branch_taken(self, mocks):
        result = run_dry_run(_config(mode="scrape", skip_recon=True))
        assert result == 0

    def test_default_mode_returns_zero(self, mocks):
        result = run_dry_run(_config(mode="scrape"))
        assert result == 0

    def test_default_output_uses_compact_lifecycle_handoff(self, mocks, capsys):
        result = run_dry_run(_config(mode="scrape"))

        assert result == 0
        out = capsys.readouterr().out
        assert "RECOVERY TABLE" in out
        assert "Recovery Table JSON" not in out
        assert "NEXT STEPS" in out
        assert "--budget <usd>" in out
        assert "--check-jobs" in out
        assert "--resume-latest" in out
        assert "--list-recent" in out
        assert "For the default output directory" in out

    def test_verbose_output_retains_recovery_json(self, mocks, capsys):
        result = run_dry_run(_config(mode="scrape", verbose=True))

        assert result == 0
        out = capsys.readouterr().out
        assert "Recovery Table JSON" in out
        assert "{}" in out

    def test_budget_policy_prints_optional_strategy_checkpoint_for_premium(self, mocks, capsys):
        result = run_dry_run(_config(mode="complete", premium_mode=True, budget_usd=2.0))

        assert result == 0
        out = capsys.readouterr().out
        assert "BUDGET POLICY" in out
        assert "optional strategy generation" in out
        assert "required Deep Research task cannot be stopped" in out

    def test_budget_policy_prints_checkpoints_for_fast(self, mocks, capsys):
        result = run_dry_run(_config(mode="complete", fast_mode=True, budget_usd=2.0))

        assert result == 0
        out = capsys.readouterr().out
        assert "Checkpointed stages:" in out
        assert "strategy generation" in out


class TestDryRunCostEstimator:
    def test_passes_cloud_vendor_count_to_estimator(self, mocks, monkeypatch):
        est_mock = MagicMock()
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            est_mock,
        )
        run_dry_run(_config(mode="complete", platforms=("aws", "azure", "gcp")))
        kwargs = est_mock.call_args.kwargs
        assert kwargs["num_vendors"] == 3

    def test_clamps_empty_ai_strategy_platforms_to_one_vendor(self, mocks, monkeypatch):
        est_mock = MagicMock()
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            est_mock,
        )
        run_dry_run(_config(mode="complete", platforms=()))
        kwargs = est_mock.call_args.kwargs
        assert kwargs["num_vendors"] == 1

    def test_passes_lite_strategy_flag(self, mocks, monkeypatch):
        est_mock = MagicMock()
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            est_mock,
        )
        run_dry_run(_config(mode="complete", lite_strategy=True))
        assert est_mock.call_args.kwargs["lite_strategy"] is True

    def test_passes_grok_tier(self, mocks, monkeypatch):
        est_mock = MagicMock()
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            est_mock,
        )
        run_dry_run(_config(mode="complete", fast_mode=True, grok_tier="max"))
        assert est_mock.call_args.kwargs["grok_tier"] == "max"
