# Easy one-line installer for primr (Windows PowerShell)
# Usage (recommended):
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.ps1 | iex"

$ErrorActionPreference = "Stop"

$Package = "primr"
$Cli = "primr"

Write-Host "==> Installing $Package ..." -ForegroundColor Cyan
Write-Host ""

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
    exit 1
}

if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    Write-Host "==> pipx not found. Installing pipx..." -ForegroundColor Yellow
    & $python -m pip install --user pipx --quiet
    & $python -m pipx ensurepath
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","User") + ";" + [System.Environment]::GetEnvironmentVariable("Path","Machine")
}

Write-Host "==> Using pipx to install $Package ..." -ForegroundColor Green
pipx install $Package

Write-Host ""
Write-Host "==> Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Open a NEW terminal"
Write-Host "  2. Run: $Cli init          # Guided setup for API keys + browser"
Write-Host "  3. Run: $Cli doctor        # Verify everything"
Write-Host ""
Write-Host "Quick start:"
Write-Host "  $Cli `"Company Name`" https://company.com"
Write-Host ""
Write-Host "For development / editable from source:"
Write-Host "  git clone https://github.com/blisspixel/primr.git"
Write-Host "  cd primr"
Write-Host "  pipx install -e ."
Write-Host ""