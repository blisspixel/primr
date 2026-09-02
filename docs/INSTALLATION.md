# Installation and Upgrades

Primr requires Python 3.12 or newer. The keyless `primr recon` and `primr prep`
commands need no provider API keys or GPU. Configure provider keys only when
you want an estimated, billable research run.

Stable support currently covers Python 3.12 through 3.14 on Windows, macOS,
and Linux. Python 3.15.0rc2 was released on September 1, 2026, with final
scheduled for October 1. CI includes a hard Linux 3.15 preview lane, but Primr
does not yet claim stable or cross-platform 3.15 support. On Windows, the
locked MCP and DOCX stack currently depends on `pywin32`, whose latest release
does not yet publish a `cp315` wheel. Keep using Python 3.14 on Windows until
that upstream dependency is available and the full platform matrix passes.
The Linux preview lane currently builds `lxml` from source and installs its
`libxml2`, `libxslt`, and zlib development headers explicitly because a 3.15
wheel is not yet available.

## Recommended installation

Install Primr in an isolated environment with pipx:

```bash
pipx install primr
primr --version
```

Plain `pip install primr` also works. On Windows, prefer pipx or the convenience
installer if `primr` is not on `PATH` after installation.

## Convenience installers

The repository installers set up pipx and handle common `PATH` issues. Download
and inspect the script before running it.

PowerShell:

```powershell
$primrInstaller = Join-Path $env:TEMP "primr-install.ps1"
Invoke-WebRequest https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.ps1 -OutFile $primrInstaller
Get-Content $primrInstaller
powershell -ExecutionPolicy Bypass -File $primrInstaller
```

Bash:

```bash
primr_installer="$(mktemp)"
trap 'rm -f "$primr_installer"' EXIT
curl -fsSL https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.sh -o "$primr_installer"
cat "$primr_installer"
bash "$primr_installer"
```

## Provider-backed setup

Run setup only when you want the billable provider-backed pipeline:

```bash
primr init
primr doctor
```

See [API Key Setup](API_KEYS.md) for provider credentials and
[Configuration](CONFIG.md) for the complete settings reference.

## Upgrade

Check for a release without changing the environment:

```bash
primr update --check
```

Run `primr update` in a foreground terminal and review its confirmation prompt.
An approved automated upgrade must use `primr update --yes`; without `--yes`,
a noninteractive invocation exits before inspecting or changing the installed
package.

## PATH troubleshooting

After installing with pipx, run `pipx ensurepath`, open a new terminal, and
retry `primr --version`. You can also verify the installed module directly:

```bash
python -m primr --version
```

If the module command works but `primr` does not, the Python scripts directory
is not on the shell's `PATH`. The convenience installers above cover the common
Windows and Unix cases.

## Source checkout

For development, clone the repository and install the locked environment:

```bash
uv sync --locked --extra dev --extra api
uv run primr --version
```

See [Contributing](CONTRIBUTING.md) for the complete development and validation
workflow.
