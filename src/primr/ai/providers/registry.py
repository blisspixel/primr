"""
Provider registry for auto-detecting which providers are configured.

Reading the env keys directly from many places makes the codebase brittle
when we add a fourth or fifth provider. This module is the single place
that knows "primr currently supports providers X, Y, Z and you have
configured A, C". Used by ``primr doctor`` and by the routing layer when
multi-provider policies need to inspect availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from primr.ai.providers.base import CredentialCheck
from primr.ai.providers.gemini import GeminiProvider
from primr.ai.providers.openai_compatible import OpenAICompatibleProvider
from primr.ai.providers.xai import XAIProvider
from primr.config.models import PrimrModels

if TYPE_CHECKING:
    from primr.ai.providers.base import Provider


@dataclass(frozen=True)
class ProviderEntry:
    """One row in the registry."""

    name: str
    api_key_env: str
    description: str
    factory: type[Provider] | None = None
    base_url: str | None = None
    roles: tuple[str, ...] = ()
    api_key_default: str | None = None
    # Alternative env vars that also make the provider configured (e.g. Bedrock
    # can authenticate via AWS_ACCESS_KEY_ID / AWS_PROFILE instead of a Bedrock
    # API key). Any one being set marks the provider available for listing.
    env_alternatives: tuple[str, ...] = ()


# Static registry of providers primr knows about. Adding a new provider is
# (1) a model registry entry in ``primr.config.models`` and (2) a row here.
# Routing policy (which roles a provider serves) lives in routing.py.
KNOWN_PROVIDERS: tuple[ProviderEntry, ...] = (
    ProviderEntry(
        name="xai",
        api_key_env="XAI_API_KEY",
        description="xAI Grok (analysis, writing, utility)",
        roles=("utility", "reasoning", "writing"),
    ),
    ProviderEntry(
        name="gemini",
        api_key_env="GEMINI_API_KEY",
        description="Google Gemini (premium pipeline, utility fallback)",
        roles=("utility", "pro", "premium_research"),
    ),
    ProviderEntry(
        name="openai",
        api_key_env="OPENAI_API_KEY",
        description="OpenAI GPT (utility, reasoning, writing, premium research)",
        roles=("utility", "reasoning", "writing", "premium_research"),
    ),
    ProviderEntry(
        name="anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        description="Anthropic Claude (reasoning, writing, pro)",
        roles=("reasoning", "writing", "pro"),
    ),
    ProviderEntry(
        name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        description="OpenRouter gateway (opt-in utility, reasoning, writing)",
        roles=("utility", "reasoning", "writing"),
    ),
    ProviderEntry(
        name="ollama",
        api_key_env="OLLAMA_API_KEY",
        api_key_default="ollama",
        description="Ollama local inference (utility, zero cost)",
        roles=("utility",),
    ),
    ProviderEntry(
        name="foundry",
        api_key_env="AZURE_OPENAI_API_KEY",
        description="Microsoft Foundry / Azure OpenAI (OpenAI-compatible: Phi, GPT, Llama, DeepSeek)",
        roles=("utility", "reasoning", "writing", "pro"),
    ),
    ProviderEntry(
        name="bedrock",
        api_key_env="AWS_BEARER_TOKEN_BEDROCK",
        env_alternatives=("AWS_ACCESS_KEY_ID", "AWS_PROFILE", "AWS_ROLE_ARN"),
        description="Amazon Bedrock via converse (Claude, Nova, Llama, Gemma, DeepSeek)",
        roles=("utility", "reasoning", "writing", "pro", "premium_research"),
    ),
)
_PROVIDER_INSTANCES: dict[str, Provider] = {}


def list_known_providers() -> tuple[ProviderEntry, ...]:
    """Return all providers primr knows how to call (configured or not)."""
    return KNOWN_PROVIDERS


def get_available_providers() -> list[ProviderEntry]:
    """Return the subset of providers that are usable.

    A provider is available if its API key env var is set OR if it has a
    configured default key (e.g. Ollama doesn't need a real key).
    """
    import os

    def _configured(p: ProviderEntry) -> bool:
        if p.api_key_default is not None or os.getenv(p.api_key_env):
            return True
        return any(os.getenv(alt) for alt in p.env_alternatives)

    return [p for p in KNOWN_PROVIDERS if _configured(p)]


def build_provider(entry: ProviderEntry) -> Provider:
    """Instantiate a provider for an entry. Used for doctor connectivity checks."""
    if entry.name == "xai":
        return XAIProvider()
    if entry.name == "gemini":
        return GeminiProvider()
    if entry.name == "openai":
        return OpenAICompatibleProvider(
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            billing_help_url="https://platform.openai.com/account/billing",
            api_style="responses",
        )
    if entry.name == "anthropic":
        from primr.ai.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if entry.name == "openrouter":
        from primr.ai.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider()
    if entry.name == "ollama":
        return OpenAICompatibleProvider(
            name="ollama",
            base_url="http://localhost:11434/v1",
            api_key_env="OLLAMA_API_KEY",
            api_key_default="ollama",
        )
    if entry.name == "foundry":
        from primr.ai.providers.azure_foundry import AzureFoundryProvider

        return AzureFoundryProvider()
    if entry.name == "bedrock":
        from primr.ai.providers.bedrock import BedrockProvider

        return BedrockProvider()
    raise ValueError(f"No provider factory for entry {entry.name!r}")


def validate_provider_credentials(entry: ProviderEntry) -> CredentialCheck:
    """Live, auth-only validation for one provider.

    Builds the provider and runs its free metadata probe with no model
    generation or token spend. Every failure class is captured and returned as
    a result rather than raised, so a caller can report on all providers
    uniformly.
    """
    try:
        provider = build_provider(entry)
    except Exception as exc:
        return CredentialCheck(
            provider=entry.name, ok=False, detail=f"{type(exc).__name__}: {str(exc)[:120]}"
        )
    return provider.validate_credentials()


def get_registered_provider_for_model(model_name: str) -> Provider:
    """Return one cached registry provider without importing the routing layer."""
    config = PrimrModels.get_model_config(model_name)
    if config is None:
        raise KeyError(f"Unknown model: {model_name}")

    provider_name = "gemini" if config.provider == "google" else config.provider
    provider = _PROVIDER_INSTANCES.get(provider_name)
    if provider is not None:
        return provider

    entry = next((item for item in KNOWN_PROVIDERS if item.name == provider_name), None)
    if entry is None:
        raise ValueError(
            f"Model {model_name!r} has provider {config.provider!r} which has no "
            "registered provider implementation."
        )
    provider = build_provider(entry)
    _PROVIDER_INSTANCES[provider_name] = provider
    return provider
