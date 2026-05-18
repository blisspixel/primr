"""
Browser automation with BrowserSession abstraction.

Provides browser-based scraping tiers for sites that require JavaScript
rendering or challenge solving.
"""

import contextlib
import logging
import os
import platform
import threading
import time
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from .config import (
    DEFAULT_TIMEOUT_DRISSION,
    DEFAULT_TIMEOUT_DRISSION_STEALTH,
    DEFAULT_TIMEOUT_PLAYWRIGHT,
    DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE,
    DEFAULT_TIMEOUT_VISION,
    PLAYWRIGHT_LAZY_SCROLL_MAX_STEPS,
    PLAYWRIGHT_LAZY_SCROLL_PAUSE_MS,
    PLAYWRIGHT_LAZY_SCROLL_SETTLE_ROUNDS,
)
from .models import Attempt, ErrorType, ScrapeResult
from .net import extract_host
from .profiles import (
    BrowserContextProfile,
    get_browser_compatible_http_profile,
    get_random_context_profile,
    get_stealth_script,
)

logger = logging.getLogger(__name__)


def _can_use_shared_browser() -> bool:
    """Allow shared Playwright only where thread affinity is safe."""
    enabled = os.getenv("PRIMR_PLAYWRIGHT_SHARED_BROWSER", "1").lower() in {"1", "true", "yes"}
    return enabled and threading.current_thread() is threading.main_thread()


def _browser_session_mode() -> str:
    """Return configured Playwright session mode."""
    mode = os.getenv("PRIMR_BROWSER_SESSION_MODE", "persistent").strip().lower()
    return mode if mode in {"isolated", "persistent"} else "persistent"


def _use_persistent_browser_context() -> bool:
    """Whether Playwright should reuse a context per host for the current run."""
    return _browser_session_mode() == "persistent"


def _resolve_headless(headless: bool | None) -> bool:
    """Allow CLI/env to force a headed browser for scrape recovery."""
    if os.getenv("PRIMR_BROWSER_HEADED", "").strip().lower() in {"1", "true", "yes"}:
        return False
    return True if headless is None else headless


# =============================================================================
# Shared Browser Launch Args
# =============================================================================

_SANDBOX_OPT_OUT = os.getenv("PRIMR_DISABLE_CHROMIUM_SANDBOX", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

# Primr renders arbitrary third-party company websites — i.e. attacker-
# controlled JavaScript. The Chromium sandbox is the primary containment
# boundary for renderer compromise, so the previous unconditional
# --no-sandbox / --disable-setuid-sandbox flags removed our last line of
# defense and were a regression. Sandbox is now ON by default and only
# disabled when an operator explicitly opts in via
# PRIMR_DISABLE_CHROMIUM_SANDBOX=1 (containers that genuinely cannot run
# the SUID sandbox should set it knowingly, not by default).
_SANDBOX_ARGS = (
    ["--no-sandbox", "--disable-setuid-sandbox"] if _SANDBOX_OPT_OUT else []
)

BROWSER_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-http2",
    *_SANDBOX_ARGS,
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-background-networking",
    "--disable-breakpad",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-sync",
    "--force-color-profile=srgb",
    "--metrics-recording-only",
    "--no-first-run",
    "--password-store=basic",
    "--use-mock-keychain",
    "--export-tagged-pdf",
]


# =============================================================================
# Shared Browser Singleton
# =============================================================================


class SharedBrowser:
    """Shared Playwright browser instance for sequential scraping.

    Creates one Chromium process and reuses it across pages.
    Each page gets its own browser context (cheap, ~50ms) for isolation.
    Safe because scraping is single-threaded and sequential.
    """

    _instance: "SharedBrowser | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._browser_headless = None
        self._contexts = {}

    @classmethod
    def get(cls) -> "SharedBrowser":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = SharedBrowser()
        return cls._instance

    def get_browser(self, headless: bool = True):
        """Get or create the shared Chromium browser. Lazy init on first call."""
        headless = _resolve_headless(headless)
        # Crash recovery: if browser died, restart
        if self._browser and not self._browser.is_connected():
            logger.info("Shared browser disconnected, restarting...")
            self._cleanup_internal()

        if self._browser is not None and self._browser_headless != headless:
            logger.info("Shared browser headless mode changed, restarting...")
            self._cleanup_internal()

        if self._browser is None:
            from playwright.sync_api import sync_playwright

            pw = sync_playwright().start()
            try:
                browser = pw.chromium.launch(
                    headless=headless,
                    args=BROWSER_LAUNCH_ARGS,
                )
            except Exception:
                # Don't leak playwright if browser launch fails
                with contextlib.suppress(Exception):
                    pw.stop()
                raise
            self._playwright = pw
            self._browser = browser
            self._browser_headless = headless
            logger.info("Shared Playwright browser started")

        return self._browser

    def get_context(
        self,
        host: str,
        *,
        headless: bool = True,
        viewport: dict,
        locale: str,
        timezone_id: str,
        user_agent: str,
        accept_language: str,
        stealth_script: str | None = None,
    ):
        """Get or create a persistent browser context for a host."""
        browser = self.get_browser(headless=headless)
        key = (host.lower(), self._browser_headless)
        context = self._contexts.get(key)
        if context is not None:
            return context

        # bypass_csp/ignore_https_errors deliberately omitted: scraping
        # third-party sites should respect CSP and TLS validation. Bypassing
        # them weakens defense-in-depth against hostile XSS/MITM during
        # content extraction.
        context = browser.new_context(
            viewport=viewport,
            locale=locale,
            timezone_id=timezone_id,
            user_agent=user_agent,
            java_script_enabled=True,
            extra_http_headers={"Accept-Language": accept_language},
        )
        if stealth_script:
            context.add_init_script(stealth_script)
        self._contexts[key] = context
        logger.info("Shared Playwright context started for %s", host)
        return context

    def _cleanup_internal(self):
        for context in self._contexts.values():
            with contextlib.suppress(Exception):
                context.close()
        self._contexts = {}
        if self._browser:
            with contextlib.suppress(Exception):
                self._browser.close()
            self._browser = None
            self._browser_headless = None
        if self._playwright:
            with contextlib.suppress(Exception):
                self._playwright.stop()
            self._playwright = None

    def close(self):
        """Shut down the shared browser."""
        with self._lock:
            self._cleanup_internal()
            SharedBrowser._instance = None
            logger.info("Shared Playwright browser closed")


