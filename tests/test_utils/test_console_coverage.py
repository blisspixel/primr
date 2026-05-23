"""Coverage tests for primr.utils.console.

Targets the formatting branches, interactive (cursor) code paths, the
backward-compat API, and the context managers that the existing
test_console.py does not exercise.
"""

from __future__ import annotations

import time

from primr.utils.console import (
    Console,
    Theme,
    _detect_terminal,
    _enable_windows_ansi,
    _TerminalCaps,
)


def _interactive_caps(unicode=True, color=True):
    return _TerminalCaps.for_testing(
        supports_color=color,
        supports_unicode=unicode,
        supports_cursor=True,
        width=80,
        is_interactive=True,
    )


def _noncursor_caps(unicode=False, color=False):
    return _TerminalCaps.for_testing(
        supports_color=color,
        supports_unicode=unicode,
        supports_cursor=False,
        width=80,
        is_interactive=False,
    )


class TestTerminalCaps:
    def test_for_testing_defaults(self):
        caps = _TerminalCaps.for_testing()
        assert caps.supports_color is True
        assert caps.supports_cursor is True
        assert caps.width == 80

    def test_detect_terminal_returns_caps(self):
        caps = _detect_terminal()
        assert isinstance(caps, _TerminalCaps)
        assert caps.width >= 40

    def test_enable_windows_ansi_no_error(self):
        # Should be a no-op or succeed silently on any platform.
        _enable_windows_ansi()


class TestColorAndSymbolSelection:
    def test_color_enabled_when_interactive(self):
        c = Console(capabilities=_interactive_caps(color=True))
        assert c._green == "\033[32m"
        assert c._reset == "\033[0m"

    def test_color_disabled_when_not_interactive(self):
        c = Console(capabilities=_noncursor_caps(color=False))
        assert c._green == ""
        assert c._reset == ""

    def test_unicode_symbols(self):
        c = Console(capabilities=_interactive_caps(unicode=True))
        assert c._check == "✓"
        assert c._arrow == "→"

    def test_ascii_symbols(self):
        c = Console(capabilities=_noncursor_caps(unicode=False))
        assert c._check == "+"
        assert c._arrow == "->"

    def test_term_width_property(self):
        c = Console(capabilities=_interactive_caps())
        assert c.term_width == 80

    def test_theme_property_returns_self(self):
        c = Console(capabilities=_interactive_caps())
        assert c.theme is c

    def test_theme_color_properties(self):
        c = Console(capabilities=_interactive_caps(color=True))
        assert c._green == c.SUCCESS
        assert c._yellow == c.WARNING
        assert c._red == c.ERROR
        assert c._cyan == c.INFO
        assert c._dim == c.MUTED
        assert c._bold == c.BOLD
        assert c._reset == c.RESET
        assert c._check == c.INDICATOR_DONE
        assert c._cross == c.INDICATOR_FAIL


class TestElapsedAndDuration:
    def test_elapsed_zero_start(self):
        c = Console(capabilities=_interactive_caps())
        assert c._elapsed(0) == ""

    def test_elapsed_sub_second(self):
        c = Console(capabilities=_interactive_caps())
        assert c._elapsed(time.time()) == ""

    def test_elapsed_seconds(self):
        c = Console(capabilities=_interactive_caps())
        assert c._elapsed(time.time() - 5) == "5s"

    def test_elapsed_minutes(self):
        c = Console(capabilities=_interactive_caps())
        out = c._elapsed(time.time() - 125)
        assert "m" in out
        assert "s" in out

    def test_elapsed_hours(self):
        c = Console(capabilities=_interactive_caps())
        out = c._elapsed(time.time() - 7200)
        assert out.endswith("m")
        assert "h" in out

    def test_format_duration_zero(self):
        c = Console(capabilities=_interactive_caps())
        assert c._format_duration(0.4) == ""

    def test_format_duration_seconds(self):
        c = Console(capabilities=_interactive_caps())
        assert c._format_duration(30) == "30s"

    def test_format_duration_minutes_with_seconds(self):
        c = Console(capabilities=_interactive_caps())
        assert c._format_duration(90) == "1m 30s"

    def test_format_duration_whole_minutes(self):
        c = Console(capabilities=_interactive_caps())
        assert c._format_duration(120) == "2m"

    def test_format_duration_hours(self):
        c = Console(capabilities=_interactive_caps())
        out = c._format_duration(3700)
        assert out.startswith("1h")


