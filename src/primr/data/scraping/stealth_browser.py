"""
Stealth browser tier using Patchright + real Chrome channel.

Patchright is a drop-in replacement for Playwright that patches ~20 detection
leaks (navigator.webdriver, runtime.enable CDP signals, AutomationControlled
flags, etc.) that vanilla Playwright leaves in place. Combined with the real
user-installed Chrome binary (channel="chrome") and a persistent user-data-dir
owned by primr, this tier gets through Kasada / Akamai / PerimeterX challenges
that blank plain Playwright.

Flow:
1. Try headless first (fast, invisible, no popup).
2. If headless returns a challenge shell / empty body, retry headed with a
   CLI notice so the user understands why a browser window is opening.
3. Each attempt waits for networkidle + an extra 8s buffer so Kasada's
   proof-of-work has time to resolve and swap in real content.
4. On success, primr's persistent user-data-dir accumulates the clearance
   cookies, so subsequent runs on the same host can go headless.

This is a high-cost tier (10-25s per page) and should only run after lighter
HTTP tiers have failed.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from primr.config.config import PROJECT_ROOT

from .headed_budget import (
    remaining_headed_budget,
    try_consume_headed_budget,
)
from .models import Attempt, ErrorType, ScrapeResult

logger = logging.getLogger(__name__)

# Persistent user-data-dir so cookies (especially Kasada clearance tokens)
# accumulate across runs and survive process restarts. One profile per
# host keeps cross-site cookie pollution isolated.
BROWSER_PROFILE_ROOT = Path(PROJECT_ROOT) / "logs" / "browser_profiles"

# Settings that meaningfully reduce detection vs default Chromium launch.
# Window position / size keeps the fallback popup out of the user's way when
# it does launch. Chromium still steals focus on launch (OS-level), which we
# can't fully suppress — but it sits in the corner instead of center-screen.
STEALTH_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-default-apps",
    "--password-store=basic",
    "--window-size=600,400",
    "--window-position=-3000,-3000",
]


def _profile_dir_for_host(host: str) -> Path:
    """Return a per-host persistent user-data-dir."""
    safe_host = host.replace(":", "_").replace("/", "_")[:80] or "_default"
    path = BROWSER_PROFILE_ROOT / safe_host
    path.mkdir(parents=True, exist_ok=True)
    return path


def _force_small_window_prefs(profile_dir: Path) -> None:
    """Overwrite Chrome's saved window placement so it launches tiny, not maximized.

    Chrome persists window size/state to ``Default/Preferences`` (JSON). On a
    fresh profile the first headed launch uses our ``--window-size`` arg, but
    after the user (or Chrome itself) moves/resizes the window, Chrome saves
    the new state and honors it over the launch arg next time. That's how we
    end up with a near-maximized popup on subsequent runs.

    We edit the prefs file in place before each launch to force a small,
    out-of-the-way window. This only touches ``browser.window_placement``
    and ``profile.exit_type`` — cookies, storage, and Kasada clearance
    cookies remain intact.
    """
    import json

    prefs_path = profile_dir / "Default" / "Preferences"
    if not prefs_path.exists():
        return

    try:
        with prefs_path.open("r", encoding="utf-8") as f:
            prefs = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Could not read Chrome prefs at %s: %s", prefs_path, e)
        return

    # Set a tiny window parked in the top-left corner. 380x260 is the minimum
    # Chrome accepts without automatically resizing.
    prefs.setdefault("browser", {})["window_placement"] = {
        "bottom": 260,
        "left": 0,
        "maximized": False,
        "right": 380,
        "top": 0,
        "work_area_bottom": 1040,
        "work_area_left": 0,
        "work_area_right": 1920,
        "work_area_top": 0,
    }
    # Ensure Chrome doesn't show the "Chrome didn't shut down cleanly" prompt,
    # and doesn't try to restore session tabs.
    prefs.setdefault("profile", {})["exit_type"] = "Normal"
    prefs["profile"]["exited_cleanly"] = True

    try:
        with prefs_path.open("w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except OSError as e:
        logger.debug("Could not write sanitized Chrome prefs: %s", e)


# ---------------------------------------------------------------------------
# Low-value URL filter
# ---------------------------------------------------------------------------
#
# Some URLs are simply not worth burning a stealth-browser attempt (and
# especially not a visible popup) on. Privacy policies, terms pages, review
# aggregators, job boards, and social sites rarely surface strategic content
# and often sit behind aggressive WAFs. If one of these appears on the scrape
# list, Patchright bails out fast and lets the orchestrator fall through to
# other tiers or skip the page entirely.

_LOW_VALUE_DOMAINS = frozenset(
    {
        # Review / ratings aggregators
        "glassdoor.com",
        "indeed.com",
        "ziprecruiter.com",
        "g2.com",
        "capterra.com",
        "trustradius.com",
        "getapp.com",
        "trustpilot.com",
        "sitejabber.com",
        # Social
        "twitter.com",
        "x.com",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "youtube.com",
        "pinterest.com",
        # Discussion
        "reddit.com",
        "quora.com",
        "medium.com",
        # Deal / profile databases (usually paywalled)
        "crunchbase.com",
        "pitchbook.com",
        "zoominfo.com",
        "owler.com",
        # Technographic scrapers (we already have recon)
        "builtwith.com",
        "similarweb.com",
        "semrush.com",
        "ahrefs.com",
    }
)

_LOW_VALUE_PATH_SUBSTRINGS = (
    "/privacy",
    "/privacy-policy",
    "/cookie",
    "/cookies",
    "/gdpr",
    "/ccpa",
    "/legal",
    "/terms",
    "/terms-of-service",
    "/tos",
    "/accessibility",
    "/sitemap",
    "/404",
    "/not-found",
)


def _is_low_value_url(url: str) -> bool:
    """Return True if the URL isn't worth a stealth-browser attempt."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    host = (parsed.netloc or "").lower().removeprefix("www.")
    for domain in _LOW_VALUE_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True

    path = (parsed.path or "").lower()
    return any(sub in path for sub in _LOW_VALUE_PATH_SUBSTRINGS)


