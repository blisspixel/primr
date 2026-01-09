"""
Browser automation with BrowserSession abstraction.

Provides browser-based scraping tiers for sites that require JavaScript
rendering or challenge solving.
"""

import logging
import time
import threading
from abc import ABC, abstractmethod
from typing import Optional, List, Set, Dict
from urllib.parse import urlparse

from .config import (
    DEFAULT_TIMEOUT_PLAYWRIGHT,
    DEFAULT_TIMEOUT_DRISSION,
    DEFAULT_TIMEOUT_DRISSION_STEALTH,
    DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE,
    DEFAULT_TIMEOUT_VISION,
)
from .models import Attempt, ErrorType, ScrapeResult
from .net import extract_host
from .profiles import (
    BrowserContextProfile,
    get_random_context_profile,
    get_stealth_script,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Browser Pool - DISABLED due to greenlet conflicts
# =============================================================================
# 
# NOTE: Browser pooling is disabled because Playwright's sync API uses greenlet
# internally, and greenlet cannot switch between different call contexts.
# This caused "Cannot switch to a different thread" errors.
#
# The performance cost of launching a fresh browser per page (~1-2s) is
# acceptable compared to the complexity of managing greenlet contexts.
# =============================================================================

class BrowserPool:
    """
    DEPRECATED: Browser pool disabled due to greenlet conflicts.
    
    This class is kept for API compatibility but always returns None,
    forcing callers to create fresh browser instances.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_context(self, host: str) -> Optional[tuple]:
        """Always returns None - pool is disabled."""
        return None
    
    def close_all(self) -> None:
        """No-op - pool is disabled."""
        pass


# Global browser pool (disabled)
_browser_pool = None

def get_browser_pool() -> BrowserPool:
    """Get the global browser pool (disabled - always returns fresh instances)."""
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = BrowserPool()
    return _browser_pool


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
        pass
    
    @abstractmethod
    def wait_for_clearance(self, max_wait_seconds: int = 30) -> bool:
        """Wait for challenge to clear. Returns True if cleared."""
        pass
    
    @abstractmethod
    def dismiss_consent(self) -> bool:
        """Try to dismiss cookie consent banner. Returns True if dismissed."""
        pass
    
    @abstractmethod
    def expand_content(self, max_clicks: int = 20) -> int:
        """
        Click "read more" type elements to expand content.
        
        Args:
            max_clicks: Maximum number of clicks (budget)
        
        Returns:
            Number of successful expansions
        """
        pass
    
    @abstractmethod
    def get_page_html(self) -> str:
        """Get current page HTML."""
        pass
    
    @abstractmethod
    def get_cookies(self) -> dict:
        """Get cookies as dict."""
        pass
    
    @abstractmethod
    def get_current_url(self) -> str:
        """Get current URL (after redirects)."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close the browser session."""
        pass
    
    def _is_safe_to_click(self, element_text: str) -> bool:
        """Check if element is safe to click."""
        text_lower = element_text.lower().strip()
        
        # Check denylist first
        for denied in CLICK_DENYLIST:
            if denied in text_lower:
                return False
        
        # Check if matches expand pattern
        for pattern in EXPAND_PATTERNS:
            if pattern in text_lower:
                return True
        
        return False
    
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
        cookies: Optional[dict] = None,
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
        profile: Optional[BrowserContextProfile] = None,
        headless: bool = True,
        reusable: bool = False,
    ):
        self._profile = profile or get_random_context_profile()
        self._headless = headless
        self._reusable = reusable
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
            from playwright.sync_api import sync_playwright
            from .profiles import get_random_http_profile
            
            self._playwright = sync_playwright().start()
            
            # Launch with anti-detection args
            self._browser = self._playwright.chromium.launch(
                headless=self._headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-http2',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ],
            )
            
            # Get a proper Chrome user agent
            http_profile = get_random_http_profile()
            
            # Create context with profile settings
            self._context = self._browser.new_context(
                viewport={
                    "width": self._profile.viewport_width,
                    "height": self._profile.viewport_height,
                },
                locale=self._profile.locale,
                timezone_id=self._profile.timezone,
                user_agent=http_profile.user_agent,
            )
            
            # Apply stealth patches
            stealth_script = get_stealth_script()
            if stealth_script:
                self._context.add_init_script(stealth_script)
            
            self._page = self._context.new_page()
            
        except ImportError:
            raise ImportError("playwright not installed")
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
            logger.warning(f"Navigation failed: {e}")
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
                        pass
                
                if not challenge_visible:
                    # Also check page title
                    title = self._page.title().lower()
                    if "just a moment" not in title and "checking" not in title:
                        return True
                
                time.sleep(1)
            
            return False
            
        except Exception as e:
            logger.warning(f"Error waiting for clearance: {e}")
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
                    pass
                
                # Try link with text
                try:
                    link = self._page.get_by_role("link", name=pattern)
                    if link.count() > 0:
                        link.first.click(timeout=2000)
                        time.sleep(0.5)
                        return True
                except Exception:
                    pass
            
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
                                if not self._url_domain_unchanged(self._original_url, self._page.url):
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
                        pass
                    
                    try:
                        # Try links
                        links = self._page.get_by_role("link", name=pattern)
                        if links.count() > 0:
                            link = links.first
                            if link.is_visible() and self._is_safe_to_click(pattern):
                                link.click(timeout=2000)
                                time.sleep(0.5)
                                
                                if not self._url_domain_unchanged(self._original_url, self._page.url):
                                    self._page.go_back()
                                    continue
                                
                                new_length = len(self._page.inner_text("body"))
                                if new_length > initial_text_length:
                                    expansions += 1
                                    initial_text_length = new_length
                                    clicked = True
                                    break
                    except Exception:
                        pass
                
                if not clicked:
                    break  # No more expandable elements
            
        except Exception as e:
            logger.debug(f"Content expansion error: {e}")
        
        return expansions
    
    def get_page_html(self) -> str:
        """Get current page HTML."""
        try:
            return self._page.content()
        except Exception:
            return ""
    
    def get_cookies(self) -> dict:
        """Get cookies as dict."""
        try:
            cookies = self._context.cookies()
            return {c["name"]: c["value"] for c in cookies}
        except Exception:
            return {}
    
    def get_current_url(self) -> str:
        """Get current URL."""
        try:
            return self._page.url
        except Exception:
            return self._original_url or ""
    
    def close(self) -> None:
        """Close browser."""
        self._closed = True
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if hasattr(self, '_playwright') and self._playwright:
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
        profile: Optional[BrowserContextProfile] = None,
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
            from DrissionPage import ChromiumPage, ChromiumOptions
            
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
                try:
                    self._page.run_cdp("Page.addScriptToEvaluateOnNewDocument", source=stealth_script)
                except Exception:
                    pass
            
        except ImportError:
            raise ImportError("DrissionPage not installed")
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
            logger.warning(f"Navigation failed: {e}")
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
            logger.warning(f"Error waiting for clearance: {e}")
            return False
    
    def dismiss_consent(self) -> bool:
        """Try to dismiss cookie consent banner."""
        try:
            for pattern in CONSENT_DISMISS_PATTERNS:
                # Try to find and click button/link with pattern
                try:
                    elements = self._page.eles(f"xpath://*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern}')]")
                    for elem in elements[:3]:  # Try first 3 matches
                        if elem.is_displayed():
                            elem.click()
                            time.sleep(0.5)
                            return True
                except Exception:
                    pass
            
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
                        elements = self._page.eles(f"xpath://*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern}')]")
                        for elem in elements[:2]:
                            if elem.is_displayed():
                                elem.click()
                                time.sleep(0.5)
                                
                                # Check domain
                                if not self._url_domain_unchanged(self._original_url, self._page.url):
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
                        pass
                    
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
        except Exception:
            return ""
    
    def get_cookies(self) -> dict:
        """Get cookies as dict."""
        try:
            cookies = self._page.cookies()
            return {c["name"]: c["value"] for c in cookies}
        except Exception:
            return {}
    
    def get_current_url(self) -> str:
        """Get current URL."""
        try:
            return self._page.url or self._original_url or ""
        except Exception:
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
    profile: Optional[BrowserContextProfile] = None,
    headless: bool = True,
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
    return _scrape_with_playwright_impl(url, timeout, profile, headless)


