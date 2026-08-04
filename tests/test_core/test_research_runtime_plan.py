"""Tests for pure research runtime routing and estimate-shaping policy."""

from __future__ import annotations

import pytest

from primr.core.research_runtime_plan import (
    prepare_research_runtime,
    resolve_research_runtime_plan,
)


@pytest.mark.parametrize("mode", ["complete", "structured", "hybrid"])
def test_xai_auto_selects_fast_for_full_modes(mode):
    plan = resolve_research_runtime_plan(
        mode=mode,
        explicit_fast_mode=False,
        premium_mode=False,
        xai_available=True,
        platform_count=2,
        ai_strategy=True,
        strategy_types=None,
        refresh_vendor_research=True,
    )

    assert plan.use_fast is True
    assert plan.runtime_platform_count == 2
    assert plan.vendor_refresh_tasks == 2
    assert plan.error_message is None


def test_premium_prevents_automatic_fast_selection():
    plan = resolve_research_runtime_plan(
        mode="complete",
        explicit_fast_mode=False,
        premium_mode=True,
        xai_available=True,
        platform_count=1,
        ai_strategy=True,
        strategy_types=None,
        refresh_vendor_research=False,
    )

    assert plan.use_fast is False


@pytest.mark.parametrize(
    ("strategy_types", "platform_count", "message_fragment"),
    [
        (["customer_experience"], 1, "Explicit strategy types"),
        (None, 2, "Multiple strategy platforms"),
    ],
)
def test_legacy_structured_rejects_ignored_shapes(strategy_types, platform_count, message_fragment):
    plan = resolve_research_runtime_plan(
        mode="structured",
        explicit_fast_mode=False,
        premium_mode=False,
        xai_available=False,
        platform_count=platform_count,
        ai_strategy=True,
        strategy_types=strategy_types,
        refresh_vendor_research=True,
    )

    assert message_fragment in (plan.error_message or "")
    assert plan.runtime_platform_count == 1


def test_refresh_is_not_priced_when_selected_strategy_cannot_execute_it():
    plan = resolve_research_runtime_plan(
        mode="complete",
        explicit_fast_mode=False,
        premium_mode=True,
        xai_available=False,
        platform_count=1,
        ai_strategy=True,
        strategy_types=["customer_experience"],
        refresh_vendor_research=True,
    )

    assert plan.vendor_refresh_tasks == 0


def test_explicit_fast_is_not_dependent_on_an_environment_key():
    plan = resolve_research_runtime_plan(
        mode="complete",
        explicit_fast_mode=True,
        premium_mode=False,
        xai_available=False,
        platform_count=1,
        ai_strategy=False,
        strategy_types=None,
        refresh_vendor_research=True,
    )

    assert plan.use_fast is True
    assert plan.vendor_refresh_tasks == 0


def test_preparation_forwards_the_resolved_shape_to_confirmation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "primr.utils.cost_display.display_cost_estimate",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )

    preparation = prepare_research_runtime(
        mode="complete",
        display_name="ExampleCo",
        explicit_fast_mode=True,
        premium_mode=False,
        xai_available=False,
        platform_count=2,
        ai_strategy=True,
        strategy_types=None,
        refresh_vendor_research=True,
        skip_confirm=False,
        lite_strategy=False,
        verify=True,
        grok_tier="max",
    )

    assert preparation.status == "ready"
    assert calls[0][1]["fast_mode"] is True
    assert calls[0][1]["num_vendors"] == 2
    assert calls[0][1]["vendor_research_refreshes"] == 2


def test_invalid_preparation_never_requests_cost_confirmation(monkeypatch):
    confirm = pytest.fail
    monkeypatch.setattr("primr.utils.cost_display.display_cost_estimate", confirm)
    monkeypatch.setattr("primr.utils.cost_display.print_cost_estimate", confirm)

    preparation = prepare_research_runtime(
        mode="structured",
        display_name="ExampleCo",
        explicit_fast_mode=False,
        premium_mode=False,
        xai_available=False,
        platform_count=2,
        ai_strategy=True,
        strategy_types=None,
        refresh_vendor_research=True,
        skip_confirm=False,
        lite_strategy=False,
        verify=False,
        grok_tier="hybrid",
    )

    assert preparation.status == "invalid"


def test_skip_confirm_still_prints_cost_estimate(monkeypatch):
    """Single-company runs skip Proceed, but must never start silently."""
    printed = []
    monkeypatch.setattr(
        "primr.utils.cost_display.print_cost_estimate",
        lambda *args, **kwargs: printed.append((args, kwargs)) or object(),
    )
    confirm = pytest.fail
    monkeypatch.setattr("primr.utils.cost_display.display_cost_estimate", confirm)

    preparation = prepare_research_runtime(
        mode="complete",
        display_name="ExampleCo",
        explicit_fast_mode=True,
        premium_mode=False,
        xai_available=True,
        platform_count=1,
        ai_strategy=True,
        strategy_types=None,
        refresh_vendor_research=False,
        skip_confirm=True,
        lite_strategy=False,
        verify=False,
        grok_tier="hybrid",
    )

    assert preparation.status == "ready"
    assert len(printed) == 1
    assert printed[0][0][0] == "complete"
    assert printed[0][0][1] == "ExampleCo"
    assert printed[0][1]["fast_mode"] is True
    assert printed[0][1]["grok_tier"] == "hybrid"
