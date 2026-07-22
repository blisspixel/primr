"""Amazon Bedrock is routable in the main process only, and never crosses the
supervised-worker credential boundary.

Bedrock (Nova) models are registered with real prices so the mandatory cost
gate can price them. Routing reaches ``BedrockProvider`` through the registry
builder. Crucially, a supervised worker must refuse Bedrock routing (AWS
secrets are deliberately stripped from worker environments), and the env
allowlist must never be widened to let them through.
"""

from __future__ import annotations

import pytest

from primr.config.env import is_supervised_worker_env_allowed
from primr.config.models import PrimrModels

BEDROCK_MODELS = [
    "us.amazon.nova-micro-v1:0",
    "us.amazon.nova-lite-v1:0",
    "us.amazon.nova-pro-v1:0",
]


@pytest.mark.parametrize("model", BEDROCK_MODELS)
def test_bedrock_model_is_registered_and_priced(model: str) -> None:
    config = PrimrModels.get_model_config(model)
    assert config is not None, f"{model} must be in ALL_MODELS"
    assert config.provider == "bedrock"
    assert config.cost_per_1m_input_tokens > 0
    assert config.cost_per_1m_output_tokens > 0
    # The mandatory pre-run estimate must not KeyError on a Bedrock model.
    assert PrimrModels.calculate_cost(model, 100_000, 20_000) > 0


def test_bedrock_routes_to_registry_provider_in_main_process(monkeypatch) -> None:
    monkeypatch.delenv("PRIMR_SUPERVISED_WORKER", raising=False)
    sentinel = object()
    import primr.ai.providers.registry as registry

    monkeypatch.setattr(registry, "get_registered_provider_for_model", lambda name: sentinel)
    from primr.ai.routing import get_provider_for_model

    assert get_provider_for_model("us.amazon.nova-micro-v1:0") is sentinel


def test_bedrock_routing_refused_in_supervised_worker(monkeypatch) -> None:
    monkeypatch.setenv("PRIMR_SUPERVISED_WORKER", "1")
    from primr.ai.routing import get_provider_for_model

    with pytest.raises(ValueError, match="main-process only"):
        get_provider_for_model("us.amazon.nova-micro-v1:0")


@pytest.mark.parametrize(
    "secret",
    [
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "AZURE_OPENAI_API_KEY",
    ],
)
def test_cloud_infra_secrets_never_enter_a_worker(secret: str) -> None:
    # Regression pin: nobody may "fix" Bedrock/Foundry worker routing by
    # widening the allowlist. These stay stripped from supervised workers.
    assert is_supervised_worker_env_allowed(secret) is False
