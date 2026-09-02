"""Preflight checks for CLI research runs."""

from __future__ import annotations

import os

from primr.ai.genai_factory import default_genai_http_options
from primr.config.models import PrimrModels

FULL_EXECUTION_MODES = ("complete", "hybrid", "structured")


def _selected_openrouter_models() -> tuple[str, ...]:
    """Return role models that would actually use the enabled gateway."""

    from primr.ai.routing import Role, pick_model_for_role

    selected: list[str] = []
    for role in (Role.UTILITY, Role.WRITING, Role.REASONING):
        model = pick_model_for_role(role)
        config = PrimrModels.get_model_config(model)
        if config is not None and config.provider == "openrouter":
            selected.append(model)
    return tuple(dict.fromkeys(selected))


def _check_model_provider_keys(
    mode: str,
    *,
    premium_mode: bool = False,
    fast_mode: bool = False,
    refresh_vendor_research: bool = False,
    grok_tier: str = "hybrid",
) -> tuple[list[str], str, bool, bool]:
    errors = []

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    xai_key = os.environ.get("XAI_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    from primr.ai.providers.openrouter import openrouter_routing_enabled

    openrouter_enabled = openrouter_routing_enabled()
    has_gemini = bool(gemini_key and len(gemini_key) >= 10)
    has_xai = bool(xai_key and len(xai_key) >= 10)
    has_openrouter = bool(openrouter_enabled and openrouter_key and len(openrouter_key) >= 10)
    if has_openrouter:
        try:
            _selected_openrouter_models()
        except ValueError as exc:
            errors.append(f"OpenRouter configuration is invalid: {exc}")
            has_openrouter = False
    is_full_execution = mode in FULL_EXECUTION_MODES
    requires_gemini = mode == "deep-research" or premium_mode or refresh_vendor_research
    requires_xai = fast_mode and (grok_tier == "max" or not has_openrouter)

    if requires_gemini:
        if not gemini_key:
            errors.append(
                "GEMINI_API_KEY not configured. Run 'primr keys set gemini' "
                "or get a key at https://aistudio.google.com/apikey"
            )
        elif len(gemini_key) < 10:
            errors.append("GEMINI_API_KEY set but appears too short")
    if requires_xai:
        if not xai_key:
            errors.append(
                "XAI_API_KEY not configured. Run 'primr keys set xai' "
                "or get a key at https://console.x.ai/"
            )
        elif len(xai_key) < 10:
            errors.append("XAI_API_KEY set but appears too short")
    elif is_full_execution and not requires_gemini:
        if gemini_key and len(gemini_key) < 10:
            errors.append("GEMINI_API_KEY set but appears too short")
        if xai_key and len(xai_key) < 10:
            errors.append("XAI_API_KEY set but appears too short")
        if openrouter_enabled and openrouter_key and len(openrouter_key) < 10:
            errors.append("OPENROUTER_API_KEY set but appears too short")
        if not (has_gemini or has_xai or has_openrouter):
            if openrouter_key and not openrouter_enabled:
                errors.append(
                    "OPENROUTER_API_KEY is configured, but paid OpenRouter routing is disabled. "
                    "Set PRIMR_OPENROUTER_ENABLED=1, then run the exact dry-run again."
                )
            if openai_key or anthropic_key:
                errors.append(
                    "Full report execution currently requires XAI_API_KEY or "
                    "GEMINI_API_KEY, or an explicitly enabled OpenRouter route. "
                    "OpenAI/Anthropic are wired for routed dry-runs and eval paths, "
                    "but full single-provider execution is still tracked in the roadmap."
                )
            elif not openrouter_key:
                errors.append(
                    "Full report execution requires XAI_API_KEY, GEMINI_API_KEY, or an "
                    "explicitly enabled OpenRouter route."
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


def _check_fast_dependency(fast_mode: bool, errors: list[str]) -> None:
    """Validate the optional fast client without making a network request."""

    if not fast_mode:
        return
    try:
        import openai  # noqa: F401
    except ImportError:
        errors.append(
            "Fast mode requires the 'openai' package. Install with: "
            "pip install 'primr[fast]' or pip install openai"
        )


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
        _ = client.models.get(model=PrimrModels.FAST_MODEL)
    except Exception as e:
        error_str = str(e).lower()
        if "quota" in error_str or "rate" in error_str:
            errors.append("Gemini API quota exceeded - wait and retry later")
        elif "invalid" in error_str or "api key" in error_str:
            errors.append("Gemini API key is invalid - check your .env file")
        else:
            errors.append(f"Gemini API connection failed: {e}")


def _check_openrouter_connectivity(*, is_full_execution: bool, errors: list[str]) -> None:
    """Validate an enabled OpenRouter key without generating model output."""

    from primr.ai.providers.openrouter import openrouter_routing_enabled

    if not is_full_execution or not openrouter_routing_enabled():
        return
    if not os.environ.get("OPENROUTER_API_KEY"):
        return
    try:
        selected_models = _selected_openrouter_models()
    except ValueError:
        # Local configuration validation already reports this before network
        # checks. Do not duplicate the same error.
        return
    if not selected_models:
        return
    from primr.ai.providers import KNOWN_PROVIDERS, validate_provider_credentials

    entry = next(item for item in KNOWN_PROVIDERS if item.name == "openrouter")
    result = validate_provider_credentials(entry)
    if not result.ok:
        errors.append(f"OpenRouter credential check failed: {result.detail}")


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
    refresh_vendor_research: bool = False,
    grok_tier: str = "hybrid",
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
        mode,
        premium_mode=premium_mode,
        fast_mode=fast_mode,
        refresh_vendor_research=refresh_vendor_research,
        grok_tier=grok_tier,
    )
    _check_playwright(mode, errors)
    _check_fast_dependency(fast_mode, errors)
    if allow_network:
        _check_gemini_connectivity(
            gemini_key,
            requires_gemini=requires_gemini,
            is_full_execution=is_full_execution,
            errors=errors,
        )
        _check_openrouter_connectivity(is_full_execution=is_full_execution, errors=errors)
        _check_google_search(errors)

    return (len(errors) == 0, errors)


def _run_network_preflight_checks(
    mode: str,
    *,
    premium_mode: bool = False,
    fast_mode: bool = False,
    refresh_vendor_research: bool = False,
    grok_tier: str = "hybrid",
) -> tuple[bool, list[str]]:
    """Run only provider and search connectivity checks after budget approval."""

    errors, gemini_key, requires_gemini, is_full_execution = _check_model_provider_keys(
        mode,
        premium_mode=premium_mode,
        fast_mode=fast_mode,
        refresh_vendor_research=refresh_vendor_research,
        grok_tier=grok_tier,
    )
    if not errors:
        _check_gemini_connectivity(
            gemini_key,
            requires_gemini=requires_gemini,
            is_full_execution=is_full_execution,
            errors=errors,
        )
        _check_openrouter_connectivity(is_full_execution=is_full_execution, errors=errors)
        _check_google_search(errors)
    return (len(errors) == 0, errors)
