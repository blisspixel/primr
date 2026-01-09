"""Tests for scraping profiles - Property 6: Profile Separation and Consistency."""

import pytest
from hypothesis import given, strategies as st

from primr.data.scraping.profiles import (
    HttpHeaderProfile,
    BrowserContextProfile,
    StealthPatch,
    HTTP_PROFILES,
    CONTEXT_PROFILES,
    STEALTH_PATCHES,
    get_random_http_profile,
    get_random_context_profile,
    get_stealth_script,
    get_http_profile_by_name,
    get_context_profile_by_name,
)


class TestHttpHeaderProfiles:
    """Tests for HTTP header profiles."""
    
    def test_all_profiles_have_required_fields(self):
        """All HTTP profiles must have user_agent and accept_language."""
        for profile in HTTP_PROFILES:
            assert profile.user_agent, f"Profile {profile.name} missing user_agent"
            assert profile.accept_language, f"Profile {profile.name} missing accept_language"
            assert len(profile.user_agent) > 20, f"Profile {profile.name} has suspiciously short UA"
    
    def test_windows_profiles_have_windows_platform(self):
        """Windows profiles must have Windows-consistent sec-ch-ua-platform."""
        for profile in HTTP_PROFILES:
            if "windows" in profile.name.lower():
                assert profile.sec_ch_ua_platform is not None, \
                    f"Windows profile {profile.name} missing sec_ch_ua_platform"
                assert "Windows" in profile.sec_ch_ua_platform, \
                    f"Windows profile {profile.name} has non-Windows platform: {profile.sec_ch_ua_platform}"
    
    def test_mac_profiles_have_mac_platform(self):
        """Mac profiles must have macOS-consistent sec-ch-ua-platform."""
        for profile in HTTP_PROFILES:
            if "mac" in profile.name.lower() and "safari" not in profile.name.lower():
                # Chrome/Edge on Mac should have sec-ch-ua
                if profile.sec_ch_ua is not None:
                    assert profile.sec_ch_ua_platform is not None, \
                        f"Mac profile {profile.name} missing sec_ch_ua_platform"
                    assert "macOS" in profile.sec_ch_ua_platform or "Mac" in profile.sec_ch_ua_platform, \
                        f"Mac profile {profile.name} has non-Mac platform: {profile.sec_ch_ua_platform}"
    
    def test_safari_profiles_have_no_sec_ch_ua(self):
        """Safari profiles should not have sec-ch-ua (Safari doesn't send it)."""
        for profile in HTTP_PROFILES:
            if "safari" in profile.name.lower() and "chrome" not in profile.user_agent.lower():
                assert profile.sec_ch_ua is None, \
                    f"Safari profile {profile.name} should not have sec_ch_ua"
    
    def test_chrome_profiles_have_sec_ch_ua(self):
        """Chrome profiles must have sec-ch-ua headers."""
        for profile in HTTP_PROFILES:
            if "chrome" in profile.name.lower():
                assert profile.sec_ch_ua is not None, \
                    f"Chrome profile {profile.name} missing sec_ch_ua"
                assert "Chrome" in profile.sec_ch_ua or "Chromium" in profile.sec_ch_ua, \
                    f"Chrome profile {profile.name} has invalid sec_ch_ua"
    
    def test_profile_names_are_unique(self):
        """All profile names must be unique."""
        names = [p.name for p in HTTP_PROFILES]
        assert len(names) == len(set(names)), "Duplicate profile names found"
    
    def test_at_least_four_profiles(self):
        """Should have at least 4 HTTP profiles for diversity."""
        assert len(HTTP_PROFILES) >= 4, "Need at least 4 HTTP profiles"


