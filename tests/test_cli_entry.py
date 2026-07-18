"""Contracts for the lightweight public CLI composition boundary."""

from __future__ import annotations

import sys

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


@pytest.mark.parametrize("command", ["init", "doctor"])
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