class TestStatusAndInteractive:
    def test_status_interactive_writes_inline(self, capsys):
        c = Console(capabilities=_interactive_caps())
        c.status("scanning")
        out = capsys.readouterr().out
        assert "scanning" in out
        assert "\r" in out

    def test_status_non_interactive_prints(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.status("scanning")
        out = capsys.readouterr().out
        assert "scanning" in out

    def test_status_quiet_suppressed(self, capsys):
        c = Console(quiet=True, capabilities=_interactive_caps())
        c.status("scanning")
        assert capsys.readouterr().out == ""

    def test_clear_line_interactive(self, capsys):
        c = Console(capabilities=_interactive_caps())
        c.clear_line()
        assert "\r" in capsys.readouterr().out

    def test_clear_line_non_interactive_noop(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.clear_line()
        assert capsys.readouterr().out == ""

    def test_found_prints(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.found("Found 47 pages")
        assert "Found 47 pages" in capsys.readouterr().out

    def test_found_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.found("Found 47 pages")
        assert capsys.readouterr().out == ""

    def test_done_prints(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.done("complete")
        assert "complete" in capsys.readouterr().out

    def test_fail_prints_even_in_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.fail("boom")
        assert "boom" in capsys.readouterr().out

    def test_muted_prints(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.muted("dim text")
        assert "dim text" in capsys.readouterr().out

    def test_muted_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.muted("dim text")
        assert capsys.readouterr().out == ""


class TestScrapeProgress:
    def test_scrape_progress_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_interactive_caps())
        c.scrape_progress(1, 10, "/about")
        assert capsys.readouterr().out == ""

    def test_scrape_progress_non_interactive_only_on_complete(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.scrape_progress(3, 10, "/about")
        assert capsys.readouterr().out == ""
        c.scrape_progress(10, 10, "/about", start_time=time.time() - 5)
        out = capsys.readouterr().out
        assert "/about" in out

    def test_scrape_progress_interactive_with_timing_and_eta(self, capsys):
        c = Console(capabilities=_interactive_caps())
        c.scrape_progress(
            3,
            50,
            "/about",
            start_time=time.time() - 8,
            eta_seconds=120,
            ok_count=1,
        )
        out = capsys.readouterr().out
        assert "Scraping 3/50" in out
        assert "ok 1" in out
        assert "elapsed" in out
        assert "left" in out

    def test_scrape_progress_truncates_long_path(self, capsys):
        c = Console(capabilities=_interactive_caps())
        c.scrape_progress(1, 2, "/" + "x" * 300)
        out = capsys.readouterr().out
        assert "..." in out


class TestBackwardCompat:
    def test_grades_color_branches(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.grades([("A", 90), ("B", 75), ("C", 40)])
        out = capsys.readouterr().out
        assert "90" in out
        assert "75" in out
        assert "40" in out
        assert "Quality" in out

    def test_grades_empty(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.grades([])
        assert capsys.readouterr().out == ""

    def test_grades_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.grades([("A", 90)])
        assert capsys.readouterr().out == ""

    def test_blank(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.blank()
        assert capsys.readouterr().out == "\n"

    def test_blank_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.blank()
        assert capsys.readouterr().out == ""

    def test_text(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.text("hello")
        assert "hello" in capsys.readouterr().out

    def test_text_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.text("hello")
        assert capsys.readouterr().out == ""

    def test_result_highlight(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.result("Output", "/tmp/x", highlight=True)
        out = capsys.readouterr().out
        assert "Output" in out
        assert "/tmp/x" in out

    def test_result_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.result("Output", "/tmp/x")
        assert capsys.readouterr().out == ""

    def test_trust_summary(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.trust_summary("Trust", [("Sources", "10")])
        out = capsys.readouterr().out
        assert "Trust" in out
        assert "Sources" in out

    def test_trust_summary_empty_stats(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.trust_summary("Trust", [])
        assert capsys.readouterr().out == ""

    def test_banner_no_version(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.banner("App")
        out = capsys.readouterr().out
        assert "App" in out

    def test_banner_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.banner("App", "1.0")
        assert capsys.readouterr().out == ""

    def test_phase_complete_skips_duration_stat(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.phase_complete("Phase", stats=[("Duration", "5s"), ("Pages", "10")])
        out = capsys.readouterr().out
        assert "Pages" in out
        assert "Duration" not in out

    def test_phase_complete_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.phase_complete("Phase")
        assert capsys.readouterr().out == ""

    def test_phase_banner_no_total(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.phase_banner(2, 0, "Title")
        out = capsys.readouterr().out
        assert "PHASE 2" in out
        assert "/0" not in out

    def test_divider_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.divider()
        assert capsys.readouterr().out == ""

    def test_progress_non_interactive_incomplete_silent(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.progress(5, 10, "x")
        assert capsys.readouterr().out == ""

    def test_progress_interactive_writes(self, capsys):
        c = Console(capabilities=_interactive_caps())
        c.progress(5, 10, "x")
        out = capsys.readouterr().out
        assert "5/10" in out

    def test_progress_interactive_truncates_label(self, capsys):
        c = Console(capabilities=_interactive_caps())
        c.progress(5, 10, "y" * 40)
        out = capsys.readouterr().out
        assert "..." in out

    def test_progress_zero_total(self, capsys):
        c = Console(capabilities=_interactive_caps())
        c.progress(0, 0, "x")
        # 0% with zero total, no crash
        assert "0/0" in capsys.readouterr().out

    def test_progress_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_interactive_caps())
        c.progress(1, 2)
        assert capsys.readouterr().out == ""

    def test_status_with_time_shows_elapsed(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c.status_with_time("working", start_time=time.time() - 5)
        out = capsys.readouterr().out
        assert "working" in out
        assert "5s" in out

    def test_status_with_time_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.status_with_time("working")
        assert capsys.readouterr().out == ""

    def test_status_line_done(self, capsys):
        c = Console(capabilities=_interactive_caps())
        c.status_line_done()
        assert "\r" in capsys.readouterr().out

    def test_warn_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        c.warn("careful")
        assert capsys.readouterr().out == ""


class TestContextManagers:
    def test_spinner_non_interactive(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        with c.spinner("loading") as update:
            update("still loading")
        out = capsys.readouterr().out
        assert "loading" in out

    def test_spinner_quiet_falls_through_to_static(self, capsys):
        # quiet still hits the non-animated branch which prints "<msg>...".
        c = Console(quiet=True, capabilities=_noncursor_caps())
        with c.spinner("loading"):
            pass
        assert "loading" in capsys.readouterr().out

    def test_spinner_interactive_animates(self, capsys):
        c = Console(capabilities=_interactive_caps(unicode=True))
        with c.spinner("loading") as update:
            update("phase two")
            time.sleep(0.25)
        # Spinner thread wrote frames and cleared on exit.
        assert capsys.readouterr().out != ""

    def test_timed_operation_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        with c.timed_operation("op"):
            pass
        assert capsys.readouterr().out == ""

    def test_timed_operation_non_interactive(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        with c.timed_operation("op", show_spinner=True):
            pass
        out = capsys.readouterr().out
        assert "op" in out

    def test_timed_operation_interactive_with_spinner(self, capsys):
        c = Console(capabilities=_interactive_caps())
        with c.timed_operation("op", show_spinner=True):
            time.sleep(0.05)
        out = capsys.readouterr().out
        assert "op" in out

    def test_heartbeat_quiet(self, capsys):
        c = Console(quiet=True, capabilities=_noncursor_caps())
        with c.heartbeat("beat", interval=0.05):
            pass
        assert capsys.readouterr().out == ""

    def test_heartbeat_non_interactive_emits(self, capsys):
        c = Console(capabilities=_noncursor_caps())
        c._last_output_time = time.time() - 100
        with c.heartbeat("beat", interval=0.05):
            time.sleep(0.12)
        out = capsys.readouterr().out
        assert "beat" in out


class TestThemeClass:
    def test_theme_descriptors_resolve(self):
        t = Theme()
        # These delegate to the global console; just confirm attribute access works.
        assert isinstance(t.LINE_H, str)
        assert t.PROG_FILL == "#"
        assert t.INDICATOR_WARN == "!"
        assert isinstance(t.SUCCESS, str)
