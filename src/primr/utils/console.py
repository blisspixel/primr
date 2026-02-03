"""
Modern CLI output system - 2026 standards.

Design principles:
- Minimal output, maximum information density
- No excessive indentation or visual noise
- Clean progress updates that overwrite in place
- Unicode symbols for modern terminals, ASCII fallback
"""

import os
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class _TerminalCaps:
    supports_color: bool
    supports_unicode: bool
    supports_cursor: bool
    width: int
    is_interactive: bool

    @classmethod
    def for_testing(cls, supports_color=True, supports_unicode=False,
                    supports_cursor=True, width=80, is_interactive=True):
        return cls(supports_color, supports_unicode, supports_cursor, width, is_interactive)


def _enable_windows_ansi():
    """Enable ANSI escape sequences on Windows."""
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            STD_OUTPUT_HANDLE = -11
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        except Exception:
            pass

_enable_windows_ansi()


@lru_cache(maxsize=1)
def _detect_terminal():
    is_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    no_color = os.environ.get("NO_COLOR") is not None
    term_dumb = os.environ.get("TERM", "").lower() == "dumb"
    force_color = os.environ.get("FORCE_COLOR") is not None
    supports_color = force_color or (is_tty and not no_color and not term_dumb)
    encoding = getattr(sys.stdout, 'encoding', None) or ''
    supports_unicode = 'utf' in encoding.lower()
    supports_cursor = is_tty and not term_dumb
    try:
        width = shutil.get_terminal_size(fallback=(80, 24)).columns
    except (ValueError, OSError):
        width = 80
    return _TerminalCaps(supports_color, supports_unicode, supports_cursor, max(width, 40), is_tty)


# Backward compatibility alias
TerminalCapabilities = _TerminalCaps


