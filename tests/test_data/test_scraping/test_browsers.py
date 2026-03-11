"""Tests for browser automation scrapers."""

import asyncio
import sys
from unittest.mock import MagicMock, patch

import pytest

from primr.data.scraping.browsers import (
    BROWSER_TIERS,
    CLICK_DENYLIST,
    CONSENT_DISMISS_PATTERNS,
    EXPAND_PATTERNS,
    FakeBrowserSession,
    scrape_with_drissionpage,
    scrape_with_drissionpage_stealth,
    scrape_with_playwright,
    scrape_with_playwright_aggressive,
    scrape_with_vision,
)
from primr.data.scraping.models import ErrorType, ScrapeResult

_ASYNC_SUBPROCESS_AVAILABLE: bool | None = None


def _is_playwright_subprocess_blocked(error: Exception | str) -> bool:
    """Detect sandboxed Windows subprocess restrictions affecting Playwright."""
    text = str(error).lower()
    patterns = (
        "winerror 5",
        "access is denied",
        "permissionerror",
        "createfile",
        "create_subprocess_exec",
    )
    return any(pattern in text for pattern in patterns)


def _can_spawn_asyncio_subprocess() -> bool:
    """Probe whether asyncio subprocess creation is permitted."""
    global _ASYNC_SUBPROCESS_AVAILABLE
    if _ASYNC_SUBPROCESS_AVAILABLE is not None:
        return _ASYNC_SUBPROCESS_AVAILABLE

    async def _probe() -> bool:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "print('ok')",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0

    try:
        _ASYNC_SUBPROCESS_AVAILABLE = asyncio.run(_probe())
    except Exception:
        _ASYNC_SUBPROCESS_AVAILABLE = False

    return _ASYNC_SUBPROCESS_AVAILABLE


class TestExpandPatterns:
    """Tests for expand patterns configuration."""

    def test_has_common_patterns(self):
        """Should include common expand patterns."""
        assert "read more" in EXPAND_PATTERNS
        assert "show more" in EXPAND_PATTERNS
        assert "expand" in EXPAND_PATTERNS

    def test_patterns_are_lowercase(self):
        """All patterns should be lowercase for matching."""
        for pattern in EXPAND_PATTERNS:
            assert pattern == pattern.lower()


class TestClickDenylist:
    """Tests for click denylist configuration."""

    def test_has_navigation_items(self):
        """Should include navigation items."""
        assert "login" in CLICK_DENYLIST
        assert "sign in" in CLICK_DENYLIST
        assert "contact" in CLICK_DENYLIST

    def test_has_social_items(self):
        """Should include social media items."""
        assert "facebook" in CLICK_DENYLIST
        assert "twitter" in CLICK_DENYLIST or "tweet" in CLICK_DENYLIST
        assert "linkedin" in CLICK_DENYLIST

    def test_has_commerce_items(self):
        """Should include commerce items."""
        assert "buy" in CLICK_DENYLIST
        assert "purchase" in CLICK_DENYLIST
        assert "add to cart" in CLICK_DENYLIST


class TestConsentDismissPatterns:
    """Tests for consent dismiss patterns."""

    def test_has_accept_patterns(self):
        """Should include accept patterns."""
        assert "accept" in CONSENT_DISMISS_PATTERNS
        assert "accept all" in CONSENT_DISMISS_PATTERNS
        assert "agree" in CONSENT_DISMISS_PATTERNS

    def test_has_dismiss_patterns(self):
        """Should include dismiss patterns."""
        assert "close" in CONSENT_DISMISS_PATTERNS
        assert "dismiss" in CONSENT_DISMISS_PATTERNS


class TestFakeBrowserSession:
    """Tests for FakeBrowserSession."""

    def test_navigate_returns_true(self):
        """Navigate should return True."""
        session = FakeBrowserSession()
        assert session.navigate("https://example.com") is True
        assert session._current_url == "https://example.com"

    def test_get_page_html(self):
        """Should return configured HTML."""
        html = "<html><body>Custom content</body></html>"
        session = FakeBrowserSession(html=html)
        assert session.get_page_html() == html

    def test_get_cookies(self):
        """Should return configured cookies."""
        cookies = {"session": "abc123", "cf_clearance": "xyz"}
        session = FakeBrowserSession(cookies=cookies)
        assert session.get_cookies() == cookies

    def test_wait_for_clearance(self):
        """Should return configured clearance result."""
        session_clears = FakeBrowserSession(challenge_clears=True)
        assert session_clears.wait_for_clearance() is True

        session_blocks = FakeBrowserSession(challenge_clears=False)
        assert session_blocks.wait_for_clearance() is False

    def test_dismiss_consent(self):
        """Should return configured consent result."""
        session_dismisses = FakeBrowserSession(consent_dismisses=True)
        assert session_dismisses.dismiss_consent() is True

        session_fails = FakeBrowserSession(consent_dismisses=False)
        assert session_fails.dismiss_consent() is False

    def test_expand_content(self):
        """Should return simulated expansions."""
        session = FakeBrowserSession()
        expansions = session.expand_content(max_clicks=10)
        assert expansions >= 0
        assert expansions <= 10

    def test_close(self):
        """Should mark session as closed."""
        session = FakeBrowserSession()
        session.close()
        assert session._closed is True


