"""Azure AI Foundry deployments are routable via operator-declared env config.

A Foundry model id is a per-user *deployment name*, so primr cannot ship a
fixed priced registry entry. The operator declares the deployment and its
pricing through the environment; nothing is guessed into the cost gate, and a
run fails closed (unknown model) if pricing is not fully declared. Like
Bedrock, Foundry routing is main-process only and never crosses the
supervised-worker credential boundary.
"""

from __future__ import annotations

import pytest

from primr.config.models import PrimrModels

DEPLOYMENT = "my-foundry-deploy"


def _configure_foundry_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", DEPLOYMENT)
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "https://acct.openai.azure.com/openai/v1/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-key-for-tests")
    monkeypatch.delenv("PRIMR_SUPERVISED_WORKER", raising=False)


def test_foundry_deployment_prices_via_price_as(monkeypatch) -> None:
    _configure_foundry_endpoint(monkeypatch)
    monkeypatch.setenv("AZURE_FOUNDRY_PRICE_AS", "gpt-5.4")
    base = PrimrModels.get_model_config("gpt-5.4")
    config = PrimrModels.get_model_config(DEPLOYMENT)
    assert config is not None
    assert config.provider == "foundry"
    assert config.name == DEPLOYMENT
    # Price is copied from the declared underlying model, not guessed.
    assert config.cost_per_1m_input_tokens == base.cost_per_1m_input_tokens
    assert config.cost_per_1m_output_tokens == base.cost_per_1m_output_tokens
    assert PrimrModels.calculate_cost(DEPLOYMENT, 100_000, 20_000) > 0


def test_foundry_deployment_prices_via_explicit_rates(monkeypatch) -> None:
    _configure_foundry_endpoint(monkeypatch)
    monkeypatch.setenv("AZURE_FOUNDRY_INPUT_PRICE", "1.00")
    monkeypatch.setenv("AZURE_FOUNDRY_OUTPUT_PRICE", "4.00")
    config = PrimrModels.get_model_config(DEPLOYMENT)
    assert config is not None
    assert config.provider == "foundry"
    # 1M input @ $1 + 1M output @ $4 = $5.00
    assert PrimrModels.calculate_cost(DEPLOYMENT, 1_000_000, 1_000_000) == pytest.approx(5.0)


def test_foundry_fails_closed_without_declared_pricing(monkeypatch) -> None:
    _configure_foundry_endpoint(monkeypatch)
    # No AZURE_FOUNDRY_PRICE_AS and no explicit rates → unrouteable, unpriced.
    assert PrimrModels.get_model_config(DEPLOYMENT) is None
    with pytest.raises(KeyError):
        PrimrModels.calculate_cost(DEPLOYMENT, 100, 100)


def test_only_the_declared_deployment_name_resolves(monkeypatch) -> None:
    _configure_foundry_endpoint(monkeypatch)
    monkeypatch.setenv("AZURE_FOUNDRY_PRICE_AS", "gpt-5.4")
    assert PrimrModels.get_model_config("some-other-deployment") is None


def test_foundry_routes_to_provider_in_main_process(monkeypatch) -> None:
    _configure_foundry_endpoint(monkeypatch)
    monkeypatch.setenv("AZURE_FOUNDRY_PRICE_AS", "gpt-5.4")
    from primr.ai.providers.azure_foundry import AzureFoundryProvider
    from primr.ai.routing import get_provider_for_model

    provider = get_provider_for_model(DEPLOYMENT)
    assert isinstance(provider, AzureFoundryProvider)
    assert provider.name == "foundry"


def test_foundry_routing_refused_in_supervised_worker(monkeypatch) -> None:
    _configure_foundry_endpoint(monkeypatch)
    monkeypatch.setenv("AZURE_FOUNDRY_PRICE_AS", "gpt-5.4")
    monkeypatch.setenv("PRIMR_SUPERVISED_WORKER", "1")
    from primr.ai.routing import get_provider_for_model

    with pytest.raises(ValueError, match="main-process only"):
        get_provider_for_model(DEPLOYMENT)
