"""
Property-based tests for the Console system.

These tests verify visual hierarchy consistency, terminal width respect,
and other console output properties.
"""

import io
import sys
import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import patch

from primr.utils.console import (
    Console,
    INDENT_PHASE,
    INDENT_STEP,
    INDENT_DETAIL,
    INDENT_RESULT,
)
from primr.utils.terminal import TerminalCapabilities
from primr.utils.theme import Theme


class TestVisualHierarchyConsistency:
    """
    **Feature: cli-ux-enhancement, Property 1: Visual Hierarchy Consistency**
    **Validates: Requirements 1.1, 1.3**
    
    For any output message at a given hierarchy level, the output SHALL
    contain the correct indentation and styling for that level.
    """
    
    def _capture_output(self, console_method, *args, **kwargs):
        """Capture console output to a string."""
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            console_method(*args, **kwargs)
        return captured.getvalue()
    
    def _create_test_console(self, quiet: bool = False) -> Console:
        """Create a console for testing with predictable capabilities."""
        caps = TerminalCapabilities.for_testing(
            supports_color=False,  # No color for easier testing
            supports_unicode=False,
            supports_cursor=True,
            width=80,
            is_interactive=True
        )
        return Console(quiet=quiet, capabilities=caps)
    
    @given(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S'),
        blacklist_characters='\n\r'
    )))
    @settings(max_examples=100)
    def test_step_uses_level2_indent(self, message: str):
        """Step output uses Level 2 indentation (2 spaces)."""
        console = self._create_test_console()
        output = self._capture_output(console.step, message)
        
        # Step should start with newline + 2-space indent
        lines = output.split('\n')
        # Find the line with the message
        for line in lines:
            if message in line:
                # Should start with 2-space indent (after any newlines)
                stripped = line.lstrip('\n\r')
                assert stripped.startswith(INDENT_STEP), \
                    f"Step should use {len(INDENT_STEP)}-space indent"
                break
    
    @given(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S'),
        blacklist_characters='\n\r'
    )))
    @settings(max_examples=100)
    def test_info_uses_level3_indent(self, message: str):
        """Info output uses Level 3 indentation (4 spaces)."""
        console = self._create_test_console()
        
        # Clear any in-place output first
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            console.info(message)
        output = captured.getvalue()
        
        # Info clears the line first with \r, then prints with indent
        # Split on \r and take the last part which contains the actual message
        parts = output.split('\r')
        actual_output = parts[-1] if parts else output
        
        # Info should use 4-space indent
        lines = actual_output.split('\n')
        for line in lines:
            if message in line:
                assert line.startswith(INDENT_DETAIL), \
                    f"Info should use {len(INDENT_DETAIL)}-space indent"
                break
    
    @given(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S'),
        blacklist_characters='\n\r'
    )))
    @settings(max_examples=100)
    def test_ok_uses_level4_indent(self, message: str):
        """Ok (result) output uses Level 4 indentation (4 spaces)."""
        console = self._create_test_console()
        output = self._capture_output(console.ok, message, show_time=False)
        
        lines = output.split('\n')
        for line in lines:
            if message in line:
                assert line.startswith(INDENT_RESULT), \
                    f"Ok should use {len(INDENT_RESULT)}-space indent"
                break
    
    @given(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S'),
        blacklist_characters='\n\r'
    )))
    @settings(max_examples=100)
    def test_error_uses_level4_indent(self, message: str):
        """Error output uses Level 4 indentation."""
        console = self._create_test_console()
        output = self._capture_output(console.error, message)
        
        lines = output.split('\n')
        for line in lines:
            if message in line:
                assert line.startswith(INDENT_RESULT), \
                    f"Error should use {len(INDENT_RESULT)}-space indent"
                break
    
    def test_indentation_levels_are_consistent(self):
        """Indentation increases by 2 spaces per level."""
        assert len(INDENT_PHASE) == 0, "Level 1 should have no indent"
        assert len(INDENT_STEP) == 2, "Level 2 should have 2-space indent"
        assert len(INDENT_DETAIL) == 4, "Level 3 should have 4-space indent"
        assert len(INDENT_RESULT) == 4, "Level 4 should have 4-space indent"
    
    def test_quiet_mode_suppresses_non_error_output(self):
        """Quiet mode suppresses info but not errors."""
        console = self._create_test_console(quiet=True)
        
        # Info should be suppressed
        info_output = self._capture_output(console.info, "test info")
        assert info_output == "", "Info should be suppressed in quiet mode"
        
        # Error should still show
        error_output = self._capture_output(console.error, "test error")
        assert "test error" in error_output, "Error should show in quiet mode"


