"""
Terminal capability detection.

Detects terminal features to enable graceful degradation:
- Color support (ANSI escape codes)
- Unicode support
- Cursor movement (for in-place updates)
- Terminal dimensions
- Interactive vs piped output
"""

import os
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class TerminalCapabilities:
    """
    Detected terminal capabilities.

    Use TerminalCapabilities.detect() to get capabilities
    for the current environment.
    """

    supports_color: bool
    supports_unicode: bool
    supports_cursor: bool
    width: int
    height: int
    is_interactive: bool

    @classmethod
    def detect(cls) -> "TerminalCapabilities":
        """
        Detect capabilities from the current environment.

        Checks:
        - stdout.isatty() for interactive terminal
        - NO_COLOR environment variable
        - TERM environment variable
        - stdout encoding for Unicode
        - Terminal size

        Returns:
            TerminalCapabilities with detected values
        """
        # Check if stdout is a TTY (interactive terminal)
        is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

        # Check for NO_COLOR environment variable (standard)
        # https://no-color.org/
        no_color_env = os.environ.get("NO_COLOR") is not None

        # Check for TERM=dumb (minimal terminal)
        term_dumb = os.environ.get("TERM", "").lower() == "dumb"

        # Check for FORCE_COLOR (override NO_COLOR)
        force_color = os.environ.get("FORCE_COLOR") is not None

        # Color support: TTY + not NO_COLOR + not dumb, or FORCE_COLOR
        supports_color = force_color or (is_tty and not no_color_env and not term_dumb)

        # Unicode support: check stdout encoding
        encoding = getattr(sys.stdout, "encoding", None) or ""
        supports_unicode = "utf" in encoding.lower()

        # Also check LANG/LC_ALL for Unicode hints
        if not supports_unicode:
            lang = os.environ.get("LANG", "") + os.environ.get("LC_ALL", "")
            supports_unicode = "utf" in lang.lower()

        # Cursor movement: need TTY and not dumb terminal
        supports_cursor = is_tty and not term_dumb

        # Terminal size with fallback
        try:
            size = shutil.get_terminal_size(fallback=(80, 24))
            width = size.columns
            height = size.lines
        except (ValueError, OSError):
            width = 80
            height = 24

        # Ensure minimum width
        width = max(width, 40)

        return cls(
            supports_color=supports_color,
            supports_unicode=supports_unicode,
            supports_cursor=supports_cursor,
            width=width,
            height=height,
            is_interactive=is_tty,
        )

    @classmethod
    def for_testing(
        cls,
        supports_color: bool = True,
        supports_unicode: bool = False,
        supports_cursor: bool = True,
        width: int = 80,
        height: int = 24,
        is_interactive: bool = True,
    ) -> "TerminalCapabilities":
        """
        Create capabilities with explicit values for testing.

        Args:
            supports_color: Whether to enable color
            supports_unicode: Whether to enable Unicode
            supports_cursor: Whether to enable cursor movement
            width: Terminal width
            height: Terminal height
            is_interactive: Whether terminal is interactive

        Returns:
            TerminalCapabilities with specified values
        """
        return cls(
            supports_color=supports_color,
            supports_unicode=supports_unicode,
            supports_cursor=supports_cursor,
            width=width,
            height=height,
            is_interactive=is_interactive,
        )

    def should_use_color(self) -> bool:
        """
        Determine if color output should be used.

        Returns True if:
        - Terminal supports color AND
        - Output is interactive (not piped)
        """
        return self.supports_color and self.is_interactive

    def should_use_unicode(self) -> bool:
        """
        Determine if Unicode characters should be used.

        Returns True if terminal supports Unicode encoding.
        """
        return self.supports_unicode

    def should_update_in_place(self) -> bool:
        """
        Determine if in-place updates (progress bars) should be used.

        Returns True if:
        - Terminal supports cursor movement AND
        - Output is interactive
        """
        return self.supports_cursor and self.is_interactive

    def get_safe_width(self, margin: int = 4) -> int:
        """
        Get terminal width with safety margin.

        Args:
            margin: Characters to reserve for safety

        Returns:
            Width minus margin, minimum 40
        """
        return max(self.width - margin, 40)


@lru_cache(maxsize=1)
def get_terminal_capabilities() -> TerminalCapabilities:
    """
    Get cached terminal capabilities.

    Capabilities are detected once and cached for performance.
    Use clear_terminal_cache() to force re-detection.

    Returns:
        TerminalCapabilities for current environment
    """
    return TerminalCapabilities.detect()


def clear_terminal_cache() -> None:
    """
    Clear the cached terminal capabilities.

    Call this if the terminal environment changes
    (e.g., window resize, environment variable change).
    """
    get_terminal_capabilities.cache_clear()


def is_color_enabled() -> bool:
    """
    Quick check if color output is enabled.

    Returns:
        True if color should be used
    """
    return get_terminal_capabilities().should_use_color()


def is_unicode_enabled() -> bool:
    """
    Quick check if Unicode output is enabled.

    Returns:
        True if Unicode should be used
    """
    return get_terminal_capabilities().should_use_unicode()


def get_terminal_width() -> int:
    """
    Get current terminal width.

    Returns:
        Terminal width in characters
    """
    return get_terminal_capabilities().width


def is_interactive() -> bool:
    """
    Check if running in interactive terminal.

    Returns:
        True if stdout is a TTY
    """
    return get_terminal_capabilities().is_interactive
