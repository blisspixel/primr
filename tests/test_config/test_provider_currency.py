"""Published prices, tier boundaries and offline request compatibility."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from primr.ai.providers.anthropic import AnthropicProvider
from primr.ai.providers.bedrock import BedrockProvider
from primr.ai.providers.openrouter import _provider_policy
from primr.config.models import GrokTier, PrimrModels


@pytest.mark.parametrize(
    ("name", "input_rate", "output_rate", "cache_rate"),
    [
        ("gpt-6-astra", 10, 50, 1),
        ("gpt-6-sol", 2, 10, 0.2),
        ("gpt-6.1-sol", 2, 10, 0.1),
        ("gpt-6-luna", 0.1, 0.5, 0.01),
        ("gpt-5.6-sol", 4, 20, 0.4),
        ("gpt-5.6", 4, 20, 0.4),
        ("o4-mini", 1.1, 4.4, 0.275),
        ("claude-sonnet-5", 2, 10, 0.2),
        ("claude-fable-5-1", 10, 50, 0.25),
        ("claude-opus-5-5", 4, 20, 0.2),
        ("claude-sonnet-5-5", 2, 10, 0.1),
        ("claude-haiku-5-5", 0.1, 0.5, 0.01),
        ("grok-4.7", 2, 6, 0.5),
    ],
)
def test_published_standard_rates(name, input_rate, output_rate, cache_rate):
    config = PrimrModels.get_model_config(name)
    assert config is not None
    assert config.standard_rates(date(2026, 10, 22)) == pytest.approx(
        (input_rate, output_rate, cache_rate)
    )
    cost = PrimrModels.calculate_cost(name, 1_000, 500, cached_input_tokens=400)
    assert cost == pytest.approx(
        (600 * input_rate + 400 * cache_rate + 500 * output_rate) / 1_000_000
    )


@pytest.mark.parametrize(
    ("model", "threshold", "inclusive", "base", "high"),
    [
        ("gpt-6.1-sol", 272_000, False, 2, 4),
        ("openai/gpt-6.1-sol", 272_000, True, 2, 4),
        ("anthropic/claude-haiku-5.5", 100_000, True, 0.1, 0.5),
        ("claude-haiku-5-5", 100_000, False, 0.1, 0.5),
        ("grok-4.7", 200_000, True, 2, 4),
        ("global.anthropic.claude-haiku-5-5", 100_000, False, 0.1, 0.5),
        ("us.anthropic.claude-haiku-5-5", 100_000, False, 0.11, 0.55),
    ],
)
def test_exact_prompt_threshold_reprices_all_tokens(model, threshold, inclusive, base, high):
    for size in (threshold - 1, threshold, threshold + 1):
        cost = PrimrModels.calculate_cost_breakdown(
            model, size, 200, prompt_tokens=size, cached_input_tokens=400
        )
        expected = high if size > threshold or (inclusive and size == threshold) else base
        assert cost.input_rate_per_million == pytest.approx(expected)
        assert cost.tier_applied is (expected == high)
        assert cost.total_cost == pytest.approx(cost.input_cost + cost.output_cost)


def test_recorded_single_call_preserves_its_actual_prompt_size():
    usage = {
        "input_tokens": 300_000,
        "output_tokens": 1_000,
        "cached_input_tokens": 100_000,
        "call_count": 1,
    }
    cost, exact = PrimrModels.calculate_recorded_cost("gpt-5.4", usage)
    assert not exact
    assert cost == pytest.approx(1.0725)
    usage.update(actual_cost_calls=1, actual_cost_usd=0.5)
    assert PrimrModels.calculate_recorded_cost("gpt-5.4", usage) == (0.5, True)


@pytest.mark.parametrize(
    "model", ["openai/gpt-6.1-sol", "anthropic/claude-haiku-5.5", "x-ai/grok-4.7"]
)
def test_gateway_price_ceiling_covers_declared_tiers_and_keeps_privacy(model):
    config = PrimrModels.get_model_config(model)
    assert config is not None
    policy = _provider_policy(model)
    assert policy["max_price"] == {
        "prompt": config.cost_per_1m_input_tokens_high,
        "completion": config.cost_per_1m_output_tokens_high,
    }
    assert policy["zdr"]
    assert policy["require_parameters"]
    assert policy["data_collection"] == "deny"


@pytest.mark.parametrize(
    "name", ["deepseek/deepseek-r1", "anthropic/claude-3.7-sonnet", "anthropic/claude-3.5-haiku"]
)
def test_absent_gateway_routes_keep_historical_prices_but_reject_work(name):
    config = PrimrModels.get_model_config(name)
    assert config is not None
    with pytest.raises(ValueError, match="unavailable"):
        config.require_available()
    assert PrimrModels.calculate_cost(name, 1000, 1000) > 0


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
@pytest.mark.parametrize("field", ["AZURE_FOUNDRY_INPUT_PRICE", "AZURE_FOUNDRY_OUTPUT_PRICE"])
def test_deployment_pricing_must_be_finite(monkeypatch, value, field):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "example-deployment")
    monkeypatch.delenv("AZURE_FOUNDRY_PRICE_AS", raising=False)
    monkeypatch.setenv("AZURE_FOUNDRY_INPUT_PRICE", "2")
    monkeypatch.setenv("AZURE_FOUNDRY_OUTPUT_PRICE", "10")
    monkeypatch.setenv(field, value)
    assert PrimrModels.get_model_config("example-deployment") is None


@pytest.mark.parametrize(
    "model", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"]
)
def test_current_claude_sdk_payload_uses_adaptive_configuration(model):
    provider = AnthropicProvider()
    client = MagicMock()
    client.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text="answer")],
        usage=MagicMock(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )
    provider._client = client
    response = provider.chat(
        [{"role": "user", "content": "ExampleCo"}],
        model=model,
        max_tokens=32,
        thinking={"type": "enabled", "budget_tokens": 16},
        effort="high",
        retries=0,
    )
    assert response.text == "answer"
    kwargs = client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs
    assert "thinking" not in kwargs  # Legacy budgets yield to the adaptive default.
    assert kwargs["output_config"] == {"effort": "high"}
    assert client.messages.create.call_count == 1


@pytest.mark.parametrize(
    "model", ["global.anthropic.claude-opus-5-5", "us.anthropic.claude-haiku-5-5"]
)
def test_current_bedrock_claude_payload_omits_invalid_sampling(model):
    provider = BedrockProvider()
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": "answer"}]}},
        "usage": {"inputTokens": 12, "outputTokens": 7},
    }
    provider._runtime = client
    response = provider.chat(
        [{"role": "user", "content": "ExampleCo"}], model=model, max_tokens=32, retries=0
    )
    assert response.text == "answer"
    assert client.converse.call_args.kwargs["inferenceConfig"] == {"maxTokens": 32}


def test_defaults_track_the_current_provider_flagships():
    assert PrimrModels.FLASH_MODEL == "gemini-3.8-flash"
    assert PrimrModels.PRO_MODEL == "gemini-4-argon"
    assert PrimrModels.get_grok_models(GrokTier.MAX) == ("grok-4.7", "grok-4.7")


@pytest.mark.parametrize("model", ["qwen3.8:27b", "gemma4:12b", "gemma4:26b", "gemma4:31b"])
def test_local_library_candidates_have_no_cloud_cost_or_cloud_tag(model):
    config = PrimrModels.get_model_config(model)
    assert config is not None
    assert config.provider == "ollama"
    assert "cloud" not in config.name
    assert PrimrModels.calculate_cost(model, 100_000, 10_000) == 0


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-fable-5-1"])
def test_always_thinking_models_reject_disable_before_sdk(model):
    provider = AnthropicProvider()
    client = MagicMock()
    provider._client = client
    with pytest.raises(ValueError, match="cannot be disabled"):
        provider.chat(
            [{"role": "user", "content": "ExampleCo"}],
            model=model,
            thinking={"type": "disabled"},
            retries=0,
        )
    client.messages.create.assert_not_called()


@pytest.mark.parametrize(
    ("model", "rates"),
    [
        ("deepseek/deepseek-v3.2", (0.28, 0.42, 0.028)),
        ("google/gemini-3.8-flash", (0.825, 4.125, 0.0825)),
        ("deepseek/deepseek-chat", (0.2574, 1.0287, None)),
        ("z-ai/glm-5.3", (0.7, 2.2, 0.13)),
        ("z-ai/glm-5.3-flash", (0.15, 0.5, 0.03)),
        ("moonshotai/kimi-k3.1-pro", (2.0, 10.0, 0.2)),
        ("meta/muse-spark-1.3", (1.25, 4.25, 0.15)),
        ("mistralai/mistral-large-4-0", (1.36, 4.18, 0.14)),
        ("deepseek/deepseek-v4.1-flash", (0.3, 1.2, 0.006)),
        ("deepseek/deepseek-v4-pro-0813", (1.32, 3.96, 0.044)),
        ("meta-llama/llama-3.3-70b-instruct", (0.1, 0.32, None)),
    ],
)
def test_gateway_snapshot_rates_and_scheduled_ceilings(model, rates):
    config = PrimrModels.get_model_config(model)
    assert config is not None
    assert config.standard_rates(date(2026, 10, 22)) == rates
    policy = _provider_policy(model)
    assert policy["max_price"] == {"prompt": rates[0], "completion": rates[1]}


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna"])
def test_current_openai_candidates_use_existing_responses_transport(model):
    from types import SimpleNamespace

    from primr.ai.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        api_style="responses",
    )
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(
        output_text="answer", usage=SimpleNamespace(input_tokens=10, output_tokens=5)
    )
    provider._client = client
    result = provider.chat(
        [{"role": "user", "content": "ExampleCo"}], model=model, max_tokens=32, retries=0
    )
    assert result.text == "answer"
    kwargs = client.responses.create.call_args.kwargs
    assert kwargs["model"] == model
    assert kwargs["max_output_tokens"] == 32
    assert kwargs["store"] is False
    client.chat.completions.create.assert_not_called()


def test_foundry_can_reference_current_model_but_keeps_deployment_identity(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "example-deployment")
    monkeypatch.setenv("AZURE_FOUNDRY_PRICE_AS", "gpt-6.1-sol")
    config = PrimrModels.get_model_config("example-deployment")
    assert config is not None
    assert config.name == "example-deployment"
    assert config.provider == "foundry"
    assert config.standard_rates() == (2.0, 10.0, 0.1)
    assert config.cost_per_1m_input_tokens_high == 4


@pytest.mark.parametrize(
    "model", ["google/gemini-2.5-flash-lite", "google/gemini-2.5-flash", "google/gemini-2.5-pro"]
)
def test_current_gateway_base_catalog_no_longer_announces_old_retirement(monkeypatch, model):
    monkeypatch.setenv("PRIMR_OPENROUTER_MODEL", model)
    monkeypatch.setenv("PRIMR_OPENROUTER_INPUT_PRICE", "1")
    monkeypatch.setenv("PRIMR_OPENROUTER_OUTPUT_PRICE", "1")
    config = PrimrModels.get_model_config(model)
    assert config is not None
    assert config.expiration_date is None
    config.require_available(date(2026, 10, 22))


def test_foundry_responses_is_explicit_and_preserves_deployment_on_wire(monkeypatch):
    from types import SimpleNamespace

    from primr.ai.providers.azure_foundry import AzureFoundryProvider

    monkeypatch.setenv("AZURE_OPENAI_API_STYLE", "responses")
    provider = AzureFoundryProvider()
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(
        output_text="answer", usage=SimpleNamespace(input_tokens=10, output_tokens=5)
    )
    provider._client = client
    result = provider.chat(
        [{"role": "user", "content": "ExampleCo"}],
        model="example-deployment",
        max_tokens=32,
        retries=0,
    )
    assert result.text == "answer"
    kwargs = client.responses.create.call_args.kwargs
    assert kwargs["model"] == "example-deployment"
    assert kwargs["max_output_tokens"] == 32
    assert kwargs["store"] is False
    client.chat.completions.create.assert_not_called()


def test_foundry_rejects_unknown_api_style(monkeypatch):
    from primr.ai.providers.azure_foundry import AzureFoundryProvider

    monkeypatch.setenv("AZURE_OPENAI_API_STYLE", "unknown")
    with pytest.raises(ValueError, match="API style"):
        AzureFoundryProvider()


@pytest.mark.parametrize(
    "model,ceiling",
    [
        ("gpt-6.1-sol", 10.0),
        ("claude-haiku-5-5", 1.0),
        ("anthropic/claude-haiku-5.5", 1.0),
        ("global.anthropic.claude-haiku-5-5", 1.0),
    ],
)
def test_conservative_quote_includes_largest_declared_write_price(model, ceiling):
    # The token rate remains the published ordinary rate. Only quotes use
    # a write allowance when the pipeline cannot prove absence of writes.
    assert PrimrModels.calculate_cost_conservative(model, 1_000_000, 0) == pytest.approx(ceiling)


def test_recorded_usage_does_not_mislabel_quote_allowance_as_spend():
    usage = {"input_tokens": 1_000, "output_tokens": 0, "call_count": 1}
    cost, exact = PrimrModels.calculate_recorded_cost("claude-sonnet-5-5", usage)
    assert cost == pytest.approx(0.002)
    assert not exact
    usage.update(actual_cost_calls=1, actual_cost_usd=0.002)
    assert PrimrModels.calculate_recorded_cost("claude-sonnet-5-5", usage) == (0.002, True)


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-5-5",
        "claude-haiku-5-5",
        "anthropic/claude-sonnet-5.5",
        "global.anthropic.claude-fable-5-1",
    ],
)
def test_current_claude_token_estimates_keep_documented_tokenizer_margin(model):
    from primr.utils.cost_estimator import _apply_tokenizer_safety_factor

    assert _apply_tokenizer_safety_factor(model, 100_000, 10_000) == (130_000, 13_000, True)


def test_real_openai_sdk_wire_disables_automatic_paid_cache_writes():
    import json
    import httpx
    from openai import OpenAI
    from primr.ai.providers.openai_compatible import OpenAICompatibleProvider

    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_fixture",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "gpt-6.1-sol",
                "output": [
                    {
                        "id": "msg_fixture",
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "answer", "annotations": []}],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )

    with OpenAI(
        api_key="fake-key",
        base_url="https://openai.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        max_retries=0,
    ) as client:
        provider = OpenAICompatibleProvider(
            name="openai",
            base_url="https://openai.invalid/v1",
            api_key_env="OPENAI_API_KEY",
            api_style="responses",
        )
        provider._client = client
        result = provider.chat(
            [{"role": "user", "content": "ExampleCo"}],
            model="gpt-6.1-sol",
            retries=0,
            extra_body={
                "prompt_cache_options": {"mode": "implicit", "prewarm": True, "ttl": "12h"}
            },
        )
    assert result.text == "answer"
    assert len(captured) == 1
    assert captured[0]["model"] == "gpt-6.1-sol"
    assert captured[0]["store"] is False
    assert captured[0]["prompt_cache_options"] == {"mode": "explicit"}
