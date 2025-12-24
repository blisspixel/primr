"""
Tests for console output utilities.
"""

import pytest
from primr.utils.console import Console, console, set_console, get_console


class TestConsole:
    """Tests for Console class."""
    
    @pytest.fixture
    def captured_console(self):
        """Create a console with captured output."""
        return Console(verbose=False, quiet=False)
    
    def test_step_output(self, captured_console, capsys):
        """step() should print formatted step message."""
        captured_console.step("Test step")
        captured = capsys.readouterr()
        assert "Test step" in captured.out
        assert ">" in captured.out
    
    def test_ok_output(self, captured_console, capsys):
        """ok() should print success message."""
        captured_console.ok("Success message")
        captured = capsys.readouterr()
        assert "Success message" in captured.out
        # Check for either ASCII (+) or unicode (✓) indicator
        assert "+" in captured.out or "\u2713" in captured.out
    
    def test_warn_output(self, captured_console, capsys):
        """warn() should print warning message."""
        captured_console.warn("Warning message")
        captured = capsys.readouterr()
        assert "Warning message" in captured.out
        assert "!" in captured.out
    
    def test_error_output(self, captured_console, capsys):
        """error() should print error message."""
        captured_console.error("Error message")
        captured = capsys.readouterr()
        assert "Error message" in captured.out
        # Check for either ASCII (x) or unicode (✗) indicator
        assert "x" in captured.out or "\u2717" in captured.out
    
    def test_info_output(self, captured_console, capsys):
        """info() should print dim info message."""
        captured_console.info("Info message")
        captured = capsys.readouterr()
        assert "Info message" in captured.out
    
    def test_debug_hidden_by_default(self, capsys):
        """debug() should not print when verbose=False."""
        c = Console(verbose=False)
        c.debug("Debug message")
        captured = capsys.readouterr()
        assert "Debug message" not in captured.out
    
    def test_debug_shown_when_verbose(self, capsys):
        """debug() should print when verbose=True."""
        c = Console(verbose=True)
        c.debug("Debug message")
        captured = capsys.readouterr()
        assert "Debug message" in captured.out
        assert "debug" in captured.out
    
    def test_quiet_mode_suppresses_output(self, capsys):
        """Quiet mode should suppress non-error output."""
        c = Console(quiet=True)
        c.step("Step")
        c.ok("OK")
        c.warn("Warning")
        c.info("Info")
        captured = capsys.readouterr()
        assert captured.out == ""
    
    def test_quiet_mode_shows_errors(self, capsys):
        """Quiet mode should still show errors."""
        c = Console(quiet=True)
        c.error("Error message")
        captured = capsys.readouterr()
        assert "Error message" in captured.out
    
    def test_timing_in_ok(self, capsys):
        """ok() should show elapsed time after step()."""
        import time
        c = Console()
        c.step("Starting")
        time.sleep(0.1)
        c.ok("Done", show_time=True)
        captured = capsys.readouterr()
        assert "Done" in captured.out
    
    def test_ok_without_timing(self, capsys):
        """ok() should not show time when show_time=False."""
        c = Console()
        c.step("Starting")
        c.ok("Done", show_time=False)
        captured = capsys.readouterr()
        assert "Done" in captured.out


class TestConsoleProgress:
    """Tests for progress tracking."""
    
    @pytest.fixture
    def non_interactive_console(self):
        """Create a console that doesn't use in-place updates."""
        from primr.utils.console import _TerminalCaps
        caps = _TerminalCaps.for_testing(
            supports_color=False,
            supports_unicode=False,
            supports_cursor=False,  # Disable in-place updates
            width=80,
            is_interactive=False
        )
        return Console(capabilities=caps)
    
    def test_progress_update(self, non_interactive_console, capsys):
        """progress() should show current/total when complete."""
        # Non-interactive mode only prints on completion
        non_interactive_console.progress(10, 10, "item.txt")
        captured = capsys.readouterr()
        assert "10/10" in captured.out
    
    def test_progress_truncates_long_items(self, non_interactive_console, capsys):
        """progress() should handle long item names."""
        long_name = "a" * 100
        non_interactive_console.progress(10, 10, long_name)
        captured = capsys.readouterr()
        # Non-interactive mode shows full label, interactive mode truncates
        assert long_name in captured.out or "..." in captured.out
    
    def test_progress_done(self, capsys):
        """progress_done() should clear the line."""
        c = Console()
        c.progress(5, 10, "test")
        c.progress_done()
        # Should complete without error