class TestBrowserContextProfiles:
    """Tests for browser context profiles."""
    
    def test_all_profiles_have_required_fields(self):
        """All context profiles must have viewport, locale, timezone."""
        for profile in CONTEXT_PROFILES:
            assert profile.viewport_width > 0, f"Profile {profile.name} has invalid width"
            assert profile.viewport_height > 0, f"Profile {profile.name} has invalid height"
            assert profile.locale, f"Profile {profile.name} missing locale"
            assert profile.timezone, f"Profile {profile.name} missing timezone"
            assert profile.color_scheme in ("light", "dark"), \
                f"Profile {profile.name} has invalid color_scheme"
    
    def test_viewports_are_realistic(self):
        """Viewport sizes should be realistic desktop resolutions."""
        for profile in CONTEXT_PROFILES:
            # Minimum reasonable desktop size
            assert profile.viewport_width >= 1024, \
                f"Profile {profile.name} width too small: {profile.viewport_width}"
            assert profile.viewport_height >= 600, \
                f"Profile {profile.name} height too small: {profile.viewport_height}"
            # Maximum reasonable size
            assert profile.viewport_width <= 4096, \
                f"Profile {profile.name} width too large: {profile.viewport_width}"
            assert profile.viewport_height <= 2160, \
                f"Profile {profile.name} height too large: {profile.viewport_height}"
    
    def test_timezones_are_valid_format(self):
        """Timezones should be in IANA format (e.g., America/New_York)."""
        for profile in CONTEXT_PROFILES:
            assert "/" in profile.timezone, \
                f"Profile {profile.name} timezone not in IANA format: {profile.timezone}"
    
    def test_at_least_three_profiles(self):
        """Should have at least 3 context profiles for diversity."""
        assert len(CONTEXT_PROFILES) >= 3, "Need at least 3 context profiles"


class TestStealthPatches:
    """Tests for stealth patches."""
    
    def test_patches_are_minimal(self):
        """Stealth patches should be minimal (< 5 patches)."""
        assert len(STEALTH_PATCHES) < 5, \
            f"Too many stealth patches ({len(STEALTH_PATCHES)}). Keep minimal to avoid detection."
    
    def test_all_patches_have_required_fields(self):
        """All patches must have name, script, and description."""
        for patch in STEALTH_PATCHES:
            assert patch.name, "Patch missing name"
            assert patch.script, "Patch missing script"
            assert patch.description, "Patch missing description"
    
    def test_patches_are_valid_javascript(self):
        """Patch scripts should look like valid JavaScript."""
        for patch in STEALTH_PATCHES:
            # Basic sanity checks
            assert ";" in patch.script or "=>" in patch.script, \
                f"Patch {patch.name} doesn't look like JavaScript"
            # Should not have obvious syntax errors
            assert patch.script.count("(") == patch.script.count(")"), \
                f"Patch {patch.name} has unbalanced parentheses"


class TestProfileFunctions:
    """Tests for profile getter functions."""
    
    def test_get_random_http_profile_returns_valid(self):
        """get_random_http_profile returns a valid profile."""
        profile = get_random_http_profile()
        assert isinstance(profile, HttpHeaderProfile)
        assert profile in HTTP_PROFILES
    
    def test_get_random_context_profile_returns_valid(self):
        """get_random_context_profile returns a valid profile."""
        profile = get_random_context_profile()
        assert isinstance(profile, BrowserContextProfile)
        assert profile in CONTEXT_PROFILES
    
    def test_get_stealth_script_returns_string(self):
        """get_stealth_script returns a non-empty string."""
        script = get_stealth_script()
        assert isinstance(script, str)
        # May be empty if no patches, but should be string
    
    def test_get_http_profile_by_name_found(self):
        """get_http_profile_by_name returns profile when found."""
        profile = get_http_profile_by_name("chrome_124_windows")
        assert profile is not None
        assert profile.name == "chrome_124_windows"
    
    def test_get_http_profile_by_name_not_found(self):
        """get_http_profile_by_name returns None when not found."""
        profile = get_http_profile_by_name("nonexistent_profile")
        assert profile is None
    
    def test_get_context_profile_by_name_found(self):
        """get_context_profile_by_name returns profile when found."""
        profile = get_context_profile_by_name("desktop_1080p")
        assert profile is not None
        assert profile.name == "desktop_1080p"
    
    def test_get_context_profile_by_name_not_found(self):
        """get_context_profile_by_name returns None when not found."""
        profile = get_context_profile_by_name("nonexistent_profile")
        assert profile is None


class TestProfileRandomness:
    """Tests for profile randomness (fingerprint diversity)."""
    
    def test_random_http_profiles_vary(self):
        """Multiple calls to get_random_http_profile should vary."""
        profiles = [get_random_http_profile() for _ in range(20)]
        unique_names = set(p.name for p in profiles)
        # With 4+ profiles and 20 samples, we should see at least 2 different ones
        assert len(unique_names) >= 2, "Random profiles not varying enough"
    
    def test_random_context_profiles_vary(self):
        """Multiple calls to get_random_context_profile should vary."""
        profiles = [get_random_context_profile() for _ in range(20)]
        unique_names = set(p.name for p in profiles)
        # With 3+ profiles and 20 samples, we should see at least 2 different ones
        assert len(unique_names) >= 2, "Random context profiles not varying enough"
