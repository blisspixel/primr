"""First-time setup helpers for the `primr init` flow.

Extracted from `primr.core.cli` for isolated unit testing.

These cover interactive yes/no prompting, "is this API key plausibly
configured" detection, live key verification against Gemini/xAI,
Playwright browser-availability checks and installation, project-level
.env file scaffolding, and the end-to-end `_run_init_flow` driver.
"""

from __future__ import annotations

import getpass
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from primr.ai.genai_factory import default_genai_http_options
from primr.data.scraping.playwright_compat import (
    SYNC_BROWSER_UNAVAILABLE_REASON,
    sync_browser_runtime_supported,
)
from primr.utils.console import console
from primr.utils.console import prompt_yes_no as _prompt_yes_no
from primr.utils.terminal import can_prompt_for_input

logger = logging.getLogger(__name__)

MODEL_PROVIDER_ENV_NAMES = (
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
)


def _should_offer_interactive_key_setup(validation_result: Any) -> bool:
    """Return True when the only validation errors are missing API keys and we're on a TTY."""
    if not can_prompt_for_input():
        return False
    if not validation_result.errors:
        return False
    key_error_fields = {
        "MODEL_PROVIDER_API_KEY",
        "GEMINI_API_KEY/XAI_API_KEY",
        *MODEL_PROVIDER_ENV_NAMES,
    }
    return all(getattr(err, "field", "") in key_error_fields for err in validation_result.errors)


def _key_looks_configured(env_name: str) -> bool:
    value = os.environ.get(env_name, "")
    return bool(value and len(value.strip()) >= 10)


def _validate_key_live(provider: str, value: str) -> tuple[bool, str]:
    """Make a cheap, no-token API call to verify the key authenticates.

    Returns (ok, message). On failure, message is a short user-facing reason.
    """
    value = value.strip()
    if not value:
        return False, "empty key"

    if provider == "gemini":
        try:
            from google import genai

            client = genai.Client(api_key=value, http_options=default_genai_http_options())
            list(client.models.list())
            return True, "verified"
        except ImportError:
            return True, "saved without verification (google-genai not installed)"
        except Exception as exc:
            err = str(exc).lower()
            if (
                "api key" in err
                or "unauthenticated" in err
                or "permission" in err
                or "401" in err
                or "403" in err
            ):
                return False, "rejected by Google (invalid key)"
            return False, f"could not verify: {exc}"

    if provider == "xai":
        try:
            import openai

            xai_client = openai.OpenAI(api_key=value, base_url="https://api.x.ai/v1")
            list(xai_client.models.list())
            return True, "verified"
        except ImportError:
            return True, "saved without verification (openai not installed)"
        except Exception as exc:
            err = str(exc).lower()
            if (
                "401" in err
                or "403" in err
                or "unauthorized" in err
                or "invalid" in err
                or "api key" in err
            ):
                return False, "rejected by xAI (invalid key)"
            return False, f"could not verify: {exc}"

    if provider == "openrouter":
        try:
            import httpx

            from primr.ai.providers.openrouter import OPENROUTER_BASE_URL

            with httpx.Client(follow_redirects=False, timeout=15.0) as http_client:
                response = http_client.get(
                    f"{OPENROUTER_BASE_URL}/key",
                    headers={"Authorization": f"Bearer {value}"},
                )
                response.raise_for_status()
            return True, "verified"
        except ImportError:
            return True, "saved without verification (httpx not installed)"
        except Exception as exc:
            err = str(exc).lower()
            if (
                "401" in err
                or "403" in err
                or "unauthorized" in err
                or "invalid" in err
                or "api key" in err
            ):
                return False, "rejected by OpenRouter (invalid key)"
            return False, f"could not verify: {exc}"

    return True, "saved without verification"