# =============================================================================
# Safe Click Patterns and Denylist
# =============================================================================

# Elements safe to click for content expansion
EXPAND_PATTERNS = [
    "read more",
    "show more",
    "view more",
    "see more",
    "expand",
    "load more",
    "continue reading",
    "full article",
    "show all",
    "view all",
]

# Elements to NEVER click (navigation, external links, etc.)
CLICK_DENYLIST = [
    "login",
    "sign in",
    "sign up",
    "register",
    "subscribe",
    "buy",
    "purchase",
    "add to cart",
    "checkout",
    "download",
    "share",
    "tweet",
    "facebook",
    "linkedin",
    "instagram",
    "youtube",
    "contact",
    "support",
    "help",
    "faq",
    "privacy",
    "terms",
    "cookie",
    "settings",
    "preferences",
    "account",
    "profile",
    "logout",
    "sign out",
]

# Consent banner dismiss patterns
CONSENT_DISMISS_PATTERNS = [
    "accept",
    "accept all",
    "agree",
    "i agree",
    "ok",
    "got it",
    "continue",
    "close",
    "dismiss",
    "reject all",
    "decline",
]


# =============================================================================
# BrowserSession Abstraction
# =============================================================================


class BrowserSession(ABC):
    """
    Abstract browser session interface.

    Provides unified interface for Playwright and DrissionPage.
    Enables testing with fake implementations.
    """

    @abstractmethod
    def navigate(self, url: str, timeout_ms: int = 30000) -> bool:
        """Navigate to URL. Returns True on success."""

    @abstractmethod
    def wait_for_clearance(self, max_wait_seconds: int = 30) -> bool:
        """Wait for challenge to clear. Returns True if cleared."""

    @abstractmethod
    def dismiss_consent(self) -> bool:
        """Try to dismiss cookie consent banner. Returns True if dismissed."""

    @abstractmethod
    def expand_content(self, max_clicks: int = 20) -> int:
        """
        Click "read more" type elements to expand content.

        Args:
            max_clicks: Maximum number of clicks (budget)

        Returns:
            Number of successful expansions
        """

    @abstractmethod
    def get_page_html(self) -> str:
        """Get current page HTML."""

    @abstractmethod
    def get_cookies(self) -> dict:
        """Get cookies as dict."""

    @abstractmethod
    def get_current_url(self) -> str:
        """Get current URL (after redirects)."""

    @abstractmethod
    def close(self) -> None:
        """Close the browser session."""

    def _is_safe_to_click(self, element_text: str) -> bool:
        """Check if element is safe to click."""
        text_lower = element_text.lower().strip()

        # Check denylist first
        for denied in CLICK_DENYLIST:
            if denied in text_lower:
                return False

        # Check if matches expand pattern
        return any(pattern in text_lower for pattern in EXPAND_PATTERNS)

    def _url_domain_unchanged(self, original_url: str, current_url: str) -> bool:
        """Check if we're still on the same domain."""
        original_host = urlparse(original_url).netloc.lower()
        current_host = urlparse(current_url).netloc.lower()
        return original_host == current_host


# =============================================================================
# Fake Sessions for Testing
# =============================================================================


class FakeBrowserSession(BrowserSession):
    """Fake browser session for testing."""

    def __init__(
        self,
        html: str = "<html><body>Test</body></html>",
        cookies: dict | None = None,
        challenge_clears: bool = True,
        consent_dismisses: bool = True,
    ):
        self.html = html
        self._cookies = cookies or {}
        self._challenge_clears = challenge_clears
        self._consent_dismisses = consent_dismisses
        self._current_url = "https://example.com"
        self._navigate_count = 0
        self._expand_count = 0
        self._closed = False

    def navigate(self, url: str, timeout_ms: int = 30000) -> bool:
        self._current_url = url
        self._navigate_count += 1
        return True

    def wait_for_clearance(self, max_wait_seconds: int = 30) -> bool:
        return self._challenge_clears

    def dismiss_consent(self) -> bool:
        return self._consent_dismisses

    def expand_content(self, max_clicks: int = 20) -> int:
        # Simulate some expansions
        expansions = min(3, max_clicks)
        self._expand_count += expansions
        return expansions

    def get_page_html(self) -> str:
        return self.html

    def get_cookies(self) -> dict:
        return self._cookies

    def get_current_url(self) -> str:
        return self._current_url

    def close(self) -> None:
        self._closed = True


# =============================================================================
# Playwright Session Implementation
# =============================================================================


