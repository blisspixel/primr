"""
Tests for the adaptive scraper module.

Tests domain learning, tier selection, and adaptive behavior.
"""

import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from primr.data.adaptive_scraper import (
    AdaptiveScraper,
    DomainLearner,
    DomainProfile,
    adaptive_scrape,
    get_adaptive_scraper,
    get_domain_learner,
    reset_adaptive_scraper,
)

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_learner():
    """Create a learner with temporary storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = str(Path(tmpdir) / "profiles.json")
        learner = DomainLearner(storage_path=storage_path)
        yield learner


@pytest.fixture
def mock_scrape_functions():
    """Create mock scrape functions."""
    def make_scraper(tier: str, success: bool = True):
        def scrape(url: str, timeout: float = 30) -> tuple[str | None, str | None]:
            if success:
                return f"Content from {tier}", None
            return None, f"{tier} failed"
        return scrape

    return {
        "requests": make_scraper("requests"),
        "httpx": make_scraper("httpx"),
        "playwright": make_scraper("playwright"),
        "playwright_aggressive": make_scraper("playwright_aggressive"),
        "vision": make_scraper("vision"),
    }


# =============================================================================
# DOMAIN PROFILE TESTS
# =============================================================================

class TestDomainProfile:
    """Tests for DomainProfile dataclass."""

    def test_default_values(self):
        """Test default profile values."""
        profile = DomainProfile(domain="example.com")

        assert profile.domain == "example.com"
        assert profile.preferred_tier == "requests"
        assert profile.success_rate == 1.0
        assert profile.timeout_multiplier == 1.0

    def test_record_success(self):
        """Test recording successful attempt."""
        profile = DomainProfile(domain="example.com")

        profile.record_attempt("requests", True, 1.5)

        assert profile.total_attempts == 1
        assert profile.total_successes == 1
        assert profile.tier_successes.get("requests") == 1
        assert profile.last_success is not None

    def test_record_failure(self):
        """Test recording failed attempt."""
        profile = DomainProfile(domain="example.com")

        profile.record_attempt("requests", False, 5.0)

        assert profile.total_attempts == 1
        assert profile.total_successes == 0
        assert profile.tier_failures.get("requests") == 1
        assert profile.last_failure is not None

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        profile = DomainProfile(domain="example.com")

        profile.record_attempt("requests", True, 1.0)
        profile.record_attempt("requests", True, 1.0)
        profile.record_attempt("requests", False, 5.0)
        profile.record_attempt("requests", False, 5.0)

        assert profile.success_rate == 0.5

    def test_preferred_tier_selection(self):
        """Test that preferred tier is selected based on success."""
        profile = DomainProfile(domain="example.com")

        # requests fails
        profile.record_attempt("requests", False, 5.0)
        profile.record_attempt("requests", False, 5.0)

        # httpx succeeds
        profile.record_attempt("httpx", True, 1.0)
        profile.record_attempt("httpx", True, 1.0)

        assert profile.preferred_tier == "httpx"

    def test_timeout_multiplier_adjustment(self):
        """Test timeout multiplier adjusts for slow sites."""
        profile = DomainProfile(domain="slow.com")

        # Record slow responses
        for _ in range(5):
            profile.record_attempt("requests", True, 12.0)

        assert profile.timeout_multiplier == 2.0

    def test_get_tier_stats(self):
        """Test getting tier statistics."""
        profile = DomainProfile(domain="example.com")

        profile.record_attempt("requests", True, 1.0)
        profile.record_attempt("requests", True, 2.0)
        profile.record_attempt("httpx", False, 5.0)

        stats = profile.get_tier_stats()

        assert stats["requests"]["attempts"] == 2
        assert stats["requests"]["successes"] == 2
        assert stats["requests"]["success_rate"] == 1.0
        assert stats["httpx"]["failures"] == 1


# =============================================================================
# DOMAIN LEARNER TESTS
# =============================================================================

class TestDomainLearner:
    """Tests for DomainLearner class."""

    def test_initialization(self, temp_learner):
        """Test learner initialization."""
        assert temp_learner is not None

    def test_get_domain(self, temp_learner):
        """Test domain extraction."""
        assert temp_learner.get_domain("https://example.com/page") == "example.com"
        assert temp_learner.get_domain("http://www.test.org/path") == "www.test.org"

    def test_get_profile_creates_new(self, temp_learner):
        """Test that get_profile creates new profile."""
        profile = temp_learner.get_profile("https://newdomain.com")

        assert profile.domain == "newdomain.com"
        assert profile.preferred_tier == "requests"

    def test_get_profile_returns_existing(self, temp_learner):
        """Test that get_profile returns existing profile."""
        profile1 = temp_learner.get_profile("https://example.com")
        profile1.record_attempt("httpx", True, 1.0)

        profile2 = temp_learner.get_profile("https://example.com/other")

        assert profile2.tier_successes.get("httpx") == 1

    def test_record_attempt(self, temp_learner):
        """Test recording attempt through learner."""
        temp_learner.record_attempt("https://example.com", "requests", True, 1.5)

        profile = temp_learner.get_profile("https://example.com")
        assert profile.total_attempts == 1

    def test_get_recommended_tier(self, temp_learner):
        """Test getting recommended tier."""
        # Record some attempts
        temp_learner.record_attempt("https://example.com", "requests", False, 5.0)
        temp_learner.record_attempt("https://example.com", "requests", False, 5.0)
        temp_learner.record_attempt("https://example.com", "playwright", True, 2.0)
        temp_learner.record_attempt("https://example.com", "playwright", True, 2.0)

        tier = temp_learner.get_recommended_tier("https://example.com")
        assert tier == "playwright"

    def test_get_recommended_timeout(self, temp_learner):
        """Test getting recommended timeout."""
        # Record slow responses
        for _ in range(5):
            temp_learner.record_attempt("https://slow.com", "requests", True, 15.0)

        timeout = temp_learner.get_recommended_timeout("https://slow.com", base_timeout=30.0)
        assert timeout == 60.0  # 2x multiplier

    def test_persistence(self, temp_learner):
        """Test that profiles are persisted."""
        temp_learner.record_attempt("https://example.com", "httpx", True, 1.0)
        temp_learner.save()

        # Create new learner with same storage
        new_learner = DomainLearner(storage_path=temp_learner._storage_path)
        profile = new_learner.get_profile("https://example.com")

        assert profile.tier_successes.get("httpx") == 1

    def test_get_stats(self, temp_learner):
        """Test getting overall statistics."""
        temp_learner.record_attempt("https://example1.com", "requests", True, 1.0)
        temp_learner.record_attempt("https://example2.com", "httpx", True, 1.0)
        temp_learner.record_attempt("https://example3.com", "requests", False, 5.0)

        stats = temp_learner.get_stats()

        assert stats["total_domains"] == 3
        assert stats["total_attempts"] == 3
        assert stats["total_successes"] == 2

    def test_clear(self, temp_learner):
        """Test clearing all profiles."""
        temp_learner.record_attempt("https://example.com", "requests", True, 1.0)
        temp_learner.clear()

        assert len(temp_learner.get_all_profiles()) == 0


# =============================================================================
# ADAPTIVE SCRAPER TESTS
# =============================================================================

class TestAdaptiveScraper:
    """Tests for AdaptiveScraper class."""

    def test_initialization(self, temp_learner, mock_scrape_functions):
        """Test scraper initialization."""
        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=mock_scrape_functions
        )
        assert scraper is not None

    def test_scrape_success(self, temp_learner, mock_scrape_functions):
        """Test successful scrape."""
        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=mock_scrape_functions
        )

        content, tier = scraper.scrape("https://example.com")

        assert content is not None
        assert "Content from" in content

    def test_scrape_uses_recommended_tier(self, temp_learner, mock_scrape_functions):
        """Test that scraper uses recommended tier."""
        # Train learner to prefer httpx
        temp_learner.record_attempt("https://example.com", "requests", False, 5.0)
        temp_learner.record_attempt("https://example.com", "requests", False, 5.0)
        temp_learner.record_attempt("https://example.com", "httpx", True, 1.0)
        temp_learner.record_attempt("https://example.com", "httpx", True, 1.0)

        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=mock_scrape_functions
        )

        content, tier = scraper.scrape("https://example.com")

        assert tier == "httpx"

    def test_scrape_force_tier(self, temp_learner, mock_scrape_functions):
        """Test forcing a specific tier."""
        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=mock_scrape_functions
        )

        content, tier = scraper.scrape("https://example.com", force_tier="playwright")

        assert tier == "playwright"

    def test_scrape_fallback_on_failure(self, temp_learner):
        """Test fallback to next tier on failure."""
        call_order = []

        def failing_requests(url, timeout=30):
            call_order.append("requests")
            return None, "Failed"

        def succeeding_httpx(url, timeout=30):
            call_order.append("httpx")
            return "Content", None

        scrape_functions = {
            "requests": failing_requests,
            "httpx": succeeding_httpx,
            "playwright": lambda u, timeout=30: ("Content", None),
        }

        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=scrape_functions
        )

        content, tier = scraper.scrape("https://example.com")

        assert content == "Content"
        assert tier == "httpx"
        assert call_order == ["requests", "httpx"]

    def test_scrape_max_tiers(self, temp_learner):
        """Test max_tiers limits fallback attempts."""
        call_count = 0

        def failing_scrape(url, timeout=30):
            nonlocal call_count
            call_count += 1
            return None, "Failed"

        scrape_functions = {
            "requests": failing_scrape,
            "httpx": failing_scrape,
            "playwright": failing_scrape,
            "playwright_aggressive": failing_scrape,
            "vision": failing_scrape,
        }

        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=scrape_functions
        )

        content, error = scraper.scrape("https://example.com", max_tiers=2)

        assert content is None
        assert call_count == 2

    def test_scrape_records_attempts(self, temp_learner, mock_scrape_functions):
        """Test that scrape records attempts to learner."""
        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=mock_scrape_functions
        )

        scraper.scrape("https://example.com")

        profile = temp_learner.get_profile("https://example.com")
        assert profile.total_attempts >= 1

    def test_get_domain_profile(self, temp_learner, mock_scrape_functions):
        """Test getting domain profile through scraper."""
        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=mock_scrape_functions
        )

        scraper.scrape("https://example.com")
        profile = scraper.get_domain_profile("https://example.com")

        assert profile.domain == "example.com"

    def test_get_stats(self, temp_learner, mock_scrape_functions):
        """Test getting scraper statistics."""
        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=mock_scrape_functions
        )

        scraper.scrape("https://example1.com")
        scraper.scrape("https://example2.com")

        stats = scraper.get_stats()

        assert stats["total_domains"] == 2


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton access."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_adaptive_scraper()

    def teardown_method(self):
        """Clean up after each test."""
        reset_adaptive_scraper()

    def test_get_domain_learner_singleton(self):
        """Test that get_domain_learner returns singleton."""
        learner1 = get_domain_learner()
        learner2 = get_domain_learner()

        assert learner1 is learner2

    def test_get_adaptive_scraper_singleton(self):
        """Test that get_adaptive_scraper returns singleton."""
        scraper1 = get_adaptive_scraper()
        scraper2 = get_adaptive_scraper()

        assert scraper1 is scraper2

    def test_reset_adaptive_scraper(self):
        """Test resetting singletons."""
        scraper1 = get_adaptive_scraper()
        reset_adaptive_scraper()
        scraper2 = get_adaptive_scraper()

        assert scraper1 is not scraper2


# =============================================================================
# THREAD SAFETY TESTS
# =============================================================================

class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_profile_access(self, temp_learner):
        """Test concurrent profile access."""
        errors = []

        def record_attempts(domain: str, count: int):
            try:
                for i in range(count):
                    temp_learner.record_attempt(
                        f"https://{domain}/page{i}",
                        "requests",
                        i % 2 == 0,
                        1.0
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record_attempts, args=(f"domain{i}.com", 50))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_scraping(self, temp_learner, mock_scrape_functions):
        """Test concurrent scraping."""
        scraper = AdaptiveScraper(
            learner=temp_learner,
            scrape_functions=mock_scrape_functions
        )

        errors = []
        results = []

        def scrape_url(url: str):
            try:
                content, tier = scraper.scrape(url)
                results.append((url, content, tier))
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=scrape_url, args=(f"https://domain{i}.com",))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_adaptive_scraper()

    def teardown_method(self):
        """Clean up after each test."""
        reset_adaptive_scraper()

    @patch('primr.data.adaptive_scraper.AdaptiveScraper.scrape')
    def test_adaptive_scrape(self, mock_scrape):
        """Test adaptive_scrape convenience function."""
        mock_scrape.return_value = ("Content", "requests")

        content, tier = adaptive_scrape("https://example.com")

        assert content == "Content"
        mock_scrape.assert_called_once()