def _patchright_available() -> bool:
    try:
        import patchright  # noqa: F401

        return True
    except ImportError:
        return False


_PATCHRIGHT_BROWSER_INSTALLED: bool | None = None


def _ensure_patchright_browser() -> bool:
    """Ensure a Chromium browser is installed for Patchright.

    Runs `python -m patchright install chromium` on first use if the browser
    binaries aren't present. Idempotent and cached within a process. Surfaces
    progress to the console so the user understands what's happening.
    """
    global _PATCHRIGHT_BROWSER_INSTALLED
    if _PATCHRIGHT_BROWSER_INSTALLED is not None:
        return _PATCHRIGHT_BROWSER_INSTALLED

    # Cheapest check: try to launch Patchright and see if it complains about
    # a missing browser. If launch succeeds, browsers are there.
    try:
        from patchright.sync_api import sync_playwright

        with sync_playwright() as p:
            # executable_path resolves to the bundled browser binary; if it's
            # missing patchright raises on launch — but checking without
            # launching is the cheapest probe.
            browser_path = p.chromium.executable_path
            if browser_path and os.path.exists(browser_path):
                _PATCHRIGHT_BROWSER_INSTALLED = True
                return True
    except Exception:
        pass  # fall through to install

    # Install via subprocess. This runs once per machine unless the user blows
    # away their browser cache.
    import subprocess
    import sys

    try:
        from primr.utils.console import console

        console.info(
            "First-time setup: installing stealth browser (one-time, ~150MB). This runs silently from now on."
        )
    except Exception:
        logger.info("Installing patchright chromium (first-time setup)")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "patchright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes for slow connections
        )
        if result.returncode == 0:
            _PATCHRIGHT_BROWSER_INSTALLED = True
            logger.info("Patchright chromium installed successfully")
            return True
        logger.warning(
            "Patchright browser install returned %s: %s",
            result.returncode,
            (result.stderr or result.stdout or "")[-500:],
        )
    except subprocess.TimeoutExpired:
        logger.warning("Patchright browser install timed out after 10 minutes")
    except Exception as e:
        logger.warning("Patchright browser install failed: %s", e)

    _PATCHRIGHT_BROWSER_INSTALLED = False
    return False


