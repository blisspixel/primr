"""
Premium CLI output system with visual hierarchy.

Visual Hierarchy Levels:
  Level 1: PHASE - Bold headers with separators
  Level 2: STEP - Indicator + text, 2-space indent
  Level 3: DETAIL - 4-space indent, muted
  Level 4: RESULT - 4-space indent, highlighted
"""

import os
import shutil
import sys
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache

INDENT_PHASE = ""
INDENT_STEP = "  "
INDENT_DETAIL = "    "
INDENT_RESULT = "    "


@dataclass
class _TerminalCaps:
    supports_color: bool
    supports_unicode: bool
    supports_cursor: bool
    width: int
    is_interactive: bool
    
    def should_use_color(self):
        return self.supports_color and self.is_interactive
    
    def should_use_unicode(self):
        return self.supports_unicode
    
    def should_update_in_place(self):
        return self.supports_cursor and self.is_interactive
    
    @classmethod
    def for_testing(cls, supports_color=True, supports_unicode=False,
                    supports_cursor=True, width=80, is_interactive=True):
        return cls(supports_color, supports_unicode, supports_cursor, width, is_interactive)


def _enable_windows_ansi():
    """Enable ANSI escape sequences on Windows (required for \\r and colors to work)."""
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING for stdout
            STD_OUTPUT_HANDLE = -11
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        except Exception:
            pass  # If it fails, continue without - some terminals handle it natively

# Enable Windows ANSI support at module load
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


@dataclass
class _Theme:
    INDICATOR_ACTIVE: str = ">"
    INDICATOR_DONE: str = "+"
    INDICATOR_FAIL: str = "x"
    INDICATOR_WARN: str = "!"
    INDICATOR_INFO: str = "."
    PROG_FILL: str = "#"
    PROG_EMPTY: str = "-"
    LINE_H: str = "-"
    SUCCESS: str = "\033[32m"
    WARNING: str = "\033[33m"
    ERROR: str = "\033[31m"
    INFO: str = "\033[36m"
    MUTED: str = "\033[2m"
    BOLD: str = "\033[1m"
    RESET: str = "\033[0m"
    
    @classmethod
    def for_terminal(cls, supports_color, supports_unicode):
        t = cls()
        if not supports_color:
            t.SUCCESS = t.WARNING = t.ERROR = t.INFO = t.MUTED = t.BOLD = t.RESET = ""
        if supports_unicode:
            t.INDICATOR_DONE = "\u2713"
            t.INDICATOR_FAIL = "\u2717"
            t.PROG_FILL = "\u2588"
            t.PROG_EMPTY = "\u2591"
        return t


@lru_cache(maxsize=4)
def _get_theme(supports_color, supports_unicode):
    return _Theme.for_terminal(supports_color, supports_unicode)


def _get_default_theme():
    caps = _detect_terminal()
    return _get_theme(caps.should_use_color(), caps.should_use_unicode())


TerminalCapabilities = _TerminalCaps


class Theme:
    BRAND = property(lambda s: _get_default_theme().INFO)
    SUCCESS = property(lambda s: _get_default_theme().SUCCESS)
    WARNING = property(lambda s: _get_default_theme().WARNING)
    ERROR = property(lambda s: _get_default_theme().ERROR)
    MUTED = property(lambda s: _get_default_theme().MUTED)
    TEXT = property(lambda s: _get_default_theme().BOLD)
    RESET = property(lambda s: _get_default_theme().RESET)
    LINE_H = property(lambda s: _get_default_theme().LINE_H)
    PROG_FILL = property(lambda s: _get_default_theme().PROG_FILL)
    PROG_EMPTY = property(lambda s: _get_default_theme().PROG_EMPTY)
    INDICATOR_ACTIVE = property(lambda s: _get_default_theme().INDICATOR_ACTIVE)
    INDICATOR_DONE = property(lambda s: _get_default_theme().INDICATOR_DONE)
    INDICATOR_FAIL = property(lambda s: _get_default_theme().INDICATOR_FAIL)
    INDICATOR_WARN = property(lambda s: _get_default_theme().INDICATOR_WARN)
    INDICATOR_INFO = property(lambda s: _get_default_theme().INDICATOR_INFO)


