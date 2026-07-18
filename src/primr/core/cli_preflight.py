"""Preflight checks for CLI research runs."""

from __future__ import annotations

import os

from primr.ai.genai_factory import default_genai_http_options
from primr.config.models import PrimrModels

FULL_EXECUTION_MODES = ("complete", "hybrid", "structured")


def _check_model_provider_keys(
    mode: str, *, premium_mode: bool = False, fast_mode: bool = False
) -> tuple[list[str], str, bool, bool]:
    errors = []

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    xai_key = os.environ.get("XAI_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    has_gemini = bool(gemini_key and len(gemini_key) >= 10)
    has_xai = bool(xai_key and len(xai_key) >= 10)
    is_full_execution = mode in FULL_EXECUTION_MODES
    requires_gemini = mode == "deep-research" or premium_mode
    requires_xai = fast_mode

    if requires_gemini:
        if not gemini_key:
            errors.append(
                "GEMINI_API_KEY not configured. Run 'primr keys set gemini' "
                "or get a key at https://aistudio.google.com/apikey"
            )
        elif len(gemini_key) < 10:
            errors.append("GEMINI_API_KEY set but appears too short")
    elif requires_xai:
        if not xai_key:
            errors.append(
                "XAI_API_KEY not configured. Run 'primr keys set xai' "
                "or get a key at https://console.x.ai/"
            )
        elif len(xai_key) < 10:
            errors.append("XAI_API_KEY set but appears too short")
    elif is_full_execution:
        if gemini_key and len(gemini_key) < 10:
            errors.append("GEMINI_API_KEY set but appears too short")
        if xai_key and len(xai_key) < 10:
            errors.append("XAI_API_KEY set but appears too short")
        if not (has_gemini or has_xai):
            if openai_key or anthropic_key:
                errors.append(
                    "Full report execution currently requires XAI_API_KEY or "
                    "GEMINI_API_KEY. OpenAI/Anthropic are wired for routed "
                    "dry-runs and eval paths, but full no-XAI execution is "
                    "still tracked in the roadmap."
                )
            else:
                errors.append(
                    "Full report execution requires XAI_API_KEY or GEMINI_API_KEY. "
                    "Run 'primr keys set xai' or 'primr keys set gemini'."
                )

    return errors, gemini_key, requires_gemini, is_full_execution


def _check_playwright(mode: str, errors: list[str]) -> None:
    if mode not in ("scrape-only", *FULL_EXECUTION_MODES):
        return
    try:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=True)
            browser.close()
        finally:
            pw.stop()
    except Exception as e:
        error_msg = str(e)
        if "Executable doesn't exist" in error_msg or "playwright install" in error_msg.lower():
            errors.append("Playwright browsers not installed. Run: playwright install chromium")
        else:
            errors.append(f"Playwright check failed: {error_msg}")


def _check_gemini_connectivity(
    gemini_key: str,
    *,
    requires_gemini: bool,
    is_full_execution: bool,
    errors: list[str],
) -> None:
    should_check_gemini = bool(
        gemini_key and len(gemini_key) >= 10 and (requires_gemini or is_full_execution)
    )
    if not should_check_gemini:
        return

    try:
        from google import genai

        client = genai.Client(api_key=gemini_key, http_options=default_genai_http_options())
        _ = client.models.generate_content(
            model=PrimrModels.FAST_MODEL,
            contents="Reply with: ok",
        )
    except Exception as e:
        error_str = str(e).lower()
        if "quota" in error_str or "rate" in error_str:
            errors.append("Gemini API quota exceeded - wait and retry later")
        elif "invalid" in error_str or "api key" in error_str:
            errors.append("Gemini API key is invalid - check your .env file")
        else:
            errors.append(f"Gemini API connection failed: {e}")


def _check_google_search(errors: list[str]) -> None:
    search_provider = os.environ.get("SEARCH_PROVIDER", "auto").lower().strip()
    if search_provider != "google":
        return

    search_key = os.environ.get("SEARCH_API_KEY", "")
    search_engine_id = os.environ.get("SEARCH_ENGINE_ID", "")

    if not search_key or len(search_key) < 10:
        errors.append(
            "SEARCH_API_KEY not configured. Get your key at: https://console.cloud.google.com/apis/credentials"
        )
        return
    if not search_engine_id or len(search_engine_id) < 10:
        errors.append(
            "SEARCH_ENGINE_ID not configured or invalid. Get it at: https://programmablesearchengine.google.com/controlpanel/all"
        )
        return

    try:
        import requests

        test_url = "https://www.googleapis.com/customsearch/v1"
        params: dict[str, str | int] = {
            "q": "test",
            "key": search_key,
            "cx": search_engine_id,
            "num": 1,
        }
        search_response = requests.get(test_url, params=params, timeout=10)
        if search_response.status_code == 400:
            error_detail = search_response.json().get("error", {}).get("message", "Bad Request")
            errors.append(f"Google Search API config invalid: {error_detail}")
        elif search_response.status_code == 403:
            errors.append("Google Search API key invalid or quota exceeded")
        elif search_response.status_code != 200:
            errors.append(f"Google Search API error: HTTP {search_response.status_code}")
    except requests.exceptions.Timeout:
        errors.append("Google Search API timeout - check your internet connection")
    except Exception as e:
        errors.append(f"Google Search API check failed: {e}")


def _run_preflight_checks(
    mode: str,
    *,
    premium_mode: bool = False,
    fast_mode: bool = False,
    allow_network: bool = True,
) -> tuple[bool, list[str]]:
    """
    Run preflight checks before starting research pipeline.

    Validates critical dependencies upfront to fail fast rather than
    failing 30 minutes into a long pipeline.

    Returns:
        (success, errors) - True if all checks pass, list of error messages if not
    """
    errors, gemini_key, requires_gemini, is_full_execution = _check_model_provider_keys(
        mode, premium_mode=premium_mode, fast_mode=fast_mode
    )
    _check_playwright(mode, errors)
    if allow_network:
        _check_gemini_connectivity(
            gemini_key,
            requires_gemini=requires_gemini,
            is_full_execution=is_full_execution,
            errors=errors,
        )
        _check_google_search(errors)

    return (len(errors) == 0, errors)
