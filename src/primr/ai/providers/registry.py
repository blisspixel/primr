"""
Provider registry — auto-detect which providers are configured.

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
)


def list_known_providers() -> tuple[ProviderEntry, ...]:
    """Return all providers primr knows how to call (configured or not)."""
    return KNOWN_PROVIDERS


def get_available_providers() -> list[ProviderEntry]:
    """Return the subset of providers whose API keys are present in the env."""
    import os

    return [p for p in KNOWN_PROVIDERS if os.getenv(p.api_key_env)]


def build_provider(entry: ProviderEntry) -> Provider:
    """Instantiate a provider for an entry. Used for doctor connectivity checks."""
    if entry.name == "xai":
        return OpenAICompatibleProvider(
            name="xai",
            base_url="https://api.x.ai/v1",
            api_key_env="XAI_API_KEY",
            billing_help_url="https://console.x.ai/",
        )
    if entry.name == "gemini":
        return GeminiProvider()
    raise ValueError(f"No provider factory for entry {entry.name!r}")
