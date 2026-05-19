"""Unit tests for _handle_eval early-return validation in primr.core.cli.

The body of _handle_eval is enormous; this file targets the front-loaded
validation gates that bail before any eval execution.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.cli import CLIConfig, Command, _handle_eval


def _config(**overrides):
    defaults = {"command": Command.EVAL}
    defaults.update(overrides)
    return CLIConfig(**defaults)


class TestEvalValidation:
    def test_missing_eval_id_returns_1(self):
        assert _handle_eval(_config(eval_id=None)) == 1

    def test_baseline_not_in_profiles_returns_1(self):
        assert (
            _handle_eval(
                _config(
                    eval_id="eval-2026-r1",
                    eval_baseline="not-in-list",
                    eval_profiles=("full", "lite"),
                )
            )
            == 1
        )

    def test_unknown_profile_returns_1(self, monkeypatch):
        # Mock model_eval helpers
        monkeypatch.setattr(
            "primr.core.model_eval.get_eval_profile",
            lambda p: None,  # everything unknown
        )
        monkeypatch.setattr(
            "primr.core.model_eval.list_eval_profile_names",
            lambda: ["full", "lite", "fast"],
        )
        result = _handle_eval(
            _config(
                eval_id="eval-2026-r1",
                eval_baseline="full",
                eval_profiles=("full",),
            )
        )
        assert result == 1

    def test_unknown_baseline_returns_1(self, monkeypatch):
        # baseline is in profiles list but not registered
        def get_profile(p):
            return MagicMock() if p == "lite" else None

        monkeypatch.setattr(
            "primr.core.model_eval.get_eval_profile", get_profile
        )
        monkeypatch.setattr(
            "primr.core.model_eval.list_eval_profile_names",
            lambda: ["full", "lite", "fast"],
        )
        result = _handle_eval(
            _config(
                eval_id="eval-2026-r1",
                eval_baseline="full",  # not registered
                eval_profiles=("full", "lite"),  # only lite is registered
            )
        )
        assert result == 1

    def test_invalid_eval_id_with_traversal_returns_1(self, monkeypatch, tmp_path):
        # All profiles validate as registered
        monkeypatch.setattr(
            "primr.core.model_eval.get_eval_profile",
            lambda p: MagicMock(),
        )
        # Force _safe_eval_dir to reject
        monkeypatch.setattr(
            "primr.core.model_eval._safe_eval_dir",
            MagicMock(side_effect=ValueError("path traversal")),
        )
        result = _handle_eval(
            _config(
                eval_id="../escape",
                eval_baseline="full",
                eval_profiles=("full",),
                eval_root=str(tmp_path),
            )
        )
        assert result == 1
