"""Unit tests for _list_installed_ollama_models and _resolve_local_judge_models."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.cli import (
    CLIConfig,
    Command,
    _list_installed_ollama_models,
    _resolve_local_judge_models,
)


def _config(**overrides):
    defaults = {"command": Command.EVAL}
    defaults.update(overrides)
    return CLIConfig(**defaults)


class TestListInstalledOllamaModels:
    def test_returns_empty_set_when_ollama_missing(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            MagicMock(side_effect=FileNotFoundError("ollama not installed")),
        )
        assert _list_installed_ollama_models() == set()

    def test_returns_empty_when_command_fails(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            MagicMock(side_effect=RuntimeError("subprocess failed")),
        )
        assert _list_installed_ollama_models() == set()

    def test_parses_model_names_from_output(self, monkeypatch):
        result = MagicMock()
        result.stdout = (
            "NAME             ID         SIZE   MODIFIED\n"
            "llama3:latest    abc123     4.7GB  2 weeks ago\n"
            "qwen2.5:7b       def456     4.4GB  1 month ago\n"
        )
        monkeypatch.setattr("subprocess.run", MagicMock(return_value=result))
        models = _list_installed_ollama_models()
        assert models == {"llama3:latest", "qwen2.5:7b"}

    def test_skips_header_line(self, monkeypatch):
        result = MagicMock()
        result.stdout = "name id\nmodel1 abc\n"
        monkeypatch.setattr("subprocess.run", MagicMock(return_value=result))
        models = _list_installed_ollama_models()
        assert "name" not in models
        assert "model1" in models

    def test_handles_empty_output(self, monkeypatch):
        result = MagicMock()
        result.stdout = ""
        monkeypatch.setattr("subprocess.run", MagicMock(return_value=result))
        assert _list_installed_ollama_models() == set()


class TestResolveLocalJudgeModels:
    def test_returns_judge_models_when_explicit(self, monkeypatch):
        monkeypatch.setattr(
            "primr.core.cli._list_installed_ollama_models",
            lambda: {"llama3", "qwen"},
        )
        config = _config(
            eval_judge_models=("llama3", "qwen"),
            eval_judge_model_list=None,
            eval_judge_model="default",
        )
        available, missing = _resolve_local_judge_models(config)
        assert "llama3" in available
        assert "qwen" in available
        assert missing == []

    def test_returns_missing_when_not_installed(self, monkeypatch):
        monkeypatch.setattr(
            "primr.core.cli._list_installed_ollama_models",
            lambda: {"llama3"},
        )
        config = _config(
            eval_judge_models=("llama3", "qwen", "phi"),
            eval_judge_model_list=None,
            eval_judge_model="default",
        )
        available, missing = _resolve_local_judge_models(config)
        assert available == ["llama3"]
        assert "qwen" in missing
        assert "phi" in missing

    def test_uses_model_list_when_specified(self, monkeypatch):
        monkeypatch.setattr(
            "primr.config.local_eval_models.get_local_eval_model_list",
            lambda name: ["m1", "m2"],
        )
        monkeypatch.setattr(
            "primr.core.cli._list_installed_ollama_models",
            lambda: {"m1", "m2"},
        )
        config = _config(
            eval_judge_models=(),
            eval_judge_model_list="default-list",
            eval_judge_model="default",
        )
        available, missing = _resolve_local_judge_models(config)
        assert available == ["m1", "m2"]

    def test_uses_single_judge_model_when_no_list(self, monkeypatch):
        monkeypatch.setattr(
            "primr.core.cli._list_installed_ollama_models",
            lambda: {"llama3"},
        )
        config = _config(
            eval_judge_models=(),
            eval_judge_model_list=None,
            eval_judge_model="llama3",
        )
        available, missing = _resolve_local_judge_models(config)
        assert "llama3" in available

    def test_empty_installed_returns_selected_as_available(self, monkeypatch):
        monkeypatch.setattr(
            "primr.core.cli._list_installed_ollama_models",
            lambda: set(),
        )
        config = _config(
            eval_judge_models=("llama3",),
            eval_judge_model_list=None,
            eval_judge_model="default",
        )
        available, missing = _resolve_local_judge_models(config)
        # When ollama not detected, all selected models pass through
        assert "llama3" in available
        assert missing == []

    def test_dedupes_repeated_models(self, monkeypatch):
        monkeypatch.setattr(
            "primr.core.cli._list_installed_ollama_models",
            lambda: {"llama3"},
        )
        config = _config(
            eval_judge_models=("llama3", "llama3", "llama3"),
            eval_judge_model_list=None,
            eval_judge_model="default",
        )
        available, missing = _resolve_local_judge_models(config)
        assert available == ["llama3"]
        assert missing == []