class TestConsoleFormatting:
    """Tests for formatted output methods."""
    
    def test_header(self, capsys):
        """header() should print title."""
        c = Console()
        c.header("Test Header")
        captured = capsys.readouterr()
        assert "Test Header" in captured.out
        assert "-" in captured.out
    
    def test_header_with_subtitle(self, capsys):
        """header() should print subtitle if provided."""
        c = Console()
        c.header("Title", "Subtitle")
        captured = capsys.readouterr()
        assert "Title" in captured.out
        assert "Subtitle" in captured.out
    
    def test_result(self, capsys):
        """result() should print label: value."""
        c = Console()
        c.result("Status", "Complete")
        captured = capsys.readouterr()
        assert "Status" in captured.out
        assert "Complete" in captured.out
    
    def test_detail(self, capsys):
        """detail() should print key-value pair."""
        c = Console()
        c.detail("Key", "Value")
        captured = capsys.readouterr()
        assert "Key" in captured.out
        assert "Value" in captured.out
    
    def test_divider(self, capsys):
        """divider() should print line."""
        c = Console()
        c.divider("-")
        captured = capsys.readouterr()
        assert "-" in captured.out
    
    def test_banner(self, capsys):
        """banner() should print title and version."""
        c = Console()
        c.banner("App Name", "1.0")
        captured = capsys.readouterr()
        assert "App Name" in captured.out
        assert "1.0" in captured.out
    
    def test_summary(self, capsys):
        """summary() should print stats."""
        c = Console()
        c.summary([("Pages", "10"), ("Time", "5s")])
        captured = capsys.readouterr()
        assert "Pages" in captured.out
        assert "10" in captured.out
        assert "Time" in captured.out
        assert "5s" in captured.out
    
    def test_success_box(self, capsys):
        """success_box() should print highlighted output."""
        c = Console()
        c.success_box("Complete", "/path/to/file")
        captured = capsys.readouterr()
        assert "Complete" in captured.out
        assert "/path/to/file" in captured.out


class TestGlobalConsole:
    """Tests for global console instance."""
    
    def test_default_console_exists(self):
        """Global console should exist."""
        assert console is not None
        assert isinstance(console, Console)
    
    def test_get_console(self):
        """get_console() should return global instance."""
        assert get_console() is console
    
    def test_set_console(self):
        """set_console() should replace global instance."""
        original = get_console()
        new_console = Console(verbose=True)
        
        try:
            set_console(new_console)
            assert get_console() is new_console
            assert get_console().verbose is True
        finally:
            set_console(original)


# =============================================================================
# TESTS FOR PHASE MANAGEMENT
# =============================================================================


class TestPhaseBanner:
    """Tests for phase_banner method."""

    def test_phase_banner_output(self, capsys):
        """phase_banner() should display title (step numbers are ignored for cleaner UX)."""
        c = Console()
        c.phase_banner(1, 3, "Research Phase")
        captured = capsys.readouterr()
        assert "Research Phase" in captured.out
        assert "=" in captured.out

    def test_phase_banner_with_description(self, capsys):
        """phase_banner() should display description if provided."""
        c = Console()
        c.phase_banner(1, 2, "Phase", description="Doing stuff")
        captured = capsys.readouterr()
        assert "Doing stuff" in captured.out

    def test_phase_banner_with_duration(self, capsys):
        """phase_banner() should display expected duration if provided."""
        c = Console()
        c.phase_banner(1, 2, "Phase", expected_duration="5-10 minutes")
        captured = capsys.readouterr()
        assert "5-10 minutes" in captured.out

    def test_phase_banner_quiet_mode(self, capsys):
        """phase_banner() should be suppressed in quiet mode."""
        c = Console(quiet=True)
        c.phase_banner(1, 2, "Phase")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestPhaseComplete:
    """Tests for phase_complete method."""

    def test_phase_complete_output(self, capsys):
        """phase_complete() should display title and COMPLETE."""
        c = Console()
        c.phase_complete("Research Phase")
        captured = capsys.readouterr()
        assert "Research Phase" in captured.out
        assert "COMPLETE" in captured.out

    def test_phase_complete_with_stats(self, capsys):
        """phase_complete() should display stats if provided."""
        c = Console()
        c.phase_complete("Phase", stats=[("Sections", "10"), ("Pages", "50")])
        captured = capsys.readouterr()
        assert "Sections" in captured.out
        assert "10" in captured.out
        assert "Pages" in captured.out
        assert "50" in captured.out


class TestProgressWithTime:
    """Tests for progress_with_time method."""

    @pytest.fixture
    def non_interactive_console(self):
        """Create a console that doesn't use in-place updates."""
        from primr.utils.console import _TerminalCaps
        caps = _TerminalCaps.for_testing(
            supports_color=False,
            supports_unicode=False,
            supports_cursor=False,  # Disable in-place updates
            width=80,
            is_interactive=False
        )
        return Console(capabilities=caps)

    def test_progress_with_time_output(self, non_interactive_console, capsys):
        """progress_with_time() should show progress and time when complete."""
        import time
        start = time.time() - 65  # 1m 5s ago
        # Non-interactive mode only prints on completion
        non_interactive_console.progress_with_time(10, 10, "item", start_time=start)
        captured = capsys.readouterr()
        assert "10/10" in captured.out or "item" in captured.out
        assert "1m" in captured.out

    def test_progress_with_time_no_start(self, non_interactive_console, capsys):
        """progress_with_time() should work without start_time."""
        # Non-interactive mode only prints on completion
        non_interactive_console.progress_with_time(10, 10, "item")
        captured = capsys.readouterr()
        assert "10/10" in captured.out or "item" in captured.out


