"""Contracts for the lightweight public CLI composition boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from primr import __version__, cli_entry
from primr.cli_help import ROOT_HELP


def _block_operational_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "primr.core.cli", None)


def test_version_fast_path_does_not_load_operational_cli(monkeypatch, capsys) -> None:
    _block_operational_cli(monkeypatch)

    assert cli_entry.main(["--version"]) == 0

    assert capsys.readouterr().out == f"primr {__version__}\n"


def test_root_help_fast_path_does_not_load_operational_cli(monkeypatch, capsys) -> None:
    _block_operational_cli(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        cli_entry.main(["--help"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == ROOT_HELP + "\n"


@pytest.mark.parametrize("command", ["init", "doctor", "update", "upgrade", "self-update"])
def test_scoped_help_fast_path_does_not_load_operational_cli(
    command: str,
    monkeypatch,
    capsys,
) -> None:
    _block_operational_cli(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        cli_entry.main([command, "--help"])

    assert exc_info.value.code == 0
    assert f"usage: primr {command}" in capsys.readouterr().out


def test_prep_fast_path_does_not_load_operational_cli(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    _block_operational_cli(monkeypatch)
    monkeypatch.chdir(tmp_path)

    assert cli_entry.main(["prep", "ExampleCo", "https://example.co", "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "Primr prep plan for ExampleCo" in output
    assert "Incremental API spend: $0.00" in output
    assert "Network requests: 0 (dry run)" in output
    assert "Files written: 0 (dry run)" in output
    assert list(tmp_path.iterdir()) == []


def test_prep_dry_runs_leave_fresh_workspace_untouched(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1] / "src"
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(source_root), environment.get("PYTHONPATH")) if part
    )
    script = """
import sys
from primr.cli_entry import main

assert main(["prep", "ExampleCo", "https://example.co", "--dry-run"]) == 0
assert main(["prep", "--install-skill", "skills/primr-zero", "--dry-run"]) == 0
assert "primr.core" not in sys.modules
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("args", [[], ["--banner"]])
def test_home_and_explicit_banner_do_not_import_operational_cli(args, monkeypatch, capsys):
    _block_operational_cli(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("home must not prompt"))
    assert cli_entry.main(args) == 0
    output = capsys.readouterr().out
    assert "primr" in output
    if not args:
        assert "$0 now: primr prep" in output
        assert "Provider-backed: primr init" in output


def test_home_defers_unrelated_utilities_in_fresh_interpreter():
    script = """
import importlib, sys
from primr.cli_entry import main
main([])
assert 'primr.core.cli' not in sys.modules
assert 'primr.utils.sensitive_instruction_safety' not in sys.modules
assert 'primr.utils.async_utils' not in sys.modules
import primr.utils as utilities
from primr.utils import run_sync, RetryPolicy, Console, console
assert run_sync is importlib.import_module('primr.utils.async_utils').run_sync
assert RetryPolicy is importlib.import_module('primr.utils.retry').RetryPolicy
assert Console is importlib.import_module('primr.utils.console').Console
assert console is importlib.import_module('primr.utils.console').console
assert 'run_sync' in dir(utilities)
try:
    utilities.not_a_real_export
except AttributeError:
    pass
else:
    raise AssertionError('unknown exports must fail')
"""
    subprocess.run([sys.executable, "-B", "-c", script], check=True, capture_output=True, text=True)