class Spinner:
    # Modern braille dots spinner (smooth animation)
    FRAMES_UNICODE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    # Fallback for terminals without unicode
    FRAMES_ASCII = ["|", "/", "-", "\\"]

    def __init__(self, message=""):
        self.message = message
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._caps = _detect_terminal()
        self._theme = _get_default_theme()
        self._frames = self.FRAMES_UNICODE if self._caps.should_use_unicode() else self.FRAMES_ASCII

    def _animate(self):
        idx = 0
        while not self._stop.is_set():
            frame = self._frames[idx % len(self._frames)]
            with self._lock:
                sys.stdout.write(f"\r{INDENT_STEP}{self._theme.INFO}{frame}{self._theme.RESET} {self.message}")
                sys.stdout.flush()
            idx += 1
            time.sleep(0.08)  # Slightly faster for smoother animation

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self, clear=True):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        if clear:
            sys.stdout.write("\r" + " " * 70 + "\r")
            sys.stdout.flush()

    def update(self, message):
        with self._lock:
            self.message = message


class Console:
    def __init__(self, verbose=False, quiet=False, capabilities=None):
        self.verbose = verbose
        self.quiet = quiet
        self._lock = threading.Lock()
        self._step_start: float = 0.0
        self._phase_start: float = 0.0
        self._caps = capabilities or _detect_terminal()
        self._theme = _get_theme(self._caps.should_use_color(), self._caps.should_use_unicode())
        self._term_width = self._caps.width
        self._last_output_time: float = 0.0  # Track when last output occurred

    @property
    def term_width(self):
        return self._term_width

    @property
    def theme(self):
        return self._theme

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

    def _truncate(self, text, max_len):
        if len(text) <= max_len:
            return text
        return text[:max_len-3] + "..."

    def banner(self, title, version=""):
        if self.quiet:
            return
        width = min(50, self._term_width - 4)
        self._print()
        self._print(f"{INDENT_STEP}{self._theme.INFO}{title}{self._theme.RESET}", end="")
        if version:
            self._print(f"  {self._theme.MUTED}{version}{self._theme.RESET}")
        else:
            self._print()
        self._print(f"{INDENT_STEP}{self._theme.MUTED}{self._theme.LINE_H * width}{self._theme.RESET}")

    def header(self, title, subtitle=""):
        if self.quiet:
            return
        self._phase_start = time.time()
        self._print()
        self._print(f"{INDENT_STEP}{self._theme.BOLD}{title}{self._theme.RESET}")
        if subtitle:
            self._print(f"{INDENT_STEP}{self._theme.MUTED}{subtitle}{self._theme.RESET}")
        width = min(50, self._term_width - 4)
        self._print(f"{INDENT_STEP}{self._theme.MUTED}{self._theme.LINE_H * width}{self._theme.RESET}")


    def phase_banner(self, step_num, total_steps, title, description="", expected_duration=""):
        if self.quiet:
            return
        self._phase_start = time.time()
        self._print()
        # Modern: just bold title with a subtle underline, no heavy borders
        self._print(f"{INDENT_STEP}{self._theme.BOLD}{self._theme.INFO}{title}{self._theme.RESET}")
        if description:
            self._print(f"{INDENT_STEP}{self._theme.MUTED}{description}{self._theme.RESET}")
        if expected_duration:
            self._print(f"{INDENT_STEP}{self._theme.MUTED}Expected: {expected_duration}{self._theme.RESET}")
        self._print()

    def phase_complete(self, title, stats=None):
        if self.quiet:
            return
        elapsed = self._elapsed(self._phase_start) if self._phase_start else ""
        # Modern: simple checkmark with title, not shouty "COMPLETE"
        self._print(f"{INDENT_STEP}{self._theme.SUCCESS}{self._theme.INDICATOR_DONE} {title}{self._theme.RESET}", end="")
        if elapsed:
            self._print(f" {self._theme.MUTED}({elapsed}){self._theme.RESET}")
        else:
            self._print()
        
        if stats:
            for label, value in stats:
                if label.lower() != "duration":  # Skip duration, we show it inline
                    self._print(f"{INDENT_DETAIL}{self._theme.MUTED}{label}: {value}{self._theme.RESET}")

    def step(self, msg):
        if self.quiet:
            return
        self._step_start = time.time()
        self._print(f"\n{INDENT_STEP}{self._theme.INFO}{self._theme.INDICATOR_ACTIVE}{self._theme.RESET} {msg}")

    def info(self, msg):
        if self.quiet:
            return
        # Clear any in-place updates (heartbeat, spinner) before printing
        if self._caps.should_update_in_place():
            with self._lock:
                sys.stdout.write("\r" + " " * 70 + "\r")
                sys.stdout.flush()
        self._print(f"{INDENT_DETAIL}{self._theme.MUTED}{msg}{self._theme.RESET}")

    def detail(self, label, value):
        if self.quiet:
            return
        self._print(f"{INDENT_DETAIL}{self._theme.MUTED}{label}:{self._theme.RESET} {value}")

    def warn(self, msg):
        if self.quiet:
            return
        self._print(f"{INDENT_DETAIL}{self._theme.WARNING}{self._theme.INDICATOR_WARN}{self._theme.RESET} {msg}")

    def ok(self, msg="", show_time=True):
        if self.quiet:
            return
        time_str = ""
        if show_time:
            elapsed = self._elapsed(self._step_start)
            if elapsed:
                time_str = f" {self._theme.MUTED}({elapsed}){self._theme.RESET}"
        display = msg if msg else "Done"
        self._print(f"{INDENT_RESULT}{self._theme.SUCCESS}{self._theme.INDICATOR_DONE}{self._theme.RESET} {display}{time_str}")

    def error(self, msg):
        self._print(f"{INDENT_RESULT}{self._theme.ERROR}{self._theme.INDICATOR_FAIL}{self._theme.RESET} {msg}")

    def result(self, label, value, highlight=False):
        if self.quiet:
            return
        if highlight:
            self._print(f"\n{INDENT_STEP}{self._theme.SUCCESS}{label}{self._theme.RESET}")
            self._print(f"{INDENT_STEP}{value}")
        else:
            self._print(f"{INDENT_STEP}{self._theme.MUTED}{label}:{self._theme.RESET} {value}")

    def success_box(self, title, path):
        if self.quiet:
            return
        self._print()
        self._print(f"{INDENT_STEP}{self._theme.SUCCESS}{self._theme.INDICATOR_DONE} {title}{self._theme.RESET}")
        self._print(f"{INDENT_STEP}{path}")
        self._print()

    def summary(self, stats):
        if self.quiet:
            return
        self._print()
        for label, value in stats:
            self._print(f"{INDENT_STEP}{self._theme.MUTED}{label}:{self._theme.RESET} {value}")


    def progress(self, current, total, label=""):
        if self.quiet:
            return
        if not self._caps.should_update_in_place():
            if current == total:
                self._print(f"{INDENT_DETAIL}{self._theme.INDICATOR_DONE} {label} ({current}/{total})")
            return
        bar_width = 20
        filled = int(bar_width * current / total) if total > 0 else 0
        bar = (self._theme.PROG_FILL * filled + self._theme.MUTED +
               self._theme.PROG_EMPTY * (bar_width - filled) + self._theme.RESET)
        display_label = self._truncate(label, 25) if label else ""
        line = f"\r{INDENT_DETAIL}[{bar}] {current}/{total}"
        if display_label:
            line += f" {self._theme.MUTED}{display_label}{self._theme.RESET}"
        with self._lock:
            sys.stdout.write(line.ljust(70))
            sys.stdout.flush()

    def progress_done(self):
        if self.quiet or not self._caps.should_update_in_place():
            return
        with self._lock:
            sys.stdout.write("\r" + " " * 70 + "\r")
            sys.stdout.flush()

    def progress_with_time(self, current, total, label="", start_time=None):
        if self.quiet:
            return
        if not self._caps.should_update_in_place():
            if current == total:
                elapsed = self._elapsed(start_time) if start_time else ""
                time_str = f" ({elapsed})" if elapsed else ""
                self._print(f"{INDENT_DETAIL}{self._theme.INDICATOR_DONE} {label}{time_str}")
            return
        
        # Throttle updates to max 10/sec for smoother visual display
        now = time.time()
        is_first = current == 1
        is_last = current == total
        time_since_last = now - self._last_output_time
        
        if not is_first and not is_last and time_since_last < 0.1:
            return  # Skip this update, too soon
        
        # Simple format: "Processing 5/50: /about-us (12s)"
        display_label = self._truncate(label, 30) if label else ""
        time_str = ""
        if start_time:
            elapsed = self._elapsed(start_time)
            if elapsed:
                time_str = f" {self._theme.MUTED}({elapsed}){self._theme.RESET}"
        
        line = f"{current}/{total}"
        if display_label:
            line += f" {display_label}"
        line += time_str
        
        padded = f"{INDENT_DETAIL}{line}".ljust(60)
        with self._lock:
            self._last_output_time = now
            sys.stdout.write(f"\r{padded}")
            sys.stdout.flush()

    def status_with_time(self, message, start_time=None):
        if self.quiet:
            return
        time_str = ""
        if start_time:
            elapsed = self._elapsed(start_time)
            if elapsed:
                time_str = f" {self._theme.MUTED}({elapsed}){self._theme.RESET}"
        if self._caps.should_update_in_place():
            line = f"\r{INDENT_DETAIL}{self._theme.MUTED}{message}{self._theme.RESET}{time_str}"
            with self._lock:
                sys.stdout.write(line.ljust(70))
                sys.stdout.flush()
        else:
            self._print(f"{INDENT_DETAIL}{self._theme.MUTED}{message}{self._theme.RESET}{time_str}")

    def status_line_done(self):
        if self.quiet or not self._caps.should_update_in_place():
            return
        with self._lock:
            sys.stdout.write("\r" + " " * 75 + "\r")
            sys.stdout.flush()


    @contextmanager
    def spinner(self, message="Working"):
        if self.quiet or not self._caps.should_update_in_place():
            self._print(f"{INDENT_DETAIL}{self._theme.MUTED}{message}...{self._theme.RESET}")
            yield lambda m: None
            return
        spin = Spinner(message)
        spin.start()
        try:
            yield spin.update
        finally:
            spin.stop()

    @contextmanager
    def timed_operation(self, message, show_spinner=True):
        if self.quiet:
            yield
            return
        start = time.time()
        if show_spinner and self._caps.should_update_in_place():
            spin = Spinner(message)
            spin.start()
            stop_event = threading.Event()
            def update_time():
                while not stop_event.is_set():
                    elapsed = self._elapsed(start)
                    if elapsed:
                        spin.update(f"{message} ({elapsed})")
                    stop_event.wait(1.0)
            time_thread = threading.Thread(target=update_time, daemon=True)
            time_thread.start()
            try:
                yield
            finally:
                stop_event.set()
                time_thread.join(timeout=0.5)
                spin.stop()
                elapsed = self._elapsed(start)
                time_str = f" ({elapsed})" if elapsed else ""
                self._print(f"{INDENT_RESULT}{self._theme.SUCCESS}{self._theme.INDICATOR_DONE}{self._theme.RESET} {message}{self._theme.MUTED}{time_str}{self._theme.RESET}")
        else:
            self._print(f"{INDENT_DETAIL}{self._theme.MUTED}{message}...{self._theme.RESET}")
            try:
                yield
            finally:
                elapsed = self._elapsed(start)
                time_str = f" ({elapsed})" if elapsed else ""
                self._print(f"{INDENT_RESULT}{self._theme.SUCCESS}{self._theme.INDICATOR_DONE}{self._theme.RESET} {message}{self._theme.MUTED}{time_str}{self._theme.RESET}")

    @contextmanager
    def heartbeat(self, message, interval=30.0):
        """
        Show periodic heartbeat messages during long operations.
        
        The heartbeat uses in-place updates (carriage return) to avoid
        cluttering the output with repeated messages. It only shows
        when there's been no other output for at least `interval` seconds.
        """
        if self.quiet:
            yield
            return
        start = time.time()
        stop_event = threading.Event()
        
        def show_heartbeat():
            while not stop_event.is_set():
                stop_event.wait(interval)
                if not stop_event.is_set():
                    # Only show heartbeat if no recent output
                    time_since_output = time.time() - self._last_output_time
                    if time_since_output >= interval:
                        elapsed = self._elapsed(start)
                        # Use in-place update to avoid cluttering output
                        if self._caps.should_update_in_place():
                            with self._lock:
                                line = f"\r{INDENT_DETAIL}{self._theme.MUTED}{self._theme.INDICATOR_INFO} {message} ({elapsed}){self._theme.RESET}"
                                sys.stdout.write(line.ljust(70))
                                sys.stdout.flush()
                        else:
                            # Fallback for non-interactive terminals
                            self._print(f"{INDENT_DETAIL}{self._theme.MUTED}{self._theme.INDICATOR_INFO} {message} ({elapsed}){self._theme.RESET}")
        
        heartbeat_thread = threading.Thread(target=show_heartbeat, daemon=True)
        heartbeat_thread.start()
        try:
            yield
        finally:
            stop_event.set()
            heartbeat_thread.join(timeout=0.5)
            # Clear the heartbeat line
            if self._caps.should_update_in_place():
                with self._lock:
                    sys.stdout.write("\r" + " " * 70 + "\r")
                    sys.stdout.flush()

    def blank(self):
        if self.quiet:
            return
        self._print()

    def text(self, msg):
        if self.quiet:
            return
        self._print(msg)

    def divider(self, char="-"):
        if self.quiet:
            return
        width = min(50, self._term_width - 4)
        self._print(f"{INDENT_STEP}{self._theme.MUTED}{char * width}{self._theme.RESET}")

    def debug(self, msg):
        if not self.verbose:
            return
        self._print(f"{INDENT_DETAIL}{self._theme.MUTED}[debug] {msg}{self._theme.RESET}")


console = Console()


def set_console(new_console):
    global console
    console = new_console


def get_console():
    return console
