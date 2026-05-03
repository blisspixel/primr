"""
LLM interface using Google Gemini API (modern SDK)
Supports Gemini 3 Pro with thinking_level control.

Utility-tier dispatch: when ``XAI_API_KEY`` is set, the cheap utility calls
(scraping summaries, link selection, generic "fast" tasks) route to Grok 4.1
fast non-reasoning instead of Gemini Flash. Grok 4.1 NR is 2.5x cheaper on
input and 6x cheaper on output than Gemini Flash, lives on the same key the
user already needs for the standard pipeline, and removes a cross-provider
dependency that previously could stall the run on a Gemini hang. Pro-tier
calls (analysis, section writing) stay on Gemini regardless — those are
provider-specific code paths.
"""

from dataclasses import dataclass
from typing import Any

from colorama import Fore, Style

try:
    from google import genai as _google_genai
    from google.genai import types as _google_types

    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as import_error:
    _GENAI_IMPORT_ERROR = import_error

    class _GenAIUnavailable:
        class Client:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("google.genai is unavailable")

    @dataclass
    class _FallbackThinkingConfig:
        thinking_level: str

    @dataclass
    class _FallbackGenerateContentConfig:
        temperature: float
        thinking_config: _FallbackThinkingConfig

    class _FallbackTypes:
        GenerateContentConfig = _FallbackGenerateContentConfig
        ThinkingConfig = _FallbackThinkingConfig

    _google_genai = _GenAIUnavailable()  # type: ignore[assignment]
    _google_types = _FallbackTypes()  # type: ignore[assignment]
    _FALLBACK_CLIENT_CLASS = _GenAIUnavailable.Client
else:
    _FALLBACK_CLIENT_CLASS = None  # type: ignore[misc]

genai = _google_genai
types = _google_types

from primr.config.config import GEMINI_API_KEY, MAX_RETRIES
from primr.config.env import load_primr_env
from primr.config.models import PrimrModels
from primr.utils.chat_logger import log_chat_interaction
from primr.utils.logging_config import get_logger

load_primr_env()

logger = get_logger("llm")

# Lazy-initialized client (created on first use to allow import without API key)
_client: genai.Client | None = None


def _require_genai_dependency() -> None:
    if _GENAI_IMPORT_ERROR is None:
        return
    if (
        _FALLBACK_CLIENT_CLASS is not None
        and getattr(genai, "Client", None) is not _FALLBACK_CLIENT_CLASS
    ):
        return
    raise RuntimeError(
        "google.genai is not available. Install compatible dependencies "
        "(Python 3.11+ and project requirements)."
    ) from _GENAI_IMPORT_ERROR


def _get_client() -> genai.Client:
    """Get or create the Gemini client."""
    global _client
    _require_genai_dependency()
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _get_model_for_type(model_type: str) -> str:
    """Get model name for a given legacy ``model_type`` string.

    This is a thin shim over :func:`primr.ai.routing.pick_model_for_legacy_type`.
    The actual policy (utility tier prefers Grok 4.1-NR when ``XAI_API_KEY`` is
    set, pro tier uses Gemini Pro) lives in the routing module.

    Model types (USE THESE):
        - "scraping": utility - summarizing scraped content
        - "link_selection": utility - which pages to scrape
        - "fast": utility - general quick tasks
        - "section_writing": Pro - writing report sections
        - "analysis": Pro - complex analysis
        - "reasoning": Pro - general reasoning tasks

    Legacy aliases (backward compatible):
        - "filtering" -> utility (DEPRECATED - use link_selection)
        - "research" -> utility (DEPRECATED - confusing name)
        - "summarization" -> utility
        - "report" -> Pro
    """
    from primr.ai.routing import pick_model_for_legacy_type

    return pick_model_for_legacy_type(model_type)