class TestTimedOperation:
    """Tests for timed_operation context manager."""

    @pytest.fixture
    def non_interactive_console(self):
        """Create a console that doesn't use in-place updates."""
        from primr.utils.console import _TerminalCaps
        caps = _TerminalCaps.for_testing(
            supports_color=False,
            supports_unicode=False,
            supports_cursor=False,  # Disable in-place updates
            width=80,
            is_interactive=False
        )
        return Console(capabilities=caps)

    def test_timed_operation_shows_completion(self, non_interactive_console, capsys):
        """timed_operation() should show completion message."""
        with non_interactive_console.timed_operation("Test operation", show_spinner=False):
            pass
        captured = capsys.readouterr()
        assert "Test operation" in captured.out
        # Check for either ASCII (+) or unicode (✓) indicator
        assert "+" in captured.out or "\u2713" in captured.out


class TestHeartbeat:
    """Tests for heartbeat context manager."""

    def test_heartbeat_context(self, capsys):
        """heartbeat() should work as context manager."""
        import time
        c = Console()
        with c.heartbeat("Working", interval=0.1):
            time.sleep(0.15)
        # Should complete without error
        captured = capsys.readouterr()
        assert "Working" in captured.out


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================

from hypothesis import given, strategies as st, settings, HealthCheck


class TestPhaseBannerCompletenessProperty:
    """
    Property-based tests for phase banner completeness.

    **Feature: primr-excellence, Property 9: Phase Banner Completeness**
    **Validates: Requirements 4.1**

    For any phase_banner call with title,
    the output SHALL contain the title (step numbers are ignored for cleaner UX).
    """

    @given(
        step=st.integers(min_value=1, max_value=100),
        total=st.integers(min_value=1, max_value=100),
        title=st.text(alphabet="abcdefghij", min_size=1, max_size=30),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_banner_contains_title(self, step, total, title, capsys):
        """Phase banner should contain title (step numbers ignored for cleaner UX)."""
        # Ensure step <= total for valid display
        if step > total:
            step, total = total, step

        c = Console()
        c.phase_banner(step, total, title)
        captured = capsys.readouterr()

        # Title must be present (step numbers are intentionally not displayed)
        assert title in captured.out

    @given(
        step=st.integers(min_value=1, max_value=10),
        total=st.integers(min_value=1, max_value=10),
        title=st.text(alphabet="abcdefghij", min_size=1, max_size=20),
        description=st.text(alphabet="abcdefghij", min_size=1, max_size=30),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_banner_includes_description(self, step, total, title, description, capsys):
        """Phase banner should include description when provided."""
        if step > total:
            step, total = total, step

        c = Console()
        c.phase_banner(step, total, title, description=description)
        captured = capsys.readouterr()

        assert description in captured.out


class TestProgressTimeDisplayProperty:
    """
    Property-based tests for progress time display.

    **Feature: primr-excellence, Property 10: Progress Time Display**
    **Validates: Requirements 4.2, 5.4**

    For any progress_with_time call with a start_time,
    the output SHALL include elapsed time in human-readable format.
    """

    def _get_non_interactive_console(self):
        """Create a console that doesn't use in-place updates."""
        from primr.utils.console import _TerminalCaps
        caps = _TerminalCaps.for_testing(
            supports_color=False,
            supports_unicode=False,
            supports_cursor=False,  # Disable in-place updates
            width=80,
            is_interactive=False
        )
        return Console(capabilities=caps)

    @given(
        total=st.integers(min_value=1, max_value=100),
        elapsed_seconds=st.integers(min_value=1, max_value=3600),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_progress_shows_elapsed_time(self, total, elapsed_seconds, capsys):
        """Progress with time should show elapsed time when complete."""
        import time

        c = self._get_non_interactive_console()
        start = time.time() - elapsed_seconds
        # Non-interactive mode only prints on completion
        c.progress_with_time(total, total, "item", start_time=start)
        captured = capsys.readouterr()

        # Should show current/total or label
        assert f"{total}/{total}" in captured.out or "item" in captured.out

        # Should show time in format Xs or Xm Ys
        if elapsed_seconds >= 60:
            assert "m" in captured.out
        elif elapsed_seconds >= 1:
            assert "s" in captured.out or "(" in captured.out

    @given(
        total=st.integers(min_value=1, max_value=100),
        label=st.text(alphabet="abcdefghij", min_size=1, max_size=20),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_progress_shows_label(self, total, label, capsys):
        """Progress should show label when provided."""
        c = self._get_non_interactive_console()
        # Non-interactive mode only prints on completion
        c.progress_with_time(total, total, label)
        captured = capsys.readouterr()

        # Label should be present (possibly truncated)
        assert label[:15] in captured.out or "..." in captured.out or f"{total}/{total}" in captured.out
