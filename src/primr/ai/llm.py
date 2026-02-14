"""
LLM interface using Google Gemini API (modern SDK)
Supports Gemini 3 Pro with thinking_level control
"""
import time
from dataclasses import dataclass
from typing import Any

from colorama import Fore, Style
from dotenv import load_dotenv

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
from primr.config.models import PrimrModels
from primr.utils.chat_logger import log_chat_interaction

load_dotenv()

# Lazy-initialized client (created on first use to allow import without API key)
_client: genai.Client | None = None


def _require_genai_dependency() -> None:
    if _GENAI_IMPORT_ERROR is None:
        return
    if _FALLBACK_CLIENT_CLASS is not None and getattr(genai, "Client", None) is not _FALLBACK_CLIENT_CLASS:
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
    """Get model name for a given type.

    Model types (USE THESE):
        - "scraping": Flash - summarizing scraped content
        - "link_selection": Flash - intelligent link prioritization (which pages to scrape)
        - "fast": Flash - general quick tasks
        - "section_writing": Pro - writing report sections
        - "analysis": Pro - complex analysis
        - "reasoning": Pro - general reasoning tasks

    Legacy aliases (backward compatible):
        - "filtering" -> Flash (DEPRECATED - use link_selection)
        - "research" -> Flash (DEPRECATED - confusing name)
        - "report" -> Pro
        - "summarization" -> Flash
    """
    # Flash model (cheap, fast)
    if model_type in ("scraping", "link_selection", "filtering", "fast", "research", "summarization"):
        return PrimrModels.FLASH_MODEL
    # Pro model (expensive, smart)
    elif model_type in ("section_writing", "analysis", "reasoning", "report"):
        return PrimrModels.PRO_MODEL
    else:
        return PrimrModels.FLASH_MODEL


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
    retries = 0

    log_chat_interaction(prompt, f"Model: {model_name}")

    # Build config - Gemini 3 uses thinking_level instead of thinking_budget
    config_params = {
        "temperature": temperature,
        "thinking_config": types.ThinkingConfig(thinking_level=thinking_level)
    }

    while retries < MAX_RETRIES:
        try:
            ai_response = ""

            if not streaming:
                response = _get_client().models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_params)
                )
                ai_response = (response.text or "").strip()
            else:
                stream_response = _get_client().models.generate_content_stream(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_params)
                )

                response_text: list[str] = []
                for chunk in stream_response:
                    if hasattr(chunk, "text") and chunk.text:
                        response_text.append(str(chunk.text))

                ai_response = "".join(response_text).strip()

            log_chat_interaction(prompt, ai_response)
            return ai_response

        except Exception as e:
            error_str = str(e).lower()
            retries += 1

            # Check for quota exhaustion (daily limit hit) - STOP IMMEDIATELY
            # Matches: per_day, per_model_per_day, PerDay, etc.
            is_quota_exhausted = (
                "resource_exhausted" in error_str and
                ("per_day" in error_str or ("quota" in error_str and "exceeded" in error_str))
            )

            if is_quota_exhausted:
                print(Fore.RED + "\n" + "=" * 60 + Style.RESET_ALL)
                print(Fore.RED + "[QUOTA EXHAUSTED] Daily API limit reached." + Style.RESET_ALL)
                print(Fore.YELLOW + "Your Gemini API quota has been exhausted for today." + Style.RESET_ALL)
                print(Fore.YELLOW + "Options:" + Style.RESET_ALL)
                print(Fore.YELLOW + "  1. Wait until quota resets (usually midnight PT)" + Style.RESET_ALL)
                print(Fore.YELLOW + "  2. Upgrade your API plan at https://ai.google.dev" + Style.RESET_ALL)
                print(Fore.YELLOW + "  3. Use a different API key" + Style.RESET_ALL)
                print(Fore.YELLOW + "  4. Check quota: primr --check-quota" + Style.RESET_ALL)
                print(Fore.RED + "=" * 60 + "\n" + Style.RESET_ALL)
                error_message = "[ERROR] Daily API quota exhausted. Cannot continue."
                log_chat_interaction(prompt, error_message)
                raise RuntimeError(error_message) from e

            # Check for temporary rate limit (retry with backoff, but limit retries)
            if "429" in str(e) or "resource_exhausted" in error_str:
                if retries >= MAX_RETRIES:
                    print(Fore.RED + f"[ERROR] Rate limit persists after {MAX_RETRIES} retries. Stopping." + Style.RESET_ALL)
                    raise RuntimeError(f"Rate limit exceeded after {MAX_RETRIES} retries") from e
                wait_time = min(2 ** retries * 5, 60)  # Exponential backoff: 10s, 20s, 40s, max 60s
                print(Fore.YELLOW + f"[RATE LIMITED] Waiting {wait_time}s before retry {retries}/{MAX_RETRIES}..." + Style.RESET_ALL)
                time.sleep(wait_time)
            else:
                # Other errors: short delay
                print(Fore.YELLOW + f"[WARNING] Gemini API Call Failed. Retrying {retries}/{MAX_RETRIES}... Error: {e}" + Style.RESET_ALL)
                time.sleep(2)

    error_message = "[ERROR] LLM API call failed after max retries."
    log_chat_interaction(prompt, error_message)
    raise RuntimeError(error_message)


def llm_fast(prompt, model_type="fast"):
    """
    Fast LLM call with minimal thinking - for simple tasks like filtering links.
    Uses Flash model with thinking_level="low" for fastest responses.
    """
    return llm(prompt, model_type=model_type, thinking_level="low")
