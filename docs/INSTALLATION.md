# Installation and Upgrades

Primr requires Python 3.12 or newer. The keyless `primr recon` and `primr prep`
commands need no provider API keys or GPU. Configure provider keys only when
you want an estimated, billable research run.

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