class PlaywrightSession(BrowserSession):
    """Browser session using Playwright."""

    def __init__(
        self,
        profile: BrowserContextProfile | None = None,
        headless: bool | None = True,
        reusable: bool = False,
        persistent_context: bool | None = None,
        context_host: str | None = None,
    ):
        self._profile = profile or get_random_context_profile()
        self._headless = _resolve_headless(headless)
        self._reusable = reusable
        self._persistent_context = (
            _use_persistent_browser_context() if persistent_context is None else persistent_context
        )
        self._context_host = context_host
        self._browser = None
        self._context = None
        self._page = None
        self._original_url = None
        self._closed = False
        self._consent_dismissed = False  # Track if we've dismissed consent for this session

        self._setup_browser()

    def _setup_browser(self) -> None:
        """Initialize Playwright browser."""
        try:
            self._owns_browser = False
            self._playwright = None

            # Playwright sync API objects are thread-affine.
            # In worker threads, use an isolated browser instance per session.
            if _can_use_shared_browser():
                shared = SharedBrowser.get()
                self._browser = shared.get_browser(headless=self._headless)
            else:
                from playwright.sync_api import sync_playwright

                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(
                    headless=self._headless,
                    args=BROWSER_LAUNCH_ARGS,
                )
                self._owns_browser = True

            http_profile = get_browser_compatible_http_profile(
                browser_version=getattr(self._browser, "version", None),
                platform_name=platform.system(),
            )

            # Apply stealth patches
            stealth_script = get_stealth_script(
                user_agent=http_profile.user_agent,
                platform_name=platform.system(),
            )

            if self._persistent_context and _can_use_shared_browser() and self._context_host:
                shared = SharedBrowser.get()
                self._context = shared.get_context(
                    self._context_host,
                    headless=self._headless,
                    viewport={
                        "width": self._profile.viewport_width,
                        "height": self._profile.viewport_height,
                    },
                    locale=self._profile.locale,
                    timezone_id=self._profile.timezone,
                    user_agent=http_profile.user_agent,
                    accept_language=http_profile.accept_language,
                    stealth_script=stealth_script,
                )
            else:
                # Create context with profile settings. bypass_csp /
                # ignore_https_errors removed: see _SANDBOX_OPT_OUT comment
                # — Primr scrapes untrusted sites and should not weaken
                # CSP or TLS validation by default.
                self._context = self._browser.new_context(
                    viewport={
                        "width": self._profile.viewport_width,
                        "height": self._profile.viewport_height,
                    },
                    locale=self._profile.locale,
                    timezone_id=self._profile.timezone,
                    user_agent=http_profile.user_agent,
                    java_script_enabled=True,
                    extra_http_headers={"Accept-Language": http_profile.accept_language},
                )
                if stealth_script:
                    self._context.add_init_script(stealth_script)

            self._page = self._context.new_page()

        except ImportError as e:
            raise ImportError("playwright not installed") from e
        except Exception as e:
            logger.error(f"Failed to setup Playwright: {e}")
            raise

    def navigate(self, url: str, timeout_ms: int = 30000) -> bool:
        """Navigate to URL."""
        try:
            self._original_url = url
            self._page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            return True
        except Exception as e:
            # Debug level - navigation failures are expected, tier escalation handles them
            logger.debug(f"Navigation timeout (expected): {e}")
            return False

    def wait_for_clearance(self, max_wait_seconds: int = 30) -> bool:
        """Wait for Cloudflare/challenge to clear."""
        try:
            # Wait for challenge indicators to disappear
            challenge_selectors = [
                "#challenge-running",
                "#cf-challenge-running",
                ".cf-browser-verification",
                "[data-ray]",
            ]

            start = time.time()
            while time.time() - start < max_wait_seconds:
                # Check if any challenge element is visible
                challenge_visible = False
                for selector in challenge_selectors:
                    try:
                        element = self._page.query_selector(selector)
                        if element and element.is_visible():
                            challenge_visible = True
                            break
                    except Exception:
                        logger.debug(
                            "Challenge selector check failed for %s", selector, exc_info=True
                        )

                if not challenge_visible:
                    # Also check page title
                    title = self._page.title().lower()
                    if "just a moment" not in title and "checking" not in title:
                        return True

                time.sleep(1)

            return False

        except Exception as e:
            logger.debug(f"Error waiting for clearance: {e}")
            return False

    def dismiss_consent(self) -> bool:
        """Try to dismiss cookie consent banner."""
        try:
            for pattern in CONSENT_DISMISS_PATTERNS:
                # Try button with text
                try:
                    button = self._page.get_by_role("button", name=pattern)
                    if button.count() > 0:
                        button.first.click(timeout=2000)
                        time.sleep(0.5)
                        return True
                except Exception:
                    logger.debug(
                        "Consent button click failed for pattern %s", pattern, exc_info=True
                    )

                # Try link with text
                try:
                    link = self._page.get_by_role("link", name=pattern)
                    if link.count() > 0:
                        link.first.click(timeout=2000)
                        time.sleep(0.5)
                        return True
                except Exception:
                    logger.debug("Consent link click failed for pattern %s", pattern, exc_info=True)

            return False

        except Exception as e:
            logger.debug(f"Consent dismiss failed: {e}")
            return False

    def expand_content(self, max_clicks: int = 20) -> int:
        """Click expand buttons to reveal more content."""
        expansions = 0

        try:
            initial_text_length = len(self._page.inner_text("body"))

            for _ in range(max_clicks):
                # Find clickable elements with expand patterns
                clicked = False

                for pattern in EXPAND_PATTERNS:
                    try:
                        # Try buttons
                        buttons = self._page.get_by_role("button", name=pattern)
                        if buttons.count() > 0:
                            btn = buttons.first
                            if btn.is_visible() and self._is_safe_to_click(pattern):
                                btn.click(timeout=2000)
                                time.sleep(0.5)

                                # Check if still on same domain
                                if not self._url_domain_unchanged(
                                    self._original_url, self._page.url
                                ):
                                    self._page.go_back()
                                    continue

                                # Check if text increased
                                new_length = len(self._page.inner_text("body"))
                                if new_length > initial_text_length:
                                    expansions += 1
                                    initial_text_length = new_length
                                    clicked = True
                                    break
                    except Exception:
                        logger.debug(
                            "Expand button click failed for pattern %s", pattern, exc_info=True
                        )

                    try:
                        # Try links
                        links = self._page.get_by_role("link", name=pattern)
                        if links.count() > 0:
                            link = links.first
                            if link.is_visible() and self._is_safe_to_click(pattern):
                                link.click(timeout=2000)
                                time.sleep(0.5)

                                if not self._url_domain_unchanged(
                                    self._original_url, self._page.url
                                ):
                                    self._page.go_back()
                                    continue

                                new_length = len(self._page.inner_text("body"))
                                if new_length > initial_text_length:
                                    expansions += 1
                                    initial_text_length = new_length
                                    clicked = True
                                    break
                    except Exception:
                        logger.debug(
                            "Expand link click failed for pattern %s", pattern, exc_info=True
                        )

                if not clicked:
                    break  # No more expandable elements

        except Exception as e:
            logger.debug(f"Content expansion error: {e}")

        return expansions

    def get_page_html(self) -> str:
        """Get current page HTML."""
        try:
            return self._page.content()
        except Exception as e:
            logger.debug("Failed to get page HTML: %s", e)
            return ""

    def get_cookies(self) -> dict:
        """Get cookies as dict."""
        try:
            cookies = self._context.cookies()
            return {c["name"]: c["value"] for c in cookies}
        except Exception as e:
            logger.debug("Failed to get cookies: %s", e)
            return {}

    def get_current_url(self) -> str:
        """Get current URL."""
        try:
            return self._page.url
        except Exception as e:
            logger.debug("Failed to get current URL: %s", e)
            return self._original_url or ""

    def close(self) -> None:
        """Close page and context. Browser stays alive in SharedBrowser for reuse."""
        self._closed = True
        try:
            if self._page:
                self._page.close()
            if self._context and not self._persistent_context:
                self._context.close()
            if getattr(self, "_owns_browser", False):
                if self._browser:
                    self._browser.close()
                if hasattr(self, "_playwright") and self._playwright:
                    self._playwright.stop()
        except Exception as e:
            logger.debug(f"Error closing browser: {e}")


