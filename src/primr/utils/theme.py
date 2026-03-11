"""
Visual theme system for CLI output.

Provides consistent styling across all CLI components with
terminal capability awareness for graceful degradation.
"""

from dataclasses import dataclass, field


@dataclass
class Theme:
    """
    Visual theme with terminal capability awareness.

    All visual elements are defined here for consistency:
    - Status indicators (ASCII-safe by default)
    - Progress characters
    - Box drawing characters
    - Semantic color codes (ANSI)

    Use Theme.for_terminal() to create a theme appropriate
    for the current terminal's capabilities.
    """

    # Status indicators (ASCII-safe defaults)
    INDICATOR_ACTIVE: str = ">"
    INDICATOR_DONE: str = "+"
    INDICATOR_FAIL: str = "x"
    INDICATOR_WARN: str = "!"
    INDICATOR_INFO: str = "."
    INDICATOR_BULLET: str = "*"

    # Progress characters
    PROG_FILL: str = "#"
    PROG_EMPTY: str = "-"
    PROG_BRACKET_L: str = "["
    PROG_BRACKET_R: str = "]"

    # Box drawing (ASCII)
    LINE_H: str = "-"
    LINE_V: str = "|"
    CORNER_TL: str = "+"
    CORNER_TR: str = "+"
    CORNER_BL: str = "+"
    CORNER_BR: str = "+"

    # Semantic colors (ANSI escape codes)
    SUCCESS: str = "\033[32m"  # Green
    WARNING: str = "\033[33m"  # Yellow
    ERROR: str = "\033[31m"  # Red
    INFO: str = "\033[36m"  # Cyan
    MUTED: str = "\033[2m"  # Dim
    BOLD: str = "\033[1m"  # Bold
    RESET: str = "\033[0m"  # Reset all

    # Computed flag for color support
    _has_color: bool = field(default=True, repr=False)

    @classmethod
    def for_terminal(cls, supports_color: bool = True, supports_unicode: bool = False) -> "Theme":
        """
        Create a theme appropriate for terminal capabilities.

        Args:
            supports_color: Whether terminal supports ANSI colors
            supports_unicode: Whether terminal supports Unicode characters

        Returns:
            Theme configured for the terminal's capabilities
        """
        theme = cls()
        theme._has_color = supports_color

        # Disable colors if not supported
        if not supports_color:
            theme.SUCCESS = ""
            theme.WARNING = ""
            theme.ERROR = ""
            theme.INFO = ""
            theme.MUTED = ""
            theme.BOLD = ""
            theme.RESET = ""

        # Use Unicode characters if supported
        if supports_unicode:
            theme.INDICATOR_DONE = "\u2713"  # ✓
            theme.INDICATOR_FAIL = "\u2717"  # ✗
            theme.INDICATOR_WARN = "\u26a0"  # ⚠ (warning sign)
            theme.PROG_FILL = "\u2588"  # █
            theme.PROG_EMPTY = "\u2591"  # ░
            # Box drawing with Unicode
            theme.LINE_H = "\u2500"  # ─
            theme.LINE_V = "\u2502"  # │
            theme.CORNER_TL = "\u250c"  # ┌
            theme.CORNER_TR = "\u2510"  # ┐
            theme.CORNER_BL = "\u2514"  # └
            theme.CORNER_BR = "\u2518"  # ┘

        return theme

    @property
    def has_color(self) -> bool:
        """Whether this theme has color support enabled."""
        return self._has_color

    def get_indicator(self, status: str) -> str:
        """
        Get the indicator symbol for a status type.

        Args:
            status: One of 'active', 'done', 'fail', 'warn', 'info', 'bullet'

        Returns:
            The indicator character for that status
        """
        indicators = {
            "active": self.INDICATOR_ACTIVE,
            "done": self.INDICATOR_DONE,
            "fail": self.INDICATOR_FAIL,
            "warn": self.INDICATOR_WARN,
            "info": self.INDICATOR_INFO,
            "bullet": self.INDICATOR_BULLET,
        }
        return indicators.get(status, self.INDICATOR_BULLET)

    def get_status_color(self, status: str) -> str:
        """
        Get the color code for a status type.

        Args:
            status: One of 'success', 'warning', 'error', 'info', 'muted'

        Returns:
            The ANSI color code (empty string if colors disabled)
        """
        colors = {
            "success": self.SUCCESS,
            "warning": self.WARNING,
            "error": self.ERROR,
            "info": self.INFO,
            "muted": self.MUTED,
        }
        return colors.get(status, "")

    def colorize(self, text: str, status: str) -> str:
        """
        Apply status color to text.

        Args:
            text: Text to colorize
            status: Status type for color selection

        Returns:
            Colorized text (or plain text if colors disabled)
        """
        color = self.get_status_color(status)
        if color:
            return f"{color}{text}{self.RESET}"
        return text

    def strip_ansi(self, text: str) -> str:
        """
        Remove all ANSI escape codes from text.

        Useful for calculating visible string length.

        Args:
            text: Text potentially containing ANSI codes

        Returns:
            Text with all ANSI codes removed
        """
        import re

        ansi_pattern = re.compile(r"\033\[[0-9;]*m")
        return ansi_pattern.sub("", text)

    def visible_len(self, text: str) -> int:
        """
        Get the visible length of text (excluding ANSI codes).

        Args:
            text: Text potentially containing ANSI codes

        Returns:
            Number of visible characters
        """
        return len(self.strip_ansi(text))


# Default theme instance (with colors, ASCII indicators)
default_theme = Theme()

# No-color theme for piped output or NO_COLOR environments
plain_theme = Theme.for_terminal(supports_color=False, supports_unicode=False)


def get_theme(supports_color: bool = True, supports_unicode: bool = False) -> Theme:
    """
    Get a theme appropriate for the given capabilities.

    This is a convenience function that returns cached themes
    for common configurations.

    Args:
        supports_color: Whether terminal supports ANSI colors
        supports_unicode: Whether terminal supports Unicode

    Returns:
        Appropriate Theme instance
    """
    if not supports_color:
        return plain_theme
    if supports_unicode:
        return Theme.for_terminal(supports_color=True, supports_unicode=True)
    return default_theme
