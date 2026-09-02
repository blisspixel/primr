"""OpenRouter's opt-in, privacy, pricing, and accounting contract."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.providers.base import ProviderUnavailableError
from primr.ai.providers.openrouter import OPENROUTER_APP_HEADERS, OpenRouterProvider
from primr.config.models import ModelRegistry


def _response(*, cost: object = "0.000123") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="professional output"))],
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=30,
            cached_tokens=20,
            cost=cost,
        ),
    )


def _enabled_provider(monkeypatch) -> tuple[OpenRouterProvider, MagicMock]:
    monkeypatch.setenv("PRIMR_OPENROUTER_ENABLED", "1")
    provider = OpenRouterProvider()
    client = MagicMock()
    client.chat.completions.create.return_value = _response()
    provider._client = client
    return provider, client


def test_key_presence_does_not_bypass_paid_routing_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("PRIMR_OPENROUTER_ENABLED", raising=False)
    provider = OpenRouterProvider()

    with pytest.raises(ProviderUnavailableError, match="paid routing is disabled"):
        provider.chat(
            [{"role": "user", "content": "test"}],
            model=ModelRegistry.OPENROUTER_GEMINI_2_5_FLASH_LITE.name,
        )


def test_request_enforces_privacy_and_registered_price_ceiling(monkeypatch) -> None:
    provider, client = _enabled_provider(monkeypatch)

    response = provider.chat(
        [{"role": "user", "content": "test"}],
        model=ModelRegistry.OPENROUTER_GEMINI_2_5_FLASH_LITE.name,
        max_tokens=64,
        extra_body={
            "plugins": [{"id": "allowed-caller-extension"}],
            "provider": {"zdr": False, "max_price": {"prompt": 999}},
        },
    )

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"]["plugins"] == [{"id": "allowed-caller-extension"}]
    assert kwargs["extra_body"]["provider"] == {
        "allow_fallbacks": True,
        "require_parameters": True,
        "data_collection": "deny",
        "max_price": {"prompt": 0.10, "completion": 0.40},
        "zdr": True,
    }
    assert response.actual_cost_usd == pytest.approx(0.000123)
    assert response.cached_input_tokens == 20


def test_request_caps_output_at_registered_model_limit(monkeypatch) -> None:
    provider, client = _enabled_provider(monkeypatch)

    provider.chat(
        [{"role": "user", "content": "test"}],
        model=ModelRegistry.OPENROUTER_GPT_4_1_MINI.name,
        max_tokens=65_000,
    )

    assert client.chat.completions.create.call_args.kwargs["max_tokens"] == 32_768


def test_zdr_can_be_explicitly_relaxed_but_data_collection_stays_denied(monkeypatch) -> None:
    provider, client = _enabled_provider(monkeypatch)
    monkeypatch.setenv("PRIMR_OPENROUTER_ZDR", "0")

    provider.chat(
        [{"role": "user", "content": "test"}],
        model=ModelRegistry.OPENROUTER_GPT_4_1_MINI.name,
    )

    policy = client.chat.completions.create.call_args.kwargs["extra_body"]["provider"]
    assert "zdr" not in policy
    assert policy["data_collection"] == "deny"
    assert policy["max_price"] == {"prompt": 0.40, "completion": 1.60}


@pytest.mark.parametrize("cost", [None, True, -0.1, "nan", "not-a-number"])
def test_invalid_exact_cost_is_not_treated_as_billed_amount(monkeypatch, cost: object) -> None:
    provider, client = _enabled_provider(monkeypatch)
    client.chat.completions.create.return_value = _response(cost=cost)

    response = provider.chat(
        [{"role": "user", "content": "test"}],
        model=ModelRegistry.OPENROUTER_DEEPSEEK_V3_2.name,
    )

    assert response.actual_cost_usd is None


def test_unknown_model_fails_before_transport(monkeypatch) -> None:
    provider, client = _enabled_provider(monkeypatch)

    with pytest.raises(ValueError, match="not registered with explicit pricing"):
        provider.chat(
            [{"role": "user", "content": "test"}],
            model="unknown/unpriced",
        )

    client.chat.completions.create.assert_not_called()


def test_credential_probe_uses_authenticated_key_endpoint_without_generation(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    monkeypatch.delenv("PRIMR_OPENROUTER_ENABLED", raising=False)
    provider = OpenRouterProvider()
    response = MagicMock()
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.return_value = response

    with patch("primr.ai.providers.openrouter.httpx.Client", return_value=client) as factory:
        result = provider.validate_credentials()

    assert result.ok is True
    assert result.detail == "authenticated; key endpoint reachable"
    factory.assert_called_once_with(follow_redirects=False, timeout=15.0)
    client.get.assert_called_once_with(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": "Bearer test-openrouter"},
    )
    response.raise_for_status.assert_called_once_with()


def test_sdk_client_sends_openrouter_app_headers(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    provider = OpenRouterProvider()
    http_client = object()

    with (
        patch("openai.DefaultHttpxClient", return_value=http_client),
        patch("openai.OpenAI") as factory,
    ):
        provider._get_client()

    factory.assert_called_once_with(
        api_key="test-openrouter",
        base_url="https://openrouter.ai/api/v1",
        max_retries=0,
        http_client=http_client,
        default_headers=OPENROUTER_APP_HEADERS,
    )
