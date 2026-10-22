"""Provider-specific retirement guards preserve historical cost accounting."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from primr.ai.providers.openrouter import OpenRouterProvider
from primr.ai.routing import Role, pick_model_for_role
from primr.config import model_config
from primr.config.models import ModelRegistry, PrimrModels
from primr.config.settings import AIConfig


@pytest.fixture(autouse=True)
def frozen_gateway_retirement_snapshot(monkeypatch):
    """Exercise guards with the earlier snapshot, independent of current availability."""
    from primr.config.openrouter_models import OPENROUTER_EXPIRATIONS

    for name in (
        "google/gemini-2.5-flash-lite",
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
    ):
        monkeypatch.setitem(OPENROUTER_EXPIRATIONS, name, date(2026, 10, 20))
    config = ModelRegistry.OPENROUTER_GEMINI_2_5_FLASH_LITE
    monkeypatch.setattr(config, "expiration_date", date(2026, 10, 20))


def set_today(monkeypatch, day: date) -> None:
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return cls(day.year, day.month, day.day, tzinfo=UTC)

    monkeypatch.setattr(model_config, "datetime", Clock)


@pytest.mark.parametrize("day", [date(2026, 10, 20), date(2026, 10, 21)])
def test_expired_gateway_model_fails_before_transport(monkeypatch, day):
    set_today(monkeypatch, day)
    monkeypatch.setenv("PRIMR_OPENROUTER_ENABLED", "1")
    provider = OpenRouterProvider()
    provider._client = MagicMock()
    with pytest.raises(ValueError, match=r"expired on 2026-10-20.*3\.1-flash-lite"):
        provider.chat([], model="google/gemini-2.5-flash-lite")
    provider._client.chat.completions.create.assert_not_called()


def test_retirement_boundary_keeps_old_costs_and_direct_api_available():
    historical = ModelRegistry.OPENROUTER_MODELS[0]
    assert historical is ModelRegistry.OPENROUTER_GEMINI_2_5_FLASH_LITE
    historical.require_available(date(2026, 10, 19))
    with pytest.raises(ValueError, match="Re-estimate"):
        historical.require_available(date(2026, 10, 20))
    assert PrimrModels.calculate_cost(historical.name, 1_000_000, 1_000_000) == 0.5
    for name in ("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"):
        config = PrimrModels.get_model_config(name)
        assert config is not None
        assert not config.deprecated
        config.require_available(date(2026, 10, 21))


@pytest.mark.parametrize(
    ("role", "variable"),
    [(Role.UTILITY, "UTILITY"), (Role.WRITING, "WRITING"), (Role.REASONING, "REASONING")],
)
def test_role_overrides_reject_retirement_without_silent_replacement(monkeypatch, role, variable):
    set_today(monkeypatch, date(2026, 10, 20))
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-test-key")
    monkeypatch.setenv("PRIMR_PROVIDER", "openrouter")
    monkeypatch.setenv(f"PRIMR_OPENROUTER_{variable}_MODEL", "google/gemini-2.5-flash-lite")
    with pytest.raises(ValueError, match="expired on"):
        pick_model_for_role(role)
    monkeypatch.setenv(f"PRIMR_OPENROUTER_{variable}_MODEL", "google/gemini-3.1-flash-lite")
    assert pick_model_for_role(role) == "google/gemini-3.1-flash-lite"


@pytest.mark.parametrize(
    "name",
    [
        "google/gemini-2.5-flash-lite",
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
        "google/gemini-2.5-flash:batch",
        "google/gemini-2.5-pro:batch",
    ],
)
def test_global_override_cannot_bypass_expiration_with_custom_prices(monkeypatch, name):
    set_today(monkeypatch, date(2026, 10, 21))
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-test-key")
    monkeypatch.setenv("PRIMR_PROVIDER", "openrouter")
    monkeypatch.setenv("PRIMR_OPENROUTER_MODEL", name)
    monkeypatch.setenv("PRIMR_OPENROUTER_INPUT_PRICE", "1")
    monkeypatch.setenv("PRIMR_OPENROUTER_OUTPUT_PRICE", "1")
    with pytest.raises(ValueError, match="expired on"):
        pick_model_for_role(Role.UTILITY)
    provider = OpenRouterProvider()
    provider._client = MagicMock()
    with pytest.raises(ValueError, match="expired on"):
        provider.chat([], model=name)
    provider._client.chat.completions.create.assert_not_called()


def test_default_roles_are_available_and_utility_estimate_uses_successor(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-test-key")
    monkeypatch.setenv("PRIMR_PROVIDER", "openrouter")
    for role in Role:
        model = PrimrModels.get_model_config(pick_model_for_role(role))
        assert model is not None
        model.require_available()
        model.require_available(date(2026, 10, 21))
    utility = pick_model_for_role(Role.UTILITY)
    assert utility == "google/gemini-3.1-flash-lite"
    assert PrimrModels.calculate_cost(utility, 1_000_000, 1_000_000) == 1.75


def test_direct_role_overrides_and_pilot_judge_share_settings(monkeypatch):
    import importlib.util
    from pathlib import Path

    from primr.config.settings import get_settings

    monkeypatch.setenv("AI_FAST_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setenv("AI_REASONING_MODEL", "gemini-3.8-flash")
    settings = AIConfig()
    assert settings.flash_model == settings.fast_model == "gemini-3.1-flash-lite"
    assert settings.pro_model == settings.reasoning_model == "gemini-3.8-flash"
    monkeypatch.setattr(get_settings().ai, "pro_model", settings.pro_model)
    path = Path(__file__).parents[2] / "tools" / "pilot_judge.py"
    spec = importlib.util.spec_from_file_location("pilot_judge_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.JUDGE_MODEL == "gemini-3.8-flash"


def test_direct_runtime_routes_honor_generic_and_role_specific_overrides(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setenv("PRIMR_PROVIDER", "gemini")
    monkeypatch.setenv("AI_FAST_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("AI_REASONING_MODEL", "gemini-3.8-flash")
    assert pick_model_for_role(Role.UTILITY) == "gemini-3.5-flash-lite"
    assert pick_model_for_role(Role.REASONING) == "gemini-3.8-flash"
    assert pick_model_for_role(Role.PRO) == "gemini-3.8-flash"
    assert pick_model_for_role(Role.WRITING) == "gemini-3.1-flash-lite"
    for role, variable in (
        (Role.UTILITY, "UTILITY"),
        (Role.WRITING, "WRITING"),
        (Role.REASONING, "REASONING"),
        (Role.PRO, "REASONING"),
    ):
        monkeypatch.setenv(f"PRIMR_GEMINI_{variable}_MODEL", "gemini-3.7-flash")
        assert pick_model_for_role(role) == "gemini-3.7-flash"


def test_sdk_wire_model_cannot_bypass_retirement_checks(monkeypatch):
    import json

    import httpx
    from openai import OpenAI

    set_today(monkeypatch, date(2026, 10, 21))
    monkeypatch.setenv("PRIMR_OPENROUTER_ENABLED", "1")
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "google/gemini-3.1-flash-lite",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    with OpenAI(
        api_key="fake-test-key",
        base_url="https://openrouter.invalid/api/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        max_retries=0,
    ) as client:
        provider = OpenRouterProvider()
        provider._client = client
        for extra in (
            {"model": "google/gemini-2.5-flash-lite"},
            {"models": ["google/gemini-2.5-flash-lite"]},
        ):
            with pytest.raises(ValueError, match="cannot override model or models"):
                provider.chat([], model="google/gemini-3.1-flash-lite", extra_body=extra)
        assert not requests
        provider.chat(
            [{"role": "user", "content": "test"}],
            model="google/gemini-3.1-flash-lite",
            extra_body={"user": "fixture"},
        )
    assert len(requests) == 1
    assert requests[0]["model"] == "google/gemini-3.1-flash-lite"
    assert requests[0]["user"] == "fixture"
    assert requests[0]["provider"]["max_price"] == {"prompt": 0.25, "completion": 1.5}
