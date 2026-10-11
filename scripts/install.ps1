# Installer / updater for primr (Windows PowerShell)
# Recommended: download this file, inspect it, then run it with PowerShell.
#
# Idempotent: run it again any time to upgrade to the latest release.

$ErrorActionPreference = "Stop"

$Package = "primr"
$Cli = "primr"

Write-Host "==> Installing / updating $Package ..." -ForegroundColor Cyan
Write-Host ""

function Show-ToolGuidance {
    Write-Host "Install uv (https://docs.astral.sh/uv/getting-started/installation/) and rerun this script."
    Write-Host "Or install pipx: https://pipx.pypa.io/stable/how-to/install-pipx.html"
}

function Invoke-Checked([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed (exit $LASTEXITCODE)."
    }
}

# Keep an existing pipx install with its manager; prefer uv for fresh installs.
$pipxInstalled = $false
if (Get-Command pipx -ErrorAction SilentlyContinue) {
    try {
        $pipxList = & pipx list 2>$null | Out-String
        $pipxInstalled = $LASTEXITCODE -eq 0 -and $pipxList -match "(?im)^\s*package\s+$Package(?:\s|$)"
    } catch {
        $pipxInstalled = $false
    }
}

if (-not $pipxInstalled -and (Get-Command uv -ErrorAction SilentlyContinue)) {
    $installer = "uv"
    $pathCommand = "uv tool update-shell"
    Write-Host "==> Using uv with Python 3.14 (downloaded automatically if needed)" -ForegroundColor DarkGray
} else {
    $installer = "pipx"
    $pathCommand = "pipx ensurepath"
    $pipxCommand = "pipx"
    $pipxPrefix = @()
    $pythonPath = $null
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($minor in @("3.14", "3.13", "3.12")) {
            $candidates += @{ Command = "py"; Prefix = @("-$minor") }
        }
    }
    foreach ($name in @("python3.14", "python3.13", "python3.12", "python", "python3")) {
        if (Get-Command $name -ErrorAction SilentlyContinue) {
            $candidates += @{ Command = $name; Prefix = @() }
        }
    }
    foreach ($candidate in $candidates) {
        $prefix = $candidate.Prefix
        # Validate actual versions: a versioned executable can itself be a shim.
        try {
            & $candidate.Command @prefix -c 'import sys; sys.exit(not ((3, 12) <= sys.version_info[:2] <= (3, 14)))' 2>$null
        } catch {
            continue
        }
        if ($LASTEXITCODE -eq 0) {
            $pythonPath = & $candidate.Command @prefix -c 'import sys; print(sys.executable)'
            break
        }
    }
    if (-not $pythonPath) {
        Write-Host "Error: pipx needs Python 3.12 through 3.14 for browser-complete Primr installs." -ForegroundColor Red
        Show-ToolGuidance
        exit 1
    }
    $ver = & $pythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    Write-Host "==> Using Python $ver" -ForegroundColor DarkGray

    if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
        & $pythonPath -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)'
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Error: the selected Python is a virtual environment; install uv or pipx separately." -ForegroundColor Red
            Show-ToolGuidance
            exit 1
        }
        # PEP 668 also prohibits --user installs outside a virtual environment.
        & $pythonPath -c "import sys, sysconfig; from pathlib import Path; sys.exit(not (sys.prefix == sys.base_prefix and (Path(sysconfig.get_path('stdlib')) / 'EXTERNALLY-MANAGED').is_file()))"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Error: this Python is externally managed; install pipx with your package manager." -ForegroundColor Red
            Show-ToolGuidance
            exit 1
        }
        $pipAvailable = $false
        try {
            & $pythonPath -m pip --version 2>$null
            $pipAvailable = $LASTEXITCODE -eq 0
        } catch {
            $pipAvailable = $false
        }
        if (-not $pipAvailable) {
            Write-Host "Error: pipx and pip are unavailable." -ForegroundColor Red
            Show-ToolGuidance
            exit 1
        }
        Write-Host "==> pipx not found. Installing pipx..." -ForegroundColor Yellow
        Invoke-Checked $pythonPath @("-m", "pip", "install", "--user", "pipx")
        $pipxCommand = $pythonPath
        $pipxPrefix = @("-m", "pipx")
        Invoke-Checked $pipxCommand ($pipxPrefix + @("ensurepath"))
    }
}

# --- Dev mode: if run from inside a primr checkout, install EDITABLE from source
# so `primr` tracks the working tree instead of a frozen PyPI release. That trap
# (a released install shadowing local edits) is exactly what makes new commands
# like `keys set openai` look "missing". A downloaded copy outside a checkout
# installs the published package instead.
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
}

if ($installer -eq "uv") {
    $installArguments = @("tool", "install", "--upgrade", "--python", "3.14")
    if ($repoRoot) {
        $installArguments += @("--editable", "$repoRoot")
    } else {
        $installArguments += $Package
    }
    Invoke-Checked "uv" $installArguments
} else {
    if ($pipxInstalled) {
        # --force install ignores --python in older distro pipx releases.
        Write-Host "==> Reinstalling $Package with Python $ver..." -ForegroundColor Green
        Invoke-Checked $pipxCommand ($pipxPrefix + @("reinstall", "--python", $pythonPath, $Package))
    }
    if ($repoRoot) {
        Invoke-Checked $pipxCommand ($pipxPrefix + @("install", "--force", "--editable", "--python", $pythonPath, "$repoRoot"))
    } elseif (-not $pipxInstalled) {
        Write-Host "==> Installing $Package with pipx..." -ForegroundColor Green
        Invoke-Checked $pipxCommand ($pipxPrefix + @("install", "--python", $pythonPath, $Package))
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
    Write-Host "    Run '$pathCommand', then open a new terminal." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==> Done." -ForegroundColor Green
Write-Host ""
Write-Host "Keyless agent-host path:" -ForegroundColor Cyan
Write-Host "  1. Open a NEW terminal (so PATH is fresh)"
Write-Host "  2. Run: $Cli prep `"ExampleCo`" https://example.co --dry-run"
Write-Host "  3. Run: $Cli prep `"ExampleCo`" https://example.co"
Write-Host ""
Write-Host "Provider-backed path:" -ForegroundColor Cyan
Write-Host "  1. Run: $Cli init          # Guided provider setup"
Write-Host "  2. Run: $Cli doctor        # Verify configuration"
Write-Host "  3. Run: $Cli `"ExampleCo`" https://example.co --dry-run"
Write-Host "     Review the estimate and approve spend before launching the paid run."
Write-Host ""
Write-Host "To update later:"
Write-Host "  $Cli update                # Self-update to the latest release"
Write-Host ""
Write-Host "For development / editable from source:"
Write-Host "  git clone https://github.com/blisspixel/primr.git"
Write-Host "  cd primr"
Write-Host "  uv tool install --python 3.14 --editable ."
Write-Host ""
