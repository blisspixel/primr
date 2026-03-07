from unittest.mock import patch

from primr.utils.banner import (
    BannerContext,
    maybe_show_startup_banner,
    resolve_banner_mode,
    should_show_banner,
)


def _ctx(*, is_tty: bool = True, unicode: bool = True, cursor: bool = True) -> BannerContext:
    return BannerContext(
        is_tty=is_tty,
        supports_color=True,
        supports_unicode=unicode,
        supports_cursor=cursor,
    )


def test_resolve_banner_mode_auto_animated(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    assert resolve_banner_mode("auto", explicit=False, ctx=_ctx()) == "animated"


def test_resolve_banner_mode_auto_off_non_tty():
    assert resolve_banner_mode("auto", explicit=False, ctx=_ctx(is_tty=False)) == "off"


def test_should_show_banner_honors_quiet_unless_explicit():
    assert should_show_banner(mode="auto", quiet=True, explicit=False, ctx=_ctx()) is False
    assert should_show_banner(mode="static", quiet=True, explicit=True, ctx=_ctx()) is True


def test_resolve_banner_mode_honors_env_disable_when_not_explicit(monkeypatch):
    monkeypatch.setenv("PRIMR_NO_BANNER", "1")
    assert resolve_banner_mode("auto", explicit=False, ctx=_ctx()) == "off"


def test_maybe_show_startup_banner_static_path():
    with patch("primr.utils.banner.detect_banner_context", return_value=_ctx()), \
         patch("primr.utils.banner.render_static_banner") as mock_static, \
         patch("primr.utils.banner.render_animated_banner") as mock_animated:
        shown = maybe_show_startup_banner(mode="static", quiet=False, explicit=True)
        assert shown is True
        mock_static.assert_called_once()
        mock_animated.assert_not_called()