class TestBrowserSessionSafetyMethods:
    """Tests for BrowserSession safety methods."""

    def test_is_safe_to_click_expand_patterns(self):
        """Should allow expand patterns."""
        session = FakeBrowserSession()

        assert session._is_safe_to_click("Read More") is True
        assert session._is_safe_to_click("Show more details") is True
        assert session._is_safe_to_click("Expand section") is True

    def test_is_safe_to_click_denies_navigation(self):
        """Should deny navigation patterns."""
        session = FakeBrowserSession()

        assert session._is_safe_to_click("Login") is False
        assert session._is_safe_to_click("Sign in to continue") is False
        assert session._is_safe_to_click("Contact us") is False

    def test_is_safe_to_click_denies_commerce(self):
        """Should deny commerce patterns."""
        session = FakeBrowserSession()

        assert session._is_safe_to_click("Buy now") is False
        assert session._is_safe_to_click("Add to cart") is False
        assert session._is_safe_to_click("Purchase") is False

    def test_url_domain_unchanged_same_domain(self):
        """Should return True for same domain."""
        session = FakeBrowserSession()

        assert (
            session._url_domain_unchanged("https://example.com/page1", "https://example.com/page2")
            is True
        )

    def test_url_domain_unchanged_different_domain(self):
        """Should return False for different domain."""
        session = FakeBrowserSession()

        assert (
            session._url_domain_unchanged("https://example.com/page", "https://other.com/page")
            is False
        )


