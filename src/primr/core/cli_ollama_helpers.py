"""Ollama local-model discovery helpers used by the eval CLI."""

from __future__ import annotations

from typing import Any


def list_installed_ollama_models() -> set[str]:
    """Best-effort listing of locally available Ollama models."""
    import subprocess

    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
    except Exception:
        return set()

    models: set[str] = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("name "):
            continue
        parts = stripped.split()
        if parts:
            models.add(parts[0])
    return models


def resolve_local_judge_models(config: Any) -> tuple[list[str], list[str]]:
    """Resolve the requested local judge models and return (selected, missing)."""
    from primr.config.local_eval_models import get_local_eval_model_list

    selected: list[str] = []
    if config.eval_judge_models:
        selected.extend(config.eval_judge_models)
    elif config.eval_judge_model_list:
        selected.extend(get_local_eval_model_list(config.eval_judge_model_list))
    else:
        selected.append(config.eval_judge_model)

    # Deduplicate while preserving order.
    selected = list(dict.fromkeys(model.strip() for model in selected if model and model.strip()))
    installed = list_installed_ollama_models()
    if not installed:
        return selected, []

    available = [model for model in selected if model in installed]
    missing = [model for model in selected if model not in installed]
    return available, missing
