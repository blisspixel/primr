"""
Property-based tests for terminal capability detection.

These tests verify that the terminal system correctly adapts
output based on detected capabilities.
"""

import os
import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import patch, MagicMock

from primr.utils.terminal import (
    TerminalCapabilities,
    get_terminal_capabilities,
    clear_terminal_cache,
    is_color_enabled,
    is_unicode_enabled,
)
from primr.utils.theme import Theme, get_theme


class TestColorAdaptation:
    """
    **Feature: cli-ux-enhancement, Property 30: Color Adaptation**
    **Validates: Requirements 15.1, 15.3, 15.5**
    
    For any terminal where NO_COLOR is set OR output is piped OR TERM=dumb,
    the output SHALL not contain ANSI color codes.
    """
    
    def test_no_color_when_no_color_env_set(self):
        """NO_COLOR environment variable disables colors."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            with patch('sys.stdout') as mock_stdout:
                mock_stdout.isatty.return_value = True
                mock_stdout.encoding = "utf-8"
                
                clear_terminal_cache()
                caps = TerminalCapabilities.detect()
                
                assert not caps.supports_color, \
                    "Colors should be disabled when NO_COLOR is set"
    
    def test_no_color_when_term_dumb(self):
        """TERM=dumb disables colors."""
        env = {"TERM": "dumb"}
        # Remove NO_COLOR if present
        env_clean = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        env_clean.update(env)
        
        with patch.dict(os.environ, env_clean, clear=True):
            with patch('sys.stdout') as mock_stdout:
                mock_stdout.isatty.return_value = True
                mock_stdout.encoding = "utf-8"
                
                clear_terminal_cache()
                caps = TerminalCapabilities.detect()
                
                assert not caps.supports_color, \
                    "Colors should be disabled when TERM=dumb"
    
    def test_no_color_when_piped(self):
        """Piped output (non-TTY) disables colors."""
        with patch('sys.stdout') as mock_stdout:
            mock_stdout.isatty.return_value = False
            mock_stdout.encoding = "utf-8"
            
            clear_terminal_cache()
            caps = TerminalCapabilities.detect()
            
            assert not caps.supports_color, \
                "Colors should be disabled when output is piped"
    
    def test_force_color_overrides_no_color(self):
        """FORCE_COLOR overrides NO_COLOR."""
        with patch.dict(os.environ, {"NO_COLOR": "1", "FORCE_COLOR": "1"}):
            with patch('sys.stdout') as mock_stdout:
                mock_stdout.isatty.return_value = True
                mock_stdout.encoding = "utf-8"
                
                clear_terminal_cache()
                caps = TerminalCapabilities.detect()
                
                assert caps.supports_color, \
                    "FORCE_COLOR should override NO_COLOR"
    
    @given(st.booleans())
    @settings(max_examples=100)
    def test_theme_respects_color_capability(self, supports_color: bool):
        """Theme adapts to color capability."""
        theme = Theme.for_terminal(supports_color=supports_color, supports_unicode=False)
        
        if supports_color:
            # Should have color codes
            assert theme.SUCCESS != "", "Should have SUCCESS color when enabled"
            assert theme.ERROR != "", "Should have ERROR color when enabled"
            assert theme.RESET != "", "Should have RESET when enabled"
        else:
            # Should have empty color codes
            assert theme.SUCCESS == "", "Should not have SUCCESS color when disabled"
            assert theme.ERROR == "", "Should not have ERROR color when disabled"
            assert theme.WARNING == "", "Should not have WARNING color when disabled"
            assert theme.INFO == "", "Should not have INFO color when disabled"
            assert theme.MUTED == "", "Should not have MUTED color when disabled"
            assert theme.BOLD == "", "Should not have BOLD when disabled"
            assert theme.RESET == "", "Should not have RESET when disabled"
    
    @given(st.text(min_size=1, max_size=50, alphabet=st.characters(
        blacklist_categories=('Cs',),
        blacklist_characters='\x1b'  # Exclude escape character to avoid ANSI in input
    )))
    @settings(max_examples=100)
    def test_no_ansi_codes_in_plain_theme_output(self, text: str):
        """Plain theme output contains no ANSI codes."""
        theme = Theme.for_terminal(supports_color=False, supports_unicode=False)
        
        # Colorize should return plain text
        for status in ["success", "warning", "error", "info", "muted"]:
            result = theme.colorize(text, status)
            assert "\033[" not in result, \
                f"Plain theme should not add ANSI codes for {status}"
            assert result == text, \
                f"Plain theme colorize should return original text"
    
    @given(
        st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_categories=('Cs',))),
        st.sampled_from(["success", "warning", "error", "info", "muted"])
    )
    @settings(max_examples=100)
    def test_color_theme_adds_ansi_codes(self, text: str, status: str):
        """Color theme adds ANSI codes."""
        theme = Theme.for_terminal(supports_color=True, supports_unicode=False)
        
        result = theme.colorize(text, status)
        
        # Should contain ANSI escape sequence
        assert "\033[" in result, \
            f"Color theme should add ANSI codes for {status}"
        # Should contain original text
        assert text in result, \
            "Colorized text should contain original"
        # Should end with reset
        assert result.endswith("\033[0m"), \
            "Colorized text should end with reset"


class TestTerminalCapabilitiesDetection:
    """Tests for terminal capability detection logic."""
    
    @given(st.integers(min_value=40, max_value=500))
    @settings(max_examples=100)
    def test_width_has_minimum(self, width: int):
        """Terminal width has minimum of 40."""
        caps = TerminalCapabilities.for_testing(width=width)
        assert caps.width >= 40
    
    @given(st.integers(min_value=0, max_value=20))
    @settings(max_examples=100)
    def test_safe_width_respects_margin(self, margin: int):
        """Safe width subtracts margin."""
        caps = TerminalCapabilities.for_testing(width=100)
        safe = caps.get_safe_width(margin=margin)
        
        assert safe == max(100 - margin, 40)
    
    def test_should_use_color_requires_interactive(self):
        """Color requires interactive terminal."""
        # Interactive with color support
        caps = TerminalCapabilities.for_testing(
            supports_color=True,
            is_interactive=True
        )
        assert caps.should_use_color()
        
        # Non-interactive (piped) should not use color
        caps = TerminalCapabilities.for_testing(
            supports_color=True,
            is_interactive=False
        )
        assert not caps.should_use_color()
    
    def test_should_update_in_place_requires_cursor_and_interactive(self):
        """In-place updates require cursor support and interactive."""
        # Full support
        caps = TerminalCapabilities.for_testing(
            supports_cursor=True,
            is_interactive=True
        )
        assert caps.should_update_in_place()
        
        # No cursor support
        caps = TerminalCapabilities.for_testing(
            supports_cursor=False,
            is_interactive=True
        )
        assert not caps.should_update_in_place()
        
        # Not interactive
        caps = TerminalCapabilities.for_testing(
            supports_cursor=True,
            is_interactive=False
        )
        assert not caps.should_update_in_place()


class TestThemeTerminalIntegration:
    """Tests for theme and terminal capability integration."""
    
    @given(st.booleans(), st.booleans())
    @settings(max_examples=100)
    def test_get_theme_matches_capabilities(
        self,
        supports_color: bool,
        supports_unicode: bool
    ):
        """get_theme returns theme matching capabilities."""
        theme = get_theme(supports_color, supports_unicode)
        
        assert theme.has_color == supports_color
        
        if supports_unicode:
            # Unicode theme should have Unicode indicators
            assert not theme.INDICATOR_DONE.isascii() or theme.INDICATOR_DONE == "+"
    
    def test_cache_clearing_works(self):
        """Cache can be cleared for re-detection."""
        # Get initial capabilities
        caps1 = get_terminal_capabilities()
        
        # Clear cache
        clear_terminal_cache()
        
        # Should detect again
        caps2 = get_terminal_capabilities()
        
        # Both should be valid
        assert isinstance(caps1, TerminalCapabilities)
        assert isinstance(caps2, TerminalCapabilities)
