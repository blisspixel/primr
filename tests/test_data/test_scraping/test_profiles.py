"""Tests for scraping profiles - Property 6: Profile Separation and Consistency."""

from primr.data.scraping.profiles import (
    CONTEXT_PROFILES,
    HTTP_PROFILES,
    STEALTH_SCRIPT,
    BrowserContextProfile,
    HttpHeaderProfile,
    get_browser_compatible_http_profile,
    get_context_profile_by_name,
    get_http_profile_by_name,
    get_random_context_profile,
    get_random_http_profile,
    get_stealth_script,
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
                assert profile.sec_ch_ua_platform is not None, (
                    f"Windows profile {profile.name} missing sec_ch_ua_platform"
                )
                assert "Windows" in profile.sec_ch_ua_platform, (
                    f"Windows profile {profile.name} has non-Windows platform: {profile.sec_ch_ua_platform}"
                )

    def test_mac_profiles_have_mac_platform(self):
        """Mac profiles must have macOS-consistent sec-ch-ua-platform."""
        for profile in HTTP_PROFILES:
            if "mac" in profile.name.lower() and "safari" not in profile.name.lower():
                # Chrome/Edge on Mac should have sec-ch-ua
                if profile.sec_ch_ua is not None:
                    assert profile.sec_ch_ua_platform is not None, (
                        f"Mac profile {profile.name} missing sec_ch_ua_platform"
                    )
                    assert (
                        "macOS" in profile.sec_ch_ua_platform or "Mac" in profile.sec_ch_ua_platform
                    ), (
                        f"Mac profile {profile.name} has non-Mac platform: {profile.sec_ch_ua_platform}"
                    )

    def test_safari_profiles_have_no_sec_ch_ua(self):
        """Safari profiles should not have sec-ch-ua (Safari doesn't send it)."""
        for profile in HTTP_PROFILES:
            if "safari" in profile.name.lower() and "chrome" not in profile.user_agent.lower():
                assert profile.sec_ch_ua is None, (
                    f"Safari profile {profile.name} should not have sec_ch_ua"
                )

    def test_chrome_profiles_have_sec_ch_ua(self):
        """Chrome profiles must have sec-ch-ua headers."""
        for profile in HTTP_PROFILES:
            if "chrome" in profile.name.lower():
                assert profile.sec_ch_ua is not None, (
                    f"Chrome profile {profile.name} missing sec_ch_ua"
                )
                assert "Chrome" in profile.sec_ch_ua or "Chromium" in profile.sec_ch_ua, (
                    f"Chrome profile {profile.name} has invalid sec_ch_ua"
                )

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
            assert profile.color_scheme in ("light", "dark"), (
                f"Profile {profile.name} has invalid color_scheme"
            )

    def test_viewports_are_realistic(self):
        """Viewport sizes should be realistic desktop resolutions."""
        for profile in CONTEXT_PROFILES:
            # Minimum reasonable desktop size
            assert profile.viewport_width >= 1024, (
                f"Profile {profile.name} width too small: {profile.viewport_width}"
            )
            assert profile.viewport_height >= 600, (
                f"Profile {profile.name} height too small: {profile.viewport_height}"
            )
            # Maximum reasonable size
            assert profile.viewport_width <= 4096, (
                f"Profile {profile.name} width too large: {profile.viewport_width}"
            )
            assert profile.viewport_height <= 2160, (
                f"Profile {profile.name} height too large: {profile.viewport_height}"
            )

    def test_timezones_are_valid_format(self):
        """Timezones should be in IANA format (e.g., America/New_York)."""
        for profile in CONTEXT_PROFILES:
            assert "/" in profile.timezone, (
                f"Profile {profile.name} timezone not in IANA format: {profile.timezone}"
            )

    def test_at_least_three_profiles(self):
        """Should have at least 3 context profiles for diversity."""
        assert len(CONTEXT_PROFILES) >= 3, "Need at least 3 context profiles"


class TestStealthPatches:
    """Tests for stealth script."""

    def test_stealth_script_exists(self):
        """Stealth script should be defined."""
        assert STEALTH_SCRIPT, "STEALTH_SCRIPT is empty"
        assert len(STEALTH_SCRIPT) > 100, "STEALTH_SCRIPT is too short"

    def test_stealth_script_is_valid_javascript(self):
        """Stealth script should look like valid JavaScript."""
        # Basic sanity checks
        assert ";" in STEALTH_SCRIPT or "=>" in STEALTH_SCRIPT, (
            "STEALTH_SCRIPT doesn't look like JavaScript"
        )
        # Should have key anti-detection features
        assert "webdriver" in STEALTH_SCRIPT.lower(), "STEALTH_SCRIPT missing webdriver detection"

    def test_get_stealth_script_returns_script(self):
        """get_stealth_script() returns the stealth script."""
        script = get_stealth_script()
        assert "__PRIMR_PLATFORM__" not in script
        assert "__PRIMR_APP_VERSION__" not in script
        assert len(script) > 100


class TestProfileFunctions:
    """Tests for profile getter functions."""

    def test_get_random_http_profile_returns_valid(self):
        """get_random_http_profile returns a valid profile."""
        profile = get_random_http_profile()
        assert isinstance(profile, HttpHeaderProfile)
        assert profile in HTTP_PROFILES

    def test_get_browser_compatible_http_profile_matches_browser_version(self):
        """Browser-compatible profiles should align UA and client hints to the actual Chromium major."""
        profile = get_browser_compatible_http_profile(
            browser_version="145.0.7632.6",
            platform_name="Windows",
        )
        assert profile.user_agent.endswith("Chrome/145.0.0.0 Safari/537.36")
        assert '"145"' in profile.sec_ch_ua
        assert profile.sec_ch_ua_platform == '"Windows"'

    def test_get_stealth_script_allows_platform_and_version_alignment(self):
        """Stealth script should embed caller-provided platform and UA values."""
        script = get_stealth_script(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
            ),
            platform_name="Darwin",
        )
        assert "MacIntel" in script
        assert "Chrome/145.0.0.0 Safari/537.36" in script

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
        profile = get_http_profile_by_name("chrome_131_windows")
        assert profile is not None
        assert profile.name == "chrome_131_windows"

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
        unique_names = {p.name for p in profiles}
        # With 4+ profiles and 20 samples, we should see at least 2 different ones
        assert len(unique_names) >= 2, "Random profiles not varying enough"

    def test_random_context_profiles_vary(self):
        """Multiple calls to get_random_context_profile should vary."""
        profiles = [get_random_context_profile() for _ in range(20)]
        unique_names = {p.name for p in profiles}
        # With 3+ profiles and 20 samples, we should see at least 2 different ones
        assert len(unique_names) >= 2, "Random context profiles not varying enough"