# =============================================================================
# DrissionPage Session Implementation
# =============================================================================


class DrissionPageSession(BrowserSession):
    """Browser session using DrissionPage (CDP-based, driverless)."""

    def __init__(
        self,
        profile: BrowserContextProfile | None = None,
        headless: bool = True,
    ):
        self._profile = profile or get_random_context_profile()
        self._headless = headless
        self._page = None
        self._original_url = None

        self._setup_browser()

    def _setup_browser(self) -> None:
        """Initialize DrissionPage browser."""
        try:
            from DrissionPage import ChromiumOptions, ChromiumPage

            options = ChromiumOptions()
            if self._headless:
                options.headless()

            # Set viewport
            options.set_argument(
                f"--window-size={self._profile.viewport_width},{self._profile.viewport_height}"
            )

            # Set timezone
            if self._profile.timezone:
                options.set_argument(f"--timezone={self._profile.timezone}")

            self._page = ChromiumPage(options)

            # Apply stealth patches via CDP
            stealth_script = get_stealth_script()
            if stealth_script:
                with contextlib.suppress(Exception):
                    self._page.run_cdp(
                        "Page.addScriptToEvaluateOnNewDocument", source=stealth_script
                    )

        except ImportError as e:
            raise ImportError("DrissionPage not installed") from e
        except Exception as e:
            logger.error(f"Failed to setup DrissionPage: {e}")
            raise

    def navigate(self, url: str, timeout_ms: int = 30000) -> bool:
        """Navigate to URL."""
        try:
            self._original_url = url
            self._page.get(url, timeout=timeout_ms / 1000)
            return True
        except Exception as e:
            # Debug level - navigation failures are expected, tier escalation handles them
            logger.debug(f"Navigation timeout (expected): {e}")
            return False

    def wait_for_clearance(self, max_wait_seconds: int = 30) -> bool:
        """Wait for challenge to clear with explicit detection loop."""
        try:
            start = time.time()

            while time.time() - start < max_wait_seconds:
                # Check page content for challenge indicators
                html = self._page.html.lower() if self._page.html else ""
                title = self._page.title.lower() if self._page.title else ""

                challenge_indicators = [
                    "just a moment",
                    "checking your browser",
                    "please wait",
                    "cf-browser-verification",
                    "challenge-running",
                ]

                is_challenge = any(ind in html or ind in title for ind in challenge_indicators)

                if not is_challenge:
                    return True

                time.sleep(1)

            return False

        except Exception as e:
            logger.debug(f"Error waiting for clearance: {e}")
            return False

    def dismiss_consent(self) -> bool:
        """Try to dismiss cookie consent banner."""
        try:
            for pattern in CONSENT_DISMISS_PATTERNS:
                # Try to find and click button/link with pattern
                try:
                    elements = self._page.eles(
                        f"xpath://*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern}')]"
                    )
                    for elem in elements[:3]:  # Try first 3 matches
                        if elem.is_displayed():
                            elem.click()
                            time.sleep(0.5)
                            return True
                except Exception:
                    logger.debug(
                        "DrissionPage consent click failed for pattern %s", pattern, exc_info=True
                    )

            return False

        except Exception as e:
            logger.debug(f"Consent dismiss failed: {e}")
            return False

    def expand_content(self, max_clicks: int = 20) -> int:
        """Click expand buttons to reveal more content."""
        expansions = 0

        try:
            initial_text_length = len(self._page.html or "")

            for _ in range(max_clicks):
                clicked = False

                for pattern in EXPAND_PATTERNS:
                    if not self._is_safe_to_click(pattern):
                        continue

                    try:
                        elements = self._page.eles(
                            f"xpath://*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern}')]"
                        )
                        for elem in elements[:2]:
                            if elem.is_displayed():
                                elem.click()
                                time.sleep(0.5)

                                # Check domain
                                if not self._url_domain_unchanged(
                                    self._original_url, self._page.url
                                ):
                                    self._page.back()
                                    continue

                                # Check text increase
                                new_length = len(self._page.html or "")
                                if new_length > initial_text_length:
                                    expansions += 1
                                    initial_text_length = new_length
                                    clicked = True
                                    break
                    except Exception:
                        logger.debug(
                            "DrissionPage expand click failed for pattern %s",
                            pattern,
                            exc_info=True,
                        )

                    if clicked:
                        break

                if not clicked:
                    break

        except Exception as e:
            logger.debug(f"Content expansion error: {e}")

        return expansions

    def get_page_html(self) -> str:
        """Get current page HTML."""
        try:
            return self._page.html or ""
        except Exception as e:
            logger.debug("DrissionPage: failed to get HTML: %s", e)
            return ""

    def get_cookies(self) -> dict:
        """Get cookies as dict."""
        try:
            cookies = self._page.cookies()
            return {c["name"]: c["value"] for c in cookies}
        except Exception as e:
            logger.debug("DrissionPage: failed to get cookies: %s", e)
            return {}

    def get_current_url(self) -> str:
        """Get current URL."""
        try:
            return self._page.url or self._original_url or ""
        except Exception as e:
            logger.debug("DrissionPage: failed to get current URL: %s", e)
            return self._original_url or ""

    def close(self) -> None:
        """Close browser."""
        try:
            if self._page:
                self._page.quit()
        except Exception as e:
            logger.debug(f"Error closing browser: {e}")


# =============================================================================
# Scrape Functions (Tier Entry Points)
# =============================================================================


def scrape_with_playwright(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_PLAYWRIGHT,
    profile: BrowserContextProfile | None = None,
    headless: bool | None = True,
    reuse_browser: bool = False,  # Ignored - always creates fresh instance
) -> ScrapeResult:
    """
    Scrape URL using Playwright browser.

    Tier 1: Full browser automation for JavaScript-heavy sites.
    Creates a fresh browser instance for each call to avoid greenlet conflicts.

    Args:
        url: URL to scrape
        timeout: Timeout in seconds
        profile: Optional browser context profile
        headless: Run browser in headless mode
        reuse_browser: Ignored (kept for API compatibility)

    Returns:
        ScrapeResult with raw HTML bytes
    """
    from primr.utils.validators import validate_url_for_request

    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {error}",
            tier="playwright",
            elapsed_ms=0,
            attempts=[],
        )

    url = normalized_url
    return _scrape_with_playwright_impl(url, timeout, profile, headless)


