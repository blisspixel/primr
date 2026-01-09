"""Tests for browser automation scrapers."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from primr.data.scraping.browsers import (
    BrowserSession,
    FakeBrowserSession,
    EXPAND_PATTERNS,
    CLICK_DENYLIST,
    CONSENT_DISMISS_PATTERNS,
    scrape_with_playwright,
    scrape_with_playwright_aggressive,
    scrape_with_drissionpage,
    scrape_with_drissionpage_stealth,
    scrape_with_vision,
    BROWSER_TIERS,
)
from primr.data.scraping.models import ErrorType, ScrapeResult


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
        
        assert session._url_domain_unchanged(
            "https://example.com/page1",
            "https://example.com/page2"
        ) is True
    
    def test_url_domain_unchanged_different_domain(self):
        """Should return False for different domain."""
        session = FakeBrowserSession()
        
        assert session._url_domain_unchanged(
            "https://example.com/page",
            "https://other.com/page"
        ) is False


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
        with patch("primr.data.scraping.browsers.PlaywrightSession", side_effect=ImportError("playwright not installed")):
            result = scrape_with_playwright("https://example.com")
        
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
            scrape_with_playwright_aggressive(
                "https://example.com",
                max_expand_clicks=5
            )
        
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
        with patch("primr.data.scraping.browsers.DrissionPageSession", side_effect=ImportError("DrissionPage not installed")):
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
                max_challenge_wait=1  # Short wait for test
            )
        
        assert result.success is False
        assert result.error_type == ErrorType.CHALLENGE


class TestScrapeWithVision:
    """Tests for scrape_with_vision function."""
    
    def test_skipped_when_not_enabled(self):
        """Should skip when enabled=False (default)."""
        result = scrape_with_vision("https://example.com")
        
        assert result.success is False
        assert "not enabled" in result.error.lower() or "opt-in" in result.error.lower()
    
    def test_returns_vision_content_type(self):
        """Should return content_type='vision_text' when enabled."""
        result = scrape_with_vision("https://example.com", enabled=True)
        
        # Currently returns not implemented, but should have vision_text type
        assert result.content_type == "vision_text"
        assert result.tier == "vision"


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
    
    def test_result_has_cookies_field(self):
        """Browser results should include cookies for handoff."""
        mock_session = FakeBrowserSession(
            html="<html><body>Test</body></html>",
            cookies={"cf_clearance": "abc123"},
        )
        
        with patch("primr.data.scraping.browsers.PlaywrightSession", return_value=mock_session):
            result = scrape_with_playwright("https://example.com")
        
        assert result.cookies is not None
        assert "cf_clearance" in result.cookies
    
    def test_result_has_attempts(self):
        """Results should include attempt records."""
        mock_session = FakeBrowserSession()
        
        with patch("primr.data.scraping.browsers.PlaywrightSession", return_value=mock_session):
            result = scrape_with_playwright("https://example.com")
        
        assert len(result.attempts) >= 1
        assert result.attempts[0].tier == "playwright"