class TestTerminalWidthRespect:
    """
    **Feature: cli-ux-enhancement, Property 3: Terminal Width Respect**
    **Validates: Requirements 1.5, 15.2**
    
    For any terminal width W and any output line, the visible character
    count of that line SHALL not exceed W.
    """
    
    def _create_console_with_width(self, width: int) -> Console:
        """Create console with specific terminal width."""
        caps = TerminalCapabilities.for_testing(
            supports_color=False,
            supports_unicode=False,
            supports_cursor=True,
            width=width,
            is_interactive=True
        )
        return Console(capabilities=caps)
    
    @given(st.integers(min_value=40, max_value=200))
    @settings(max_examples=100)
    def test_divider_respects_width(self, width: int):
        """Divider line respects terminal width."""
        console = self._create_console_with_width(width)
        
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            console.divider()
        output = captured.getvalue()
        
        for line in output.split('\n'):
            if line.strip():
                # Visible length should not exceed width
                visible_len = len(line.rstrip())
                assert visible_len <= width, \
                    f"Divider line ({visible_len}) exceeds width ({width})"
    
    @given(st.integers(min_value=40, max_value=200))
    @settings(max_examples=100)
    def test_phase_banner_respects_width(self, width: int):
        """Phase banner respects terminal width."""
        console = self._create_console_with_width(width)
        
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            console.phase_banner(1, 3, "Test Phase", "Description", "10 min")
        output = captured.getvalue()
        
        for line in output.split('\n'):
            if line.strip():
                visible_len = len(line.rstrip())
                assert visible_len <= width, \
                    f"Phase banner line ({visible_len}) exceeds width ({width})"
    
    @given(
        st.integers(min_value=40, max_value=200),
        st.text(min_size=1, max_size=100, alphabet=st.characters(
            whitelist_categories=('L', 'N'),
            blacklist_characters='\n\r'
        ))
    )
    @settings(max_examples=100)
    def test_truncation_respects_max_length(self, width: int, text: str):
        """Truncation produces strings within max length."""
        console = self._create_console_with_width(width)
        max_len = 25
        
        result = console._truncate(text, max_len)
        
        assert len(result) <= max_len, \
            f"Truncated text ({len(result)}) exceeds max ({max_len})"
        
        if len(text) <= max_len:
            assert result == text, "Short text should not be truncated"
        else:
            assert result.endswith("..."), "Truncated text should end with ..."


class TestConsoleCapabilityAdaptation:
    """Tests for console adapting to terminal capabilities."""
    
    def test_progress_fallback_for_non_interactive(self):
        """Progress falls back to append-only for non-interactive terminals."""
        caps = TerminalCapabilities.for_testing(
            supports_color=False,
            supports_unicode=False,
            supports_cursor=False,  # No cursor = no in-place updates
            width=80,
            is_interactive=False
        )
        console = Console(capabilities=caps)
        
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            console.progress(5, 10, "Test")
            console.progress(10, 10, "Test")  # Only final shows
        output = captured.getvalue()
        
        # Should only show final completion, not in-place updates
        lines = [l for l in output.split('\n') if l.strip()]
        assert len(lines) <= 1, "Non-interactive should not spam progress lines"
    
    def test_spinner_fallback_for_non_interactive(self):
        """Spinner falls back to simple message for non-interactive."""
        caps = TerminalCapabilities.for_testing(
            supports_color=False,
            supports_unicode=False,
            supports_cursor=False,
            width=80,
            is_interactive=False
        )
        console = Console(capabilities=caps)
        
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            with console.spinner("Working"):
                pass
        output = captured.getvalue()
        
        # Should show simple message, not animated spinner
        assert "Working" in output


class TestElapsedTimeFormatting:
    """Tests for elapsed time formatting."""
    
    def _create_test_console(self) -> Console:
        caps = TerminalCapabilities.for_testing(
            supports_color=False,
            supports_unicode=False,
            supports_cursor=True,
            width=80,
            is_interactive=True
        )
        return Console(capabilities=caps)
    
    @given(st.floats(min_value=0, max_value=0.99))
    @settings(max_examples=100)
    def test_no_time_under_1_second(self, elapsed: float):
        """No time shown for operations under 1 second."""
        console = self._create_test_console()
        import time
        console._step_start = time.time() - elapsed
        
        result = console._elapsed(console._step_start)
        assert result == "", f"Should not show time for {elapsed}s"
    
    @given(st.floats(min_value=1, max_value=59.99))
    @settings(max_examples=100)
    def test_seconds_format_under_1_minute(self, elapsed: float):
        """Shows seconds for 1-60 second operations."""
        console = self._create_test_console()
        import time
        console._step_start = time.time() - elapsed
        
        result = console._elapsed(console._step_start)
        assert "s" in result, f"Should show seconds for {elapsed}s"
        assert "m" not in result, f"Should not show minutes for {elapsed}s"
    
    @given(st.floats(min_value=60, max_value=3599))
    @settings(max_examples=100)
    def test_minutes_format_under_1_hour(self, elapsed: float):
        """Shows minutes and seconds for 1-60 minute operations."""
        console = self._create_test_console()
        import time
        console._step_start = time.time() - elapsed
        
        result = console._elapsed(console._step_start)
        assert "m" in result, f"Should show minutes for {elapsed}s"
        assert "h" not in result, f"Should not show hours for {elapsed}s"
    
    @given(st.floats(min_value=3600, max_value=36000))
    @settings(max_examples=100)
    def test_hours_format_over_1_hour(self, elapsed: float):
        """Shows hours and minutes for 1+ hour operations."""
        console = self._create_test_console()
        import time
        console._step_start = time.time() - elapsed
        
        result = console._elapsed(console._step_start)
        assert "h" in result, f"Should show hours for {elapsed}s"
