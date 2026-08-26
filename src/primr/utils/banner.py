"""
Animated ASCII banner for Primr CLI.

Renders a gradient-colored wordmark with optional sweep animation,
ported from Scribe CLI's banner engine.

The animation engine bypasses Rich's rendering pipeline during playback,
writing pre-rendered ANSI escape strings directly to stdout at 60fps
with precise timing (hybrid sleep + busy-wait to defeat Windows timer
granularity).

Env overrides:
  PRIMR_BANNER             auto | off | static | animated
  PRIMR_NO_BANNER          1 | true | yes  ->  disable
  PRIMR_BANNER_DURATION_MS 250-3000 (default 1500)
  NO_COLOR                 disables all color (standard)
  CI                       auto-disables banner
"""

from __future__ import annotations

import colorsys
import os
import sys
import time
from dataclasses import dataclass

from rich.console import Console
from rich.markup import escape
from rich.text import Text

from primr.utils.terminal import stream_is_tty

# ─── ASCII Wordmark ─────────────────────────────────────────────────────
# ANSI Shadow block font — bold 6-line design.
# Uses █ (full block) for fills and ╔═╗║╚╝ (double-line box-drawing) for edges.

BANNER_ART = (
    "  ██████╗ ██████╗ ██╗███╗   ███╗██████╗ \n"
    "  ██╔══██╗██╔══██╗██║████╗ ████║██╔══██╗\n"
    "  ██████╔╝██████╔╝██║██╔████╔██║██████╔╝\n"
    "  ██╔═══╝ ██╔══██╗██║██║╚██╔╝██║██╔══██╗\n"
    "  ██║     ██║  ██║██║██║ ╚═╝ ██║██║  ██║\n"
    "  ╚═╝     ╚═╝  ╚═╝╚═╝╚═╝     ╚═╝╚═╝  ╚═╝"
)

# Brand hue range: cyan (180deg) to magenta (320deg)
_START_HUE = 180 / 360
_END_HUE = 320 / 360
_MUTED_COLOR = "dim"

_TAGLINE = "strategic intelligence in minutes"

# ANSI escape constants
_ANSI_RESET = "\033[0m"
_ANSI_HIDE_CURSOR = "\033[?25l"
_ANSI_SHOW_CURSOR = "\033[?25h"
_DIM = "\033[2m"

# Animation: 60fps for buttery smooth playback
_ANIM_FPS = 60
_ANIM_FRAME_TIME = 1.0 / _ANIM_FPS


# ─── Context Detection ──────────────────────────────────────────────────


@dataclass(frozen=True)
class BannerContext:
    is_tty: bool
    supports_color: bool
    supports_unicode: bool
    supports_cursor: bool
    supports_truecolor: bool = False


def detect_banner_context() -> BannerContext:
    is_tty = stream_is_tty(sys.stdout)
    no_color = os.environ.get("NO_COLOR") is not None
    term_dumb = os.environ.get("TERM", "").lower() == "dumb"
    supports_color = is_tty and not no_color and not term_dumb
    encoding = getattr(sys.stdout, "encoding", "") or ""
    supports_unicode = "utf" in encoding.lower()
    supports_cursor = is_tty and not term_dumb

    supports_truecolor = False
    if supports_color:
        colorterm = os.environ.get("COLORTERM", "").lower()
        if colorterm in ("truecolor", "24bit") or os.environ.get("WT_SESSION"):
            supports_truecolor = True
        else:
            tp = os.environ.get("TERM_PROGRAM", "").lower()
            if tp in ("iterm.app", "wezterm", "hyper", "vscode", "ghostty"):
                supports_truecolor = True

    return BannerContext(
        is_tty=is_tty,
        supports_color=supports_color,
        supports_unicode=supports_unicode,
        supports_cursor=supports_cursor,
        supports_truecolor=supports_truecolor,
    )


# ─── Mode Resolution ────────────────────────────────────────────────────


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


# ─── Timing ──────────────────────────────────────────────────────────────


