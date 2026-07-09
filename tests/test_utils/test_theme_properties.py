"""
Property-based tests for the Theme system.

These tests verify that the theme system maintains consistency
across all configurations and terminal capabilities.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.utils.theme import Theme, get_theme

# Status types that must have indicators
STATUS_TYPES = ["active", "done", "fail", "warn", "info", "bullet"]

# Color status types
COLOR_STATUS_TYPES = ["success", "warning", "error", "info", "muted"]


class TestSymbolVocabularyConsistency:
    """
    **Feature: cli-ux-enhancement, Property 2: Symbol Vocabulary Consistency**
    **Validates: Requirements 1.4**

    For any status type, the displayed indicator SHALL match
    the defined symbol for that status type.
    """

    @given(st.sampled_from(STATUS_TYPES))
    @settings(max_examples=100)
    def test_indicator_consistency_default_theme(self, status: str):
        """Each status type maps to a consistent, non-empty indicator."""
        theme = Theme()
        indicator = theme.get_indicator(status)

        # Indicator must be non-empty
        assert indicator, f"Indicator for '{status}' should not be empty"

        # Indicator must be a single character (for alignment)
        assert len(indicator) == 1, f"Indicator for '{status}' should be single char"

        # Same status always returns same indicator
        assert theme.get_indicator(status) == indicator

    @given(st.sampled_from(STATUS_TYPES))
    @settings(max_examples=100)
    def test_indicator_consistency_unicode_theme(self, status: str):
        """Unicode theme also has consistent indicators."""
        theme = Theme.for_terminal(supports_color=True, supports_unicode=True)
        indicator = theme.get_indicator(status)

        assert indicator, f"Unicode indicator for '{status}' should not be empty"
        assert theme.get_indicator(status) == indicator

    @given(st.sampled_from(STATUS_TYPES))
    @settings(max_examples=100)
    def test_indicator_consistency_plain_theme(self, status: str):
        """Plain theme (no color, no unicode) has consistent indicators."""
        theme = Theme.for_terminal(supports_color=False, supports_unicode=False)
        indicator = theme.get_indicator(status)

        assert indicator, f"Plain indicator for '{status}' should not be empty"
        # Plain theme should use ASCII only
        assert indicator.isascii(), "Plain theme indicator should be ASCII"

    @given(st.sampled_from(STATUS_TYPES), st.booleans(), st.booleans())
    @settings(max_examples=100)
    def test_indicator_deterministic(
        self, status: str, supports_color: bool, supports_unicode: bool
    ):
        """Same configuration always produces same indicator."""
        theme1 = Theme.for_terminal(supports_color, supports_unicode)
        theme2 = Theme.for_terminal(supports_color, supports_unicode)

        assert theme1.get_indicator(status) == theme2.get_indicator(status)

    def test_all_status_types_have_unique_indicators(self):
        """Each status type has a distinct indicator (no collisions)."""
        theme = Theme()
        indicators = [theme.get_indicator(s) for s in STATUS_TYPES]

        # All indicators should be unique
        assert len(indicators) == len(set(indicators)), "Status indicators should be unique"

    def test_unknown_status_returns_bullet(self):
        """Unknown status types fall back to bullet indicator."""
        theme = Theme()
        assert theme.get_indicator("unknown") == theme.INDICATOR_BULLET
        assert theme.get_indicator("") == theme.INDICATOR_BULLET
        assert theme.get_indicator("random_status") == theme.INDICATOR_BULLET


class TestColorConsistency:
    """
    Tests for color code consistency across themes.
    """

    @given(st.sampled_from(COLOR_STATUS_TYPES))
    @settings(max_examples=100)
    def test_color_consistency_with_color_support(self, status: str):
        """Color theme returns non-empty color codes."""
        theme = Theme.for_terminal(supports_color=True, supports_unicode=False)
        color = theme.get_status_color(status)

        # Should have color code
        assert color, f"Color for '{status}' should not be empty when colors enabled"
        # Should be ANSI escape sequence
        assert color.startswith("\033["), "Color should be ANSI escape sequence"

    @given(st.sampled_from(COLOR_STATUS_TYPES))
    @settings(max_examples=100)
    def test_no_color_when_disabled(self, status: str):
        """No-color theme returns empty strings for all colors."""
        theme = Theme.for_terminal(supports_color=False, supports_unicode=False)
        color = theme.get_status_color(status)

        assert color == "", f"Color for '{status}' should be empty when colors disabled"

    @given(st.sampled_from(COLOR_STATUS_TYPES))
    @settings(max_examples=100)
    def test_colorize_with_colors(self, status: str):
        """Colorize wraps text with color codes when enabled."""
        theme = Theme.for_terminal(supports_color=True, supports_unicode=False)
        text = "test message"
        result = theme.colorize(text, status)

        # Should contain the original text
        assert text in result
        # Should have color codes
        assert "\033[" in result
        # Should end with reset
        assert result.endswith(theme.RESET)

    @given(st.sampled_from(COLOR_STATUS_TYPES))
    @settings(max_examples=100)
    def test_colorize_without_colors(self, status: str):
        """Colorize returns plain text when colors disabled."""
        theme = Theme.for_terminal(supports_color=False, supports_unicode=False)
        text = "test message"
        result = theme.colorize(text, status)

        # Should be exactly the original text
        assert result == text


class TestAnsiStripping:
    """Tests for ANSI code stripping functionality."""

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=100)
    def test_strip_ansi_preserves_plain_text(self, text: str):
        """Plain text without ANSI codes is unchanged."""
        theme = Theme()
        # Filter out escape characters from generated text
        plain_text = text.replace("\033", "").replace("\x1b", "")
        result = theme.strip_ansi(plain_text)
        assert result == plain_text

    def test_strip_ansi_removes_color_codes(self):
        """ANSI color codes are removed."""
        theme = Theme()
        colored = f"{theme.SUCCESS}success{theme.RESET}"
        result = theme.strip_ansi(colored)
        assert result == "success"
        assert "\033" not in result

    @given(st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_categories=("Cs",))))
    @settings(max_examples=100)
    def test_visible_len_matches_stripped_len(self, text: str):
        """Visible length equals length of stripped text."""
        theme = Theme()
        # Add some color codes
        colored = f"{theme.ERROR}{text}{theme.RESET}"

        visible = theme.visible_len(colored)
        stripped = theme.strip_ansi(colored)

        assert visible == len(stripped)
        assert visible == len(theme.strip_ansi(text))

    def test_visible_len_handles_user_supplied_reset_sequence(self):
        """User text can contain ANSI sequences that are not visible."""
        theme = Theme()
        colored = f"{theme.ERROR}\x1b[m{theme.RESET}"

        assert theme.visible_len(colored) == 0
        assert theme.strip_ansi(colored) == ""


class TestThemeFactory:
    """Tests for theme factory function."""

    @given(st.booleans(), st.booleans())
    @settings(max_examples=100)
    def test_get_theme_returns_valid_theme(self, supports_color: bool, supports_unicode: bool):
        """Factory always returns a valid Theme instance."""
        theme = get_theme(supports_color, supports_unicode)

        assert isinstance(theme, Theme)
        assert theme.has_color == supports_color

    def test_get_theme_caches_common_configs(self):
        """Common configurations return cached instances."""
        # Plain theme should be cached
        plain1 = get_theme(supports_color=False, supports_unicode=False)
        plain2 = get_theme(supports_color=False, supports_unicode=False)
        assert plain1 is plain2

        # Default theme should be cached
        default1 = get_theme(supports_color=True, supports_unicode=False)
        default2 = get_theme(supports_color=True, supports_unicode=False)
        assert default1 is default2