def llm(prompt, model_type="fast", temperature=1.0, thinking_level="high", streaming=False):
    """
    Sends a prompt to the Gemini AI model and returns the response.

    Args:
        prompt (str): The text prompt to send to the AI.
        model_type (str): Task type determines model:
                         - "scraping", "link_selection", "fast" -> Flash (cheap)
                         - "section_writing", "analysis", "reasoning" -> Pro (smart)
        temperature (float): Controls randomness. Gemini 3 recommends 1.0 (default).
        thinking_level (str): "low" or "high" - controls reasoning depth.
                             "high" = deeper reasoning, slower
                             "low" = faster, less reasoning
        streaming (bool): If True, uses real-time response streaming.

    Returns:
        str: AI-generated response (cleaned text).
    """
    model_name = _get_model_for_type(model_type)
    config = PrimrModels.get_model_config(model_name)
    if config is not None and config.provider == "xai":
        # Utility-tier dispatch: caller asked for a Flash-class task and the
        # resolver picked a Grok model because XAI_API_KEY is set. Route to
        # the Grok client and return — thinking_level / streaming have no
        # analogue on Grok 4.1 NR (it doesn't reason).
        from primr.ai.grok_client import grok_llm

        log_chat_interaction(prompt, f"Model: {model_name} (xai dispatch)")
        return grok_llm(prompt, model=model_name, temperature=temperature)

    log_chat_interaction(prompt, f"Model: {model_name}")

    # Delegate to GeminiProvider for the actual SDK call + retry. This keeps
    # the colored quota-exhausted UI in this function (a CLI concern) while
    # the API logic lives in one place we can share with future code paths.
    from primr.ai.providers import QuotaExhaustedError

    provider = _get_gemini_provider()
    # Allow tests that patched _get_client to inject a fake client through
    # the provider's lazy slot.
    if _client is not None:
        provider._client = _client

    try:
        result = provider.chat(
            [{"role": "user", "content": prompt}],
            model=model_name,
            temperature=temperature,
            retries=MAX_RETRIES - 1,
            thinking_level=thinking_level,
            streaming=streaming,
        )
    except QuotaExhaustedError as e:
        logger.error(
            "Gemini daily API quota exhausted. Options: wait for reset, "
            "upgrade plan, use different key, or run 'primr --check-quota'"
        )
        print(Fore.RED + "\n" + "=" * 60 + Style.RESET_ALL)
        print(Fore.RED + "[QUOTA EXHAUSTED] Daily API limit reached." + Style.RESET_ALL)
        print(
            Fore.YELLOW
            + "Your Gemini API quota has been exhausted for today."
            + Style.RESET_ALL
        )
        print(Fore.YELLOW + "Options:" + Style.RESET_ALL)
        print(
            Fore.YELLOW
            + "  1. Wait until quota resets (usually midnight PT)"
            + Style.RESET_ALL
        )
        print(
            Fore.YELLOW
            + "  2. Upgrade your API plan at https://ai.google.dev"
            + Style.RESET_ALL
        )
        print(Fore.YELLOW + "  3. Use a different API key" + Style.RESET_ALL)
        print(Fore.YELLOW + "  4. Check quota: primr --check-quota" + Style.RESET_ALL)
        print(Fore.RED + "=" * 60 + "\n" + Style.RESET_ALL)
        error_message = "[ERROR] Daily API quota exhausted. Cannot continue."
        log_chat_interaction(prompt, error_message)
        raise RuntimeError(error_message) from e

    log_chat_interaction(prompt, result.text)
    return result.text


_gemini_provider: "object | None" = None  # forward decl, set by _get_gemini_provider


def _get_gemini_provider():
    """Lazy singleton for the GeminiProvider used by ``llm()``."""
    from primr.ai.providers.gemini import GeminiProvider

    global _gemini_provider
    if _gemini_provider is None:
        _gemini_provider = GeminiProvider()
    return _gemini_provider


def llm_fast(prompt, model_type="fast"):
    """
    Fast LLM call with minimal thinking - for simple tasks like filtering links.
    Uses Flash model with thinking_level="low" for fastest responses.
    """
    return llm(prompt, model_type=model_type, thinking_level="low")
