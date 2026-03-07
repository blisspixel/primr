"""Startup banner rendering for Primr CLI.

Design goals:
- Default-on for interactive terminals
- Non-intrusive and short
- Safe fallbacks for non-TTY, CI, and accessibility contexts
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class BannerContext:
    is_tty: bool
    supports_color: bool
    supports_unicode: bool
    supports_cursor: bool


def detect_banner_context() -> BannerContext:
    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    no_color = os.environ.get("NO_COLOR") is not None
    term_dumb = os.environ.get("TERM", "").lower() == "dumb"
    supports_color = is_tty and not no_color and not term_dumb
    encoding = getattr(sys.stdout, "encoding", "") or ""
    supports_unicode = "utf" in encoding.lower()
    supports_cursor = is_tty and not term_dumb
    return BannerContext(
        is_tty=is_tty,
        supports_color=supports_color,
        supports_unicode=supports_unicode,
        supports_cursor=supports_cursor,
    )


def _apply_env_mode(mode: str) -> str:
    env_mode = os.environ.get("PRIMR_BANNER", "").strip().lower()
    if env_mode in {"auto", "off", "static", "animated"}:
        return env_mode
    return mode


def resolve_banner_mode(mode: str, *, explicit: bool, ctx: BannerContext) -> str:
    resolved = mode
    if not explicit:
        resolved = _apply_env_mode(resolved)

    if os.environ.get("PRIMR_NO_BANNER") in {"1", "true", "TRUE", "yes", "YES"} and not explicit:
        return "off"

    if os.environ.get("CI") and not explicit:
        return "off"

    if resolved == "auto":
        if not ctx.is_tty:
            return "off"
        if ctx.supports_cursor and ctx.supports_unicode:
            return "animated"
        return "static"

    if resolved in {"static", "animated"} and not ctx.is_tty and not explicit:
        return "off"

    return resolved


def should_show_banner(*, mode: str, quiet: bool, explicit: bool, ctx: BannerContext) -> bool:
    if quiet and not explicit:
        return False
    resolved = resolve_banner_mode(mode, explicit=explicit, ctx=ctx)
    return resolved in {"static", "animated"}


def _theme(ctx: BannerContext) -> dict[str, str]:
    if not ctx.supports_color:
        return {"accent": "", "dim": "", "reset": "", "bold": ""}
    return {
        "accent": "\033[36m",
        "dim": "\033[2m",
        "reset": "\033[0m",
        "bold": "\033[1m",
    }


def _frame_lines(ctx: BannerContext, spinner: str | None = None) -> list[str]:
    t = _theme(ctx)
    dot = "·" if ctx.supports_unicode else "."
    spin = f" {spinner}" if spinner else ""

    if ctx.supports_unicode:
        return [
            f"{t['accent']}┌──────────────────────────────────────────┐{t['reset']}",
            f"{t['accent']}│{t['reset']} {t['bold']}primr{t['reset']} {t['dim']}{dot} strategic intelligence in minutes{t['reset']} {t['accent']}│{t['reset']}",
            f"{t['accent']}│{t['reset']} URL {dot}> brief {dot}> strategy{spin:<16}{t['accent']}│{t['reset']}",
            f"{t['accent']}└──────────────────────────────────────────┘{t['reset']}",
        ]

    return [
        "+------------------------------------------+",
        "| primr . strategic intelligence in minutes |",
        f"| URL -> brief -> strategy{spin:<14}|",
        "+------------------------------------------+",
    ]


def render_static_banner(ctx: BannerContext) -> None:
    for line in _frame_lines(ctx):
        print(line)
    sys.stdout.flush()


def render_animated_banner(ctx: BannerContext, duration_ms: int = 900) -> None:
    spinners = ["|", "/", "-", "\\"] if not ctx.supports_unicode else ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    if not ctx.supports_cursor:
        render_static_banner(ctx)
        return

    start = time.time()
    frame_idx = 0
    fps = 14
    frame_delay = 1.0 / fps
    first = True

    while (time.time() - start) * 1000 < duration_ms:
        lines = _frame_lines(ctx, spinners[frame_idx % len(spinners)])
        if not first:
            sys.stdout.write(f"\033[{len(lines)}A")
        first = False
        for line in lines:
            sys.stdout.write("\033[2K\r" + line + "\n")
        sys.stdout.flush()
        time.sleep(frame_delay)
        frame_idx += 1


def maybe_show_startup_banner(*, mode: str = "auto", quiet: bool = False, explicit: bool = False) -> bool:
    """Render startup banner if conditions allow.

    Returns True when a banner was rendered.
    """
    ctx = detect_banner_context()
    if not should_show_banner(mode=mode, quiet=quiet, explicit=explicit, ctx=ctx):
        return False

    resolved = resolve_banner_mode(mode, explicit=explicit, ctx=ctx)
    if resolved == "animated":
        duration = int(os.environ.get("PRIMR_BANNER_DURATION_MS", "900"))
        duration = max(250, min(duration, 3000))
        render_animated_banner(ctx, duration_ms=duration)
    else:
        render_static_banner(ctx)

    return True
