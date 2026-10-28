"""Small presentation policies shared by Primr cost estimates.

Token and provider arithmetic remains in ``cost_estimator``. These helpers own
only additive duration and disclosure text, keeping the calculator focused and
making the same wording reusable across standard and fast estimate paths.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date


def deep_path_hiring_overhead(mode: str) -> tuple[int, int, list[str]]:
    """Return duration deltas and disclosure for deep-path hiring signals."""

    if mode not in ("deep-research", "complete"):
        return 0, 0, []
    return (
        1,
        2,
        [
            "Hiring signals via ATS / careers page (~$0.01 on the routed utility model, "
            "+1-2 min; skip with PRIMR_SKIP_HIRING_SIGNALS=1)"
        ],
    )


def strategy_type_notes(priced: Sequence[str], unavailable: Sequence[str]) -> list[str]:
    """Return disclosures for generated and runtime-skipped strategy types."""

    notes: list[str] = []
    if priced:
        notes.append(f"Strategy documents included: {', '.join(priced)}")
    if unavailable:
        notes.append(
            "Strategy type(s) not generated in this mode (the run will skip them): "
            + ", ".join(unavailable)
        )
    return notes


def vendor_refresh_duration_suffix(refresh_tasks: int) -> str:
    """Describe separately priced vendor-refresh work in a duration label."""

    return f" + {refresh_tasks} vendor research refresh task(s)" if refresh_tasks else ""


def vendor_refresh_notes(refresh_tasks: int) -> list[str]:
    """Return the estimate disclosure for explicit vendor-refresh work."""

    return (
        [f"Includes {refresh_tasks} explicitly requested vendor research refresh task(s)"]
        if refresh_tasks
        else []
    )


def cache_write_estimate_notes(model_names: Sequence[str | None]) -> list[str]:
    """Disclose published write-price allowances without claiming exact billing."""
    from primr.config.models import PrimrModels

    if any(
        (config := PrimrModels.get_model_config(name)) is not None
        and config.cost_per_1m_input_tokens_write_ceiling is not None
        for name in model_names
        if name is not None
    ):
        return [
            "Input estimates include published cache-write price ceilings; actual provider billing can be lower."
        ]
    return []


def scheduled_price_change_notes(
    model_names: Sequence[str | None], today: date | None = None
) -> list[str]:
    """Disclose published rate changes that a later run would be billed at."""
    from primr.config.models import PrimrModels

    effective = today or date.today()
    notes: list[str] = []
    for name in dict.fromkeys(name for name in model_names if name is not None):
        config = PrimrModels.get_model_config(name)
        if (
            config is None
            or config.price_change_date is None
            or config.price_change_date <= effective
            or config.cost_per_1m_input_tokens_after is None
            or config.cost_per_1m_output_tokens_after is None
        ):
            continue
        notes.append(
            f"{config.display_name} rates change on {config.price_change_date.isoformat()} "
            f"to ${config.cost_per_1m_input_tokens_after:g}/"
            f"${config.cost_per_1m_output_tokens_after:g} per 1M tokens; "
            "this estimate uses today's rates, so re-estimate after that date."
        )
    return notes
