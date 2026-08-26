"""Tests for the legacy ``python -m primr.primr_cli`` compatibility module."""

from primr import __version__, primr_cli


def test_compatibility_module_delegates_to_public_cli(capsys):
    assert primr_cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"primr {__version__}"
