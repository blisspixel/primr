"""Execute the convenience installers without installing tools or changing PATH config."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The same command double drives both real shells. Every attempted operation is
# recorded, including Python probes, so unsafe bootstrap attempts cannot hide.
STUB = """\
import json
import os
import sys
import sysconfig
from collections import namedtuple
from pathlib import Path

config = json.loads(Path(os.environ['INSTALLER_CONFIG']).read_text())
name, *args = sys.argv[1:]
with Path(os.environ['INSTALLER_LOG']).open('a') as log:
    log.write(json.dumps([name, *args]) + '\\n')
if name == 'py' or name.startswith('python'):
    if name == 'py':
        version = args.pop(0).removeprefix('-')
        if version not in config['versions'].values():
            print('Requested Python is not installed', file=sys.stderr)
            sys.exit(1)
    else:
        version = config['versions'].get(name, name.removeprefix('python'))
    if args[0] == '-c':
        # Execute the installer's real probe against a controlled interpreter,
        # including its version bounds and the PEP 668 marker check.
        Version = namedtuple('Version', 'major minor micro releaselevel serial')
        sys.version_info = Version(*map(int, version.split('.')), 0, 'final', 0)
        sys.executable = 'python' + version
        sys.prefix = config['stdlib']
        sys.base_prefix = config['stdlib'] + '-base' if config.get('venv') else sys.prefix
        sysconfig.get_path = lambda *_args, **_kwargs: config['stdlib']
        exec(args[1])
        sys.exit(0)
    if args[:2] == ['-m', 'pip']:
        if args[2:] == ['--version']:
            sys.exit(0 if config.get('pip') else 1)
        sys.exit(config.get('fail', 0))
    if args[:2] == ['-m', 'pipx']:
        name, args = 'pipx', args[2:]
if name == 'pipx' and args == ['list']:
    print(config.get('listing', '    package primr 1.0.0, installed using Python 3.15' if config.get('installed') else ''))
    sys.exit(0)
if name in ('uv', 'pipx'):
    sys.exit(config.get('fail', 0))
