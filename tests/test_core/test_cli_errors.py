"""Tests for top-level CLI error + interrupt handling (cli_errors)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from primr.core.cli_errors import (
    EXIT_INTERRUPTED,
    ISSUES_URL,
    guard_dispatch,
    report_unexpected_error,
)


def _config(*, command_name="RESEARCH", quiet=False, verbose=False, json_output=False):
    return SimpleNamespace(
        command=SimpleNamespace(name=command_name),
        quiet=quiet,
        verbose=verbose,
        json_output=json_output,
    )


class TestReportUnexpectedError:
    def test_returns_one_and_shows_guidance(self, capsys):
        rc = report_unexpected_error(RuntimeError("boom"))
        assert rc == 1
        out = capsys.readouterr().out
        assert "boom" in out
        assert "primr doctor" in out
        assert "--verbose" in out
        assert ISSUES_URL in out


class TestGuardDispatchSuccess:
    def test_returns_handler_rc(self):
        assert guard_dispatch(lambda c: 0, _config()) == 0
        assert guard_dispatch(lambda c: 7, _config(command_name="DOCTOR")) == 7

    def test_notifies_after_clean_research_run(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "primr.core.cli_update.notify_if_update_available",
            lambda: calls.append(True),
        )
        guard_dispatch(lambda c: 0, _config(command_name="RESEARCH", quiet=False))
        assert calls == [True]

    def test_no_notify_when_quiet(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "primr.core.cli_update.notify_if_update_available",
            lambda: calls.append(True),
        )
        guard_dispatch(lambda c: 0, _config(command_name="RESEARCH", quiet=True))
        assert calls == []

    def test_no_notify_for_json_research(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "primr.core.cli_update.notify_if_update_available",
            lambda: calls.append(True),
        )
        guard_dispatch(lambda c: 0, _config(command_name="RESEARCH", json_output=True))
        assert calls == []

    def test_no_notify_for_non_research(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "primr.core.cli_update.notify_if_update_available",
            lambda: calls.append(True),
        )
        guard_dispatch(lambda c: 0, _config(command_name="DOCTOR"))
        assert calls == []

    def test_no_notify_when_rc_nonzero(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "primr.core.cli_update.notify_if_update_available",
            lambda: calls.append(True),
        )
        guard_dispatch(lambda c: 1, _config(command_name="RESEARCH"))
        assert calls == []


class TestGuardDispatchErrors:
    def test_keyboard_interrupt_exits_clean(self, capsys):
        def boom(_c):
            raise KeyboardInterrupt

        rc = guard_dispatch(boom, _config())
        assert rc == EXIT_INTERRUPTED
        assert "Cancelled" in capsys.readouterr().out

    def test_unexpected_exception_is_actionable(self, capsys):
        def boom(_c):
            raise ValueError("kaboom")

        rc = guard_dispatch(boom, _config(verbose=False))
        assert rc == 1
        out = capsys.readouterr().out
        assert "kaboom" in out
        assert "primr doctor" in out

    def test_verbose_reraises_for_traceback(self):
        def boom(_c):
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            guard_dispatch(boom, _config(verbose=True))

    @pytest.mark.parametrize("verbose", [False, True])
    def test_json_unexpected_exception_is_one_machine_object(self, verbose, capsys):
        def boom(_c):
            raise ValueError("sensitive internal detail")

        assert guard_dispatch(boom, _config(verbose=verbose, json_output=True)) == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["schema_version"] == "primr.command-error.v1"
        assert payload["operation"] == "research"
        assert payload["error_type"] == "unexpected_error"
        assert "sensitive internal detail" not in captured.out
        assert captured.err == ""

    def test_json_interrupt_is_one_machine_object(self, capsys):
        def cancel(_c):
            raise KeyboardInterrupt

        assert guard_dispatch(cancel, _config(json_output=True)) == EXIT_INTERRUPTED
        payload = json.loads(capsys.readouterr().out)
        assert payload["error_type"] == "interrupted"
        assert payload["message"] == "The command was cancelled."
