"""Run-scoped usage ledger for Gemini calls made through compatibility seams."""

from __future__ import annotations

from threading import Lock
from typing import Any

_usage_by_model: dict[str, dict[str, int]] = {}
_lock = Lock()


def record_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> None:
    """Record one Gemini call in the shared run ledger."""

    with _lock:
        bucket = _usage_by_model.setdefault(
            model,
            {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0},
        )
        bucket["input_tokens"] += max(0, int(input_tokens))
        bucket["output_tokens"] += max(0, int(output_tokens))
        bucket["cached_input_tokens"] += max(0, int(cached_input_tokens))


def record_response(model: str, response: Any) -> None:
    """Extract and record token usage from a direct Gemini SDK response."""

    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return
    record_usage(
        model,
        getattr(metadata, "prompt_token_count", 0) or 0,
        getattr(metadata, "candidates_token_count", 0) or 0,
        getattr(metadata, "cached_content_token_count", 0) or 0,
    )


def get_usage_by_model() -> dict[str, dict[str, int]]:
    """Return a detached snapshot of the current run ledger."""

    with _lock:
        return {model: dict(values) for model, values in _usage_by_model.items()}


def reset_usage() -> None:
    """Clear the current run ledger."""

    with _lock:
        _usage_by_model.clear()
