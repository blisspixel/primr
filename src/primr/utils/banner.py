"""Static ANSI wordmark for the home screen and explicit banner requests.

Legacy animated modes remain accepted as static aliases. Rendering never
waits, moves the cursor, or emits RGB colors.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

from primr.utils.terminal import stream_is_tty

BANNER_ART = (
    "  ██████╗ ██████╗ ██╗███╗   ███╗██████╗ \n"
    "  ██╔══██╗██╔══██╗██║████╗ ████║██╔══██╗\n"
    "  ██████╔╝██████╔╝██║██╔████╔██║██████╔╝\n"
    "  ██╔═══╝ ██╔══██╗██║██║╚██╔╝██║██╔══██╗\n"
    "  ██║     ██║  ██║██║██║ ╚═╝ ██║██║  ██║\n"
    "  ╚═╝     ╚═╝  ╚═╝╚═╝╚═╝     ╚═╝╚═╝  ╚═╝"
)
_TAGLINE = "strategic intelligence in minutes"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_RESET = "\033[0m"


@dataclass(frozen=True)
class BannerContext:
    is_tty: bool
    supports_color: bool
    supports_unicode: bool
    supports_cursor: bool
    supports_truecolor: bool = False
    width: int = 80


def detect_banner_context() -> BannerContext:
    is_tty = stream_is_tty(sys.stdout)
    usable = is_tty and os.environ.get("TERM", "").lower() != "dumb"
    return BannerContext(
        is_tty=is_tty,
        supports_color=usable and "NO_COLOR" not in os.environ,
        supports_unicode="utf" in (getattr(sys.stdout, "encoding", "") or "").lower(),
        supports_cursor=usable,
        width=shutil.get_terminal_size(fallback=(80, 24)).columns,
    )


def _apply_env_mode(mode: str) -> str:
    value = os.environ.get("PRIMR_BANNER", "").strip().lower()
    return value if value in {"auto", "off", "static", "animated"} else mode


def resolve_banner_mode(mode: str, *, explicit: bool, ctx: BannerContext) -> str:
    resolved = mode if explicit else _apply_env_mode(mode)
    if not explicit:
        disabled = os.environ.get("PRIMR_NO_BANNER", "").lower() in {"1", "true", "yes"}
        if disabled or os.environ.get("CI") or not ctx.is_tty:
            return "off"
        if "NO_COLOR" in os.environ or os.environ.get("TERM", "").lower() == "dumb":
            return "off"
    return "static" if resolved in {"auto", "static", "animated"} else "off"


def should_show_banner(*, mode: str, quiet: bool, explicit: bool, ctx: BannerContext) -> bool:
    return (not quiet or explicit) and resolve_banner_mode(
        mode, explicit=explicit, ctx=ctx
    ) != "off"


def render_banner_plain(art: str) -> str:
    return art


def render_banner_static(art: str) -> str:
    return f"{_CYAN}{art}{_RESET}"


def _print_tagline(ctx: BannerContext) -> None:
    text = f"  {_TAGLINE}"
    sys.stdout.write(f"{_DIM}{text}{_RESET}\n" if ctx.supports_color else text + "\n")


def render_static_banner(ctx: BannerContext) -> None:
    if ctx.width < 60 or not ctx.supports_unicode or not ctx.is_tty:
        name = f"{_CYAN}primr{_RESET}" if ctx.supports_color else "primr"
        tagline = f"{_DIM}{_TAGLINE}{_RESET}" if ctx.supports_color else _TAGLINE
        sys.stdout.write(f"{name}  {tagline}\n")
    else:
        art = render_banner_static(BANNER_ART) if ctx.supports_color else BANNER_ART
        sys.stdout.write(art + "\n")
        _print_tagline(ctx)
    sys.stdout.flush()


def render_animated_banner(ctx: BannerContext, duration_ms: int = 250) -> None:
    """Accept the former renderer entry point without delaying commands."""
    render_static_banner(ctx)


def maybe_show_startup_banner(
    *, mode: str = "auto", quiet: bool = False, explicit: bool = False
) -> bool:
    ctx = detect_banner_context()
    if not should_show_banner(mode=mode, quiet=quiet, explicit=explicit, ctx=ctx):
        return False
    render_static_banner(ctx)
    return True
