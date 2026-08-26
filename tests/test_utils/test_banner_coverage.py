"""Coverage tests for primr.utils.banner.

Targets the gradient/markup rendering helpers, context detection branches,
mode resolution edge cases, the tagline writer, and the static/animated
render paths (with stdout side effects mocked / captured).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from primr.utils.banner import (
    BANNER_ART,
    BannerContext,
    _apply_env_mode,
    _ease_in_out_cubic,
    _precise_sleep,
    _precompute_gradient,
    _print_tagline,
    _render_ansi_frame,
    colorize_banner,
    detect_banner_context,
    maybe_show_startup_banner,
    render_animated_banner,
    render_banner_plain,
    render_banner_static,
    render_static_banner,
    resolve_banner_mode,
    should_show_banner,
)


def _ctx(*, is_tty=True, color=True, unicode=True, cursor=True, truecolor=False) -> BannerContext:
    return BannerContext(
        is_tty=is_tty,
        supports_color=color,
        supports_unicode=unicode,
        supports_cursor=cursor,
        supports_truecolor=truecolor,
    )


class TestEasingAndSleep:
    def test_ease_first_half(self):
        assert _ease_in_out_cubic(0.0) == 0.0
        assert 0.0 < _ease_in_out_cubic(0.25) < 0.5

    def test_ease_second_half(self):
        assert _ease_in_out_cubic(1.0) == 1.0
        assert 0.5 < _ease_in_out_cubic(0.75) < 1.0

    def test_ease_midpoint(self):
        assert abs(_ease_in_out_cubic(0.5) - 0.5) < 1e-9

    def test_precise_sleep_past_target_returns_immediately(self):
        import time

        # Target already in the past -> immediate return.
        _precise_sleep(time.perf_counter() - 1.0)

    def test_precise_sleep_short_busy_wait(self):
        import time

        start = time.perf_counter()
        _precise_sleep(start + 0.001)
        assert time.perf_counter() >= start + 0.0005


class TestContextDetection:
    def test_closed_stdout_falls_back_to_noninteractive(self):
        with patch("sys.stdout") as stdout:
            stdout.isatty.side_effect = OSError("closed")
            stdout.encoding = "utf-8"
            context = detect_banner_context()
        assert context.is_tty is False
        assert context.supports_cursor is False


class TestGradientRendering:
    def test_precompute_gradient_length(self):
        codes = _precompute_gradient(10)
        assert len(codes) == 10
        assert all(c.startswith("\033[1;38;2;") for c in codes)

    def test_precompute_gradient_width_one(self):
        codes = _precompute_gradient(1)
        assert len(codes) == 1

    def test_render_ansi_frame_full_sweep(self):
        lines = ["AB", "CD"]
        codes = _precompute_gradient(2)
        frame = _render_ansi_frame(lines, 2, 1.0, codes, "\033[38;2;96;96;96m")
        assert "A" in frame
        assert "D" in frame
        assert "\n" in frame
        assert frame.endswith("\033[0m")

    def test_render_ansi_frame_handles_spaces(self):
        lines = ["A B"]
        codes = _precompute_gradient(3)
        frame = _render_ansi_frame(lines, 3, 0.5, codes, "\033[38;2;96;96;96m")
        assert " " in frame

    def test_render_ansi_frame_zero_sweep_uses_muted(self):
        lines = ["XY"]
        codes = _precompute_gradient(2)
        muted = "\033[38;2;96;96;96m"
        frame = _render_ansi_frame(lines, 2, 0.0, codes, muted)
        assert muted in frame


class TestColorizeBanner:
    def test_colorize_full_sweep_has_rgb_markup(self):
        out = colorize_banner("AB", sweep_progress=1.0)
        assert "[bold rgb(" in out

    def test_colorize_zero_sweep_muted(self):
        out = colorize_banner("AB", sweep_progress=0.0, muted_color="dim")
        assert "[dim]" in out

    def test_colorize_empty_string(self):
        # "".split("\n") -> [""], max_width becomes 0 -> returns art unchanged.
        out = colorize_banner("")
        assert out == ""

    def test_colorize_preserves_spaces(self):
        out = colorize_banner("A B", sweep_progress=1.0)
        assert " " in out

    def test_render_banner_plain_identity(self):
        assert render_banner_plain(BANNER_ART) == BANNER_ART

    def test_render_banner_static_full_color(self):
        out = render_banner_static(BANNER_ART)
        assert "[bold rgb(" in out


class TestDetectContext:
    def test_detect_returns_context(self):
        ctx = detect_banner_context()
        assert isinstance(ctx, BannerContext)

    def test_truecolor_via_colorterm(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setenv("COLORTERM", "truecolor")
        monkeypatch.delenv("WT_SESSION", raising=False)
        with patch("primr.utils.banner.sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            mock_stdout.encoding = "utf-8"
            ctx = detect_banner_context()
        assert ctx.supports_truecolor is True

    def test_truecolor_via_term_program(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        with patch("primr.utils.banner.sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            mock_stdout.encoding = "utf-8"
            ctx = detect_banner_context()
        assert ctx.supports_truecolor is True

    def test_no_color_env_disables_color(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        with patch("primr.utils.banner.sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            mock_stdout.encoding = "utf-8"
            ctx = detect_banner_context()
        assert ctx.supports_color is False

    def test_dumb_term_disables_cursor(self, monkeypatch):
        monkeypatch.setenv("TERM", "dumb")
        with patch("primr.utils.banner.sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            mock_stdout.encoding = "utf-8"
            ctx = detect_banner_context()
        assert ctx.supports_cursor is False


class TestModeResolution:
    def test_apply_env_mode_valid(self, monkeypatch):
        monkeypatch.setenv("PRIMR_BANNER", "static")
        assert _apply_env_mode("auto") == "static"

    def test_apply_env_mode_invalid_passthrough(self, monkeypatch):
        monkeypatch.setenv("PRIMR_BANNER", "garbage")
        assert _apply_env_mode("animated") == "animated"

    def test_resolve_auto_static_when_no_cursor(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("PRIMR_BANNER", raising=False)
        ctx = _ctx(cursor=False, unicode=False)
        assert resolve_banner_mode("auto", explicit=False, ctx=ctx) == "static"

    def test_resolve_ci_off_when_not_explicit(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("PRIMR_BANNER", raising=False)
        assert resolve_banner_mode("auto", explicit=False, ctx=_ctx()) == "off"

    def test_resolve_ci_ignored_when_explicit(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("PRIMR_BANNER", raising=False)
        assert resolve_banner_mode("static", explicit=True, ctx=_ctx()) == "static"

    def test_resolve_static_off_non_tty_not_explicit(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("PRIMR_BANNER", raising=False)
        ctx = _ctx(is_tty=False)
        assert resolve_banner_mode("static", explicit=False, ctx=ctx) == "off"

    def test_resolve_static_kept_non_tty_when_explicit(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("PRIMR_BANNER", raising=False)
        ctx = _ctx(is_tty=False)
        assert resolve_banner_mode("static", explicit=True, ctx=ctx) == "static"

    def test_should_show_banner_off_mode(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("PRIMR_BANNER", raising=False)
        assert should_show_banner(mode="off", quiet=False, explicit=True, ctx=_ctx()) is False


class TestTagline:
    def test_tagline_color_unicode(self, capsys):
        _print_tagline(_ctx(color=True, unicode=True))
        out = capsys.readouterr().out
        assert "strategic intelligence" in out
        assert "→" in out  # arrow

    def test_tagline_no_color_ascii(self, capsys):
        _print_tagline(_ctx(color=False, unicode=False))
        out = capsys.readouterr().out
        assert "strategic intelligence" in out
        assert "->" in out
        assert "primr --help" in out


class TestRenderPaths:
    def test_render_static_banner_no_color(self):
        with patch("primr.utils.banner.Console") as mock_console_cls:
            mock_console = MagicMock()
            mock_console_cls.return_value = mock_console
            with patch("primr.utils.banner._print_tagline"):
                render_static_banner(_ctx(color=False))
        assert mock_console.print.called

    def test_render_static_banner_with_color(self):
        with patch("primr.utils.banner.Console") as mock_console_cls:
            mock_console = MagicMock()
            mock_console_cls.return_value = mock_console
            with patch("primr.utils.banner._print_tagline"):
                render_static_banner(_ctx(color=True))
        assert mock_console.print.called

    def test_render_animated_falls_back_to_static_without_cursor(self):
        with patch("primr.utils.banner.render_static_banner") as mock_static:
            render_animated_banner(_ctx(cursor=False))
        mock_static.assert_called_once()

    def test_render_animated_invokes_sweep(self):
        with (
            patch("primr.utils.banner.Console") as mock_console_cls,
            patch("primr.utils.banner._animate_sweep") as mock_sweep,
            patch("primr.utils.banner._print_tagline"),
        ):
            mock_console_cls.return_value = MagicMock()
            render_animated_banner(_ctx(), duration_ms=300)
        mock_sweep.assert_called_once()

    def test_render_animated_handles_sweep_exception(self):
        with (
            patch("primr.utils.banner.Console") as mock_console_cls,
            patch("primr.utils.banner._animate_sweep", side_effect=RuntimeError("boom")),
            patch("primr.utils.banner._print_tagline"),
        ):
            mock_console = MagicMock()
            mock_console.file = None
            mock_console_cls.return_value = mock_console
            # Should not raise; falls back to static markup print.
            render_animated_banner(_ctx(), duration_ms=300)


class TestMaybeShowBanner:
    def test_returns_false_when_hidden(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        with patch(
            "primr.utils.banner.detect_banner_context",
            return_value=_ctx(is_tty=False),
        ):
            assert maybe_show_startup_banner(mode="auto") is False

    def test_animated_path_clamps_duration(self, monkeypatch):
        monkeypatch.setenv("PRIMR_BANNER_DURATION_MS", "99999")
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("PRIMR_BANNER", raising=False)
        with (
            patch("primr.utils.banner.detect_banner_context", return_value=_ctx()),
            patch("primr.utils.banner.render_animated_banner") as mock_anim,
        ):
            assert maybe_show_startup_banner(mode="animated", explicit=True) is True
        # Clamped to max 3000.
        _, kwargs = mock_anim.call_args
        assert kwargs["duration_ms"] == 3000

    def test_static_path(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("PRIMR_BANNER", raising=False)
        with (
            patch("primr.utils.banner.detect_banner_context", return_value=_ctx()),
            patch("primr.utils.banner.render_static_banner") as mock_static,
            patch("primr.utils.banner.render_animated_banner") as mock_anim,
        ):
            assert maybe_show_startup_banner(mode="static", explicit=True) is True
        mock_static.assert_called_once()
        mock_anim.assert_not_called()
