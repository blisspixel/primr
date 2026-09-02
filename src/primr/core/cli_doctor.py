"""System-diagnostic `primr doctor` checks.

Extracted from `primr.core.cli` for isolated unit testing.

`run_doctor` orchestrates six smaller checks (API keys, providers,
dependencies, filesystem, zero-spend API policy, Gemini resource cleanup) and
emits a final pass/warn/fail summary. The smaller `_check_*` helpers each
return a (passed, warning_count) tuple so they compose cleanly.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

from primr.ai.availability_sanitize import (
    safe_code,
    safe_code_or,
    safe_count,
    safe_display_label,
    safe_env_label,
)
from primr.ai.genai_factory import default_genai_http_options
from primr.ai.provider_availability import (
    AvailabilityState,
    ProviderQuotaSnapshot,
    availability_decision,
)
from primr.ai.provider_availability_collectors import (
    LOCAL_OPENAI_COMPATIBLE_PROVIDER,
    collect_provider_availability_snapshots,
)
from primr.config.config import LOGS_DIR, OUTPUT_DIR, WORKING_DIR
from primr.utils.atomic_io import atomic_replace
from primr.utils.console import console
from primr.utils.terminal import can_prompt_for_input

logger = logging.getLogger(__name__)


def _check_api_keys(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check API key configuration and actually test connectivity."""
    import requests

    configured_model_keys = 0

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key and len(gemini_key) >= 10:
        configured_model_keys += 1
        if gemini_key.startswith("AI"):
            console.ok("GEMINI_API_KEY configured (valid format)")
        else:
            console.ok("GEMINI_API_KEY configured")
            console.warn("  Key format unusual (expected to start with 'AI')")
            warnings_count += 1
    elif gemini_key:
        console.error("GEMINI_API_KEY set but appears too short")
        all_passed = False
    else:
        console.info("GEMINI_API_KEY not set (Gemini writing/premium disabled)")

    xai_key = os.environ.get("XAI_API_KEY", "")
    if xai_key and len(xai_key) >= 10:
        configured_model_keys += 1
        console.ok("XAI_API_KEY configured (enables Grok hybrid/full pipeline)")
    elif xai_key:
        console.error("XAI_API_KEY set but appears too short")
        all_passed = False
    else:
        console.info("XAI_API_KEY not set (Grok hybrid/full pipeline disabled)")
        console.info("  Run: primr keys set xai")
        console.info("  Get your key at: https://console.x.ai/")

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key and len(openai_key) >= 10:
        configured_model_keys += 1
        console.ok(
            "OPENAI_API_KEY configured (dry-run/eval/routed stages; "
            "full execution still needs XAI or Gemini)"
        )
    elif openai_key:
        console.error("OPENAI_API_KEY set but appears too short")
        all_passed = False

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key and len(openrouter_key) >= 10:
        configured_model_keys += 1
        from primr.ai.providers.openrouter import openrouter_routing_enabled

        if openrouter_routing_enabled():
            console.ok("OPENROUTER_API_KEY configured (paid gateway routing enabled)")
        else:
            console.ok("OPENROUTER_API_KEY configured (routing disabled until explicit opt-in)")
    elif openrouter_key:
        console.error("OPENROUTER_API_KEY set but appears too short")
        all_passed = False

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key and len(anthropic_key) >= 10:
        configured_model_keys += 1
        console.ok(
            "ANTHROPIC_API_KEY configured (dry-run/eval/routed stages; "
            "full execution still needs XAI or Gemini)"
        )
    elif anthropic_key:
        console.error("ANTHROPIC_API_KEY set but appears too short")
        all_passed = False

    if configured_model_keys == 0:
        console.ok("Keyless ready: primr prep · primr recon · primr render")
        console.info("  Provider-backed research needs a cloud LLM key.")
        console.info("  Run one of: primr keys set gemini | xai | openai | openrouter | anthropic")

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

    return all_passed, warnings_count


def _check_providers(warnings_count: int) -> int:
    """Report which LLM providers are configured AND usable (key + SDK).

    A key being set is not enough - the provider's SDK must also be importable
    (e.g. Anthropic needs ``pip install anthropic``). ``is_available()`` checks
    both and makes no network call, so this stays cheap.
    """
    from primr.ai.providers import KNOWN_PROVIDERS, build_provider

    # SDK names differ from provider names for the OpenAI-compatible providers,
    # so only spell out the install hint where the package is non-obvious.
    sdk_hint = {"anthropic": "pip install anthropic"}

    usable_count = 0
    for entry in KNOWN_PROVIDERS:
        key_set = bool(os.getenv(entry.api_key_env)) or entry.api_key_default is not None
        if not key_set:
            console.info(f"  {entry.description}: not configured ({entry.api_key_env} unset)")
            continue
        try:
            usable = build_provider(entry).is_available()
        except Exception:
            usable = False
        roles = ", ".join(entry.roles) if entry.roles else "any"
        if usable:
            console.ok(f"{entry.description} [{roles}]")
            usable_count += 1
        else:
            console.warn(
                f"{entry.description}: {entry.api_key_env} set but the provider isn't usable"
            )
            hint = sdk_hint.get(entry.name)
            if hint:
                console.info(f"  Its SDK is missing - run: {hint}")
            warnings_count += 1

    if usable_count == 0:
        console.warn("No usable LLM providers (provider-backed research unavailable)")
        console.info("  Keyless commands remain ready: primr prep | primr recon")
        console.info(
            "  Set a provider key (primr keys set gemini|xai|openai|openrouter|anthropic) "
            "+ install its SDK"
        )
        return warnings_count + 1

    return warnings_count


