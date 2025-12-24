#!/usr/bin/env python3
"""
Primr Setup - Interactive setup wizard
"""

import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Try to use rich for beautiful output, fall back to basic if not available
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Prompt, Confirm
    RICH = True
except ImportError:
    RICH = False

console = Console() if RICH else None


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
        )
        
        for line in process.stdout:
            line = line.strip()
            output_lines.append(line)
            if line and len(line) < 60:
                progress.update(task, description=f"{status_msg} [dim]{line}[/dim]")
        
        process.wait()
    
    if process.returncode != 0:
        # Show relevant error lines
        for line in output_lines:
            if line and any(x in line.lower() for x in ["error", "failed", "cannot", "not found", "denied"]):
                console.print(f"    [dim]{line[:70]}[/dim]")
    
    return process.returncode == 0, output_lines


def install_primr():
    """Install primr with retry logic and cleanup."""
    # Clean first to avoid stale artifacts
    clean_build_artifacts()
    
    # Try normal install
    success, output = run_with_status(
        [sys.executable, "-m", "pip", "install", "-e", "."],
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
        
        # Retry with --user flag
        success, output = run_with_status(
            [sys.executable, "-m", "pip", "install", "-e", ".", "--user"],
            "Installing (user mode)"
        )
        
        if success:
            return True
        
        # Last resort: try without editable mode
        console.print("  [yellow]›[/yellow] Trying non-editable install...")
        clean_build_artifacts()
        time.sleep(1)
        
        success, _ = run_with_status(
            [sys.executable, "-m", "pip", "install", ".", "--user"],
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
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        console.print(f"  [red]✗[/red] Python {v.major}.{v.minor} [dim](need 3.10+)[/dim]")
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
    required = ["GEMINI_API_KEY", "SEARCH_API_KEY", "SEARCH_ENGINE_ID"]
    current = get_env_keys()
    missing = []
    
    for key in required:
        if key in current and key_looks_valid(key, current[key]):
            console.print(f"  [green]✓[/green] {key}")
        else:
            missing.append(key)
    
    if missing:
        console.print(f"\n  [cyan]Need {len(missing)} API key(s) from Google[/cyan]")
        
        key_info = {
            "GEMINI_API_KEY": (
                "https://aistudio.google.com/apikey",
                "Powers AI analysis"
            ),
            "SEARCH_API_KEY": (
                "https://console.cloud.google.com/apis/credentials",
                "Enable 'Custom Search API' first"
            ),
            "SEARCH_ENGINE_ID": (
                "https://programmablesearchengine.google.com/",
                "Create one that searches entire web"
            ),
        }
        
        for key in missing:
            url, desc = key_info[key]
            current[key] = get_key_interactive(key, url, desc)
            console.print(f"  [green]✓[/green] {key}")
        
        Path(".env").write_text("\n".join(f"{k}={v}" for k, v in current.items()) + "\n")
    
    # Verify
    console.print()
    console.rule(style="dim")
    console.print()
    
    with console.status("Verifying setup..."):
        result = subprocess.run(
            [sys.executable, "-m", "primr", "doctor"],
            capture_output=True, text=True
        )
    
    # Show doctor output
    if result.stdout:
        console.print(result.stdout)
    if result.stderr:
        console.print(result.stderr)
    
    console.print()
    if result.returncode == 0:
        console.print(Panel.fit(
            "[green bold]Ready![/green bold]\n\n"
            "Try: [cyan]primr \"Acme Corp\" https://acme.com[/cyan]",
            border_style="green",
            padding=(0, 2),
        ))
    else:
        console.print("[yellow]Setup complete but doctor found issues above[/yellow]")
    console.print()


def main_basic():
    """Fallback for when rich isn't available."""
    print("\nPrimr Setup\n")
    
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        print(f"  x Python {v.major}.{v.minor} (need 3.10+)")
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
    if not RICH:
        try:
            install_rich_and_restart()
        except Exception:
            main_basic()
    else:
        main_rich()