class TestScrapeWithPlaywright:
    """Tests for scrape_with_playwright function."""

    def test_returns_scrape_result(self):
        """Should return ScrapeResult."""
        # Mock PlaywrightSession
        mock_session = FakeBrowserSession(
            html="<html><body>Test</body></html>",
            cookies={"session": "abc"},
        )

        with patch("primr.data.scraping.browsers.PlaywrightSession", return_value=mock_session):
            result = scrape_with_playwright("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.tier == "playwright"

    def test_handles_import_error(self):
        """Should handle missing playwright gracefully."""
        # The scrape_with_playwright function imports playwright.sync_api.sync_playwright
        # inside the function, so we need to patch the module import itself
        import sys

        from primr.data.scraping.browsers import SharedBrowser

        # Reset the shared browser singleton so it can't serve a cached browser
        SharedBrowser.get().close()

        # Temporarily remove playwright from sys.modules to simulate import error
        original_modules = {}
        playwright_modules = [k for k in sys.modules if k.startswith("playwright")]
        for mod in playwright_modules:
            original_modules[mod] = sys.modules.pop(mod)

        # Create a mock that raises ImportError when playwright is imported
        with patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
            # Force re-import by patching builtins.__import__
            original_import = (
                __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
            )

            def mock_import(name, *args, **kwargs):
                if name.startswith("playwright"):
                    raise ImportError("playwright not installed")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = scrape_with_playwright("https://example.com")

        # Restore original modules
        sys.modules.update(original_modules)

        assert result.success is False
        assert "playwright" in result.error.lower() or "not installed" in result.error.lower()


class TestScrapeWithPlaywrightAggressive:
    """Tests for scrape_with_playwright_aggressive function."""

    def test_returns_scrape_result(self):
        """Should return ScrapeResult."""
        mock_session = FakeBrowserSession(
            html="<html><body>Expanded content</body></html>",
        )

        with patch("primr.data.scraping.browsers.PlaywrightSession", return_value=mock_session):
            result = scrape_with_playwright_aggressive("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.tier == "playwright_aggressive"

    def test_respects_max_expand_clicks(self):
        """Should respect max_expand_clicks parameter."""
        mock_session = FakeBrowserSession()

        with patch("primr.data.scraping.browsers.PlaywrightSession", return_value=mock_session):
            scrape_with_playwright_aggressive("https://example.com", max_expand_clicks=5)

        # FakeBrowserSession limits to min(3, max_clicks)
        assert mock_session._expand_count <= 5


class TestScrapeWithDrissionpage:
    """Tests for scrape_with_drissionpage function."""

    def test_returns_scrape_result(self):
        """Should return ScrapeResult."""
        mock_session = FakeBrowserSession(
            html="<html><body>DrissionPage content</body></html>",
        )

        with patch("primr.data.scraping.browsers.DrissionPageSession", return_value=mock_session):
            result = scrape_with_drissionpage("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.tier == "drissionpage"

    def test_handles_import_error(self):
        """Should handle missing DrissionPage gracefully."""
        with patch(
            "primr.data.scraping.browsers.DrissionPageSession",
            side_effect=ImportError("DrissionPage not installed"),
        ):
            result = scrape_with_drissionpage("https://example.com")

        assert result.success is False
        assert "drissionpage" in result.error.lower() or "not installed" in result.error.lower()


class TestScrapeWithDrissionpageStealth:
    """Tests for scrape_with_drissionpage_stealth function."""

    def test_returns_scrape_result_when_challenge_clears(self):
        """Should return success when challenge clears."""
        mock_session = FakeBrowserSession(
            html="<html><body>Content after challenge</body></html>",
            challenge_clears=True,
        )

        with patch("primr.data.scraping.browsers.DrissionPageSession", return_value=mock_session):
            result = scrape_with_drissionpage_stealth("https://example.com")

        assert isinstance(result, ScrapeResult)
        assert result.tier == "drissionpage_stealth"
        assert result.success is True

    def test_returns_challenge_error_when_not_cleared(self):
        """Should return challenge error when challenge doesn't clear."""
        mock_session = FakeBrowserSession(
            challenge_clears=False,
        )

        with patch("primr.data.scraping.browsers.DrissionPageSession", return_value=mock_session):
            result = scrape_with_drissionpage_stealth(
                "https://example.com",
                max_challenge_wait=1,  # Short wait for test
            )

        assert result.success is False
        assert result.error_type == ErrorType.CHALLENGE


class TestScrapeWithVision:
    """Tests for scrape_with_vision function."""

    def test_requires_gemini_api_key(self):
        """Should fail gracefully when GEMINI_API_KEY is not set."""
        from unittest.mock import patch

        # Mock settings to return no API key
        mock_settings = MagicMock()
        mock_settings.api.gemini_key = None

        # get_settings is imported inside the function from primr.config.settings
        with patch("primr.config.settings.get_settings", return_value=mock_settings):
            result = scrape_with_vision("https://example.com")

        assert result.success is False
        assert "GEMINI_API_KEY" in result.error

    def test_returns_vision_content_type(self):
        """Should return content_type='vision_text' when successful."""
        result = scrape_with_vision("https://example.com")

        # If API key is configured, should succeed with vision_text type
        if result.success:
            assert result.content_type == "vision_text"
            assert result.tier == "vision"
        else:
            # If no API key, should fail gracefully
            assert "GEMINI_API_KEY" in result.error or "vision" in result.tier


class TestBrowserTiersRegistry:
    """Tests for BROWSER_TIERS registry."""

    def test_all_tiers_registered(self):
        """Should have all browser tiers registered."""
        assert "playwright" in BROWSER_TIERS
        assert "playwright_aggressive" in BROWSER_TIERS
        assert "drissionpage" in BROWSER_TIERS
        assert "drissionpage_stealth" in BROWSER_TIERS
        assert "vision" in BROWSER_TIERS

    def test_tiers_are_callable(self):
        """All registered tiers should be callable."""
        for name, func in BROWSER_TIERS.items():
            assert callable(func), f"Tier {name} is not callable"


class TestScrapeResultStructure:
    """Tests verifying ScrapeResult structure from browser tiers."""

    @pytest.fixture(autouse=True)
    def _cleanup_shared_browser(self):
        """Close SharedBrowser after each test to prevent event loop leaks."""
        from primr.data.scraping.browsers import SharedBrowser

        yield
        SharedBrowser.get().close()

    def test_result_has_cookies_field(self):
        """Browser results should include cookies dict (may be empty for simple sites)."""
        if not _can_spawn_asyncio_subprocess():
            pytest.skip("Playwright subprocess launch blocked in this environment")

        result = scrape_with_playwright("https://example.com")

        if not result.success:
            error_text = result.error or ""
            if "Executable doesn't exist" in error_text:
                pytest.skip("Playwright browsers not installed")
            if _is_playwright_subprocess_blocked(error_text):
                pytest.skip("Playwright subprocess launch blocked in this environment")

        # Cookies should be a dict (may be empty for sites that don't set cookies)
        assert result.cookies is not None
        assert isinstance(result.cookies, dict)

    def test_result_has_attempts(self):
        """Results should include attempt records."""
        if not _can_spawn_asyncio_subprocess():
            pytest.skip("Playwright subprocess launch blocked in this environment")

        result = scrape_with_playwright("https://example.com")

        if not result.success:
            error_text = result.error or ""
            if "Executable doesn't exist" in error_text:
                pytest.skip("Playwright browsers not installed")
            if _is_playwright_subprocess_blocked(error_text):
                pytest.skip("Playwright subprocess launch blocked in this environment")

        assert len(result.attempts) >= 1
        assert result.attempts[0].tier == "playwright"