def _check_provider_availability(warnings_count: int) -> int:
    """Show sanitized provider availability snapshots for routing."""

    try:
        snapshots = collect_provider_availability_snapshots()
    except Exception as e:
        console.warn(f"Provider availability collection failed: {safe_code(str(e))}")
        return warnings_count + 1

    for snapshot in snapshots:
        level, line = _provider_availability_status(snapshot)
        if level == "ok":
            console.ok(line)
        elif level == "warn":
            console.warn(line)
            warnings_count += 1
        else:
            console.info(line)
    return warnings_count


def _provider_availability_status(snapshot: ProviderQuotaSnapshot) -> tuple[str, str]:
    provider_code = safe_code(snapshot.provider) or "provider"
    display_name = safe_display_label(snapshot.display_name or snapshot.provider, provider_code)
    decision = availability_decision(snapshot)
    error = safe_code(snapshot.error)
    quota_source = safe_code_or(snapshot.metadata.get("quota_source"), "unknown")

    if snapshot.provider == LOCAL_OPENAI_COMPATIBLE_PROVIDER:
        endpoint_source = safe_code_or(snapshot.metadata.get("endpoint_source"), "unknown")
        model_count = safe_count(snapshot.metadata.get("model_count", 0))
        if decision.available:
            return (
                "ok",
                f"{display_name}: available ({model_count} local model(s), $0 API runtime)",
            )
        if decision.state is AvailabilityState.BUSY:
            retry_seconds = decision.retry_after_seconds or 0
            retry_at = decision.retry_at.isoformat() if decision.retry_at is not None else "unknown"
            return (
                "warn",
                f"{display_name}: busy (retry after {retry_seconds}s, no earlier than {retry_at})",
            )
        return (
            "info",
            f"{display_name}: not available ({error or 'not_detected'}, source {endpoint_source})",
        )

    configured = bool(snapshot.metadata.get("configured", snapshot.ok))
    if not configured and error == "missing_api_key":
        api_key_env = safe_env_label(snapshot.metadata.get("api_key_env"))
        return ("info", f"{display_name}: not configured ({api_key_env} unset)")

    if decision.available:
        detail = f"quota {quota_source or 'unknown'}"
        if decision.headroom_percent is not None:
            detail = f"{decision.headroom_percent:.1f}% headroom, {detail}"
        return ("ok", f"{display_name}: configured ({detail})")

    return ("warn", f"{display_name}: unavailable ({error or 'availability_error'})")


def _check_dependencies(warnings_count: int) -> int:
    """Check required dependencies without risking the doctor process.

    Playwright starts a native driver while entering its context manager. A
    preview Python or newly released platform wheel can terminate the process
    before Python has an opportunity to raise an exception. Keep that probe in
    a short-lived child so doctor can report the failure instead of crashing.
    """
    probe = "from playwright.sync_api import sync_playwright\nwith sync_playwright():\n    pass\n"
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        console.warn(f"Playwright not ready: isolated probe failed ({type(e).__name__})")
        console.info("  Run: playwright install chromium")
        return warnings_count + 1

    if result.returncode == 0:
        console.ok("Playwright runtime available")
        return warnings_count

    console.warn(f"Playwright not ready: isolated probe exited with status {result.returncode}")
    console.info("  Run: playwright install chromium")
    warnings_count += 1
    return warnings_count