def _trigger_lazy_load(page, steps: int | None = None, pause_ms: int | None = None) -> None:
    """Adaptive scroll to trigger lazy-loaded blocks before HTML capture."""
    max_steps = max(1, steps or PLAYWRIGHT_LAZY_SCROLL_MAX_STEPS)
    wait_ms = max(100, pause_ms or PLAYWRIGHT_LAZY_SCROLL_PAUSE_MS)
    settle_rounds = max(1, PLAYWRIGHT_LAZY_SCROLL_SETTLE_ROUNDS)
    try:
        stable_count = 0
        previous_height = 0
        for _ in range(max_steps):
            page.evaluate(
                "window.scrollBy(0, Math.max(300, Math.floor(window.innerHeight * 0.9)));"
            )
            page.wait_for_timeout(wait_ms)
            height = int(page.evaluate("document.body.scrollHeight || 0") or 0)
            if height <= previous_height:
                stable_count += 1
                if stable_count >= settle_rounds:
                    break
            else:
                stable_count = 0
            previous_height = height
        # Nudge near top to keep sticky sections in DOM snapshots consistently.
        page.evaluate("window.scrollTo(0, Math.min(200, document.body.scrollHeight));")
        page.wait_for_timeout(120)
    except Exception:
        # Non-fatal: some pages block scripted scroll.
        pass


def _scrape_with_playwright_impl(
    url: str,
    timeout: float,
    profile: BrowserContextProfile | None,
    headless: bool | None,
) -> ScrapeResult:
    """Internal implementation of Playwright scraping - uses shared browser."""
    start_time = time.time()
    tier_name = "playwright"
    host = extract_host(url)
    headless = _resolve_headless(headless)
    browser = None
    context = None
    page = None
    _using_shared = False
    _using_persistent_context = False
    _fresh_pw = None  # Only set if we fall back to a fresh browser

    try:
        from .profiles import get_stealth_script

        # Playwright sync API objects are thread-affine.
        # Reuse shared browser only on main thread; workers use isolated instances.
        try:
            if _can_use_shared_browser():
                shared = SharedBrowser.get()
                browser = shared.get_browser(headless=headless)
                _using_shared = True
            else:
                from playwright.sync_api import sync_playwright

                _fresh_pw = sync_playwright().start()
                browser = _fresh_pw.chromium.launch(
                    headless=headless,
                    args=BROWSER_LAUNCH_ARGS,
                )
                _using_shared = False
        except ImportError:
            raise  # Playwright not installed — let outer handler catch it
        except Exception:
            logger.debug("SharedBrowser unavailable, launching fresh browser")
            from playwright.sync_api import sync_playwright

            _fresh_pw = sync_playwright().start()
            browser = _fresh_pw.chromium.launch(
                headless=headless,
                args=BROWSER_LAUNCH_ARGS,
            )

        http_profile = get_browser_compatible_http_profile(
            browser_version=getattr(browser, "version", None),
            platform_name=platform.system(),
        )
        ctx_profile = profile or get_random_context_profile()

        stealth_script = get_stealth_script(
            user_agent=http_profile.user_agent,
            platform_name=platform.system(),
        )

        if _using_shared and _use_persistent_browser_context():
            shared = SharedBrowser.get()
            context = shared.get_context(
                host,
                headless=headless,
                viewport={
                    "width": ctx_profile.viewport_width,
                    "height": ctx_profile.viewport_height,
                },
                locale=ctx_profile.locale,
                timezone_id=ctx_profile.timezone,
                user_agent=http_profile.user_agent,
                accept_language=http_profile.accept_language,
                stealth_script=stealth_script,
            )
            _using_persistent_context = True
        else:
            # bypass_csp / ignore_https_errors deliberately not set —
            # see _SANDBOX_OPT_OUT comment at the top of the module.
            context = browser.new_context(
                viewport={
                    "width": ctx_profile.viewport_width,
                    "height": ctx_profile.viewport_height,
                },
                locale=ctx_profile.locale,
                timezone_id=ctx_profile.timezone,
                user_agent=http_profile.user_agent,
                java_script_enabled=True,
                extra_http_headers={"Accept-Language": http_profile.accept_language},
            )
            if stealth_script:
                context.add_init_script(stealth_script)

        page = context.new_page()

        # Navigate
        timeout_ms = int(timeout * 1000)
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

        # Wait for JS frameworks (React, Vue, Visual Composer) to hydrate.
        # networkidle fires when no network requests for 500ms — ideal for
        # SPA/page-builder sites that fetch data after DOMContentLoaded.
        # Best-effort with whatever time remains in the tier budget (min 2s).
        elapsed_so_far_ms = (time.time() - start_time) * 1000
        idle_budget_ms = max(int(timeout_ms - elapsed_so_far_ms), 2000)
        try:
            page.wait_for_load_state("networkidle", timeout=idle_budget_ms)
        except TimeoutError:
            pass  # Timeout is expected — some sites never reach idle
        except Exception as e:
            logger.debug(
                "Unexpected error waiting for networkidle on %s: %s",
                url if "url" in dir() else "unknown",
                e,
            )

        try:
            page.wait_for_timeout(750)
        except Exception:
            pass

        # Trigger lazy-loaded content for scroll-driven page builders.
        _trigger_lazy_load(page)

        # Get HTML
        html = page.content()
        cookies = {c["name"]: c["value"] for c in context.cookies()}
        final_url = page.url

        # SSRF protection: Validate final URL after redirects
        from primr.utils.security import validate_final_url_after_redirect

        is_safe, ssrf_error = validate_final_url_after_redirect(final_url)
        if not is_safe:
            elapsed_ms = (time.time() - start_time) * 1000
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error=f"Redirect SSRF blocked: {ssrf_error}",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[
                    Attempt(
                        tier=tier_name,
                        success=False,
                        error=f"Redirect SSRF: {ssrf_error}",
                        elapsed_ms=elapsed_ms,
                    )
                ],
            )

        elapsed_ms = (time.time() - start_time) * 1000

        return ScrapeResult(
            url=url,
            success=True,
            raw_content=html.encode("utf-8") if html else b"",
            content_type="text/html",
            http_status=200,
            final_url=final_url,
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            cookies=cookies,
            attempts=[
                Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms, http_status=200)
            ],
        )

    except ImportError:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error="playwright not installed",
            tier=tier_name,
            attempts=[],
        )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        error_str = str(e).lower()

        if "timeout" in error_str:
            error_type = ErrorType.TIMEOUT
        else:
            error_type = ErrorType.NETWORK_ERROR

        return ScrapeResult(
            url=url,
            success=False,
            error_type=error_type,
            error=f"Playwright error: {e}",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[
                Attempt(
                    tier=tier_name,
                    success=False,
                    error=str(e),
                    error_type=error_type,
                    elapsed_ms=elapsed_ms,
                )
            ],
        )

    finally:
        # Always clean up page and context
        if page:
            try:
                page.close()
            except Exception as e:
                logger.debug(f"Error closing page: {e}")
        if context and not _using_persistent_context:
            try:
                context.close()
            except Exception as e:
                logger.debug(f"Error closing context: {e}")
        # Only close browser/playwright if we launched a fresh one
        if not _using_shared:
            if browser:
                try:
                    browser.close()
                except Exception as e:
                    logger.debug(f"Error closing browser: {e}")
            if _fresh_pw:
                try:
                    _fresh_pw.stop()
                except Exception as e:
                    logger.debug(f"Error stopping playwright: {e}")


