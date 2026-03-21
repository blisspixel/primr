"""Named local eval model presets.

Keep these lists small, practical, and easy to edit as the local model landscape
changes. They are used by the eval harness for local judge sweeps.
"""

from __future__ import annotations

DEFAULT_LOCAL_EVAL_MODEL_LIST = "4090-top10"

LOCAL_EVAL_MODEL_LISTS: dict[str, tuple[str, ...]] = {
    # Prioritize models that are plausible fits for a single RTX 4090 with
    # Ollama-style local inference. The list is intentionally editable as the
    # shortlist evolves.
    "4090-top10": (
        "glm-4.7-flash",
        "qwen3:32b",
        "qwen3:30b-a3b",
        "qwen3:30b",
        "qwen3-coder:30b",
        "qwen2.5-coder:32b-instruct-q5_K_M",
        "deepseek-r1:32b",
        "gemma3:27b",
        "nemotron-3-nano:30b",
        "qwen2.5:14b",
    ),
    "installed-starter": (
        "qwen3:30b",
        "qwen3-coder:30b",
        "qwen2.5-coder:32b-instruct-q5_K_M",
        "qwen2.5:14b",
    ),
}


def get_local_eval_model_list(name: str) -> tuple[str, ...]:
    try:
        return LOCAL_EVAL_MODEL_LISTS[name]
    except KeyError as exc:
        available = ", ".join(sorted(LOCAL_EVAL_MODEL_LISTS))
        raise KeyError(f"Unknown local eval model list: {name}. Available: {available}") from exc


def list_local_eval_model_lists() -> dict[str, tuple[str, ...]]:
    return dict(LOCAL_EVAL_MODEL_LISTS)