def _ease_in_out_cubic(t: float) -> float:
    """Ease-in-out cubic for smooth animation acceleration and deceleration."""
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def _precise_sleep(target_time: float) -> None:
    """Sleep until target_time with sub-millisecond precision.

    Windows time.sleep() has ~15.6ms granularity, so a 16.7ms request
    actually sleeps ~31ms. This hybrid approach sleeps for the bulk,
    then busy-waits the final 2ms for precise frame timing.
    """
    remaining = target_time - time.perf_counter()
    if remaining <= 0:
        return
    if remaining > 0.002:
        time.sleep(remaining - 0.002)
    while time.perf_counter() < target_time:
        pass


# ─── Raw ANSI Frame Rendering ───────────────────────────────────────────


def _precompute_gradient(max_width: int) -> list[str]:
    """Pre-compute bold RGB ANSI codes for each column position."""
    codes: list[str] = []
    for col in range(max_width):
        col_ratio = col / max(1, max_width - 1)
        hue = _START_HUE + (_END_HUE - _START_HUE) * col_ratio
        r, g, b = [int(v * 255) for v in colorsys.hsv_to_rgb(hue % 1.0, 0.85, 0.92)]
        codes.append(f"\033[1;38;2;{r};{g};{b}m")
    return codes


def _render_ansi_frame(
    lines: list[str],
    max_width: int,
    sweep_progress: float,
    gradient_codes: list[str],
    muted_code: str,
) -> str:
    """Render one animation frame as a raw ANSI escape string.

    Tracks the last-emitted color code and only emits a new code
    when the color actually changes, reducing output size.
    """
    parts: list[str] = []
    for line_idx, line in enumerate(lines):
        if line_idx > 0:
            parts.append("\n")
        last_code: str | None = None
        for col, ch in enumerate(line):
            if ch == " ":
                parts.append(" ")
                last_code = None
                continue

            col_ratio = col / max(1, max_width - 1)
            code = gradient_codes[col] if col_ratio <= sweep_progress else muted_code

            if code != last_code:
                parts.append(code)
                last_code = code
            parts.append(ch)

        parts.append(_ANSI_RESET)

    return "".join(parts)


# ─── Rich Markup Rendering (static output) ──────────────────────────────


def colorize_banner(
    art: str,
    sweep_progress: float = 1.0,
    start_hue: float = _START_HUE,
    end_hue: float = _END_HUE,
    muted_color: str = _MUTED_COLOR,
) -> str:
    """
    Apply gradient coloring to ASCII art with sweep position.

    Args:
        art: Multi-line ASCII art string.
        sweep_progress: 0.0 (all muted) to 1.0 (fully colored).
        start_hue: Starting hue for gradient (0.0-1.0).
        end_hue: Ending hue for gradient (0.0-1.0).
        muted_color: Rich color string for characters not yet swept.

    Returns:
        Rich markup string with per-character gradient coloring.
    """
    lines = art.split("\n")
    if not lines:
        return ""

    max_width = max(len(line) for line in lines)
    if max_width == 0:
        return art

    result_lines: list[str] = []
    for line in lines:
        parts: list[str] = []
        for col, ch in enumerate(line):
            if ch == " ":
                parts.append(" ")
                continue

            col_ratio = col / max(1, max_width - 1)

            if col_ratio <= sweep_progress:
                hue = start_hue + (end_hue - start_hue) * col_ratio
                r, g, b = [int(v * 255) for v in colorsys.hsv_to_rgb(hue % 1.0, 0.85, 0.92)]
                parts.append(f"[bold rgb({r},{g},{b})]{escape(ch)}[/]")
            else:
                parts.append(f"[{muted_color}]{escape(ch)}[/{muted_color}]")

        result_lines.append("".join(parts))

    return "\n".join(result_lines)


def render_banner_plain(art: str) -> str:
    """Return banner as plain text with no color markup."""
    return art


def render_banner_static(art: str) -> str:
    """Return banner with full gradient applied (sweep_progress=1.0)."""
    return colorize_banner(art, sweep_progress=1.0)


# ─── Tagline ─────────────────────────────────────────────────────────────


