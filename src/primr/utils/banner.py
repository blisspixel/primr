"""Startup banner rendering for Primr CLI.

Big, blocky ASCII art logo with horizontal color gradient — inspired by
Gemini CLI and GitHub Copilot CLI.

Rendering pipeline (each layer falls back to the next):
  1. Truecolor (24-bit) gradient  — smooth cyan→blue→purple→magenta
  2. 256-color approximation      - 8-stop gradient via 6x6x6 cube
  3. 4-bit ANSI                   — 4-band color sweep
  4. No color                     — plain block/ASCII characters
  5. ASCII-only                   — # characters instead of █

Platform handling:
  - Windows: VT100 processing enabled by console.py; WT_SESSION detected
  - macOS:   COLORTERM / TERM_PROGRAM checked (iTerm, Terminal.app)
  - Linux:   COLORTERM checked (gnome-terminal, konsole, xfce4-terminal)
  - SSH:     Gracefully degrades; TERM=dumb disables everything
  - CI:      Auto-disabled (CI env var)
  - Screen readers: --no-banner / PRIMR_NO_BANNER respected

Env overrides:
  PRIMR_BANNER             auto | off | static | animated
  PRIMR_NO_BANNER          1 | true | yes  →  disable
  PRIMR_BANNER_DURATION_MS 250-3000 (default 1500)
  NO_COLOR                 disables all color (standard)
  CI                       auto-disables banner
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Context detection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BannerContext:
    is_tty: bool
    supports_color: bool
    supports_unicode: bool
    supports_cursor: bool
    supports_truecolor: bool = False


def detect_banner_context() -> BannerContext:
    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    no_color = os.environ.get("NO_COLOR") is not None
    term_dumb = os.environ.get("TERM", "").lower() == "dumb"
    supports_color = is_tty and not no_color and not term_dumb
    encoding = getattr(sys.stdout, "encoding", "") or ""
    supports_unicode = "utf" in encoding.lower()
    supports_cursor = is_tty and not term_dumb

    supports_truecolor = False
    if supports_color:
        colorterm = os.environ.get("COLORTERM", "").lower()
        if colorterm in ("truecolor", "24bit"):
            supports_truecolor = True
        elif os.environ.get("WT_SESSION"):
            # Windows Terminal always supports truecolor
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


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Horizontal gradient:  cyan → blue → purple → magenta
# ---------------------------------------------------------------------------

_GRADIENT_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.00, (0, 215, 255)),     # cyan
    (0.30, (80, 140, 255)),    # blue
    (0.60, (170, 100, 245)),   # purple
    (1.00, (255, 70, 200)),    # magenta / pink
]

# Pre-computed 256-color stops (nearest matches in the 6x6x6 cube)
_GRADIENT_256: list[tuple[float, int]] = [
    (0.00, 45),   # cyan
    (0.15, 39),   # blue-cyan
    (0.30, 75),   # blue
    (0.45, 111),  # periwinkle
    (0.60, 141),  # lavender
    (0.75, 177),  # light purple
    (0.90, 176),  # mauve
    (1.00, 169),  # hot pink
]

# 4-bit fallback (broadest compatibility)
_GRADIENT_4BIT = [
    "\033[96m",  # bright cyan
    "\033[94m",  # bright blue
    "\033[95m",  # bright magenta
    "\033[35m",  # magenta
]

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def _lerp_rgb(t: float) -> tuple[int, int, int]:
    """Interpolate RGB at position *t* (0.0-1.0) across gradient stops."""
    t = max(0.0, min(1.0, t))
    for i in range(len(_GRADIENT_STOPS) - 1):
        t0, c0 = _GRADIENT_STOPS[i]
        t1, c1 = _GRADIENT_STOPS[i + 1]
        if t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return (
                int(c0[0] + (c1[0] - c0[0]) * f),
                int(c0[1] + (c1[1] - c0[1]) * f),
                int(c0[2] + (c1[2] - c0[2]) * f),
            )
    return _GRADIENT_STOPS[-1][1]


def _lerp_256(t: float) -> int:
    """Nearest 256-color code for position *t*."""
    t = max(0.0, min(1.0, t))
    for i in range(len(_GRADIENT_256) - 1):
        t0, _ = _GRADIENT_256[i]
        t1, _ = _GRADIENT_256[i + 1]
        if t <= (t0 + t1) / 2:
            return _GRADIENT_256[i][1]
    return _GRADIENT_256[-1][1]


def _color_at(col: int, width: int, ctx: BannerContext) -> str:
    """ANSI color escape for column *col* within a line of *width* chars."""
    if not ctx.supports_color:
        return ""
    t = col / max(width - 1, 1)
    if ctx.supports_truecolor:
        r, g, b = _lerp_rgb(t)
        return f"\033[1;38;2;{r};{g};{b}m"
    # Try 256-color (supported almost everywhere except TERM=dumb)
    code256 = _lerp_256(t)
    return f"\033[1;38;5;{code256}m"


def _color_at_4bit(col: int, width: int) -> str:
    """4-bit fallback when we know only 16 colors are safe."""
    t = col / max(width - 1, 1)
    idx = min(int(t * len(_GRADIENT_4BIT)), len(_GRADIENT_4BIT) - 1)
    return _GRADIENT_4BIT[idx]


# ---------------------------------------------------------------------------
# Logo art  (7 rows x 54 columns)
#
# Block chars for unicode terminals, # for ASCII.
# Each letter: P(8) R(8) I(8) M(10) R(8) with 3-col gaps.
# ---------------------------------------------------------------------------

_LOGO_BLOCKS = [
    "████████   ████████   ████████   ██      ██   ████████",
    "██    ██   ██    ██      ██      ███    ███   ██    ██",
    "██    ██   ██    ██      ██      ████  ████   ██    ██",
    "████████   ████████      ██      ██ ████ ██   ████████",
    "██         ██  ██        ██      ██  ██  ██   ██  ██  ",
    "██         ██   ██       ██      ██      ██   ██   ██ ",
    "██         ██    ██   ████████   ██      ██   ██    ██",
]

_LOGO_ASCII = [
    "########   ########   ########   ##      ##   ########",
    "##    ##   ##    ##      ##      ###    ###   ##    ##",
    "##    ##   ##    ##      ##      ####  ####   ##    ##",
    "########   ########      ##      ## #### ##   ########",
    "##         ##  ##        ##      ##  ##  ##   ##  ##  ",
    "##         ##   ##       ##      ##      ##   ##   ## ",
    "##         ##    ##   ########   ##      ##   ##    ##",
]

_LOGO_WIDTH = 54

_TAGLINE = "strategic intelligence in minutes"
_FLOW_UNICODE = "URL \u2192 brief \u2192 strategy"
_FLOW_ASCII = "URL -> brief -> strategy"


# ---------------------------------------------------------------------------
# Per-line colorization
# ---------------------------------------------------------------------------

def _colorize_line(line: str, ctx: BannerContext) -> str:
    """Apply horizontal gradient to a single logo line."""
    if not ctx.supports_color:
        return line

    parts: list[str] = []
    last_esc = ""

    for col, ch in enumerate(line):
        if ch == " ":
            # Reset color on whitespace to avoid background bleed
            if last_esc:
                parts.append(_RESET)
                last_esc = ""
            parts.append(ch)
        else:
            esc = _color_at(col, _LOGO_WIDTH, ctx)
            if esc != last_esc:
                parts.append(esc)
                last_esc = esc
            parts.append(ch)

    parts.append(_RESET)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Static banner assembly
# ---------------------------------------------------------------------------

def _static_lines(ctx: BannerContext) -> list[str]:
    """Full banner as a list of ready-to-print strings."""
    logo = _LOGO_BLOCKS if ctx.supports_unicode else _LOGO_ASCII
    flow = _FLOW_UNICODE if ctx.supports_unicode else _FLOW_ASCII
    sep = "\u00b7" if ctx.supports_unicode else "-"

    lines: list[str] = [""]
    for row in logo:
        lines.append("  " + _colorize_line(row, ctx))
    lines.append("")
    if ctx.supports_color:
        lines.append(f"  {_DIM}{_TAGLINE}  {sep}  {flow}{_RESET}")
        lines.append(f"  {_DIM}primr --help for commands{_RESET}")
    else:
        lines.append(f"  {_TAGLINE}  {sep}  {flow}")
        lines.append("  primr --help for commands")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Animated banner (left-to-right reveal + tagline fade)
# ---------------------------------------------------------------------------

def _build_reveal_frames(ctx: BannerContext) -> list[list[str]]:
    """Build animation frames for the reveal sequence."""
    logo = _LOGO_BLOCKS if ctx.supports_unicode else _LOGO_ASCII
    flow = _FLOW_UNICODE if ctx.supports_unicode else _FLOW_ASCII
    sep = "\u00b7" if ctx.supports_unicode else "-"

    # Every frame must have the same line count for cursor-up to work.
    # Structure: blank + 7 logo rows + blank + tagline + help + blank = 12 lines.

    frames: list[list[str]] = []

    # Phase 1: Logo reveals left-to-right (10 steps)
    for step in range(1, 11):
        visible = int(_LOGO_WIDTH * step / 10)
        frame: list[str] = [""]
        for row in logo:
            frame.append("  " + _colorize_line(row[:visible], ctx))
        frame.append("")
        frame.append("")   # tagline placeholder
        frame.append("")   # help placeholder
        frame.append("")
        frames.append(frame)

    # Phase 2: Tagline appears (2 steps -- dim then normal)
    full_logo: list[str] = [""]
    for row in logo:
        full_logo.append("  " + _colorize_line(row, ctx))
    full_logo.append("")

    if ctx.supports_color:
        tagline_dim = f"  \033[90m{_TAGLINE}  {sep}  {flow}{_RESET}"
        tagline_full = f"  {_DIM}{_TAGLINE}  {sep}  {flow}{_RESET}"
        help_hint = f"  {_DIM}primr --help for commands{_RESET}"
    else:
        tagline_dim = f"  {_TAGLINE}  {sep}  {flow}"
        tagline_full = tagline_dim
        help_hint = "  primr --help for commands"

    frames.append([*full_logo, tagline_dim, "", ""])
    frames.append([*full_logo, tagline_full, help_hint, ""])

    return frames


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_static_banner(ctx: BannerContext) -> None:
    """Print the banner without animation."""
    for line in _static_lines(ctx):
        print(line)
    sys.stdout.flush()


def render_animated_banner(ctx: BannerContext, duration_ms: int = 1500) -> None:
    """Render the animated reveal banner.

    Falls back to static if the terminal doesn't support cursor movement.
    """
    if not ctx.supports_cursor:
        render_static_banner(ctx)
        return

    frames = _build_reveal_frames(ctx)

    # Timing: reveal takes ~70 % of budget, rest is a brief hold
    reveal_ms = int(duration_ms * 0.70)
    frame_delay = max(reveal_ms / max(len(frames), 1) / 1000.0, 0.04)

    start = time.time()
    first = True

    for frame_lines in frames:
        if not first:
            sys.stdout.write(f"\033[{len(frame_lines)}A")
        first = False
        for line in frame_lines:
            sys.stdout.write(f"\033[2K\r{line}\n")
        sys.stdout.flush()
        time.sleep(frame_delay)

    # Hold the final frame for the remaining duration
    remaining = duration_ms / 1000.0 - (time.time() - start)
    if remaining > 0:
        time.sleep(remaining)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

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
        duration = int(os.environ.get("PRIMR_BANNER_DURATION_MS", "1500"))
        duration = max(250, min(duration, 3000))
        render_animated_banner(ctx, duration_ms=duration)
    else:
        render_static_banner(ctx)

    return True
