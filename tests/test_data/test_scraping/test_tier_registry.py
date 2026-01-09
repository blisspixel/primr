"""Tests for tier registry."""

import pytest

from primr.data.scraping.tier_registry import (
    DEFAULT_TIERS,
    get_tier_by_name,
    get_available_tiers,
    get_tier_names,
    get_available_tier_names,
)
from primr.data.scraping.models import ScrapeTier


class TestDefaultTiers:
    """Tests for DEFAULT_TIERS configuration."""
    
    def test_has_expected_tiers(self):
        """Should have all expected tiers."""
        tier_names = [t.name for t in DEFAULT_TIERS]
        
        assert "requests" in tier_names
        assert "httpx" in tier_names
        assert "curl_cffi" in tier_names
        assert "playwright" in tier_names
        assert "playwright_aggressive" in tier_names
        assert "drissionpage" in tier_names
        assert "drissionpage_stealth" in tier_names
        assert "vision" in tier_names
    
    def test_tiers_are_in_order(self):
        """Tiers should be ordered from lightest to heaviest."""
        tier_names = [t.name for t in DEFAULT_TIERS]
        
        # requests should come before playwright
        assert tier_names.index("requests") < tier_names.index("playwright")
        
        # httpx should come before drissionpage
        assert tier_names.index("httpx") < tier_names.index("drissionpage")
        
        # vision should be last
        assert tier_names[-1] == "vision"
    
    def test_all_tiers_are_scrape_tier(self):
        """All tiers should be ScrapeTier instances."""
        for tier in DEFAULT_TIERS:
            assert isinstance(tier, ScrapeTier)
    
    def test_all_tiers_have_scrape_fn(self):
        """All tiers should have callable scrape_fn."""
        for tier in DEFAULT_TIERS:
            assert callable(tier.scrape_fn), f"Tier {tier.name} has non-callable scrape_fn"
    
    def test_all_tiers_have_timeout(self):
        """All tiers should have positive timeout."""
        for tier in DEFAULT_TIERS:
            assert tier.timeout > 0, f"Tier {tier.name} has invalid timeout"
    
    def test_tier_names_are_unique(self):
        """Tier names should be unique."""
        tier_names = [t.name for t in DEFAULT_TIERS]
        assert len(tier_names) == len(set(tier_names))


class TestGetTierByName:
    """Tests for get_tier_by_name function."""
    
    def test_finds_existing_tier(self):
        """Should find tier by name."""
        tier = get_tier_by_name("requests")
        
        assert tier is not None
        assert tier.name == "requests"
    
    def test_returns_none_for_unknown(self):
        """Should return None for unknown tier."""
        tier = get_tier_by_name("nonexistent_tier")
        
        assert tier is None
    
    def test_finds_all_default_tiers(self):
        """Should find all default tiers by name."""
        for default_tier in DEFAULT_TIERS:
            found = get_tier_by_name(default_tier.name)
            assert found is not None
            assert found.name == default_tier.name


class TestGetAvailableTiers:
    """Tests for get_available_tiers function."""
    
    def test_returns_list(self):
        """Should return a list."""
        available = get_available_tiers()
        assert isinstance(available, list)
    
    def test_includes_requests_tier(self):
        """Should always include requests tier (no dependencies)."""
        available = get_available_tiers()
        tier_names = [t.name for t in available]
        
        assert "requests" in tier_names
    
    def test_all_returned_are_scrape_tier(self):
        """All returned tiers should be ScrapeTier instances."""
        available = get_available_tiers()
        
        for tier in available:
            assert isinstance(tier, ScrapeTier)


class TestGetTierNames:
    """Tests for get_tier_names function."""
    
    def test_returns_list_of_strings(self):
        """Should return list of strings."""
        names = get_tier_names()
        
        assert isinstance(names, list)
        for name in names:
            assert isinstance(name, str)
    
    def test_matches_default_tiers(self):
        """Should match DEFAULT_TIERS names."""
        names = get_tier_names()
        expected = [t.name for t in DEFAULT_TIERS]
        
        assert names == expected


class TestGetAvailableTierNames:
    """Tests for get_available_tier_names function."""
    
    def test_returns_list_of_strings(self):
        """Should return list of strings."""
        names = get_available_tier_names()
        
        assert isinstance(names, list)
        for name in names:
            assert isinstance(name, str)
    
    def test_includes_requests(self):
        """Should always include requests."""
        names = get_available_tier_names()
        
        assert "requests" in names
    
    def test_subset_of_all_tiers(self):
        """Available tiers should be subset of all tiers."""
        all_names = set(get_tier_names())
        available_names = set(get_available_tier_names())
        
        assert available_names.issubset(all_names)


class TestTierDependencies:
    """Tests for tier dependency configuration."""
    
    def test_requests_has_no_requires(self):
        """requests tier should have no dependencies."""
        tier = get_tier_by_name("requests")
        assert tier.requires is None
    
    def test_httpx_requires_httpx(self):
        """httpx tier should require httpx."""
        tier = get_tier_by_name("httpx")
        assert tier.requires == "httpx"
    
    def test_curl_cffi_requires_curl_cffi(self):
        """curl_cffi tier should require curl_cffi."""
        tier = get_tier_by_name("curl_cffi")
        assert tier.requires == "curl_cffi"
    
    def test_playwright_requires_playwright(self):
        """playwright tier should require playwright."""
        tier = get_tier_by_name("playwright")
        assert tier.requires == "playwright"
    
    def test_drissionpage_requires_drissionpage(self):
        """drissionpage tier should require DrissionPage."""
        tier = get_tier_by_name("drissionpage")
        assert tier.requires == "DrissionPage"
    
    def test_vision_has_no_local_requires(self):
        """vision tier should have no local dependency (uses API)."""
        tier = get_tier_by_name("vision")
        assert tier.requires is None