class Console:
    """Modern minimal CLI output."""

    def __init__(self, verbose=False, quiet=False, capabilities=None):
        self.verbose = verbose
        self.quiet = quiet
        self._lock = threading.Lock()
        self._caps = capabilities or _detect_terminal()
        self._last_output_time: float = 0.0

        # Colors
        if self._caps.supports_color and self._caps.is_interactive:
            self._green = "\033[32m"
            self._yellow = "\033[33m"
            self._red = "\033[31m"
            self._cyan = "\033[36m"
            self._dim = "\033[2m"
            self._bold = "\033[1m"
            self._reset = "\033[0m"
        else:
            self._green = self._yellow = self._red = self._cyan = ""
            self._dim = self._bold = self._reset = ""

        # Symbols - modern 2026 aesthetic
        if self._caps.supports_unicode:
            self._check = "✓"
            self._cross = "✗"
            self._arrow = "→"
            self._dot = "·"
        else:
            self._check = "+"
            self._cross = "x"
            self._arrow = "->"
            self._dot = "."

    @property
    def term_width(self):
        return self._caps.width

    @property
    def theme(self):
        """Backward compatibility - return a theme-like object."""
        return self

    # Theme properties for backward compatibility
    @property
    def SUCCESS(self):
        return self._green

    @property
    def WARNING(self):
        return self._yellow

    @property
    def ERROR(self):
        return self._red

    @property
    def INFO(self):
        return self._cyan

    @property
    def MUTED(self):
        return self._dim

    @property
    def BOLD(self):
        return self._bold

    @property
    def RESET(self):
        return self._reset

    @property
    def INDICATOR_DONE(self):
        return self._check

    @property
    def INDICATOR_FAIL(self):
        return self._cross

    def _print(self, msg="", end="\n"):
        with self._lock:
            self._last_output_time = time.time()
            print(msg, end=end)
            sys.stdout.flush()

    def _elapsed(self, start):
        if not start:
            return ""
        elapsed = time.time() - start
        if elapsed < 1:
            return ""
        elif elapsed < 60:
            return f"{int(elapsed)}s"
        elif elapsed < 3600:
            return f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
        else:
            return f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m"

    # =========================================================================
    # MODERN API - Clean, minimal output
    # =========================================================================

    def status(self, msg):
        """Show a status message (dim, in-place if possible)."""
        if self.quiet:
            return
        if self._caps.supports_cursor and self._caps.is_interactive:
            with self._lock:
                width = min(self._caps.width, 120)
                line = f"\r{self._dim}{msg}{self._reset}"
                sys.stdout.write(line.ljust(width))
                sys.stdout.write("\r" + line)
                sys.stdout.flush()
        else:
            self._print(f"{self._dim}{msg}{self._reset}")

    def found(self, msg):
        """Show discovery result: "Found 47 pages" """
        if self.quiet:
            return
        self.clear_line()
        self._print(f"{self._green}{self._check}{self._reset} {msg}")

    def done(self, msg):
        """Show completion: "✓ 47 pages scraped" """
        if self.quiet:
            return
        self._print(f"{self._green}{self._check}{self._reset} {msg}")

    def fail(self, msg):
        """Show failure: "✗ Could not scrape" """
        self._print(f"{self._red}{self._cross}{self._reset} {msg}")

    def muted(self, msg):
        """Show muted/secondary info."""
        if self.quiet:
            return
        self._print(f"{self._dim}{msg}{self._reset}")

    def scrape_progress(self, current, total, path, start_time=None, tier=None):
        """Show scraping progress with clean inline updates."""
        if self.quiet:
            return
        if not self._caps.supports_cursor or not self._caps.is_interactive:
            if current == total:
                elapsed = self._elapsed(start_time) if start_time else ""
                time_str = f" ({elapsed})" if elapsed else ""
                self._print(f"{self._check} {path}{time_str}")
            return

        # Interactive: clean inline progress
        # Format: "Scraping 3/50 /investors/financial-reports (9s)"
        # No tier shown - it's noise. Just path and timing.
        width = min(self._caps.width, 120)
        line = f"Scraping {current}/{total} {path}"

        # Truncate if too long, then pad to width
        if len(line) > width:
            line = line[:width-3] + "..."
        line = line.ljust(width)

        with self._lock:
            self._last_output_time = time.time()
            # Clear line first, then write new content
            # This works better on Windows terminals where \r alone may not work
            sys.stdout.write(f"\r{' ' * width}\r{line}")
            sys.stdout.flush()

    def clear_line(self):
        """Clear the current line."""
        if self._caps.supports_cursor and self._caps.is_interactive:
            with self._lock:
                width = min(self._caps.width, 120)
                # Clear by writing spaces, then return to start
                sys.stdout.write(f"\r{' ' * width}\r")
                sys.stdout.flush()


    # =========================================================================
    # BACKWARD COMPATIBILITY API - Maps to modern methods
    # =========================================================================

    def grades(self, grades: list[tuple[str, int]]):
        """Display grades inline. Clean, minimal."""
        if self.quiet:
            return
        if not grades:
            return
        parts = []
        for label, score in grades:
            if score >= 85:
                color = self._green
            elif score >= 70:
                color = self._yellow
            else:
                color = self._red
            parts.append(f"{label} {color}{score}{self._reset}")
        self._print(f"{self._dim}Quality:{self._reset} {' · '.join(parts)}")

    def blank(self):
        if self.quiet:
            return
        self._print()

    def text(self, msg):
        if self.quiet:
            return
        self._print(msg)

    def info(self, msg):
        """Backward compat - maps to muted."""
        self.muted(msg)

    def detail(self, label, value):
        if self.quiet:
            return
        self._print(f"{self._dim}{label}:{self._reset} {value}")

    def warn(self, msg):
        if self.quiet:
            return
        self._print(f"{self._yellow}!{self._reset} {msg}")

    def ok(self, msg="", show_time=True):
        """Backward compat - maps to done."""
        self.done(msg if msg else "Done")

    def error(self, msg):
        """Backward compat - maps to fail."""
        self.fail(msg)

    def step(self, msg):
        """Backward compat - show a step."""
        if self.quiet:
            return
        self._print(f"\n{self._cyan}>{self._reset} {msg}")

    def result(self, label, value, highlight=False):
        if self.quiet:
            return
        if highlight:
            self._print(f"\n{self._green}{label}{self._reset}")
            self._print(f"{value}")
        else:
            self._print(f"{self._dim}{label}:{self._reset} {value}")

    def success_box(self, title, details):
        """Show success with details."""
        if self.quiet:
            return
        self._print()
        self._print(f"{self._green}{self._check}{self._reset} {title}")
        self._print(f"  {self._dim}{details}{self._reset}")

    def summary(self, stats):
        if self.quiet:
            return
        self._print()
        for label, value in stats:
            self._print(f"{self._dim}{label}:{self._reset} {value}")

    def banner(self, title, version=""):
        """Modern minimal banner - 2026 design."""
        if self.quiet:
            return
        self._print()
        if version:
            self._print(f"{self._bold}{title}{self._reset} {self._dim}{version}{self._reset}")
        else:
            self._print(f"{self._bold}{title}{self._reset}")

    def header(self, title, subtitle=""):
        """Modern minimal header - 2026 design."""
        if self.quiet:
            return
        self._print()
        self._print(f"{self._bold}{title}{self._reset}")
        if subtitle:
            self._print(f"{self._dim}{subtitle}{self._reset}")

    def phase_banner(self, step_num, total_steps, title, description="", expected_duration=""):
        """Modern phase header - clean 2026 design."""
        if self.quiet:
            return
        self._print()
        # Modern minimal design - just bold title with subtle accent
        self._print(f"{self._cyan}▸{self._reset} {self._bold}PHASE {step_num}{self._reset} {self._dim}·{self._reset} {title}")
        if description:
            self._print(f"  {self._dim}{description}{self._reset}")
        self._print()

    def phase_complete(self, title, stats=None):
        if self.quiet:
            return
        self._print(f"{self._green}{self._check}{self._reset} {title}")
        if stats:
            for label, value in stats:
                if label.lower() != "duration":
                    self._print(f"  {self._dim}{label}: {value}{self._reset}")

    def divider(self, char="·"):
        """Modern subtle divider - 2026 design."""
        if self.quiet:
            return
        # Subtle centered divider
        min(40, self._caps.width - 4)
        self._print(f"{self._dim}{char * 3}{self._reset}")

    def debug(self, msg):
        if not self.verbose:
            return
        self._print(f"{self._dim}[debug] {msg}{self._reset}")

    # =========================================================================
    # PROGRESS METHODS - Backward compatibility
    # =========================================================================

    def progress(self, current, total, label=""):
        """Backward compat progress bar."""
        if self.quiet:
            return
        if not self._caps.supports_cursor or not self._caps.is_interactive:
            if current == total:
                self._print(f"{self._check} {label} ({current}/{total})")
            return

        pct = int(100 * current / total) if total > 0 else 0
        display_label = label[:25] + "..." if len(label) > 25 else label
        line = f"\r{current}/{total} {display_label} ({pct}%)"
        with self._lock:
            sys.stdout.write(line.ljust(60))
            sys.stdout.flush()

    def progress_done(self):
        """Clear progress line."""
        self.clear_line()

    def progress_with_time(self, current, total, label="", start_time=None):
        """Backward compat - maps to scrape_progress."""
        self.scrape_progress(current, total, label, start_time)

    def status_with_time(self, message, start_time=None):
        if self.quiet:
            return
        time_str = ""
        if start_time:
            elapsed = self._elapsed(start_time)
            if elapsed:
                time_str = f" ({elapsed})"
        self.status(f"{message}{time_str}")

    def status_line_done(self):
        self.clear_line()

    # =========================================================================
    # CONTEXT MANAGERS
    # =========================================================================

    @contextmanager
    def spinner(self, message="Working"):
        """Simple spinner context manager."""
        if self.quiet or not self._caps.supports_cursor or not self._caps.is_interactive:
            self._print(f"{self._dim}{message}...{self._reset}")
            yield lambda m: None
            return

        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"] if self._caps.supports_unicode else ["|", "/", "-", "\\"]
        stop_event = threading.Event()
        current_msg = [message]
        line_width = min(self._caps.width - 2, 80)

        def animate():
            idx = 0
            while not stop_event.is_set():
                frame = frames[idx % len(frames)]
                with self._lock:
                    # Build line with proper padding
                    msg_text = current_msg[0]
                    line = f"{self._cyan}{frame}{self._reset} {msg_text}"
                    # Truncate if needed, then pad to full width
                    visible_len = len(frame) + 1 + len(msg_text)  # frame + space + message
                    if visible_len > line_width:
                        msg_text = msg_text[:line_width - len(frame) - 4] + "..."
                        line = f"{self._cyan}{frame}{self._reset} {msg_text}"
                    # Pad with spaces to overwrite previous content
                    line = line + " " * max(0, line_width - visible_len)
                    # Write with carriage return
                    sys.stdout.write(f"\r{line}")
                    sys.stdout.flush()
                idx += 1
                time.sleep(0.08)

        thread = threading.Thread(target=animate, daemon=True)
        thread.start()

        def update(msg):
            current_msg[0] = msg

        try:
            yield update
        finally:
            stop_event.set()
            thread.join(timeout=0.5)
            self.clear_line()

    @contextmanager
    def timed_operation(self, message, show_spinner=True):
        """Timed operation with optional spinner."""
        if self.quiet:
            yield
            return

        start = time.time()
        if show_spinner and self._caps.supports_cursor and self._caps.is_interactive:
            with self.spinner(message):
                yield
            elapsed = self._elapsed(start)
            time_str = f" ({elapsed})" if elapsed else ""
            self._print(f"{self._green}{self._check}{self._reset} {message}{self._dim}{time_str}{self._reset}")
        else:
            self._print(f"{self._dim}{message}...{self._reset}")
            yield
            elapsed = self._elapsed(start)
            time_str = f" ({elapsed})" if elapsed else ""
            self._print(f"{self._green}{self._check}{self._reset} {message}{self._dim}{time_str}{self._reset}")

    @contextmanager
    def heartbeat(self, message, interval=30.0):
        """Periodic heartbeat for long operations."""
        if self.quiet:
            yield
            return

        start = time.time()
        stop_event = threading.Event()

        def show_heartbeat():
            while not stop_event.is_set():
                stop_event.wait(interval)
                if not stop_event.is_set():
                    time_since = time.time() - self._last_output_time
                    if time_since >= interval:
                        elapsed = self._elapsed(start)
                        if self._caps.supports_cursor and self._caps.is_interactive:
                            with self._lock:
                                sys.stdout.write(f"\r{self._dim}. {message} ({elapsed}){self._reset}".ljust(60))
                                sys.stdout.flush()
                        else:
                            self._print(f"{self._dim}. {message} ({elapsed}){self._reset}")

        thread = threading.Thread(target=show_heartbeat, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=0.5)
            self.clear_line()


# Backward compatibility - Theme class
class Theme:
    BRAND = property(lambda s: console._cyan)
    SUCCESS = property(lambda s: console._green)
    WARNING = property(lambda s: console._yellow)
    ERROR = property(lambda s: console._red)
    MUTED = property(lambda s: console._dim)
    TEXT = property(lambda s: console._bold)
    RESET = property(lambda s: console._reset)
    LINE_H = property(lambda s: "-")
    PROG_FILL = property(lambda s: "#")
    PROG_EMPTY = property(lambda s: "-")
    INDICATOR_ACTIVE = property(lambda s: ">")
    INDICATOR_DONE = property(lambda s: console._check)
    INDICATOR_FAIL = property(lambda s: console._cross)
    INDICATOR_WARN = property(lambda s: "!")
    INDICATOR_INFO = property(lambda s: ".")


# Global console instance
console = Console()


def set_console(new_console):
    global console
    console = new_console


def get_console():
    return console
