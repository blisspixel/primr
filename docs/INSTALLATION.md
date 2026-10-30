# Installation and Upgrades

Primr supports maintained Python 3.11 through 3.15 on Windows, macOS, and
Linux, with Python 3.15 as the default. Keyless `primr recon` and `primr prep`
need no provider keys or GPU. Provider-backed research remains estimate-first
and requires explicit spend approval.

## Recommended installation

Install Primr in an isolated tool environment with [uv](https://docs.astral.sh/uv/).
The explicit Python request avoids an unsupported default interpreter; uv can
download Python 3.15 automatically if needed:

```bash
uv tool install --python 3.15 primr
primr --version
```

Alternatively, install with pipx and an existing supported Python:

```bash
pipx install --python python3.15 primr
```

On Windows, `pipx install --python 3.15 primr` selects an installed Python 3.15
through the Python launcher. Python 3.11 through 3.14 are also supported. Plain
`pip install primr` works inside a virtual environment created with one of the
supported interpreters. Avoid installing into a distro-managed system Python,
including with `pip install --user`.

## Convenience installers

The repository installers prefer an existing uv and request Python 3.15. They
keep existing pipx installs with pipx, or use pipx with an installed Python 3.12
through 3.15 when uv is unavailable. Running a script from a Primr checkout
preserves the editable source installation. Download and inspect the script
before running it.

If neither tool is available, the installers can bootstrap pipx only with an
unmanaged Python outside a virtual environment that already has pip. If the
selected Python is externally managed, is a virtual environment, or lacks pip,
install uv or your distro's pipx package and rerun the script.
For example, Arch Linux uses `sudo pacman -S python-pipx`. See the
[pipx installation guide](https://pipx.pypa.io/stable/how-to/install-pipx.html)
for other platforms. The scripts report failed install commands as failures.

PowerShell:

```powershell
$primrInstaller = Join-Path $env:TEMP "primr-install.ps1"
Invoke-WebRequest https://raw.githubusercontent.com/pueo-labs/primr/main/scripts/install.ps1 -OutFile $primrInstaller
Get-Content $primrInstaller
powershell -ExecutionPolicy Bypass -File $primrInstaller
```

Bash:

```bash
primr_installer="$(mktemp)"
trap 'rm -f "$primr_installer"' EXIT
curl -fsSL https://raw.githubusercontent.com/pueo-labs/primr/main/scripts/install.sh -o "$primr_installer"
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

The update command uses the tool that owns the installation: `uv tool upgrade
primr`, `pipx upgrade primr`, or the current virtual environment's pip.

## PATH troubleshooting

After installing with uv, run `uv tool update-shell`. With pipx, run
`pipx ensurepath`. Open a new terminal and retry `primr --version`. Inspect the
isolated installation with `uv tool list` or `pipx list`; the system Python
does not normally see packages in a tool's environment.

For a plain pip install in an activated virtual environment, `python -m primr
--version` verifies the module. If that works but `primr` does not, check that
the environment's scripts directory is on the shell's `PATH`.

## Source checkout

For development, clone the repository and install the locked environment:

```bash
uv sync --locked --extra dev --extra api
uv run primr --version
```

See [Contributing](CONTRIBUTING.md) for the complete development and validation
workflow.
