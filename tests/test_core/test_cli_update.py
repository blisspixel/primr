"""Tests for the `primr update` command and its CLI interception."""

from __future__ import annotations

import subprocess

import pytest

from primr.core import cli_dispatch, cli_update
from primr.utils.version_check import InstallMethod

# --- interception (primr update / upgrade / self-update) ---


@pytest.mark.parametrize("token", ["update", "upgrade", "self-update"])
def test_is_update_command(token):
    assert cli_dispatch.is_update_command([token]) is True
    assert cli_dispatch.is_update_command([token, "--check"]) is True


@pytest.mark.parametrize("argv", [["research"], ["doctor"], [], ["skills", "x"]])
def test_is_not_update_command(argv):
    assert cli_dispatch.is_update_command(argv) is False


def test_run_update_delegates_check_flag(monkeypatch):
    seen = {}

    def fake_run_update(*, check_only, yes):
        seen["check_only"] = check_only
        seen["yes"] = yes
        return 0

    monkeypatch.setattr(cli_update, "run_update", fake_run_update)
    assert cli_dispatch.run_update_cli(["update", "--check"]) == 0
    assert seen == {"check_only": True, "yes": False}


def test_run_update_delegates_yes_flag(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        cli_update,
        "run_update",
        lambda *, check_only, yes: seen.update(check_only=check_only, yes=yes) or 0,
    )
    cli_dispatch.run_update_cli(["update", "-y"])
    assert seen == {"check_only": False, "yes": True}


@pytest.mark.parametrize("token", ["update", "upgrade", "self-update"])
def test_update_help_exits_zero_without_delegating(token, monkeypatch, capsys):
    monkeypatch.setattr(cli_update, "run_update", lambda **_kwargs: pytest.fail("delegated"))

    with pytest.raises(SystemExit) as exc_info:
        cli_dispatch.run_update_cli([token, "--help"])

    assert exc_info.value.code == 0
    assert f"usage: primr {token}" in capsys.readouterr().out


@pytest.mark.parametrize("extra", [["--definitely-invalid"], ["unexpected"]])
def test_update_rejects_invalid_arguments_without_delegating(extra, monkeypatch):
    monkeypatch.setattr(cli_update, "run_update", lambda **_kwargs: pytest.fail("delegated"))

    with pytest.raises(SystemExit) as exc_info:
        cli_dispatch.run_update_cli(["update", *extra])

    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("--check", {"check_only": True, "yes": False}),
        ("--check-only", {"check_only": True, "yes": False}),
        ("-y", {"check_only": False, "yes": True}),
        ("--yes", {"check_only": False, "yes": True}),
    ],
)
def test_update_flag_aliases(flag, expected, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        cli_update,
        "run_update",
        lambda *, check_only, yes: seen.update(check_only=check_only, yes=yes) or 0,
    )

    assert cli_dispatch.run_update_cli(["update", flag]) == 0
    assert seen == expected


# --- run_update behavior ---


def test_run_update_already_current(monkeypatch):
    from primr import __version__

    monkeypatch.setattr(cli_update, "get_latest_version", lambda **k: __version__)
    # Should not attempt any subprocess.
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("no upgrade!"))
    assert cli_update.run_update() == 0


def test_run_update_pypi_unreachable(monkeypatch):
    monkeypatch.setattr(cli_update, "get_latest_version", lambda **k: None)
    assert cli_update.run_update() == 1


def test_run_update_check_only_does_not_install(monkeypatch):
    monkeypatch.setattr(cli_update, "get_latest_version", lambda **k: "999.0.0")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("no install in check mode!"))
    assert cli_update.run_update(check_only=True) == 0


def test_noninteractive_update_requires_explicit_yes(monkeypatch):
    monkeypatch.setattr(cli_update, "get_latest_version", lambda **_kwargs: "999.0.0")
    monkeypatch.setattr(cli_update, "can_prompt_for_input", lambda: False)
    monkeypatch.setattr(
        cli_update,
        "detect_install_method",
        lambda: pytest.fail("installation method should not be inspected"),
    )
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: pytest.fail("no upgrade"))

    assert cli_update.run_update() == 1


