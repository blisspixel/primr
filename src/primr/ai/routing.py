"""
Routing layer for primr's LLM stack.

This module is the single source of truth for two questions every caller
eventually has to answer:

1. **Which model should I use for this stage?** — answered by
   :func:`pick_model_for_role`, which inspects the configured environment
   keys and the registered ``ModelConfig`` entries to pick the right model
   for a named *role* (utility / pro). Roles are deliberately coarse — the
   stages of the pipeline group into a small number of capability classes,
   and adding finer roles is cheap when a stage warrants it.

2. **Which provider talks to that model?** — answered by
   :func:`get_provider_for_model`, which maps a model name to the
   :class:`primr.ai.providers.Provider` instance that knows how to call it.
   This keeps callers from importing provider modules directly: they ask
   the routing layer for the right object and call ``.chat()`` on it.

The dispatch in :func:`primr.ai.llm.llm` and :func:`primr.ai.llm._get_model_for_type`
delegates here, so changing routing policy (e.g. preferring an OpenAI key
over a Gemini key for the utility tier when both are set) happens in one
place.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import TYPE_CHECKING

from primr.config.models import PrimrModels

if TYPE_CHECKING:
    from primr.ai.providers import Provider


class Role(str, Enum):
    """Coarse capability classes used by the routing layer.

    ``UTILITY`` covers scraping summaries, link selection, generic "fast"
    tasks, QA — the cheap-and-cheerful stages where any modern model in the
    7B-class range will do. ``PRO`` is for analysis, section writing, and
    reasoning where model quality genuinely matters.
    """

    UTILITY = "utility"
    PRO = "pro"


# Legacy ``model_type`` strings → ``Role`` mapping. Kept here so the
# ``llm.py::_get_model_for_type`` shim doesn't need to know about Role
# semantics — it just translates the input it gets.
LEGACY_TYPE_TO_ROLE: dict[str, Role] = {
    "scraping": Role.UTILITY,
    "link_selection": Role.UTILITY,
    "filtering": Role.UTILITY,
    "fast": Role.UTILITY,
    "research": Role.UTILITY,
    "summarization": Role.UTILITY,
    "section_writing": Role.PRO,
    "analysis": Role.PRO,
    "reasoning": Role.PRO,
    "report": Role.PRO,
}


def pick_model_for_role(role: Role | str) -> str:
    """Pick the right model name for a named role given configured keys.

    For the utility tier, prefers grok-4.20-non-reasoning when
    ``XAI_API_KEY`` is set. Falls back to Gemini Flash when only
    ``GEMINI_API_KEY`` is configured.

    For the pro tier, returns the active Pro model from the model registry
    (today: Gemini 3.1 Pro). Cross-provider Pro routing is a future
    enhancement — when OpenAI / Anthropic pro models are wired in, this is
    where the policy lands.
    """
    if isinstance(role, str):
        role = Role(role)

    if role is Role.UTILITY:
        if os.getenv("XAI_API_KEY"):
            return PrimrModels.GROK_MODEL_WRITING
        return PrimrModels.FLASH_MODEL

    # Role.PRO
    return PrimrModels.PRO_MODEL


def pick_model_for_legacy_type(model_type: str) -> str:
    """Translate a legacy ``model_type`` string into a model name."""
    role = LEGACY_TYPE_TO_ROLE.get(model_type, Role.UTILITY)
    return pick_model_for_role(role)


# ---------------------------------------------------------------------------
# Provider lookup
# ---------------------------------------------------------------------------

# Module-level cached provider instances (singletons)
_openai_provider: Provider | None = None
_anthropic_provider: Provider | None = None
_ollama_provider: Provider | None = None


def _get_openai_provider() -> Provider:
    """Return a cached OpenAI provider instance."""
    global _openai_provider
    if _openai_provider is None:
        from primr.ai.providers.openai_compatible import OpenAICompatibleProvider

        _openai_provider = OpenAICompatibleProvider(
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
        )
    return _openai_provider


def _get_anthropic_provider() -> Provider:
    """Return a cached Anthropic provider instance."""
    global _anthropic_provider
    if _anthropic_provider is None:
        from primr.ai.providers.anthropic import AnthropicProvider

        _anthropic_provider = AnthropicProvider()
    return _anthropic_provider


def _get_ollama_provider() -> Provider:
    """Return a cached Ollama provider instance.

    Respects OLLAMA_BASE_URL env var for non-default Ollama endpoints.
    Falls back to http://localhost:11434/v1.
    """
    global _ollama_provider
    if _ollama_provider is None:
        from primr.ai.providers.openai_compatible import OpenAICompatibleProvider

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"

        _ollama_provider = OpenAICompatibleProvider(
            name="ollama",
            base_url=base_url,
            api_key_env="OLLAMA_API_KEY",
            api_key_default="ollama",
        )
    return _ollama_provider


def get_provider_for_model(model_name: str) -> Provider:
    """Return the provider instance that knows how to call ``model_name``.

    Looks up the model's provider field in the ``ModelRegistry`` and returns
    the matching singleton. Raises ``KeyError`` for unregistered model names
    and ``ValueError`` for registered models whose provider has no routing
    entry yet.
    """
    config = PrimrModels.get_model_config(model_name)
    if config is None:
        raise KeyError(f"Unknown model: {model_name}")

    provider_name = config.provider
    if provider_name == "xai":
        from primr.ai.grok_client import _get_provider

        return _get_provider()
    if provider_name == "google":
        from primr.ai.llm import _get_gemini_provider

        return _get_gemini_provider()
    if provider_name == "openai":
        return _get_openai_provider()
    if provider_name == "anthropic":
        return _get_anthropic_provider()
    if provider_name == "ollama":
        return _get_ollama_provider()

    raise ValueError(
        f"Model {model_name!r} has provider {provider_name!r} which has no "
        "routing entry. Register it in primr.ai.routing.get_provider_for_model."
    )