sys.exit(0)
"""


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@pytest.fixture(params=["bash", "powershell"])
def installer(request, tmp_path):
    shell = request.param
    executable = shutil.which("bash" if shell == "bash" else "pwsh")
    if executable is None and shell == "powershell":
        executable = shutil.which("powershell")
    if executable is None or (shell == "bash" and os.name == "nt"):
        pytest.skip(f"{shell} is unavailable")

    def run(*, tools=(), versions=None, checkout=False, **options):
        versions = versions or {}
        available = [*tools, *versions]
        stdlib = tmp_path / "stdlib"
        stdlib.mkdir()
        if options.get("managed"):
            (stdlib / "EXTERNALLY-MANAGED").touch()
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"versions": versions, "stdlib": str(stdlib), **options}), encoding="utf-8"
        )
        log = tmp_path / "commands.jsonl"
        stub = tmp_path / "stub.py"
        stub.write_text(STUB, encoding="utf-8")
        root = tmp_path / "source checkout" if checkout else tmp_path / "download"
        scripts = root / "scripts"
        scripts.mkdir(parents=True)
        if checkout:
            (root / "pyproject.toml").write_text('[project]\nname = "primr"\n', encoding="utf-8")
        suffix = "sh" if shell == "bash" else "ps1"
        script = scripts / f"install.{suffix}"
        shutil.copyfile(REPO_ROOT / "scripts" / f"install.{suffix}", script)
        env = {
            **os.environ,
            "INSTALLER_CONFIG": str(config),
            "INSTALLER_LOG": str(log),
        }
        if shell == "bash":
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            for name in available:
                command = bin_dir / name
                command.write_text(
                    f"#!{sys.executable}\nimport runpy, sys\n"
                    f"sys.argv.insert(1, {name!r})\nrunpy.run_path({str(stub)!r}, run_name='__main__')\n",
                    encoding="utf-8",
                )
                command.chmod(0o755)
            for name in ("dirname", "grep"):
                (bin_dir / name).symlink_to(shutil.which(name))
            env["PATH"] = str(bin_dir)
            # Bootstrap's ensurepath is a stub; its local bin remains isolated.
            env["PIPX_BIN_DIR"] = str(bin_dir)
            command = [executable, str(script)]
        else:
            # Functions stand in for native commands, leaving the real PowerShell
            # parser, script control flow, and argument expansion under test.
            names = sorted({*available, "python3.14", "python3.13", "python3.12"})
            definitions = []
            for name in names:
                definitions.append(
                    f"function global:{name} {{ & {_ps_quote(sys.executable)} "
                    f"{_ps_quote(str(stub))} {_ps_quote(name)} @args; "
                    "$global:LASTEXITCODE = $LASTEXITCODE }"
                )
            visible = ", ".join(_ps_quote(name) for name in available)
            wrapper = tmp_path / "run.ps1"
            wrapper.write_text(
                "\n".join(definitions)
                + "\nfunction global:Get-Command { param($Name, $ErrorAction) "
                + f"if ($Name -in @({visible})) {{ [pscustomobject]@{{Source=$Name}} }} }}\n"
                + f"& {_ps_quote(str(script))}\nexit $LASTEXITCODE\n",
                encoding="utf-8",
            )
            command = [executable, "-NoProfile", "-NonInteractive", "-File", str(wrapper)]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls, root

    return run


@pytest.mark.parametrize(
    "listing",
    [
        "primr is not installed",
        "    package primr-helper 1.0.0, installed using Python 3.14",
        "    package primr_tools 1.0.0, installed using Python 3.14",
        "    package primr2 1.0.0, installed using Python 3.14",
    ],
)
def test_uv_needs_no_system_python_and_wins_over_unused_pipx(installer, listing):
    result, calls, _ = installer(tools=("uv", "pipx"), listing=listing)
    assert result.returncode == 0, result.stderr
    assert ["uv", "tool", "install", "--upgrade", "--python", "3.14", "primr"] in calls
    assert not any(call[0].startswith("python") for call in calls)
    assert "uv tool update-shell" in result.stdout


@pytest.mark.parametrize("manager", ["uv", "pipx"])
@pytest.mark.parametrize("installed", [False, True])
def test_checkout_remains_editable_with_quoted_path(installer, manager, installed):
    result, calls, root = installer(
        tools=(manager,), versions={"python3.14": "3.14"}, checkout=True, installed=installed
    )
    assert result.returncode == 0, result.stderr
    install = next(call for call in calls if "--editable" in call)
    assert str(root) == install[-1]
    assert "--python" in install
    assert "EDITABLE" in result.stdout


def test_pipx_avoids_preview_default_and_misleading_versioned_shim(installer):
    result, calls, _ = installer(
        tools=("pipx",),
        versions={"python3.14": "3.15", "python3.13": "3.13", "python3": "3.15"},
    )
    assert result.returncode == 0, result.stderr
    install = next(call for call in calls if call[:2] == ["pipx", "install"])
    assert Path(install[3]).name == "python3.13"
    assert install[-1] == "primr"


def test_supported_python_selected_with_preview_launcher_default(installer, request):
    result, calls, _ = installer(
        tools=("pipx", "py"), versions={"python3.14": "3.14", "python": "3.15"}
    )
    assert result.returncode == 0, result.stderr
    install = next(call for call in calls if call[:2] == ["pipx", "install"])
    assert Path(install[3]).name == "python3.14"
    if request.node.callspec.params["installer"] == "powershell":
        assert any(call[:2] == ["py", "-3.14"] for call in calls)


@pytest.mark.parametrize("version", ["3.12", "3.13", "3.14"])
def test_each_stable_python_is_supported(installer, version):
    result, calls, _ = installer(tools=("pipx",), versions={"python3": version})
    assert result.returncode == 0, result.stderr
    assert any(call[:2] == ["pipx", "install"] for call in calls)


def test_existing_pipx_install_is_recreated_with_supported_python(installer):
    result, calls, _ = installer(
        tools=("uv", "pipx"), versions={"python3.14": "3.14"}, installed=True
    )
    assert result.returncode == 0, result.stderr
    reinstall = next(call for call in calls if call[:2] == ["pipx", "reinstall"])
    assert reinstall[2] == "--python"
    assert Path(reinstall[3]).name == "python3.14"
    assert not any(call[0] == "uv" for call in calls)


def test_preview_only_python_fails_with_actionable_guidance(installer):
    result, calls, _ = installer(tools=("pipx",), versions={"python3": "3.15"})
    assert result.returncode != 0
    assert "Python 3.12 through 3.14" in result.stdout
    assert "Install uv" in result.stdout
    assert not any("install" in call or "reinstall" in call for call in calls)


@pytest.mark.parametrize("managed,pip", [(True, True), (False, False)])
def test_unsafe_or_unavailable_pip_does_not_bootstrap(installer, request, managed, pip):
    result, calls, _ = installer(
        tools=("pacman",), versions={"python3.14": "3.14"}, managed=managed, pip=pip
    )
    assert result.returncode != 0
    assert (
        "externally managed" in result.stdout if managed else "pip are unavailable" in result.stdout
    )
    assert "Install uv" in result.stdout
    if request.node.callspec.params["installer"] == "bash":
        assert "sudo pacman -S python-pipx" in result.stdout
    assert not any("install" in call for call in calls)
    assert not any(call[0] == "pacman" for call in calls)


def test_unmanaged_python_with_pip_preserves_bootstrap_workflow(installer):
    result, calls, _ = installer(versions={"python3.14": "3.14"}, pip=True)
    assert result.returncode == 0, result.stderr
    assert any(call[1:] == ["-m", "pip", "install", "--user", "pipx"] for call in calls)
    install = next(call for call in calls if call[1:4] == ["-m", "pipx", "install"])
    assert "--python" in install
    assert install[-1] == "primr"


def test_virtualenv_does_not_attempt_user_bootstrap(installer):
    result, calls, _ = installer(versions={"python3.14": "3.14"}, venv=True, pip=True)
    assert result.returncode != 0
    assert "selected Python is a virtual environment" in result.stdout
    assert "Install uv" in result.stdout
    assert not any("install" in call for call in calls)


@pytest.mark.parametrize("manager", ["uv", "pipx"])
def test_install_failure_does_not_report_success(installer, manager):
    result, _, _ = installer(tools=(manager,), versions={"python3.14": "3.14"}, fail=7)
    assert result.returncode != 0
    assert "==> Done." not in result.stdout


def test_bootstrap_failure_stops_before_installing_primr(installer):
    result, calls, _ = installer(versions={"python3.14": "3.14"}, pip=True, fail=7)
    assert result.returncode != 0
    assert not any("pipx" in call and "primr" in call for call in calls)
    assert "==> Done." not in result.stdout
