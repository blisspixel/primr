# Easy one-line installer / updater for primr (Windows PowerShell)
# Usage (recommended):
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.ps1 | iex"
#
# Idempotent: run it again any time to upgrade to the latest release.

$ErrorActionPreference = "Stop"

$Package = "primr"
$Cli = "primr"

Write-Host "==> Installing / updating $Package ..." -ForegroundColor Cyan
Write-Host ""

# --- Locate a suitable Python (3.12+) ---
$python = "python"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    $python = "py"
}
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Python 3.12+ is required." -ForegroundColor Red
    Write-Host "Install from https://www.python.org/downloads/"
    exit 1
}

$ver = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
if (-not $ver -or ([version]$ver -lt [version]"3.12")) {
    Write-Host "Error: Python 3.12+ is required (found $ver)." -ForegroundColor Red
    Write-Host "Install from https://www.python.org/downloads/"
    exit 1
}
Write-Host "==> Using Python $ver" -ForegroundColor DarkGray

# --- Ensure pipx is available ---
if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    Write-Host "==> pipx not found. Installing pipx..." -ForegroundColor Yellow
    & $python -m pip install --user pipx --quiet
    & $python -m pipx ensurepath
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","User") + ";" + [System.Environment]::GetEnvironmentVariable("Path","Machine")
}

# --- Dev mode: if run from inside a primr checkout, install EDITABLE from source
# so `primr` tracks the working tree instead of a frozen PyPI release. That trap
# (a released install shadowing local edits) is exactly what makes new commands
# like `keys set openai` look "missing". The remote one-liner has no $PSScriptRoot,
# so this branch only fires for a local `.\scripts\install.ps1` run.
$repoRoot = $null
if ($PSScriptRoot) {
    $candidate = (Resolve-Path (Join-Path $PSScriptRoot "..") -ErrorAction SilentlyContinue)
    $pyproject = if ($candidate) { Join-Path $candidate "pyproject.toml" } else { $null }
    if ($pyproject -and (Test-Path $pyproject) -and (Select-String -Path $pyproject -Pattern 'name\s*=\s*"primr"' -Quiet)) {
        $repoRoot = $candidate
    }
}

if ($repoRoot) {
    Write-Host "==> Detected a primr checkout at $repoRoot" -ForegroundColor Green
    Write-Host "==> Installing EDITABLE from source (dev mode) so 'primr' tracks your working tree." -ForegroundColor Green
    Write-Host "    For day-to-day dev, 'uv run primr' from the repo is the lightest path." -ForegroundColor DarkGray
    pipx install --force --editable "$repoRoot"
} else {
    # --- Install fresh, or upgrade an existing install (idempotent) ---
    $alreadyInstalled = $false
    try {
        $pipxList = & pipx list 2>$null | Out-String
        if ($pipxList -match "(?im)^\s*package\s+$Package\b" -or $pipxList -match "(?i)\b$Package\b") {
            $alreadyInstalled = $true
        }
    } catch {
        $alreadyInstalled = $false
    }

    if ($alreadyInstalled) {
        Write-Host "==> $Package is already installed. Upgrading to the latest release..." -ForegroundColor Green
        pipx upgrade $Package
    } else {
        Write-Host "==> Installing $Package with pipx..." -ForegroundColor Green
        pipx install $Package
    }
}

# --- Verify ---
Write-Host ""
$resolved = Get-Command $Cli -ErrorAction SilentlyContinue
if ($resolved) {
    $installedVer = & $Cli --version 2>$null
    Write-Host "==> Installed: $installedVer" -ForegroundColor Green
    Write-Host "    at $($resolved.Source)" -ForegroundColor DarkGray
} else {
    Write-Host "==> Installed, but '$Cli' is not on PATH in this shell yet." -ForegroundColor Yellow
    Write-Host "    Open a NEW terminal so the updated PATH takes effect." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==> Done." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Open a NEW terminal (so PATH is fresh)"
Write-Host "  2. Run: $Cli init          # Guided setup for API keys + browser"
Write-Host "  3. Run: $Cli doctor        # Verify everything"
Write-Host ""
Write-Host "Quick start:"
Write-Host "  $Cli `"Company Name`" https://company.com"
Write-Host ""
Write-Host "To update later:"
Write-Host "  $Cli update                # Self-update to the latest release"
Write-Host ""
Write-Host "For development / editable from source:"
Write-Host "  git clone https://github.com/blisspixel/primr.git"
Write-Host "  cd primr"
Write-Host "  pipx install -e ."
Write-Host ""
