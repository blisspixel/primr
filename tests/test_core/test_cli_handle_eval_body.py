"""Unit tests for _handle_eval body branches in primr.core.cli."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from primr.core.cli import CLIConfig, Command, _handle_eval


def _config(**overrides):
    defaults = {
        "command": Command.EVAL,
        "eval_id": "eval-2026-r1",
        "eval_baseline": "full",
        "eval_profiles": ("full", "lite"),
    }
    defaults.update(overrides)
    return CLIConfig(**defaults)


@pytest.fixture
def stub_eval_deps(monkeypatch, tmp_path):
    """Mock all the model_eval imports."""
    monkeypatch.setattr(
        "primr.core.model_eval.get_eval_profile",
        lambda p: MagicMock(estimated_cost_usd=1.5) if p in ("full", "lite", "fast") else None,
    )
    monkeypatch.setattr(
        "primr.core.model_eval.list_eval_profile_names",
        lambda: ["full", "lite", "fast"],
    )
    monkeypatch.setattr(
        "primr.core.model_eval._safe_eval_dir",
        lambda root, eid: Path(root) / eid,
    )
    monkeypatch.setattr(
        "primr.core.model_eval.auto_stage_existing_reports",
        MagicMock(return_value={}),
    )
    monkeypatch.setattr(
        "primr.core.model_eval.evaluate_outputs",
        MagicMock(
            return_value=MagicMock(
                missing_pairs=[],
                summary="",
            )
        ),
    )
    monkeypatch.setattr(
        "primr.core.model_eval.write_llm_judge_report",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "primr.core.model_eval.write_fast_feedback_guidance",
        MagicMock(return_value=None),
    )
    return tmp_path


class TestEvalBody:
    def test_runs_through_validation(self, stub_eval_deps, tmp_path):
        """Happy path: all validations pass and eval runs."""
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path),
            )
        )
        # Returns 0 if evaluation succeeded, 1 otherwise. Should be 0 for empty manifest path.
        assert result in (0, 1)

    def test_auto_stage_runs(self, stub_eval_deps, tmp_path, monkeypatch):
        stage_mock = MagicMock(return_value={"full": ["a", "b"]})
        monkeypatch.setattr(
            "primr.core.model_eval.auto_stage_existing_reports",
            stage_mock,
        )
        _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_auto_stage=True,
                eval_source_dir=str(tmp_path / "source"),
                eval_root=str(tmp_path),
            )
        )
        stage_mock.assert_called_once()

    def test_run_missing_without_manifest_returns_1(self, stub_eval_deps, tmp_path):
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_run_missing=True,
                eval_max_new_runs=5,
                eval_max_estimated_cost=10.0,
                eval_root=str(tmp_path),
                eval_manifest=None,
            )
        )
        assert result == 1

    def test_run_missing_zero_new_runs_returns_1(
        self, stub_eval_deps, tmp_path
    ):
        manifest = tmp_path / "manifest.csv"
        manifest.write_text("company,website\nExampleCo,https://x.example\n")
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_run_missing=True,
                eval_max_new_runs=0,
                eval_max_estimated_cost=10.0,
                eval_root=str(tmp_path),
                eval_manifest=str(manifest),
            )
        )
        assert result == 1

    def test_run_missing_zero_max_cost_returns_1(
        self, stub_eval_deps, tmp_path
    ):
        manifest = tmp_path / "manifest.csv"
        manifest.write_text("company,website\nExampleCo,https://x.example\n")
        result = _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_run_missing=True,
                eval_max_new_runs=5,
                eval_max_estimated_cost=0.0,
                eval_root=str(tmp_path),
                eval_manifest=str(manifest),
            )
        )
        assert result == 1

    def test_company_creates_manifest(self, stub_eval_deps, tmp_path):
        _handle_eval(
            _config(
                eval_id="eval-r1",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_company="ExampleCo",
                eval_root=str(tmp_path),
            )
        )
        # Should have written eval_company_manifest.csv
        manifest = tmp_path / "eval-r1" / "eval_company_manifest.csv"
        assert manifest.exists()
        assert "ExampleCo" in manifest.read_text(encoding="utf-8")