def scrape_with_playwright_aggressive(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE,
    profile: BrowserContextProfile | None = None,
    headless: bool | None = True,
    max_expand_clicks: int = 20,
) -> ScrapeResult:
    """
    Scrape URL using Playwright with content expansion.

    Tier 5: Aggressive browser automation that clicks "read more" buttons.

    Args:
        url: URL to scrape
        timeout: Timeout in seconds
        profile: Optional browser context profile
        headless: Run browser in headless mode
        max_expand_clicks: Maximum expand button clicks

    Returns:
        ScrapeResult with expanded HTML bytes
    """
    from primr.utils.validators import validate_url_for_request

    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {error}",
            tier="playwright_aggressive",
            elapsed_ms=0,
            attempts=[],
        )

    url = normalized_url
    start_time = time.time()
    tier_name = "playwright_aggressive"
    session = None

    try:
        session = PlaywrightSession(
            profile=profile,
            headless=headless,
            context_host=extract_host(url),
        )

        # Navigate
        timeout_ms = int(timeout * 1000)
        if not session.navigate(url, timeout_ms=timeout_ms):
            elapsed_ms = (time.time() - start_time) * 1000
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error="Navigation failed",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[
                    Attempt(
                        tier=tier_name,
                        success=False,
                        error="Navigation failed",
                        elapsed_ms=elapsed_ms,
                    )
                ],
            )

        # Wait for page to stabilize
        time.sleep(1)

        # Dismiss consent
        session.dismiss_consent()

        # Expand content
        expansions = session.expand_content(max_clicks=max_expand_clicks)
        logger.debug(f"Expanded {expansions} elements")

        # Trigger lazy-loaded blocks that only appear after user scrolling.
        if session._page:
            _trigger_lazy_load(session._page, steps=5, pause_ms=300)

        # Get HTML
        html = session.get_page_html()
        cookies = session.get_cookies()
        final_url = session.get_current_url()

        # SSRF protection: Validate final URL after redirects
        from primr.utils.security import validate_final_url_after_redirect

        is_safe, ssrf_error = validate_final_url_after_redirect(final_url)
        if not is_safe:
            elapsed_ms = (time.time() - start_time) * 1000
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error=f"Redirect SSRF blocked: {ssrf_error}",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[
                    Attempt(
                        tier=tier_name,
                        success=False,
                        error=f"Redirect SSRF: {ssrf_error}",
                        elapsed_ms=elapsed_ms,
                    )
                ],
            )

        elapsed_ms = (time.time() - start_time) * 1000

        return ScrapeResult(
            url=url,
            success=True,
            raw_content=html.encode("utf-8") if html else b"",
            content_type="text/html",
            http_status=200,
            final_url=final_url,
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            cookies=cookies,
            attempts=[
                Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms, http_status=200)
            ],
        )

    except ImportError:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error="playwright not installed",
            tier=tier_name,
            attempts=[],
        )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        error_type = ErrorType.TIMEOUT if "timeout" in str(e).lower() else ErrorType.NETWORK_ERROR

        return ScrapeResult(
            url=url,
            success=False,
            error_type=error_type,
            error=f"Playwright aggressive error: {e}",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[
                Attempt(
                    tier=tier_name,
                    success=False,
                    error=str(e),
                    error_type=error_type,
                    elapsed_ms=elapsed_ms,
                )
            ],
        )

    finally:
        if session:
            with contextlib.suppress(Exception):
                session.close()


def scrape_with_drissionpage(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_DRISSION,
    profile: BrowserContextProfile | None = None,
    headless: bool = True,
) -> ScrapeResult:
    """
    Scrape URL using DrissionPage (CDP-based, driverless).

    Tier 6: Driverless browser automation using Chrome DevTools Protocol.

    Args:
        url: URL to scrape
        timeout: Timeout in seconds
        profile: Optional browser context profile
        headless: Run browser in headless mode

    Returns:
        ScrapeResult with raw HTML bytes
    """
    from primr.utils.validators import validate_url_for_request

    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {error}",
            tier="drissionpage",
            elapsed_ms=0,
            attempts=[],
        )

    url = normalized_url
    start_time = time.time()
    tier_name = "drissionpage"
    session = None

    try:
        session = DrissionPageSession(profile=profile, headless=headless)

        # Navigate
        timeout_ms = int(timeout * 1000)
        if not session.navigate(url, timeout_ms=timeout_ms):
            elapsed_ms = (time.time() - start_time) * 1000
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error="Navigation failed",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[
                    Attempt(
                        tier=tier_name,
                        success=False,
                        error="Navigation failed",
                        elapsed_ms=elapsed_ms,
                    )
                ],
            )

        # Wait for page
        time.sleep(1)

        # Dismiss consent
        session.dismiss_consent()

        # Get HTML
        html = session.get_page_html()
        cookies = session.get_cookies()
        final_url = session.get_current_url()

        # SSRF protection: Validate final URL after redirects
        from primr.utils.security import validate_final_url_after_redirect

        is_safe, ssrf_error = validate_final_url_after_redirect(final_url)
        if not is_safe:
            elapsed_ms = (time.time() - start_time) * 1000
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error=f"Redirect SSRF blocked: {ssrf_error}",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[
                    Attempt(
                        tier=tier_name,
                        success=False,
                        error=f"Redirect SSRF: {ssrf_error}",
                        elapsed_ms=elapsed_ms,
                    )
                ],
            )

        elapsed_ms = (time.time() - start_time) * 1000

        return ScrapeResult(
            url=url,
            success=True,
            raw_content=html.encode("utf-8") if html else b"",
            content_type="text/html",
            http_status=200,
            final_url=final_url,
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            cookies=cookies,
            attempts=[
                Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms, http_status=200)
            ],
        )

    except ImportError:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error="DrissionPage not installed",
            tier=tier_name,
            attempts=[],
        )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        error_type = ErrorType.TIMEOUT if "timeout" in str(e).lower() else ErrorType.NETWORK_ERROR

        return ScrapeResult(
            url=url,
            success=False,
            error_type=error_type,
            error=f"DrissionPage error: {e}",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[
                Attempt(
                    tier=tier_name,
                    success=False,
                    error=str(e),
                    error_type=error_type,
                    elapsed_ms=elapsed_ms,
                )
            ],
        )

    finally:
        if session:
            with contextlib.suppress(Exception):
                session.close()


