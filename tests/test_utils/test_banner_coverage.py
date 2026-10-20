"""Static banner capabilities, fallbacks, and escape-sequence contract."""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from primr.utils.banner import (
    BANNER_ART,
    BannerContext,
    detect_banner_context,
    maybe_show_startup_banner,
    render_animated_banner,
    render_banner_plain,
    render_static_banner,
    resolve_banner_mode,
)


def _ctx(**kwargs):
    values = {
        "is_tty": True,
        "supports_color": True,
        "supports_unicode": True,
        "supports_cursor": True,
    }
    return BannerContext(**(values | kwargs))


def test_closed_stdout_falls_back_to_noninteractive():
    with patch("sys.stdout") as stdout:
        stdout.isatty.side_effect = OSError("closed")
        stdout.encoding = "utf-8"
        context = detect_banner_context()
    assert not context.is_tty
    assert not context.supports_cursor


@pytest.mark.parametrize("mode", ["auto", "static", "animated"])
def test_all_enabled_modes_resolve_to_static(mode):
    assert resolve_banner_mode(mode, explicit=True, ctx=_ctx()) == "static"


@pytest.mark.parametrize(
    "env",
    [
        {"CI": "1"},
        {"NO_COLOR": ""},
        {"TERM": "dumb"},
        {"PRIMR_NO_BANNER": "yes"},
        {"PRIMR_BANNER": "off"},
    ],
)
def test_automatic_banner_respects_environment(env, monkeypatch):
    for key in ("CI", "NO_COLOR", "TERM", "PRIMR_NO_BANNER", "PRIMR_BANNER"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert resolve_banner_mode("auto", explicit=False, ctx=_ctx()) == "off"


@pytest.mark.parametrize("changes", [{"width": 40}, {"supports_unicode": False}, {"is_tty": False}])
def test_small_or_limited_terminals_get_one_line(changes, capsys):
    render_static_banner(_ctx(**changes))
    text = capsys.readouterr().out
    assert len(text.splitlines()) == 1
    assert "primr" in text
    assert "strategic intelligence in minutes" in text
    assert "█" not in text


def test_banner_only_uses_cyan_dim_and_reset(capsys):
    render_static_banner(_ctx())
    text = capsys.readouterr().out
    escapes = re.findall(r"\x1b\[[0-9;]*[A-Za-z]", text)
    assert set(escapes) == {"\x1b[36m", "\x1b[2m", "\x1b[0m"}
    assert BANNER_ART in text
    assert "\r" not in text
    assert "38;2" not in text


def test_plain_render_has_no_escapes(capsys):
    assert render_banner_plain(BANNER_ART) == BANNER_ART
    render_static_banner(_ctx(supports_color=False))
    assert "\x1b" not in capsys.readouterr().out


def test_legacy_animation_entry_point_does_not_wait(capsys):
    with patch("time.sleep", side_effect=AssertionError("banner must not wait")):
        render_animated_banner(_ctx(), duration_ms=10000)
    assert BANNER_ART in capsys.readouterr().out


def test_quiet_banner_is_not_rendered():
    with patch("primr.utils.banner.render_static_banner") as render:
        assert not maybe_show_startup_banner(quiet=True)
    render.assert_not_called()
