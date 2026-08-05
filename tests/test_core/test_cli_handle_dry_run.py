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
    # build_run_estimate compares planning vs historical with `>`; keep numeric.
    estimate.total_cost = 0.76
    estimate.notes = []
    estimate.duration_minutes = "30-45 min"
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
    def test_host_billing_acknowledgment_requires_hybrid(self, capsys):
        result = run_dry_run(
            _config(
                mode="scrape",
                inference_profile="cloud",
                acknowledge_host_agent_may_bill=True,
            )
        )

        assert result == 1
        assert "requires --inference hybrid" in capsys.readouterr().out

    def test_human_estimate_discloses_uncapped_host_cost(self, capsys):
        result = run_dry_run(
            _config(
                mode="scrape",
                inference_profile="hybrid",
                acknowledge_host_agent_may_bill=True,
            )
        )

        assert result == 0
        out = capsys.readouterr().out
        assert "Experimental host-agent usage is acknowledged" in out
        assert "has not cleared its promotion eval" in out
        assert "excluded from Estimated Total and --budget" in out

    def test_json_estimate_discloses_uncapped_host_cost(self, capsys):
        import json

        result = run_dry_run(
            _config(
                mode="scrape",
                json_output=True,
                inference_profile="hybrid",
                acknowledge_host_agent_may_bill=True,
            )
        )

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["inference"]["host_agent"] == {
            "enabled": True,
            "runner": "codex_cli",
            "billing_mode": "potentially_metered",
            "billing_acknowledged": True,
            "promotion_status": "experimental_eval_pending",
            "eligible_stages": ["fast.source_relevance"],
            "cost_included_in_estimate": False,
            "covered_by_budget": False,
        }
        assert any("excluded from Estimated Total" in note for note in payload["notes"])

    def test_fast_and_premium_together_fails(self, mocks):
        result = run_dry_run(_config(fast_mode=True, premium_mode=True))
        assert result == 1

    @pytest.mark.parametrize(
        "overrides",
        [
            {"acknowledge_host_agent_may_bill": True},
            {"fast_mode": True, "premium_mode": True},
            {"fast_mode": True, "mode": "scrape"},
            {"premium_mode": True, "mode": "scrape"},
        ],
    )
    def test_json_option_errors_emit_one_object(self, overrides, capsys):
        import json

        assert run_dry_run(_config(json_output=True, **overrides)) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_version"] == "primr.command-error.v1"
        assert payload["operation"] == "research_estimate"
        assert payload["error"] is True

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

    def test_nonfast_structured_custom_strategy_fails_before_estimate(
        self, mocks, monkeypatch, capsys
    ):
        import json

        monkeypatch.delenv("XAI_API_KEY", raising=False)

        assert (
            run_dry_run(
                _config(
                    mode="structured",
                    strategy_type="customer_experience",
                    json_output=True,
                )
            )
            == 1
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_type"] == "unsupported_strategy_runtime"

    def test_auto_fast_mode_when_xai_key_set(self, mocks, monkeypatch):
        # Without --fast or --premium, complete mode auto-promotes to fast when XAI key is set.
        monkeypatch.setenv("XAI_API_KEY", "x" * 30)
        result = run_dry_run(_config(mode="complete"))
        assert result == 0

    @pytest.mark.parametrize(
        ("env_name", "expected_fragment"),
        [
            ("OPENAI_API_KEY", "OpenAI estimate only"),
            ("ANTHROPIC_API_KEY", "Anthropic estimate only"),
        ],
    )
    def test_auto_full_estimate_when_opt_in_provider_key_set(
        self, monkeypatch, capsys, env_name, expected_fragment
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
        assert expected_fragment in payload["mode_label"]
        assert "execution needs XAI or Gemini" in payload["mode_label"]

    @pytest.mark.parametrize("env_name", ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
    def test_non_xai_provider_does_not_select_fast_cost_shape(self, mocks, monkeypatch, env_name):
        estimate_cost = MagicMock(return_value=mocks)
        monkeypatch.setattr("primr.utils.cost_estimator.estimate_cost", estimate_cost)
        for key in (
            "XAI_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv(env_name, "provider-key-" + "x" * 20)

        assert run_dry_run(_config(mode="complete")) == 0

        assert estimate_cost.call_args.kwargs["fast_mode"] is False

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
        # Recovery details are verbose-only; default shows a one-liner.
        assert "Recovery:" in out
        assert "Recovery table JSON" not in out
        assert "Next steps" in out
        assert "--budget <usd>" in out
        assert "--check-jobs" in out
        assert "--resume-latest" in out
        assert "--list-recent" in out

    def test_full_path_estimate_header_uses_full_label(self, mocks, monkeypatch, capsys):
        monkeypatch.setenv("XAI_API_KEY", "x" * 30)
        result = run_dry_run(_config(mode="complete", fast_mode=True))

        assert result == 0
        out = capsys.readouterr().out
        assert "Cost estimate" in out
        assert "full (" in out

    def test_verbose_output_retains_recovery_json(self, mocks, capsys):
        result = run_dry_run(_config(mode="scrape", verbose=True))

        assert result == 0
        out = capsys.readouterr().out
        assert "Recovery table JSON" in out
        assert "{}" in out

    def test_budget_policy_prints_optional_strategy_checkpoint_for_premium(self, mocks, capsys):
        result = run_dry_run(_config(mode="complete", premium_mode=True, budget_usd=2.0))

        assert result == 0
        out = capsys.readouterr().out
        assert "Budget policy" in out
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
        est_mock = MagicMock(return_value=mocks)
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            est_mock,
        )
        run_dry_run(_config(mode="complete", platforms=("aws", "azure", "gcp")))
        kwargs = est_mock.call_args.kwargs
        assert kwargs["num_vendors"] == 3

    def test_clamps_empty_ai_strategy_platforms_to_one_vendor(self, mocks, monkeypatch):
        est_mock = MagicMock(return_value=mocks)
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            est_mock,
        )
        run_dry_run(_config(mode="complete", platforms=()))
        kwargs = est_mock.call_args.kwargs
        assert kwargs["num_vendors"] == 1

    def test_passes_lite_strategy_flag(self, mocks, monkeypatch):
        est_mock = MagicMock(return_value=mocks)
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            est_mock,
        )
        run_dry_run(_config(mode="complete", lite_strategy=True))
        assert est_mock.call_args.kwargs["lite_strategy"] is True

    def test_passes_grok_tier(self, mocks, monkeypatch):
        est_mock = MagicMock(return_value=mocks)
        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            est_mock,
        )
        run_dry_run(_config(mode="complete", fast_mode=True, grok_tier="max"))
        assert est_mock.call_args.kwargs["grok_tier"] == "max"