def _print_tagline(ctx: BannerContext) -> None:
    """Print the tagline and help hint below the banner."""
    flow = (
        "URL \u2192 brief \u2192 strategy" if ctx.supports_unicode else "URL -> brief -> strategy"
    )
    sep = "\u00b7" if ctx.supports_unicode else "-"
    if ctx.supports_color:
        print(f"  {_DIM}{_TAGLINE}  {sep}  {flow}{_ANSI_RESET}")
        print(f"  {_DIM}primr --help for commands{_ANSI_RESET}")
    else:
        print(f"  {_TAGLINE}  {sep}  {flow}")
        print("  primr --help for commands")
    print()
    sys.stdout.flush()


# ─── Banner Display ─────────────────────────────────────────────────────


def render_static_banner(ctx: BannerContext) -> None:
    """Display the banner with static gradient via Rich markup."""
    console = Console()
    console.print()

    if not ctx.supports_color:
        console.print(render_banner_plain(BANNER_ART))
    else:
        console.print(Text.from_markup(render_banner_static(BANNER_ART)))

    _print_tagline(ctx)


def render_animated_banner(ctx: BannerContext, duration_ms: int = 1500) -> None:
    """Display the banner with animated gradient sweep.

    Falls back to static if the terminal lacks cursor or color support.
    """
    if not ctx.supports_cursor or not ctx.supports_color:
        render_static_banner(ctx)
        return

    console = Console()
    console.print()

    try:
        _animate_sweep(console, BANNER_ART, duration=duration_ms / 1000.0)
    except Exception:
        # Ensure cursor is visible on any error
        try:
            out = console.file or sys.stdout
            out.write(_ANSI_SHOW_CURSOR + _ANSI_RESET + "\n")
            out.flush()
        except Exception:
            pass
        # Fall back to static banner via Rich
        console.print(Text.from_markup(render_banner_static(BANNER_ART)))

    _print_tagline(ctx)


def _animate_sweep(
    console: Console,
    art: str,
    duration: float = 1.5,
) -> None:
    """Animate a gradient sweep at 60fps using direct ANSI output.

    Bypasses Rich's rendering pipeline during animation for maximum
    smoothness. Pre-renders all frames as raw ANSI escape strings,
    then plays them back with precise timing and cursor repositioning.
    """
    lines = art.split("\n")
    num_lines = len(lines)
    max_width = max(len(line) for line in lines)
    total_frames = max(2, int(duration * _ANIM_FPS))

    # Pre-compute gradient ANSI codes (shared across all frames)
    gradient_codes = _precompute_gradient(max_width)
    muted_code = "\033[38;2;96;96;96m"

    # Pre-render every frame as a raw ANSI string
    frames: list[str] = []
    for f in range(total_frames + 1):
        progress = f / total_frames
        eased = _ease_in_out_cubic(progress)
        frames.append(_render_ansi_frame(lines, max_width, eased, gradient_codes, muted_code))

    out = console.file or sys.stdout
    cursor_up = f"\033[{num_lines - 1}A\r"

    # Hide cursor and render first frame
    out.write(_ANSI_HIDE_CURSOR)
    out.write(frames[0])
    out.flush()

    # Play remaining frames with precise timing
    start = time.perf_counter()
    for i in range(1, len(frames)):
        _precise_sleep(start + i * _ANIM_FRAME_TIME)
        out.write(cursor_up)
        out.write(frames[i])
        out.flush()

    # Show cursor and move to next line
    out.write(_ANSI_SHOW_CURSOR + "\n")
    out.flush()


# ─── Public Entry Point ─────────────────────────────────────────────────


def maybe_show_startup_banner(
    *,
    mode: str = "auto",
    quiet: bool = False,
    explicit: bool = False,
) -> bool:
    """Render the startup banner if conditions allow.

    Returns True when a banner was actually rendered.
    """
    ctx = detect_banner_context()
    if not should_show_banner(mode=mode, quiet=quiet, explicit=explicit, ctx=ctx):
        return False

    resolved = resolve_banner_mode(mode, explicit=explicit, ctx=ctx)
    if resolved == "animated":
        try:
            duration = int(os.environ.get("PRIMR_BANNER_DURATION_MS", "1500"))
        except (TypeError, ValueError):
            duration = 1500
        duration = max(250, min(duration, 3000))
        render_animated_banner(ctx, duration_ms=duration)
    else:
        render_static_banner(ctx)

    return True