def _scrape_with_playwright_impl(
    url: str,
    timeout: float,
    profile: Optional[BrowserContextProfile],
    headless: bool,
) -> ScrapeResult:
    """Internal implementation of Playwright scraping - always creates fresh browser."""
    start_time = time.time()
    tier_name = "playwright"
    host = extract_host(url)
    playwright_instance = None
    browser = None
    context = None
    page = None
    
    try:
        from playwright.sync_api import sync_playwright
        from .profiles import get_random_http_profile, get_stealth_script
        
        playwright_instance = sync_playwright().start()
        
        # Use new headless mode (headless="new") which is harder to detect
        # Falls back to regular headless if not supported
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-http2',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-infobars',
            '--disable-background-networking',
            '--disable-breakpad',
            '--disable-component-update',
            '--disable-domain-reliability',
            '--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process',
            '--disable-hang-monitor',
            '--disable-ipc-flooding-protection',
            '--disable-popup-blocking',
            '--disable-prompt-on-repost',
            '--disable-renderer-backgrounding',
            '--disable-sync',
            '--force-color-profile=srgb',
            '--metrics-recording-only',
            '--no-first-run',
            '--password-store=basic',
            '--use-mock-keychain',
            '--export-tagged-pdf',
        ]
        
        browser = playwright_instance.chromium.launch(
            headless=headless,
            args=launch_args,
        )
        
        http_profile = get_random_http_profile()
        ctx_profile = profile or get_random_context_profile()
        
        context = browser.new_context(
            viewport={
                "width": ctx_profile.viewport_width,
                "height": ctx_profile.viewport_height,
            },
            locale=ctx_profile.locale,
            timezone_id=ctx_profile.timezone,
            user_agent=http_profile.user_agent,
            # Additional context options for stealth
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True,
        )
        
        stealth_script = get_stealth_script()
        if stealth_script:
            context.add_init_script(stealth_script)
        
        page = context.new_page()
        
        # Navigate
        timeout_ms = int(timeout * 1000)
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        
        # Wait for JS to execute - modern sites need more time
        time.sleep(1.0)
        
        # Get HTML
        html = page.content()
        cookies = {c["name"]: c["value"] for c in context.cookies()}
        final_url = page.url
        
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
            attempts=[Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms, http_status=200)],
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
            attempts=[Attempt(tier=tier_name, success=False, error=str(e), error_type=error_type, elapsed_ms=elapsed_ms)],
        )
        
    finally:
        # Always clean up
        if page:
            try: page.close()
            except: pass
        if context:
            try: context.close()
            except: pass
        if browser:
            try: browser.close()
            except: pass
        if playwright_instance:
            try: playwright_instance.stop()
            except: pass