def _playwright_browsers_ready() -> bool:
    """Return whether Playwright can launch Chromium."""
    if not sync_browser_runtime_supported():
        return False
    try:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=True)
            browser.close()
        finally:
            pw.stop()
        return True
    except Exception:
        return False


def _install_playwright_browsers() -> bool:
    """Install the Chromium browser bundle used by Playwright."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
        text=True,
    )
    return result.returncode == 0


def _prompt_for_provider_key(provider: str, env_name: str) -> bool:
    """Prompt for, validate, and save one provider key.

    Returns False only when the secret input stream becomes unavailable.
    Skips and exhausted validation retries return True so the caller can
    continue through the remaining providers and report aggregate readiness.
    """
    from primr.config.env import mask_secret, set_user_key

    for attempt in range(3):
        try:
            value = getpass.getpass(f"  {env_name} (input hidden): ").strip()
        except (EOFError, OSError, ValueError):
            console.error("Secret input became unavailable before a value was read")
            console.info("Re-run 'primr init' in a foreground terminal.")
            return False
        if not value:
            console.warn(f"Skipped {env_name}")
            return True
        console.info("  Verifying key with provider...")
        ok, message = _validate_key_live(provider, value)
        if ok:
            set_user_key(provider, value)
            os.environ[env_name] = value
            console.ok(f"{env_name} saved ({mask_secret(value)}) - {message}")
            return True
        console.error(f"  {message}")
        if attempt < 2:
            console.info("  Try again, or press Enter to skip.")
    return True


def _ensure_project_env_file() -> tuple[bool, str | None]:
    """Create a safe local .env template for source/project checkouts."""
    cwd = Path.cwd()
    env_path = cwd / ".env"
    if env_path.exists():
        return False, str(env_path)

    if not ((cwd / ".env.example").exists() or (cwd / "pyproject.toml").exists()):
        return False, None

    env_path.write_text(
        "\n".join(
            [
                "# Primr project-specific overrides",
                "# Prefer `primr keys set ...` for user-level secrets.",
                "# Uncomment values here only when this project needs different settings.",
                "",
                "# GEMINI_API_KEY=",
                "# XAI_API_KEY=",
                "# OPENAI_API_KEY=",
                "# OPENROUTER_API_KEY=",
                "# PRIMR_OPENROUTER_ENABLED=0",
                "# ANTHROPIC_API_KEY=",
                "# OLLAMA_BASE_URL=http://localhost:11434",
                "# OLLAMA_API_KEY=ollama",
                "# SEARCH_PROVIDER=auto",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return True, str(env_path)


def _run_init_flow(
    *,
    non_interactive: bool,
    assume_yes: bool,
    skip_browsers: bool,
    run_doctor_after: bool,
    doctor_runner: Callable[..., int] | None = None,
) -> int:
    """Run first-time setup for CLI-first installs."""
    from primr.config.env import (
        get_user_env_path,
        load_primr_env,
        mask_secret,
    )

    load_primr_env()
    interactive = (not non_interactive) and can_prompt_for_input()
    all_ready = True

    console.banner("Primr Init")
    console.info(f"User config: {get_user_env_path()}")
    console.blank()

    py_version = sys.version_info
    if py_version >= (3, 12):
        console.ok(f"Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        console.error(f"Python {py_version.major}.{py_version.minor} (need 3.12+)")
        all_ready = False

    console.step("Project config")
    created_env, project_env = _ensure_project_env_file()
    if created_env:
        console.ok(f"Created local .env template: {project_env}")
    elif project_env:
        console.ok(f"Local .env already exists: {project_env}")
    else:
        console.info("Using user-level config; no project .env needed here")

    key_steps = [
        (
            "xai",
            "XAI_API_KEY",
            "Grok 4.3 standard reasoning (~$5.09 XAI-only base; sub-$1 base with Gemini writing)",
            "https://console.x.ai/",
            "$25 free credits for new accounts",
            True,
        ),
        (
            "gemini",
            "GEMINI_API_KEY",
            "Cheapest measured writer with XAI, premium mode, and scrape summaries",
            "https://aistudio.google.com/apikey",
            "free tier available",
            True,
        ),
        (
            "openai",
            "OPENAI_API_KEY",
            "Optional GPT/o-series provider for routed estimates, evals, and fallback experiments",
            "https://platform.openai.com/api-keys",
            "pay as you go",
            False,
        ),
        (
            "anthropic",
            "ANTHROPIC_API_KEY",
            "Optional Claude provider for routed estimates, evals, and fallback experiments",
            "https://console.anthropic.com/settings/keys",
            "pay as you go",
            False,
        ),
        (
            "openrouter",
            "OPENROUTER_API_KEY",
            "Optional price-bounded gateway route across multiple model providers",
            "https://openrouter.ai/settings/keys",
            "pay as you go; routing remains disabled until explicitly enabled",
            False,
        ),
    ]

    console.step("API keys")
    for provider, env_name, purpose, url, hint, default_yes in key_steps:
        already_set = _key_looks_configured(env_name)
        if already_set:
            existing = os.environ.get(env_name)
            console.ok(f"{env_name} configured ({mask_secret(existing)})")
            if not interactive or assume_yes:
                continue
            if not _prompt_yes_no(
                f"  Replace {env_name}? (only if the saved key is wrong)", default=False
            ):
                continue
            console.info(f"  Why: {purpose}")
            console.info(f"  Get one: {url}  ({hint})")
        else:
            console.warn(f"{env_name} not set")
            console.info(f"  Why: {purpose}")
            console.info(f"  Get one: {url}  ({hint})")

            if not interactive:
                console.info(f"  Run: primr keys set {provider}")
                continue

            if assume_yes and not default_yes:
                continue

            wants_to_paste = assume_yes if default_yes else False
            if not wants_to_paste:
                wants_to_paste = _prompt_yes_no(f"Paste your {env_name} now?", default=default_yes)
            if not wants_to_paste:
                continue

        if not _prompt_for_provider_key(provider, env_name):
            return 1
    if not any(_key_looks_configured(env_name) for env_name in MODEL_PROVIDER_ENV_NAMES):
        all_ready = False
        console.warn("No model provider key configured")
        console.info("  Run one of: primr keys set xai | gemini | openai | openrouter | anthropic")

    console.step("Browser dependencies")
    if skip_browsers:
        console.info("Playwright browser install skipped")
    elif not sync_browser_runtime_supported():
        console.warn(SYNC_BROWSER_UNAVAILABLE_REASON)
        console.info("Safe non-Playwright collection tiers remain available")
    elif _playwright_browsers_ready():
        console.ok("Playwright Chromium available")
    elif non_interactive and not assume_yes:
        all_ready = False
        console.warn("Playwright Chromium is not installed")
        console.info("  Run: python -m playwright install chromium")
        console.info("  Or: primr init --yes")
    else:
        should_install = assume_yes or (
            interactive and _prompt_yes_no("Install Playwright Chromium now?", default=True)
        )
        if should_install:
            if _install_playwright_browsers():
                console.ok("Playwright Chromium installed")
            else:
                all_ready = False
                console.error("Playwright Chromium install failed")
                console.info("  Run: python -m playwright install chromium")
        else:
            all_ready = False
            console.warn("Playwright Chromium skipped")
            console.info("  Run later: python -m playwright install chromium")

    if run_doctor_after and not non_interactive:
        if doctor_runner is None:
            raise RuntimeError("doctor_runner is required when run_doctor_after is enabled")

        console.blank()
        return doctor_runner(fix=False)

    console.blank()
    if all_ready:
        console.success_box(
            "Setup complete",
            'Run: primr "ExampleCo" https://example.co',
        )
        return 0

    console.warn("Setup still needs attention")
    console.info("Run 'primr doctor' after completing the steps above.")
    return 1