def _looks_like_challenge_shell(html: str) -> bool:
    """Detect when Patchright returned a pure Kasada bootstrap page.

    The raw initial response from a Kasada site contains only KPSDK script
    tags and an iframe shell — typically <2KB. A successfully cleared page
    still contains the KPSDK script tags (Kasada keeps monitoring) but also
    has the full document tree with real content — typically 50KB+.
    """
    if not html:
        return True
    if len(html) < 5000:
        return True

    # Kasada-ONLY marker patterns without any real content.
    # If the body has hundreds of elements and a big document, it's a real page.
    lower = html.lower()
    has_kasada_markers = "window.kpsdk" in lower or 'src="/149e9513-' in lower
    has_real_structure = (
        any(tag in lower for tag in ("<main", "<article", "<section", "<nav", "<header"))
        and html.count("<div") > 20
    )

    # Pure challenge: has markers but basically nothing else
    return has_kasada_markers and not has_real_structure


def _run_patchright(
    url: str,
    timeout: float,
    headless: bool,
    host: str,
    on_progress=None,
) -> tuple[str | None, str | None, int | None]:
    """Run a single Patchright fetch. Returns (html, body_text, status)."""
    from patchright.sync_api import sync_playwright

    profile_dir = _profile_dir_for_host(host)
    timeout_ms = int(timeout * 1000)

    # For headed launches, overwrite the profile's saved window size so Chrome
    # doesn't pop up a near-maximized window stealing the primary monitor.
    # Harmless for headless (that window is never shown).
    if not headless:
        _force_small_window_prefs(profile_dir)

    with sync_playwright() as p:
        # Try real Chrome first (dramatically better detection vs Chromium).
        ctx = None
        for channel in ("chrome", "msedge", None):
            try:
                if channel:
                    ctx = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        channel=channel,
                        headless=headless,
                        args=list(STEALTH_LAUNCH_ARGS),
                    )
                else:
                    ctx = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        headless=headless,
                        args=list(STEALTH_LAUNCH_ARGS),
                    )
                logger.debug(
                    "Patchright launched with channel=%s headless=%s",
                    channel or "bundled-chromium",
                    headless,
                )
                break
            except Exception as e:
                logger.debug("Patchright launch failed with channel=%s: %s", channel, e)
                ctx = None
                continue

        if ctx is None:
            return None, None, None

        try:
            # Force the initial window to be small + minimized BEFORE we open
            # our page. Chrome's persistent profile otherwise remembers a big
            # window state and the --window-size launch arg is unreliable.
            # We do two CDP calls: first an explicit tiny bounds so even the
            # brief pre-minimize flash is small, then the minimize.
            if not headless:
                try:
                    # Attach CDP to whatever about:blank target Chrome created
                    # on launch so we can resize/minimize BEFORE new_page().
                    existing_pages = ctx.pages
                    cdp_target = existing_pages[0] if existing_pages else ctx.new_page()
                    cdp = ctx.new_cdp_session(cdp_target)
                    win = cdp.send("Browser.getWindowForTarget")
                    window_id = win.get("windowId")
                    if window_id is not None:
                        cdp.send(
                            "Browser.setWindowBounds",
                            {
                                "windowId": window_id,
                                "bounds": {
                                    "left": 0,
                                    "top": 0,
                                    "width": 320,
                                    "height": 200,
                                    "windowState": "normal",
                                },
                            },
                        )
                        cdp.send(
                            "Browser.setWindowBounds",
                            {
                                "windowId": window_id,
                                "bounds": {"windowState": "minimized"},
                            },
                        )
                except Exception as cdp_err:
                    logger.debug("CDP resize/minimize failed (non-fatal): %s", cdp_err)

            page = ctx.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status = response.status if response else None

            # Post-navigation SSRF check: an attacker-controlled origin may
            # redirect into RFC1918 / loopback / cloud metadata, and unlike
            # plain HTTP tiers we cannot opt out of redirect-follow here. If
            # the final URL is internal, abort before reading the page body
            # so internal response content cannot escape into the scrape
            # corpus or raw artifacts.
            try:
                from primr.utils.security import validate_final_url_after_redirect

                safe_final, reason = validate_final_url_after_redirect(page.url)
            except Exception:
                safe_final, reason = True, None
            if not safe_final:
                logger.info(
                    "patchright: dropped %s — final URL %s blocked (%s)",
                    url,
                    page.url,
                    reason,
                )
                return None, None, None

            # Give Kasada time to run proof-of-work and swap in real content.
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 20000))
            except Exception:
                pass  # many sites never reach networkidle; that's ok

            # Extra buffer for Kasada-protected sites that need 6-10s of JS
            # proof-of-work even after networkidle.
            page.wait_for_timeout(6000)

            html = page.content()
            try:
                body_text = page.evaluate("document.body ? document.body.innerText : ''")
            except Exception:
                body_text = ""

            if on_progress:
                try:
                    on_progress(len(html), len(body_text or ""))
                except Exception:
                    pass

            return html, body_text or "", status
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def scrape_with_patchright(
    url: str,
    timeout: float = 60.0,
) -> ScrapeResult:
    """
    Stealth browser fetch using Patchright + real Chrome channel.

    Two-phase attempt: headless first, headed as fallback. The headed phase
    is announced in the primr console so the user understands why a browser
    window opens.
    """
    if not _patchright_available():
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error="patchright not installed — reinstall primr to pull it as a dependency",
            tier="patchright",
            elapsed_ms=0,
        )

    # SSRF guard: scraping is reached from research jobs whose company_url
    # was validated upstream, but discovered links and fallback fan-outs
    # can route arbitrary URLs into the scraper. Refuse loopback / RFC1918
    # / link-local / cloud metadata destinations before launching a browser.
    from primr.utils.security import is_safe_url

    safe, ssrf_reason = is_safe_url(url)
    if not safe:
        logger.info("patchright: blocked %s (%s)", url, ssrf_reason)
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.SOFT_BLOCK,
            error=f"URL blocked by SSRF guard: {ssrf_reason}",
            tier="patchright",
            elapsed_ms=0,
            attempts=[
                Attempt(
                    tier="patchright",
                    success=False,
                    error=f"ssrf blocked: {ssrf_reason}",
                    error_type=ErrorType.SOFT_BLOCK,
                )
            ],
        )

    # Short-circuit low-value URLs BEFORE spending any stealth-browser time.
    # Privacy pages, TOS, review aggregators, social profiles, etc. aren't
    # worth the popup cost even when Kasada blocks them. Fall through the
    # orchestrator instead.
    if _is_low_value_url(url):
        logger.debug("Skipping Patchright for low-value URL: %s", url)
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.SOFT_BLOCK,
            error="URL classified as low-value for stealth browser",
            tier="patchright",
            elapsed_ms=0,
            attempts=[
                Attempt(
                    tier="patchright",
                    success=False,
                    error="low-value URL skip",
                    error_type=ErrorType.SOFT_BLOCK,
                )
            ],
        )

    if not _ensure_patchright_browser():
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error="patchright chromium browser not installed and auto-install failed",
            tier="patchright",
            elapsed_ms=0,
        )

    start_time = time.time()
    tier_name = "patchright"
    host = urlparse(url).netloc or "unknown"
    attempts: list[Attempt] = []

    # Attempt 1: headless
    attempt_start = time.time()
    try:
        html, body_text, status = _run_patchright(
            url, timeout=min(timeout, 45.0), headless=True, host=host
        )
    except Exception as e:
        html, body_text, status = None, None, None
        attempts.append(
            Attempt(
                tier=f"{tier_name}:headless",
                success=False,
                error=str(e)[:200],
                error_type=ErrorType.NETWORK_ERROR,
                elapsed_ms=(time.time() - attempt_start) * 1000,
            )
        )

    cleared_headless = (
        html is not None
        and status in (200, 304)
        and not _looks_like_challenge_shell(html)
        and (body_text or "").strip()
        and len(body_text or "") > 200
    )

    if cleared_headless:
        attempts.append(
            Attempt(
                tier=f"{tier_name}:headless",
                success=True,
                http_status=status,
                elapsed_ms=(time.time() - attempt_start) * 1000,
            )
        )
        return ScrapeResult(
            url=url,
            success=True,
            raw_content=(html or "").encode("utf-8", errors="ignore"),
            extracted_text=body_text,
            tier=tier_name,
            http_status=status,
            content_type="text/html",
            elapsed_ms=(time.time() - start_time) * 1000,
            attempts=attempts,
        )

    attempts.append(
        Attempt(
            tier=f"{tier_name}:headless",
            success=False,
            error="headless returned challenge shell or empty body",
            error_type=ErrorType.SOFT_BLOCK,
            http_status=status,
            elapsed_ms=(time.time() - attempt_start) * 1000,
        )
    )

    # Attempt 2: headed with user notice. Gated by:
    #   1. PRIMR_ALLOW_HEADED_FALLBACK env (0/false/no disables entirely)
    #   2. A global per-run budget (default 0, shared with the orchestrator's
    #      adaptive retry). Opt in per-run with PRIMR_MAX_HEADED_POPUPS=N if
    #      you want the visible-browser path to be available. On Linux with
    #      no DISPLAY the budget reports 0, so headless servers skip this
    #      path entirely.
    if os.getenv("PRIMR_ALLOW_HEADED_FALLBACK", "1").lower() in ("0", "false", "no"):
        logger.info("Headed fallback disabled via PRIMR_ALLOW_HEADED_FALLBACK=0")
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.SOFT_BLOCK,
            error="Stealth headless blocked; headed fallback disabled",
            tier=tier_name,
            elapsed_ms=(time.time() - start_time) * 1000,
            attempts=attempts,
        )

    if not try_consume_headed_budget():
        attempts.append(
            Attempt(
                tier=f"{tier_name}:headed",
                success=False,
                error="headed-popup budget exhausted (PRIMR_MAX_HEADED_POPUPS)",
                error_type=ErrorType.SOFT_BLOCK,
            )
        )
        logger.info(
            "Skipping headed Patchright for %s — popup budget exhausted for this run",
            host,
        )
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.SOFT_BLOCK,
            error="Headed popup budget exhausted for this run",
            tier=tier_name,
            elapsed_ms=(time.time() - start_time) * 1000,
            attempts=attempts,
        )

    try:
        from primr.utils.console import console

        remaining = remaining_headed_budget()
        console.warn(
            f"Headless stealth blocked — opening visible browser briefly "
            f"({remaining} popup{'s' if remaining != 1 else ''} remaining this run)"
        )
    except Exception:
        logger.info("Headless blocked — falling back to headed Patchright")

    attempt_start = time.time()
    try:
        html, body_text, status = _run_patchright(url, timeout=timeout, headless=False, host=host)
    except Exception as e:
        attempts.append(
            Attempt(
                tier=f"{tier_name}:headed",
                success=False,
                error=str(e)[:200],
                error_type=ErrorType.NETWORK_ERROR,
                elapsed_ms=(time.time() - attempt_start) * 1000,
            )
        )
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Headed Patchright failed: {e}",
            tier=tier_name,
            elapsed_ms=(time.time() - start_time) * 1000,
            attempts=attempts,
        )

    cleared_headed = (
        html is not None
        and status in (200, 304)
        and not _looks_like_challenge_shell(html)
        and (body_text or "").strip()
        and len(body_text or "") > 200
    )

    if cleared_headed:
        attempts.append(
            Attempt(
                tier=f"{tier_name}:headed",
                success=True,
                http_status=status,
                elapsed_ms=(time.time() - attempt_start) * 1000,
            )
        )
        return ScrapeResult(
            url=url,
            success=True,
            raw_content=(html or "").encode("utf-8", errors="ignore"),
            extracted_text=body_text,
            tier=tier_name,
            http_status=status,
            content_type="text/html",
            elapsed_ms=(time.time() - start_time) * 1000,
            attempts=attempts,
        )

    attempts.append(
        Attempt(
            tier=f"{tier_name}:headed",
            success=False,
            error="headed returned challenge shell or empty body",
            error_type=ErrorType.SOFT_BLOCK,
            http_status=status,
            elapsed_ms=(time.time() - attempt_start) * 1000,
        )
    )
    return ScrapeResult(
        url=url,
        success=False,
        error_type=ErrorType.SOFT_BLOCK,
        error="Both headless and headed Patchright returned challenge shells",
        tier=tier_name,
        elapsed_ms=(time.time() - start_time) * 1000,
        attempts=attempts,
    )