def scrape_with_playwright_aggressive(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE,
    profile: Optional[BrowserContextProfile] = None,
    headless: bool = True,
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
    start_time = time.time()
    tier_name = "playwright_aggressive"
    session = None
    
    try:
        session = PlaywrightSession(profile=profile, headless=headless)
        
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
                attempts=[Attempt(tier=tier_name, success=False, error="Navigation failed", elapsed_ms=elapsed_ms)],
            )
        
        # Wait for page to stabilize
        time.sleep(1)
        
        # Dismiss consent
        session.dismiss_consent()
        
        # Expand content
        expansions = session.expand_content(max_clicks=max_expand_clicks)
        logger.debug(f"Expanded {expansions} elements")
        
        # Get HTML
        html = session.get_page_html()
        cookies = session.get_cookies()
        final_url = session.get_current_url()
        
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
            attempts=[Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms, http_status=200)],
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
            attempts=[Attempt(tier=tier_name, success=False, error=str(e), error_type=error_type, elapsed_ms=elapsed_ms)],
        )
        
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass


def scrape_with_drissionpage(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_DRISSION,
    profile: Optional[BrowserContextProfile] = None,
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
                attempts=[Attempt(tier=tier_name, success=False, error="Navigation failed", elapsed_ms=elapsed_ms)],
            )
        
        # Wait for page
        time.sleep(1)
        
        # Dismiss consent
        session.dismiss_consent()
        
        # Get HTML
        html = session.get_page_html()
        cookies = session.get_cookies()
        final_url = session.get_current_url()
        
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
            attempts=[Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms, http_status=200)],
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
            attempts=[Attempt(tier=tier_name, success=False, error=str(e), error_type=error_type, elapsed_ms=elapsed_ms)],
        )
        
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass


def scrape_with_drissionpage_stealth(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_DRISSION_STEALTH,
    profile: Optional[BrowserContextProfile] = None,
    headless: bool = True,
    max_challenge_wait: int = 45,
) -> ScrapeResult:
    """
    Scrape URL using DrissionPage with explicit challenge detection loop.
    
    Tier 7: Stealth browser with challenge waiting for protected sites.
    
    Args:
        url: URL to scrape
        timeout: Timeout in seconds
        profile: Optional browser context profile
        headless: Run browser in headless mode
        max_challenge_wait: Max seconds to wait for challenge to clear
    
    Returns:
        ScrapeResult with raw HTML bytes
    """
    start_time = time.time()
    tier_name = "drissionpage_stealth"
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
                attempts=[Attempt(tier=tier_name, success=False, error="Navigation failed", elapsed_ms=elapsed_ms)],
            )
        
        # Wait for challenge to clear
        if not session.wait_for_clearance(max_wait_seconds=max_challenge_wait):
            elapsed_ms = (time.time() - start_time) * 1000
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.CHALLENGE,
                error="Challenge did not clear",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[Attempt(tier=tier_name, success=False, error="Challenge timeout", error_type=ErrorType.CHALLENGE, elapsed_ms=elapsed_ms)],
            )
        
        # Dismiss consent
        session.dismiss_consent()
        
        # Get HTML
        html = session.get_page_html()
        cookies = session.get_cookies()
        final_url = session.get_current_url()
        
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
            attempts=[Attempt(tier=tier_name, success=True, elapsed_ms=elapsed_ms, http_status=200)],
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
            error=f"DrissionPage stealth error: {e}",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[Attempt(tier=tier_name, success=False, error=str(e), error_type=error_type, elapsed_ms=elapsed_ms)],
        )
        
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass


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
    tier_name = "vision"
    start_time = time.time()
    
    try:
        from playwright.sync_api import sync_playwright
        import base64
        from google import genai
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
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-http2',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ],
            )
            
            from .profiles import get_stealth_script
            
            context = browser.new_context(
                viewport={"width": 1280, "height": 1024},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            
            # Apply stealth patches
            stealth_script = get_stealth_script()
            if stealth_script:
                context.add_init_script(stealth_script)
            page = context.new_page()
            
            # Navigate and wait for content
            page.goto(url, timeout=int(timeout * 1000), wait_until="networkidle")
            page.wait_for_timeout(2000)  # Extra wait for JS rendering
            
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
                {"inline_data": {"mime_type": "image/png", "data": screenshot_b64}}
            ]
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
                attempts=[Attempt(tier=tier_name, success=False, error="Insufficient content", elapsed_ms=elapsed_ms)],
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
        logger.warning(f"Vision tier failed for {url}: {e}")
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
