"""Current Gemini evaluation candidates are registered but not defaulted.

Model-selection policy: register flagship / newer models so they can be
selected explicitly or eval-gated in, but never silently promote one to a
default tier (defaults change only after an eval on output $/1M). These pins
guard both halves of that: the new ids must be resolvable and priced, and they
must NOT be the active FLASH/PRO defaults.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from primr.config.models import PrimrModels

NEW_GEMINI_MODELS = [
    "gemini-4-argon",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]


@pytest.mark.parametrize("model", NEW_GEMINI_MODELS)
def test_new_gemini_model_is_registered_and_priced(model: str) -> None:
    config = PrimrModels.get_model_config(model)
    assert config is not None, f"{model} must be in ALL_MODELS"
    assert config.provider == "google"
    # Prices must be present so the mandatory cost gate cannot KeyError.
    assert config.cost_per_1m_input_tokens > 0
    assert config.cost_per_1m_output_tokens > 0
    # A representative estimate must compute without raising.
    assert PrimrModels.calculate_cost(model, 100_000, 20_000) > 0


@pytest.mark.parametrize("model", NEW_GEMINI_MODELS)
def test_new_gemini_model_is_not_a_default_tier(model: str) -> None:
    # Registered != defaulted. A repoint of FLASH_MODEL / PRO_MODEL is eval-gated.
    assert model != PrimrModels.FLASH_MODEL
    assert model != PrimrModels.PRO_MODEL


def test_argon_has_synchronous_limits_and_scheduled_standard_cache_prices() -> None:
    config = PrimrModels.get_model_config("gemini-4-argon")
    assert config is not None
    assert config.max_input_tokens == 1_048_576
    assert config.max_output_tokens == 65_536
    assert config.standard_rates(date(2026, 11, 30)) == (2.0, 10.0, 0.1)
    assert config.standard_rates(date(2026, 12, 1)) == (4.0, 20.0, 0.2)
    assert PrimrModels.calculate_cost(
        config.name,
        1_000_000,
        1_000_000,
        cached_input_tokens=500_000,
        pricing_date=date(2026, 12, 1),
    ) == pytest.approx(22.1)


@pytest.mark.parametrize(
    ("name", "before", "retired", "replacement"),
    [
        ("gemini-3-pro-preview", date(2026, 3, 8), date(2026, 3, 9), "gemini-3.1-pro-preview"),
        ("gemini-3-pro-image-preview", date(2026, 6, 24), date(2026, 6, 25), "gemini-3-pro-image"),
    ],
)
def test_retired_routes_reject_new_work_but_keep_historical_costs(
    name, before, retired, replacement
):
    config = PrimrModels.get_model_config(name)
    assert config is not None
    config.require_available(before)
    with pytest.raises(ValueError, match=replacement):
        config.require_available(retired)
    assert PrimrModels.calculate_cost(name, 1000, 1000) > 0


@pytest.mark.parametrize(
    "model",
    ["gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
)
def test_direct_google_routes_without_announced_shutdown_remain_available(model):
    config = PrimrModels.get_model_config(model)
    assert config is not None
    assert config.expiration_date is None
    config.require_available(date(2026, 10, 20))


@pytest.mark.parametrize("method", ["chat", "search_and_summarize"])
def test_retired_gemini_request_stops_before_sdk_client_creation(method, monkeypatch):
    from primr.ai.providers.gemini import GeminiProvider

    provider = GeminiProvider()
    client_factory = MagicMock()
    monkeypatch.setattr(provider, "_get_client", client_factory)
    call = getattr(provider, method)
    argument = [{"role": "user", "content": "control"}] if method == "chat" else "control"
    with pytest.raises(ValueError, match=r"gemini-3\.1-pro-preview"):
        call(argument, model="gemini-3-pro-preview")
    client_factory.assert_not_called()


def test_retired_configured_utility_route_stops_during_selection(monkeypatch):
    from primr.ai.routing import Role, pick_model_for_role

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-ci-tests")
    monkeypatch.setenv("PRIMR_GEMINI_UTILITY_MODEL", "gemini-3-pro-preview")
    with pytest.raises(ValueError, match=r"gemini-3\.1-pro-preview"):
        pick_model_for_role(Role.UTILITY)


def test_aliases_and_restricted_legacy_models_do_not_advertise_as_flagships():
    assert PrimrModels.is_latest_model("gemini-4-argon")
    assert PrimrModels.is_latest_model("gemini-3.8-flash")
    for name in ("gemini-3.7-flash", "gemini-3.5-flash", "gemini-3-pro-preview", "gemini-2.5-pro"):
        assert PrimrModels.get_model_config(name) is not None
        assert not PrimrModels.is_latest_model(name)


def test_verified_alias_prices_are_current_without_rewriting_historical_identity():
    legacy = PrimrModels.get_model_config("gemini-3.5-flash")
    assert legacy is not None
    assert legacy.name == "gemini-3.5-flash"
    assert legacy.cost_per_1m_input_tokens == 1.5
    assert PrimrModels.get_price(legacy.name, date(2026, 5, 20)) == (1.5, 9.0)
    assert PrimrModels.get_price(legacy.name, date(2026, 10, 20)) == (0.75, 3.75)
    assert PrimrModels.get_price(legacy.name, date(2027, 1, 1)) == (1.5, 7.5)
    assert PrimrModels.calculate_cost(
        legacy.name,
        1_000_000,
        1_000_000,
        cached_input_tokens=500_000,
        pricing_date=date(2026, 10, 20),
    ) == pytest.approx(4.1625)
    assert PrimrModels.require_model_available(legacy.name) == legacy.name
