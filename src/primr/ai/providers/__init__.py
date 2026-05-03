"""
Provider abstraction for primr's LLM stack.

This package decouples the question of *which model to use for a stage* from
the question of *how to talk to that model's provider*. Concretely:

- ``base.Provider`` defines the chat-call interface every provider implements
- ``base.ChatResponse`` is the normalized return shape (text + token usage)
- ``openai_compatible.OpenAICompatibleProvider`` is a single class that talks
  to anything with an OpenAI-shaped ``/v1/chat/completions`` endpoint —
  xAI/Grok, OpenAI itself, Ollama, vLLM, llama.cpp, and similar runtimes are
  all parameterized instances of this one class

Providers that have a genuinely different SDK shape (Google Gemini, Anthropic
Claude) get their own classes alongside ``OpenAICompatibleProvider``. The
abstraction normalizes call/response/usage but does *not* try to flatten
provider-specific features (Gemini's ``thinking_level``, Anthropic's
``cache_control`` blocks, OpenAI's reasoning-effort settings) — those stay
as provider-specific kwargs that the relevant provider knows how to use and
others ignore.
"""

from primr.ai.providers.base import (
    ChatResponse,
    Provider,
    ProviderUnavailableError,
    QuotaExhaustedError,
)
from primr.ai.providers.gemini import GeminiProvider
from primr.ai.providers.openai_compatible import OpenAICompatibleProvider
from primr.ai.providers.registry import (
    KNOWN_PROVIDERS,
    ProviderEntry,
    build_provider,
    get_available_providers,
    list_known_providers,
)

__all__ = [
    "KNOWN_PROVIDERS",
    "ChatResponse",
    "GeminiProvider",
    "OpenAICompatibleProvider",
    "Provider",
    "ProviderEntry",
    "ProviderUnavailableError",
    "QuotaExhaustedError",
    "build_provider",
    "get_available_providers",
    "list_known_providers",
]
