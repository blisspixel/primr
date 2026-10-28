"""Estimate disclosures derived from registered provider price schedules."""

from __future__ import annotations

from datetime import date

from primr.utils.cost_estimate_policy import scheduled_price_change_notes


def test_upcoming_price_change_is_disclosed_once_with_new_rates() -> None:
    notes = scheduled_price_change_notes(
        ["gemini-4-argon", "gemini-4-argon", None], today=date(2026, 10, 28)
    )

    assert notes == [
        "Gemini 4 Argon rates change on 2026-12-01 to $4/$20 per 1M tokens; "
        "this estimate uses today's rates, so re-estimate after that date."
    ]


def test_price_change_already_in_effect_is_not_disclosed() -> None:
    assert scheduled_price_change_notes(["gemini-4-argon"], today=date(2026, 12, 1)) == []


def test_models_without_a_schedule_or_registration_add_no_notes() -> None:
    assert scheduled_price_change_notes(["grok-4.7", "not-a-model"], today=date(2026, 10, 28)) == []
