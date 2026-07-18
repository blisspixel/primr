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
        name="ollama",
        api_key_env="OLLAMA_API_KEY",
        api_key_default="ollama",
        description="Ollama local inference (utility, zero cost)",
        roles=("utility",),
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

    return [p for p in KNOWN_PROVIDERS if os.getenv(p.api_key_env) or p.api_key_default is not None]


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
        )
    if entry.name == "anthropic":
        from primr.ai.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if entry.name == "ollama":
        return OpenAICompatibleProvider(
            name="ollama",
            base_url="http://localhost:11434/v1",
            api_key_env="OLLAMA_API_KEY",
            api_key_default="ollama",
        )
    raise ValueError(f"No provider factory for entry {entry.name!r}")


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
