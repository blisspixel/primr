"""
Provider abstraction for primr's LLM stack.

This package decouples the question of *which model to use for a stage* from
the question of *how to talk to that model's provider*. Concretely:

- ``base.Provider`` defines the chat-call interface every provider implements
- ``base.ChatResponse`` is the normalized return shape (text + token usage)
- ``openai_compatible.OpenAICompatibleProvider`` is a single class that talks
  to anything with an OpenAI-shaped ``/v1/chat/completions`` endpoint:
  OpenAI, Ollama, vLLM, llama.cpp, and similar runtimes are parameterized
  instances of this one class
- ``xai.XAIProvider`` inherits that chat behavior and adds xAI-only Responses
  API browsing/search synthesis

Providers that have a genuinely different SDK shape (Google Gemini, Anthropic
Claude) get their own classes alongside ``OpenAICompatibleProvider``. The
abstraction normalizes call/response/usage but does *not* try to flatten
provider-specific features (Gemini's ``thinking_level``, Anthropic's
``cache_control`` blocks, OpenAI's reasoning-effort settings); those stay
as provider-specific kwargs that the relevant provider knows how to use and
others ignore.
"""

from primr.ai.providers.azure_foundry import AzureFoundryProvider
from primr.ai.providers.base import (
    ChatResponse,
    CredentialCheck,
    Provider,
    ProviderUnavailableError,
    QuotaExhaustedError,
)
from primr.ai.providers.bedrock import BedrockProvider
from primr.ai.providers.gemini import GeminiProvider
from primr.ai.providers.openai_compatible import OpenAICompatibleProvider
from primr.ai.providers.openrouter import OpenRouterProvider
from primr.ai.providers.registry import (
    KNOWN_PROVIDERS,
    ProviderEntry,
    build_provider,
    get_available_providers,
    list_known_providers,
    validate_provider_credentials,
)
from primr.ai.providers.xai import BrowseSummary, XAIProvider

__all__ = [
    "KNOWN_PROVIDERS",
    "AzureFoundryProvider",
    "BedrockProvider",
    "BrowseSummary",
    "ChatResponse",
    "CredentialCheck",
    "GeminiProvider",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "Provider",
    "ProviderEntry",
    "ProviderUnavailableError",
    "QuotaExhaustedError",
    "XAIProvider",
    "build_provider",
    "get_available_providers",
    "list_known_providers",
    "validate_provider_credentials",
]