def _check_filesystem(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check filesystem access."""

    def _atomic_write_probe(directory: str) -> None:
        # Probe the same temp-write + atomic_replace path real runs use for
        # state files, so doctor surfaces the sync-client/antivirus lock
        # contention (OneDrive et al.) that would bite a live pipeline.
        os.makedirs(directory, exist_ok=True)
        target = os.path.join(directory, ".primr_test")
        tmp = f"{target}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("test")
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp, target)
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
    """Report live-probe policy without making a billable generation request."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        console.ok("Gemini key present; live model probe skipped to avoid model spend")
    else:
        console.info("No Gemini key; no live model probe requested")

    return all_passed, warnings_count


def _check_gemini_resources(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check for orphaned Gemini resources that could be incurring costs."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        console.info("Skipping Gemini resource check (no API key)")
        return all_passed, warnings_count

    try:
        from google import genai

        client = genai.Client(api_key=gemini_key, http_options=default_genai_http_options())
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
        except Exception:
            logger.debug("Could not list Gemini caches", exc_info=True)
            console.warn("Gemini cache inventory could not be verified")
            warnings_count += 1

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
        except Exception:
            logger.debug("Could not list Gemini file search stores", exc_info=True)
            console.warn("Gemini file search store inventory could not be verified")
            warnings_count += 1

    except ImportError:
        console.warn("google-genai not installed, skipping resource check")
        warnings_count += 1
    except Exception:
        logger.debug("Gemini resource check failed", exc_info=True)
        console.warn("Gemini resource inventory could not be verified")
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
    per company folder. Durable operator state (research memory) lives in the
    per-user data directory.
    """
    from pathlib import Path

    from primr.agentic.memory import get_default_memory_path
    from primr.core.vendor_research import get_vendor_research_dir
    from primr.utils.usage_tracker import USAGE_FILE
    from primr.utils.user_cache import get_user_cache_dir, get_user_data_dir

    locations = [
        ("Deliverables (per run)", str(Path(OUTPUT_DIR).resolve())),
        ("Working files (per run)", str(Path(WORKING_DIR).resolve())),
        ("User cache (shared)", str(get_user_cache_dir())),
        ("User data (durable)", str(get_user_data_dir())),
        ("Research memory", str(get_default_memory_path())),
        ("Vendor research (shared)", str(get_vendor_research_dir())),
        ("Usage history", str(Path(USAGE_FILE).resolve())),
    ]
    for label, path in locations:
        console.info(f"{label}: {path}")
    console.info(
        "Per-run folders are safe to archive/delete after a run; "
        "the user cache is shared across runs (PRIMR_CACHE_DIR to relocate), "
        "and durable memory uses PRIMR_DATA_DIR when relocation is needed."
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
        console.info("Run a research job first; traces are written per run.")
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
    if py_version >= (3, 12):
        console.ok(f"Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        console.error(f"Python {py_version.major}.{py_version.minor} (need 3.12+)")
        all_passed = False
    _show_install_source()

    console.step("API Configuration")
    all_passed, warnings_count = _check_api_keys(all_passed, warnings_count)
    warnings_count = _check_key_shadowing(warnings_count)

    console.step("Providers")
    warnings_count = _check_providers(warnings_count)

    console.step("Provider Availability")
    warnings_count = _check_provider_availability(warnings_count)

    console.step("Dependencies")
    warnings_count = _check_dependencies(warnings_count)

    console.step("File System")
    all_passed, warnings_count = _check_filesystem(all_passed, warnings_count)

    console.step("File Locations")
    _show_file_locations()

    console.step("Model Probe Policy")
    all_passed, warnings_count = _check_api_connectivity(all_passed, warnings_count)

    console.step("Gemini Resources")
    all_passed, warnings_count = _check_gemini_resources(all_passed, warnings_count)

    console.step("Updates")
    _check_for_update()

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
            non_interactive=not can_prompt_for_input(),
            assume_yes=False,
            skip_browsers=False,
            run_doctor_after=True,
            doctor_runner=run_doctor,
        )

    return 0 if all_passed else 1


def _show_install_source() -> None:
    """Show which primr is actually running, and from where.

    This is the single most useful line for the "why doesn't my command exist"
    confusion: a stale released install (pipx/pip) shadows a newer working tree.
    An editable/dev install resolves the package *inside* the source tree rather
    than site-packages, so we can tell the two apart and flag a mismatch with
    the repo the user is sitting in.
    """
    import primr as _pkg
    from primr import __version__

    pkg_dir = os.path.dirname(_pkg.__file__)
    editable = "site-packages" not in pkg_dir.replace("\\", "/")
    kind = "editable/dev" if editable else "installed release"
    console.ok(f"primr {__version__} ({kind})")
    console.muted(f"  running from {pkg_dir}")
    console.muted(f"  python {sys.version.split()[0]} @ {sys.executable}")

    from primr.config.env import keystore_sandbox_warning

    sandbox = keystore_sandbox_warning()
    if sandbox:
        console.warn(f"  {sandbox}")
    if not editable:
        # A released install in a directory that also looks like a primr checkout
        # is the classic "my edits aren't taking" trap.
        cwd = os.getcwd()
        if os.path.exists(os.path.join(cwd, "src", "primr", "__init__.py")):
            console.warn(
                "  You are inside a primr checkout but running an installed release, "
                "not this source. Editable dev install: pip install -e .  (or use uv run primr)"
            )


def _check_for_update() -> None:
    """Report whether a newer primr release is available on PyPI.

    Fail-safe: any network/parse error degrades to a quiet "could not check"
    note rather than affecting the doctor exit code.
    """
    from primr import __version__
    from primr.utils.version_check import check_for_update, update_check_disabled

    if update_check_disabled():
        console.muted("Update check disabled (PRIMR_NO_UPDATE_CHECK)")
        return

    latest = check_for_update(__version__, force=True)
    if latest:
        console.warn(f"Update available: v{__version__} -> v{latest}")
        console.info("  Run: primr update")
    else:
        console.ok(f"primr is up to date (v{__version__})")
