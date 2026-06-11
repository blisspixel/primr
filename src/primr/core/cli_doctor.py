"""System-diagnostic `primr doctor` checks.

Extracted from `primr.core.cli` for isolated unit testing.

`run_doctor` orchestrates six smaller checks (API keys, providers,
dependencies, filesystem, API connectivity, Gemini resource cleanup) and
emits a final pass/warn/fail summary. The smaller `_check_*` helpers each
return a (passed, warning_count) tuple so they compose cleanly.
"""

from __future__ import annotations

import logging
import os
import sys

from primr.config.config import LOGS_DIR, OUTPUT_DIR, WORKING_DIR
from primr.config.models import PrimrModels
from primr.utils.console import console

logger = logging.getLogger(__name__)


def _check_api_keys(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check API key configuration and actually test connectivity."""
    import requests

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key and len(gemini_key) >= 10:
        if gemini_key.startswith("AI"):
            console.ok("GEMINI_API_KEY configured (valid format)")
        else:
            console.ok("GEMINI_API_KEY configured")
            console.warn("  Key format unusual (expected to start with 'AI')")
            warnings_count += 1
    else:
        console.error("GEMINI_API_KEY not set or invalid")
        console.info("  Run: primr keys set gemini")
        console.info("  Get your key at: https://aistudio.google.com/apikey")
        all_passed = False

    search_provider = os.environ.get("SEARCH_PROVIDER", "auto").lower().strip()
    search_key = os.environ.get("SEARCH_API_KEY", "")
    search_engine_id = os.environ.get("SEARCH_ENGINE_ID", "")

    if search_provider == "google":
        if not search_key or len(search_key) < 10:
            console.error("SEARCH_API_KEY not set or invalid (required for SEARCH_PROVIDER=google)")
            console.info("  Get your key at: https://console.cloud.google.com/apis/credentials")
            all_passed = False
        elif not search_engine_id or len(search_engine_id) < 10:
            console.error(
                "SEARCH_ENGINE_ID not set or invalid (required for SEARCH_PROVIDER=google)"
            )
            console.info(
                "  Get it at: https://programmablesearchengine.google.com/controlpanel/all"
            )
            all_passed = False
        else:
            try:
                test_url = "https://www.googleapis.com/customsearch/v1"
                params: dict[str, str | int] = {
                    "q": "test",
                    "key": search_key,
                    "cx": search_engine_id,
                    "num": 1,
                }
                response = requests.get(test_url, params=params, timeout=10)
                if response.status_code == 200:
                    console.ok("Google Search API working")
                elif response.status_code == 400:
                    error_detail = response.json().get("error", {}).get("message", "Bad Request")
                    console.error(f"Google Search API config invalid: {error_detail}")
                    console.info(
                        "  Check SEARCH_ENGINE_ID at: "
                        "https://programmablesearchengine.google.com/controlpanel/all"
                    )
                    all_passed = False
                elif response.status_code == 403:
                    console.error("Google Search API key invalid or quota exceeded")
                    all_passed = False
                else:
                    console.error(f"Google Search API error: HTTP {response.status_code}")
                    all_passed = False
            except requests.exceptions.Timeout:
                console.error("Google Search API timeout")
                all_passed = False
            except Exception as e:
                console.error(f"Google Search API check failed: {e}")
                all_passed = False
    else:
        try:
            from ddgs import DDGS

            results = DDGS().text("test", max_results=1)
            if results:
                console.ok("DuckDuckGo search working (no API key needed)")
            else:
                console.warn("DuckDuckGo returned no results for test query")
                warnings_count += 1
        except Exception as e:
            console.error(f"DuckDuckGo search check failed: {e}")
            all_passed = False

    xai_key = os.environ.get("XAI_API_KEY", "")
    if xai_key and len(xai_key) >= 10:
        console.ok("XAI_API_KEY configured (enables Grok standard mode)")
    else:
        console.info("XAI_API_KEY not set (recommended for Grok standard mode)")
        console.info("  Run: primr keys set xai")
        console.info("  Get your key at: https://console.x.ai/")

    return all_passed, warnings_count


def _check_providers(warnings_count: int) -> int:
    """Report which LLM providers are configured and what each unlocks."""
    from primr.ai.providers import KNOWN_PROVIDERS, get_available_providers

    available = {p.name for p in get_available_providers()}

    if not available:
        console.error("No LLM providers configured")
        console.info("  Set XAI_API_KEY for the standard pipeline, or GEMINI_API_KEY for --premium")
        return warnings_count + 1

    for entry in KNOWN_PROVIDERS:
        if entry.name in available:
            roles = ", ".join(entry.roles) if entry.roles else "any"
            console.ok(f"{entry.description} [{roles}]")
        else:
            console.info(f"  {entry.description}: not configured ({entry.api_key_env} unset)")

    return warnings_count


def _check_dependencies(warnings_count: int) -> int:
    """Check required dependencies."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright():
            console.ok("Playwright browsers available")
    except Exception as e:
        console.warn(f"Playwright not ready: {e}")
        console.info("  Run: playwright install chromium")
        warnings_count += 1
    return warnings_count


def _check_filesystem(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check filesystem access."""

    def _atomic_write_probe(directory: str) -> None:
        os.makedirs(directory, exist_ok=True)
        target = os.path.join(directory, ".primr_test")
        tmp = f"{target}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("test")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
        os.remove(target)

    try:
        _atomic_write_probe(OUTPUT_DIR)
        console.ok("Output directory writable")
    except Exception as e:
        console.error(f"Cannot write to output directory: {e}")
        all_passed = False

    try:
        _atomic_write_probe(WORKING_DIR)
        console.ok("Working directory writable")
    except Exception as e:
        console.error(f"Cannot write to working directory: {e}")
        all_passed = False

    try:
        cache_path = os.path.join(LOGS_DIR, "cache.db")
        if os.path.exists(cache_path):
            cache_size = os.path.getsize(cache_path) / (1024 * 1024)
            console.ok(f"Cache accessible ({cache_size:.1f} MB)")
        else:
            console.ok("Cache directory ready")
    except Exception as e:
        console.warn(f"Cache check failed: {e}")
        warnings_count += 1

    return all_passed, warnings_count


def _check_api_connectivity(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check API connectivity."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            from google import genai

            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model=PrimrModels.FAST_MODEL,
                contents="Reply with exactly: hello",
            )
            if response and (response.text or response.candidates):
                console.ok("Gemini API responding")
            else:
                console.ok("Gemini API connected")
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str:
                console.error("Gemini API quota exceeded - wait and retry")
                all_passed = False
            elif "invalid" in error_str and "key" in error_str:
                console.error("Gemini API key is invalid")
                all_passed = False
            else:
                console.warn(f"Gemini API test failed: {e}")
                warnings_count += 1
    else:
        console.warn("Skipping API test (no key configured)")
        warnings_count += 1

    return all_passed, warnings_count


def _check_gemini_resources(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check for orphaned Gemini resources that could be incurring costs."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        console.warn("Skipping Gemini resource check (no API key)")
        warnings_count += 1
        return all_passed, warnings_count

    try:
        from google import genai

        client = genai.Client(api_key=gemini_key)
        python_cmd = f'"{sys.executable}"'

        try:
            caches = list(client.caches.list())
            if caches:
                console.warn(f"Found {len(caches)} orphaned cache(s) - costing money!")
                console.info(
                    f"  Run: {python_cmd} scripts/check_gemini_resources.py --delete-caches"
                )
                warnings_count += 1
            else:
                console.ok("No orphaned caches")
        except Exception as e:
            logger.debug(f"Could not list caches: {e}")

        try:
            stores = list(client.file_search_stores.list())
            if stores:
                console.warn(f"Found {len(stores)} orphaned file search store(s)")
                console.info(
                    f"  Run: {python_cmd} scripts/check_gemini_resources.py "
                    "--delete-stores --force-empty"
                )
                warnings_count += 1
            else:
                console.ok("No orphaned file search stores")
        except Exception as e:
            logger.debug(f"Could not list file search stores: {e}")

    except ImportError:
        console.warn("google-genai not installed, skipping resource check")
        warnings_count += 1
    except Exception as e:
        console.warn(f"Gemini resource check failed: {e}")
        warnings_count += 1

    return all_passed, warnings_count


def _check_key_shadowing(warnings_count: int) -> int:
    """Warn when an OS environment variable shadows a configured .env key.

    A common, confusing failure mode: the user edits the .env file but a stale
    shell/OS environment variable keeps overriding it, so the change never takes
    effect and key validation keeps using the old value.
    """
    from primr.config.env import KEY_HELP, describe_key_source, mask_secret

    for env_name in KEY_HELP:
        _active, _source, shadowed = describe_key_source(env_name)
        if shadowed is not None:
            console.warn(
                f"{env_name} is set by an OS environment variable, which overrides your "
                f".env file value ({mask_secret(shadowed)}). Edits to the .env file are "
                f"ignored until you clear the environment variable."
            )
            warnings_count += 1
    return warnings_count


def _show_file_locations() -> None:
    """Surface where each category of primr file lives.

    One place that documents the on-disk story (roadmap #12): per-run
    artifacts resolve relative to the invocation directory; shared state
    (vendor research) lives in the per-user cache so it is never duplicated
    per company folder.
    """
    from pathlib import Path

    from primr.core.vendor_research import get_vendor_research_dir
    from primr.utils.usage_tracker import USAGE_FILE
    from primr.utils.user_cache import get_user_cache_dir

    locations = [
        ("Deliverables (per run)", str(Path(OUTPUT_DIR).resolve())),
        ("Working files (per run)", str(Path(WORKING_DIR).resolve())),
        ("User cache (shared)", str(get_user_cache_dir())),
        ("Vendor research (shared)", str(get_vendor_research_dir())),
        ("Usage history", str(Path(USAGE_FILE).resolve())),
    ]
    for label, path in locations:
        console.info(f"{label}: {path}")
    console.info(
        "Per-run folders are safe to archive/delete after a run; "
        "the user cache is shared across runs (PRIMR_CACHE_DIR to relocate)."
    )


def run_scraper_stats() -> int:
    """`primr doctor --scraper-stats`: per-tier analytics across recent runs.

    Aggregates the JSONL scrape traces (logs/scrape_traces/) into per-tier
    success rate, latency p95, and content-quality signals so sticky-tier
    policy and circuit-breaker thresholds can be tuned from data.
    """
    from primr.data.scraping.trace_stats import (
        DEFAULT_TRACE_DIR,
        aggregate_scraper_stats,
        format_scraper_stats,
    )

    console.banner("Scraper Stats")
    console.blank()

    summary = aggregate_scraper_stats()
    if summary is None:
        console.info(f"No scrape traces found under {DEFAULT_TRACE_DIR.resolve()}")
        console.info("Run a research job first — traces are written per run.")
        return 0

    for line in format_scraper_stats(summary).splitlines():
        console.info(line)
    return 0


def run_doctor(*, fix: bool = False) -> int:
    """Run system diagnostics. Exit code 0 if all checks pass, 1 otherwise."""
    console.banner("Primr Doctor")
    console.blank()

    all_passed = True
    warnings_count = 0

    console.step("Environment")
    py_version = sys.version_info
    if py_version >= (3, 10):
        console.ok(f"Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        console.error(f"Python {py_version.major}.{py_version.minor} (need 3.10+)")
        all_passed = False

    console.step("API Configuration")
    all_passed, warnings_count = _check_api_keys(all_passed, warnings_count)
    warnings_count = _check_key_shadowing(warnings_count)

    console.step("Providers")
    warnings_count = _check_providers(warnings_count)

    console.step("Dependencies")
    warnings_count = _check_dependencies(warnings_count)

    console.step("File System")
    all_passed, warnings_count = _check_filesystem(all_passed, warnings_count)

    console.step("File Locations")
    _show_file_locations()

    console.step("API Connectivity")
    all_passed, warnings_count = _check_api_connectivity(all_passed, warnings_count)

    console.step("Gemini Resources")
    all_passed, warnings_count = _check_gemini_resources(all_passed, warnings_count)

    console.blank()
    if all_passed and warnings_count == 0:
        console.success_box("All checks passed", "Primr is ready to use")
    elif all_passed:
        console.success_box(
            f"Ready with {warnings_count} warning(s)",
            "Primr can run, but some features may be limited",
        )
    else:
        console.error("Some checks failed - fix issues above before running research")
        if not fix:
            console.info("Run 'primr doctor --fix' for guided setup.")

    if fix:
        if all_passed and warnings_count == 0:
            return 0
        from primr.core.cli_init import _run_init_flow

        console.blank()
        console.info("Launching guided setup...")
        return _run_init_flow(
            non_interactive=not sys.stdin.isatty(),
            assume_yes=False,
            skip_browsers=False,
            run_doctor_after=True,
        )

    return 0 if all_passed else 1
