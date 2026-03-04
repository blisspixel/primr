#!/usr/bin/env python3
"""
Primr Setup - Interactive setup wizard
"""

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows so Rich can print Unicode symbols.
# Must run before any Rich imports since Rich inspects the stream encoding.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Try to use rich for beautiful output, fall back to basic if not available
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Prompt, Confirm
    RICH = True
except ImportError:
    RICH = False

console = Console(legacy_windows=False) if RICH else None


def find_best_python():
    """Find the best Python interpreter (3.11+) on the system."""
    # Check current interpreter first
    v = sys.version_info
    if v.major >= 3 and v.minor >= 11:
        return sys.executable
    
    # On Windows, try py launcher
    if sys.platform == "win32":
        try:
            # Check what versions are available
            result = subprocess.run(
                ["py", "-0"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Parse output to find 3.11+
            for line in result.stdout.split("\n"):
                if "-3." in line:
                    # Extract version like "-3.13-64"
                    parts = line.strip().split()
                    for part in parts:
                        if part.startswith("-3."):
                            version_str = part.replace("-", "").split("-")[0]
                            try:
                                minor = int(version_str.split(".")[1])
                                if minor >= 11:
                                    # Found a good version, get its path
                                    py_result = subprocess.run(
                                        ["py", part, "-c", "import sys; print(sys.executable)"],
                                        capture_output=True,
                                        text=True,
                                        timeout=5
                                    )
                                    if py_result.returncode == 0:
                                        return py_result.stdout.strip()
                            except (ValueError, IndexError):
                                continue
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    
    # Try common names
    for cmd in ["python3.13", "python3.12", "python3.11", "python3"]:
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Check version
                version_line = result.stdout or result.stderr
                if "Python 3." in version_line:
                    version_str = version_line.split()[1]
                    minor = int(version_str.split(".")[1])
                    if minor >= 11:
                        # Get full path
                        path_result = subprocess.run(
                            [cmd, "-c", "import sys; print(sys.executable)"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if path_result.returncode == 0:
                            return path_result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    
    return None


def add_to_user_path_windows(scripts_dir: str) -> bool:
    """Add a directory to the user's PATH on Windows (no admin required)."""
    if sys.platform != "win32":
        return False
    
    try:
        import winreg
        
        # Open user environment variables
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE
        )
        
        try:
            current_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path = ""
        
        # Check if already in PATH
        path_dirs = [p.strip().lower() for p in current_path.split(";") if p.strip()]
        if scripts_dir.lower() in path_dirs:
            winreg.CloseKey(key)
            return True  # Already there
        
        # Add to PATH
        new_path = f"{current_path};{scripts_dir}" if current_path else scripts_dir
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
        winreg.CloseKey(key)
        
        # Broadcast environment change so new terminals pick it up
        try:
            import ctypes
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x1A
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0, 1000, None
            )
        except Exception:
            pass  # Best effort
        
        return True
    except Exception:
        return False


def get_user_scripts_dir() -> str | None:
    """Get the user's Python Scripts directory."""
    if sys.platform == "win32":
        # Check user site-packages location
        import site
        user_base = site.getuserbase()
        if user_base:
            return os.path.join(user_base, "Scripts")
    return None


def install_rich_and_restart():
    """Install rich and restart the script."""
    print("Installing setup dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "rich", "-q"], check=True)
    import os
    os.execv(sys.executable, [sys.executable] + sys.argv)


def clean_build_artifacts():
    """Remove build artifacts that can cause permission issues."""
    artifacts = [
        Path("src/primr.egg-info"),
        Path("build"),
        Path("dist"),
        Path(".eggs"),
    ]
    
    for artifact in artifacts:
        if artifact.exists():
            try:
                if artifact.is_dir():
                    # Try multiple times for network/sync drives
                    for attempt in range(3):
                        try:
                            shutil.rmtree(artifact, ignore_errors=False)
                            break
                        except PermissionError:
                            time.sleep(0.5 * (attempt + 1))
                            shutil.rmtree(artifact, ignore_errors=True)
                else:
                    artifact.unlink(missing_ok=True)
            except Exception:
                pass  # Best effort
    
    # Longer delay for network/sync drives (OneDrive, VMware shared folders)
    time.sleep(1.0)


def run_with_status(cmd, status_msg):
    """Run command with spinner, show errors if it fails."""
    output_lines = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(status_msg, total=None)
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
        )
        
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(line)
                # Only show short, meaningful status updates
                if len(line) < 50 and any(x in line.lower() for x in ["installing", "downloading", "building", "collecting"]):
                    progress.update(task, description=f"{status_msg} [dim]{line[:40]}[/dim]")
        
        process.wait()
    
    if process.returncode != 0:
        # Show relevant error lines
        console.print()
        for line in output_lines[-10:]:  # Last 10 lines only
            if line and any(x in line.lower() for x in ["error", "failed", "cannot", "not found", "denied"]):
                console.print(f"    [dim]{line[:80]}[/dim]")
    
    return process.returncode == 0, output_lines


def install_primr():
    """Install primr with retry logic and cleanup."""
    # Clean first to avoid stale artifacts
    clean_build_artifacts()
    
    # Try normal install (suppress most output)
    success, output = run_with_status(
        [sys.executable, "-m", "pip", "install", "-e", ".", "-q"],
        "Installing primr"
    )
    
    if success:
        return True
    
    # Check if it's a permission/access error
    output_text = "\n".join(output).lower()
    if "access" in output_text or "denied" in output_text or "winerror" in output_text:
        console.print("  [yellow]›[/yellow] Permission issue, cleaning and retrying...")
        clean_build_artifacts()
        time.sleep(2)  # Extra delay for sync drives
        
        # Retry with --user flag (suppress most output)
        success, output = run_with_status(
            [sys.executable, "-m", "pip", "install", "-e", ".", "--user", "-q"],
            "Installing (user mode)"
        )
        
        if success:
            return True
        
        # Last resort: try without editable mode
        console.print("  [yellow]›[/yellow] Trying non-editable install...")
        clean_build_artifacts()
        time.sleep(1)
        
        success, _ = run_with_status(
            [sys.executable, "-m", "pip", "install", ".", "--user", "-q"],
            "Installing (non-editable)"
        )
        
        if success:
            return True
    
    return False


def is_installed(package):
    """Check if a Python package is importable."""
    try:
        __import__(package)
        return True
    except ImportError:
        return False


def get_env_keys():
    """Get current .env keys."""
    env = Path(".env")
    if not env.exists():
        return {}
    
    keys = {}
    for line in env.read_text().split("\n"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if v and not v.startswith("your_"):
                keys[k] = v
    return keys


def key_looks_valid(name, value):
    """Basic validation that a key looks plausible."""
    if not value or len(value) < 10:
        return False
    if name in ["GEMINI_API_KEY", "SEARCH_API_KEY"]:
        return value.startswith("AIza") and len(value) > 30
    if name == "SEARCH_ENGINE_ID":
        return len(value) >= 10
    if name == "XAI_API_KEY":
        return value.startswith("xai-") and len(value) > 20
    return True


def get_key_interactive(name, url, description):
    """Get a single API key from user."""
    console.print()
    console.print(f"  [bold cyan]{name}[/bold cyan]")
    console.print(f"  [dim]{description}[/dim]")
    console.print()
    
    if Confirm.ask("  Open in browser?", default=True):
        webbrowser.open(url)
        console.print(f"  [dim]Opened {url[:50]}...[/dim]")
    
    while True:
        value = Prompt.ask("\n  Paste key").strip()
        if value and key_looks_valid(name, value):
            return value
        elif value:
            console.print("  [yellow]Doesn't look right - try again[/yellow]")
        else:
            console.print("  [red]Required[/red]")


def main_rich():
    """Main setup flow with rich UI."""
    console.print()
    console.print(Panel.fit(
        "[bold]Primr Setup[/bold]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()
    
    # Python check
    v = sys.version_info
    current_python = sys.executable
    
    if v.major < 3 or (v.major == 3 and v.minor < 11):
        console.print(f"  [red]✗[/red] Python {v.major}.{v.minor} [dim]({current_python})[/dim]")
        
        # Try to find a better Python
        console.print()
        console.print("  [yellow]Looking for Python 3.11+...[/yellow]")
        better_python = find_best_python()
        
        if better_python:
            console.print(f"  [green]✓[/green] Found Python 3.11+ at: [cyan]{better_python}[/cyan]")
            console.print()
            console.print("  [yellow]Restarting with correct Python...[/yellow]")
            console.print()
            
            # Restart with the better Python
            # On Windows, os.execv doesn't truly replace the process —
            # it spawns a child and exits, leaving cmd.exe without a
            # prompt after the child finishes.  Use subprocess instead.
            if sys.platform == "win32":
                result = subprocess.run([better_python] + sys.argv)
                sys.exit(result.returncode)
            else:
                os.execv(better_python, [better_python] + sys.argv)
        else:
            console.print()
            console.print("  [yellow]Python 3.11 or newer is required[/yellow]")
            console.print()
            console.print("  [cyan]Download from:[/cyan] https://www.python.org/downloads/")
            console.print()
            console.print("  [dim]Or use a version manager:[/dim]")
            console.print("  [dim]• Windows: winget install Python.Python.3.13[/dim]")
            console.print("  [dim]• macOS: brew install python@3.13[/dim]")
            console.print("  [dim]• Linux: pyenv install 3.13[/dim]")
            console.print()
            console.print("  [dim]After installing, try:[/dim]")
            console.print("  [cyan]• Windows: py -3.13 setup_env.py[/cyan]")
            console.print("  [cyan]• macOS/Linux: python3.13 setup_env.py[/cyan]")
            console.print()
            sys.exit(1)
    
    console.print(f"  [green]✓[/green] Python {v.major}.{v.minor}")
    
    # Install primr
    if is_installed("primr"):
        console.print("  [green]✓[/green] Primr installed")
    else:
        if install_primr():
            console.print("  [green]✓[/green] Primr installed")
        else:
            console.print("  [red]✗[/red] Installation failed")
            console.print()
            console.print("  [yellow]This often happens on network/sync drives.[/yellow]")
            console.print("  [dim]Try one of these:[/dim]")
            console.print("  [dim]1. Copy the folder to a local drive (C:)[/dim]")
            console.print("  [dim]2. Close VS Code and other programs using this folder[/dim]")
            console.print("  [dim]3. Delete src/primr.egg-info folder manually[/dim]")
            console.print("  [dim]4. Run: pip install . --user[/dim]")
            sys.exit(1)
    
    # Playwright
    if is_installed("playwright"):
        console.print("  [green]✓[/green] Playwright ready")
    else:
        run_with_status([sys.executable, "-m", "pip", "install", "playwright"], "Installing playwright")
        run_with_status([sys.executable, "-m", "playwright", "install", "chromium"], "Downloading browser")
        if is_installed("playwright"):
            console.print("  [green]✓[/green] Playwright ready")
        else:
            console.print("  [dim]›[/dim] Playwright skipped [dim](optional)[/dim]")
    
    # API keys
    required = ["GEMINI_API_KEY"]
    optional_keys = ["XAI_API_KEY", "SEARCH_API_KEY", "SEARCH_ENGINE_ID"]
    current = get_env_keys()
    missing = []

    for key in required:
        if key in current and key_looks_valid(key, current[key]):
            console.print(f"  [green]✓[/green] {key}")
        else:
            missing.append(key)

    # Show XAI/Grok status
    if "XAI_API_KEY" in current and key_looks_valid("XAI_API_KEY", current["XAI_API_KEY"]):
        console.print("  [green]✓[/green] XAI_API_KEY [dim](Grok — default model)[/dim]")
    else:
        console.print("  [dim]·[/dim] XAI_API_KEY [dim](optional — enables Grok default mode, ~$0.55/run)[/dim]")

    # Show search provider status
    console.print(f"  [green]✓[/green] Search: DuckDuckGo [dim](no API key needed)[/dim]")

    # Check optional Google keys
    has_google_keys = all(
        key in current and key_looks_valid(key, current[key])
        for key in ["SEARCH_API_KEY", "SEARCH_ENGINE_ID"]
    )
    if has_google_keys:
        console.print(f"  [green]✓[/green] Google Search [dim](optional, also configured)[/dim]")

    if missing:
        console.print(f"\n  [cyan]Need {len(missing)} API key(s)[/cyan]")

        key_info = {
            "GEMINI_API_KEY": (
                "https://aistudio.google.com/apikey",
                "Powers AI analysis (required)"
            ),
        }

        for key in missing:
            url, desc = key_info[key]
            current[key] = get_key_interactive(key, url, desc)
            console.print(f"  [green]✓[/green] {key}")

        Path(".env").write_text("\n".join(f"{k}={v}" for k, v in current.items()) + "\n")

    # Offer to set up XAI key if not present
    if "XAI_API_KEY" not in current or not key_looks_valid("XAI_API_KEY", current["XAI_API_KEY"]):
        console.print()
        if Confirm.ask("  Set up XAI_API_KEY for Grok? [dim](faster, cheaper default)[/dim]", default=False):
            xai_key = get_key_interactive(
                "XAI_API_KEY",
                "https://console.x.ai/",
                "Powers Grok analysis — default mode (~$0.55/run, ~30 min)"
            )
            current["XAI_API_KEY"] = xai_key
            Path(".env").write_text("\n".join(f"{k}={v}" for k, v in current.items()) + "\n")
            console.print("  [green]✓[/green] XAI_API_KEY")
    
    # Verify
    console.print()
    console.rule(style="dim")
    console.print()
    
    # Run doctor with fully captured output (only once!)
    try:
        with console.status("Verifying setup...", spinner="dots"):
            result = subprocess.run(
                [sys.executable, "-m", "primr", "doctor"],
                capture_output=True,
                text=True,
                timeout=30,
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL  # Prevent any input prompts
            )
    except subprocess.TimeoutExpired:
        console.print("  [red]✗[/red] Verification timed out")
        sys.exit(1)
    except Exception as e:
        console.print(f"  [red]✗[/red] Verification failed: {e}")
        sys.exit(1)
    
    # Show doctor output (only once, clean)
    if result.returncode == 0:
        # Parse and show just the summary
        lines = result.stdout.strip().split("\n") if result.stdout else []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("Primr Doctor"):
                console.print(f"  {line}")
    else:
        # Show errors
        if result.stderr:
            console.print("  [red]Errors:[/red]")
            for line in result.stderr.strip().split("\n"):
                if line.strip():
                    console.print(f"    {line}")
    
    console.print()
    if result.returncode == 0:
        # Check if primr CLI is on PATH (Windows issue)
        cli_available = shutil.which("primr") is not None
        
        if cli_available:
            console.print(Panel.fit(
                "[green bold]Ready![/green bold]\n\n"
                "Try: [cyan]primr \"Acme Corp\" https://acme.com[/cyan]",
                border_style="green",
                padding=(0, 2),
            ))
        else:
            # CLI not on PATH - try to fix it automatically on Windows
            scripts_dir = get_user_scripts_dir()
            path_fixed = False
            
            if scripts_dir and sys.platform == "win32":
                console.print("  [yellow]>[/yellow] Adding Python Scripts to PATH...")
                path_fixed = add_to_user_path_windows(scripts_dir)
                if path_fixed:
                    console.print("  [green]✓[/green] PATH updated")
            
            if path_fixed:
                console.print(Panel.fit(
                    "[green bold]Ready![/green bold]\n\n"
                    "[yellow]Open a new terminal[/yellow], then:\n\n"
                    "  [cyan]primr \"Acme Corp\" https://acme.com[/cyan]",
                    border_style="green",
                    padding=(0, 2),
                ))
            else:
                console.print(Panel.fit(
                    "[green bold]Ready![/green bold]\n\n"
                    "Use: [cyan]python -m primr \"Acme Corp\" https://acme.com[/cyan]",
                    border_style="green",
                    padding=(0, 2),
                ))
    else:
        console.print("[yellow]Setup complete but doctor found issues above[/yellow]")
    console.print()
    sys.exit(0)


def main_basic():
    """Fallback for when rich isn't available."""
    print("\nPrimr Setup\n")
    
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 11):
        print(f"  x Python {v.major}.{v.minor} (need 3.11+)")
        print()
        print("  Python 3.11 or newer is required")
        print()
        print("  Download from: https://www.python.org/downloads/")
        print()
        print("  Or use a version manager:")
        print("  • Windows: winget install Python.Python.3.13")
        print("  • macOS: brew install python@3.13")
        print("  • Linux: pyenv install 3.13")
        print()
        sys.exit(1)
    print(f"  + Python {v.major}.{v.minor}")
    
    if is_installed("primr"):
        print("  + Primr installed")
    else:
        print("  > Cleaning build artifacts...")
        clean_build_artifacts()
        print("  > Installing primr...")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."])
        if result.returncode == 0:
            print("  + Primr installed")
        else:
            print("  x Installation failed")
            sys.exit(1)
    
    print("\nRun again for better experience (rich now installed)\n")


if __name__ == "__main__":
    try:
        if not RICH:
            try:
                install_rich_and_restart()
            except Exception:
                main_basic()
        else:
            main_rich()
    except KeyboardInterrupt:
        console.print("\n\n  [yellow]Setup cancelled[/yellow]\n") if RICH else print("\n\nSetup cancelled\n")
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception as e:
        if RICH:
            console.print(f"\n  [red]✗[/red] Unexpected error: {e}\n")
        else:
            print(f"\nError: {e}\n")
        sys.exit(1)