def scrape_with_drissionpage_stealth(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_DRISSION_STEALTH,
    profile: BrowserContextProfile | None = None,
    headless: bool = True,
    max_challenge_wait: int | None = None,
) -> ScrapeResult:
    """
    Scrape URL using DrissionPage with stealth mode and challenge solving.

    Tier 7: Driverless browser with anti-detection and Cloudflare bypass.

    CRITICAL: DrissionPage has poor timeout handling - its get() method often
    ignores the timeout parameter. We wrap the entire execution in a hard
    timeout using threading to enforce the limit.

    Args:
        url: URL to scrape
        timeout: Timeout in seconds (HARD LIMIT - enforced via threading)
        profile: Optional browser context profile
        headless: Run browser in headless mode
        max_challenge_wait: Max seconds to wait for challenge solving (default: 70% of timeout, max 30s)

    Returns:
        ScrapeResult with raw HTML bytes
    """
    import concurrent.futures

    from primr.utils.validators import validate_url_for_request

    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {error}",
            tier="drissionpage_stealth",
            elapsed_ms=0,
            attempts=[],
        )

    url = normalized_url
    tier_name = "drissionpage_stealth"
    start_time = time.time()

    # Calculate challenge wait time from timeout budget
    # Use 70% of timeout for challenge wait, capped at 30s
    # Example: 20s timeout → 14s challenge wait
    # Example: 60s timeout → 30s challenge wait (capped)
    if max_challenge_wait is None:
        max_challenge_wait = min(int(timeout * 0.7), 30)

    # Define the actual scraping work as a separate function
    def _do_scrape():
        session = None
        try:
            session = DrissionPageSession(profile=profile, headless=headless)

            # Navigate with timeout budget
            timeout_ms = int(timeout * 1000)
            nav_start = time.time()
            if not session.navigate(url, timeout_ms=timeout_ms):
                elapsed_ms = (time.time() - start_time) * 1000
                return ScrapeResult(
                    url=url,
                    success=False,
                    error_type=ErrorType.NETWORK_ERROR,
                    error="Navigation failed",
                    tier=tier_name,
                    elapsed_ms=elapsed_ms,
                    attempts=[
                        Attempt(
                            tier=tier_name,
                            success=False,
                            error="Navigation failed",
                            elapsed_ms=elapsed_ms,
                        )
                    ],
                )

            # Calculate remaining time budget for challenge wait
            nav_elapsed = time.time() - nav_start
            remaining_budget = timeout - nav_elapsed
            effective_challenge_wait = min(max_challenge_wait, int(remaining_budget))

            if effective_challenge_wait <= 0:
                elapsed_ms = (time.time() - start_time) * 1000
                return ScrapeResult(
                    url=url,
                    success=False,
                    error_type=ErrorType.TIMEOUT,
                    error=f"Navigation consumed full timeout budget ({nav_elapsed:.1f}s)",
                    tier=tier_name,
                    elapsed_ms=elapsed_ms,
                    attempts=[
                        Attempt(
                            tier=tier_name,
                            success=False,
                            error="Timeout",
                            error_type=ErrorType.TIMEOUT,
                            elapsed_ms=elapsed_ms,
                        )
                    ],
                )

            # Wait for challenge to clear with remaining budget
            if not session.wait_for_clearance(max_wait_seconds=effective_challenge_wait):
                elapsed_ms = (time.time() - start_time) * 1000
                return ScrapeResult(
                    url=url,
                    success=False,
                    error_type=ErrorType.CHALLENGE,
                    error="Challenge did not clear",
                    tier=tier_name,
                    elapsed_ms=elapsed_ms,
                    attempts=[
                        Attempt(
                            tier=tier_name,
                            success=False,
                            error="Challenge timeout",
                            error_type=ErrorType.CHALLENGE,
                            elapsed_ms=elapsed_ms,
                        )
                    ],
                )

            # Dismiss consent
            session.dismiss_consent()

            # Get HTML
            html = session.get_page_html()
            cookies = session.get_cookies()
            final_url = session.get_current_url()

            # SSRF protection: Validate final URL after redirects
            from primr.utils.security import validate_final_url_after_redirect

            is_safe, ssrf_error = validate_final_url_after_redirect(final_url)
            if not is_safe:
                elapsed_ms = (time.time() - start_time) * 1000
                return ScrapeResult(
                    url=url,
                    success=False,
                    error_type=ErrorType.NETWORK_ERROR,
                    error=f"Redirect SSRF blocked: {ssrf_error}",
                    tier=tier_name,
                    elapsed_ms=elapsed_ms,
                    attempts=[
                        Attempt(
                            tier=tier_name,
                            success=False,
                            error=f"Redirect SSRF: {ssrf_error}",
                            elapsed_ms=elapsed_ms,
                        )
                    ],
                )

            elapsed_ms = (time.time() - start_time) * 1000

            return ScrapeResult(
                url=url,
                success=True,
                raw_content=html.encode("utf-8") if html else b"",
                content_type="text/html",
                http_status=200,
                final_url=final_url,
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                cookies=cookies,
                attempts=[
                    Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms, http_status=200)
                ],
            )

        except ImportError:
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error="DrissionPage not installed",
                tier=tier_name,
                attempts=[],
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            error_type = (
                ErrorType.TIMEOUT if "timeout" in str(e).lower() else ErrorType.NETWORK_ERROR
            )

            return ScrapeResult(
                url=url,
                success=False,
                error_type=error_type,
                error=f"DrissionPage stealth error: {e}",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[
                    Attempt(
                        tier=tier_name,
                        success=False,
                        error=str(e),
                        error_type=error_type,
                        elapsed_ms=elapsed_ms,
                    )
                ],
            )

        finally:
            if session:
                with contextlib.suppress(Exception):
                    session.close()

    # Execute with HARD timeout using ThreadPoolExecutor
    # This ensures we don't wait forever if DrissionPage hangs
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_do_scrape)
        try:
            # Add 2s buffer to timeout for cleanup
            result = future.result(timeout=timeout + 2)
            return result
        except concurrent.futures.TimeoutError:
            # Hard timeout hit - DrissionPage is hanging
            elapsed_ms = (time.time() - start_time) * 1000
            logger.debug(
                f"DrissionPage stealth HARD TIMEOUT after {elapsed_ms / 1000:.1f}s for {url}"
            )
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.TIMEOUT,
                error=f"Hard timeout after {timeout}s (DrissionPage hung)",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[
                    Attempt(
                        tier=tier_name,
                        success=False,
                        error="Hard timeout",
                        error_type=ErrorType.TIMEOUT,
                        elapsed_ms=elapsed_ms,
                    )
                ],
            )