def test_update_requires_visible_output_terminal(monkeypatch):
    monkeypatch.setattr(cli_update, "get_latest_version", lambda **_kwargs: "999.0.0")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    monkeypatch.setattr(
        cli_update,
        "detect_install_method",
        lambda: pytest.fail("installation method should not be inspected"),
    )

    assert cli_update.run_update() == 1


@pytest.mark.parametrize("prompt_error", [EOFError(), OSError("closed"), ValueError("closed")])
def test_update_reports_unavailable_confirmation_input(monkeypatch, capsys, prompt_error):
    monkeypatch.setattr(cli_update, "get_latest_version", lambda **_kwargs: "999.0.0")
    monkeypatch.setattr(cli_update, "can_prompt_for_input", lambda: True)
    monkeypatch.setattr(
        cli_update,
        "detect_install_method",
        lambda: InstallMethod(kind="pip", upgrade_command=["pip", "install", "primr"]),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: (_ for _ in ()).throw(prompt_error))
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: pytest.fail("no upgrade"))

    assert cli_update.run_update() == 1
    output = capsys.readouterr().out
    assert "input is unavailable" in output
    assert "Update cancelled" not in output


def test_run_update_runs_upgrade(monkeypatch):
    monkeypatch.setattr(cli_update, "get_latest_version", lambda **k: "999.0.0")
    monkeypatch.setattr(
        cli_update,
        "detect_install_method",
        lambda: InstallMethod(kind="pip", upgrade_command=["pip", "install", "--upgrade", "primr"]),
    )
    captured = {}

    def fake_run(cmd, check=False):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cli_update.run_update(yes=True) == 0
    assert captured["cmd"] == ["pip", "install", "--upgrade", "primr"]


def test_run_update_propagates_failure(monkeypatch):
    monkeypatch.setattr(cli_update, "get_latest_version", lambda **k: "999.0.0")
    monkeypatch.setattr(
        cli_update,
        "detect_install_method",
        lambda: InstallMethod(kind="pipx", upgrade_command=["pipx", "upgrade", "primr"]),
    )
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, check=False: subprocess.CompletedProcess(cmd, 3)
    )
    assert cli_update.run_update(yes=True) == 3


def test_run_update_handles_missing_tool(monkeypatch):
    monkeypatch.setattr(cli_update, "get_latest_version", lambda **k: "999.0.0")
    monkeypatch.setattr(
        cli_update,
        "detect_install_method",
        lambda: InstallMethod(kind="pipx", upgrade_command=["pipx", "upgrade", "primr"]),
    )

    def boom(*a, **k):
        raise FileNotFoundError("pipx")

    monkeypatch.setattr(subprocess, "run", boom)
    assert cli_update.run_update(yes=True) == 1


# --- passive notice ---


def test_notify_if_update_available(monkeypatch, capsys):
    monkeypatch.setattr(cli_update, "check_for_update", lambda _v: "9.9.9")
    cli_update.notify_if_update_available()
    out = capsys.readouterr().out
    assert "9.9.9" in out
    assert "primr update" in out


def test_notify_silent_when_current(monkeypatch, capsys):
    monkeypatch.setattr(cli_update, "check_for_update", lambda _v: None)
    cli_update.notify_if_update_available()
    assert capsys.readouterr().out == ""


def test_notify_swallows_errors(monkeypatch):
    def boom(_v):
        raise RuntimeError("network")

    monkeypatch.setattr(cli_update, "check_for_update", boom)
    # Must not raise.
    cli_update.notify_if_update_available()


def test_notify_swallows_output_errors_after_success(monkeypatch):
    monkeypatch.setattr(cli_update, "check_for_update", lambda _v: "9.9.9")

    def output_broken(_message):
        raise BrokenPipeError

    monkeypatch.setattr(cli_update.console, "info", output_broken)

    # A passive notice must not reverse a successful research exit.
    cli_update.notify_if_update_available()
