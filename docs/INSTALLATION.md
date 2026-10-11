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

On Python 3.15 preview, Primr fails closed before starting the Playwright or
Patchright sync browser tiers because the current `greenlet` runtime can
terminate the interpreter. Safe HTTP, curl-based, and DrissionPage fallbacks
remain available, and their absence does not block the run preflight. Use
Python 3.14 for browser-complete research until the upstream sync runtime is
compatible and the guard is removed.

## Recommended installation

Install Primr in an isolated tool environment with [uv](https://docs.astral.sh/uv/).
The explicit Python request avoids an unsupported default interpreter; uv can
download Python 3.14 automatically if needed:

```bash
uv tool install --python 3.14 primr
primr --version
```

Alternatively, install with pipx and an existing supported Python:

```bash
pipx install --python python3.14 primr
```

On Windows, `pipx install --python 3.14 primr` selects an installed Python 3.14
through the Python launcher. Python 3.12 and 3.13 are also supported. Plain
`pip install primr` works inside a virtual environment created with one of the
supported interpreters. Avoid installing into a distro-managed system Python,
including with `pip install --user`.

## Convenience installers

The repository installers prefer an existing uv and request Python 3.14. They
keep existing pipx installs with pipx, or use pipx with an installed Python 3.12
through 3.14 when uv is unavailable. Running a script from a Primr checkout
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