def scrape_with_vision(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_VISION,
) -> ScrapeResult:
    """
    Scrape URL using vision model (screenshot + LLM extraction).

    Tier 6: Vision fallback for image-heavy or heavily protected sites.
    Takes a screenshot and uses Gemini to extract text content.

    This is the nuclear option - costs ~$0.01-0.02 per page but works on
    almost anything that renders in a browser.

    Args:
        url: URL to scrape
        timeout: Timeout in seconds

    Returns:
        ScrapeResult with extracted_text from vision, raw_content=screenshot bytes
    """
    from primr.utils.validators import validate_url_for_request

    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {error}",
            tier="vision",
            elapsed_ms=0,
            attempts=[],
        )

    url = normalized_url
    tier_name = "vision"
    start_time = time.time()

    try:
        import base64

        from google import genai
        from playwright.sync_api import sync_playwright

        from primr.config.settings import get_settings

        settings = get_settings()

        # Check if we have Gemini API key
        if not settings.api.gemini_key:
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error="Vision tier requires GEMINI_API_KEY",
                tier=tier_name,
                attempts=[],
            )

        with sync_playwright() as p:
            # Sandbox stays on unless PRIMR_DISABLE_CHROMIUM_SANDBOX=1
            # is set — see _SANDBOX_OPT_OUT comment at the top of the
            # module. Same rationale as the main scraper: vision tier
            # renders attacker-controlled JS too.
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-http2",
                    *_SANDBOX_ARGS,
                    "--disable-dev-shm-usage",
                ],
            )

            from .profiles import get_stealth_script

            context = browser.new_context(
                viewport={"width": 1280, "height": 1024},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )

            # Apply stealth patches
            stealth_script = get_stealth_script()
            if stealth_script:
                context.add_init_script(stealth_script)
            page = context.new_page()

            # Navigate and wait for content
            page.goto(url, timeout=int(timeout * 1000), wait_until="networkidle")
            page.wait_for_timeout(2000)  # Extra wait for JS rendering

            # SSRF protection: Validate final URL after redirects
            final_url = page.url
            from primr.utils.security import validate_final_url_after_redirect

            is_safe, ssrf_error = validate_final_url_after_redirect(final_url)
            if not is_safe:
                page.close()
                context.close()
                browser.close()
                elapsed_ms = (time.time() - start_time) * 1000
                return ScrapeResult(
                    url=url,
                    success=False,
                    error_type=ErrorType.NETWORK_ERROR,
                    error=f"Redirect SSRF blocked: {ssrf_error}",
                    tier=tier_name,
                    elapsed_ms=elapsed_ms,
                    attempts=[
                        Attempt(
                            tier=tier_name,
                            success=False,
                            error=f"Redirect SSRF: {ssrf_error}",
                            elapsed_ms=elapsed_ms,
                        )
                    ],
                )

            # Scroll to load lazy content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(1000)

            # Take full page screenshot
            screenshot_bytes = page.screenshot(full_page=True, type="png")

            browser.close()

        # Use Gemini to extract text from screenshot
        client = genai.Client(api_key=settings.api.gemini_key)

        # Encode screenshot as base64
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        prompt = """Extract all readable text content from this webpage screenshot.
Focus on:
- Main headings and titles
- Body text and paragraphs
- Key facts, numbers, and statistics
- Product/service descriptions
- Company information

Ignore:
- Navigation menus
- Footer links
- Cookie banners
- Advertisements

Return the extracted text in a clean, readable format with proper paragraph breaks."""

        response = client.models.generate_content(
            model=settings.ai.flash_model,
            contents=[
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": screenshot_b64}},
            ],
        )

        extracted_text = response.text.strip() if response.text else ""
        elapsed_ms = (time.time() - start_time) * 1000

        if not extracted_text or len(extracted_text) < 100:
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.EMPTY_CONTENT,
                error="Vision extraction returned insufficient content",
                tier=tier_name,
                raw_content=screenshot_bytes,
                elapsed_ms=elapsed_ms,
                attempts=[
                    Attempt(
                        tier=tier_name,
                        success=False,
                        error="Insufficient content",
                        elapsed_ms=elapsed_ms,
                    )
                ],
            )

        return ScrapeResult(
            url=url,
            success=True,
            raw_content=screenshot_bytes,
            extracted_text=extracted_text,
            tier=tier_name,
            content_type="vision_text",
            http_status=200,
            elapsed_ms=elapsed_ms,
            attempts=[Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms)],
        )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug(f"Vision tier failed for {url}: {e}")
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=str(e),
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[Attempt(tier=tier_name, success=False, error=str(e), elapsed_ms=elapsed_ms)],
        )


# =============================================================================
# Browser Tiers Registry
# =============================================================================

BROWSER_TIERS = {
    "playwright": scrape_with_playwright,
    "playwright_aggressive": scrape_with_playwright_aggressive,
    "drissionpage": scrape_with_drissionpage,
    "drissionpage_stealth": scrape_with_drissionpage_stealth,
    "vision": scrape_with_vision,
}
