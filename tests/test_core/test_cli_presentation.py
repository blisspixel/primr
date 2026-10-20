"""Offline acceptance checks for keyless screens, streams and narrow terminals."""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from primr.ai.provider_availability_collectors import collect_provider_availability_snapshots
from primr.core import cli_doctor, cli_keys
from primr.utils.console import Console, TerminalCapabilities


def _console(*, interactive=False):
    return Console(
        capabilities=TerminalCapabilities.for_testing(
            supports_color=interactive,
            supports_unicode=False,
            supports_cursor=interactive,
            width=60,
            is_interactive=interactive,
        )
    )


def _plain(text):
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def test_keyless_doctor_is_compact_truthful_and_zero_token(tmp_path, monkeypatch, capsys):
    with patch.dict("os.environ", {}, clear=True):
        snapshots = collect_provider_availability_snapshots(
            env={}, local_list_models_fn=lambda _: ()
        )
        monkeypatch.setattr(cli_doctor, "console", _console(interactive=True))
        monkeypatch.setattr(
            cli_doctor, "collect_provider_availability_snapshots", lambda: snapshots
        )
        monkeypatch.setattr(cli_doctor, "_check_for_update", lambda: None)
        monkeypatch.setattr(cli_doctor, "_check_key_shadowing", lambda wc: wc)
        for name in ("OUTPUT_DIR", "WORKING_DIR", "LOGS_DIR"):
            monkeypatch.setattr(cli_doctor, name, str(tmp_path / name))
        with (
            patch("ddgs.DDGS") as search,
            patch.object(cli_doctor.subprocess, "run", return_value=SimpleNamespace(returncode=0)),
            patch(
                "primr.ai.providers.build_provider",
                side_effect=AssertionError("no configured providers"),
            ),
            patch("google.genai.Client", side_effect=AssertionError("no model client")),
        ):
            search.return_value.text.return_value = [{"title": "fixture"}]
            assert cli_doctor.run_doctor() == 0
    captured = capsys.readouterr()
    text = captured.out + captured.err
    lines = _plain(text).splitlines()
    assert len(lines) <= 40
    assert max(map(len, lines)) <= 60
    assert text.count("Ollama/local") == 1
    assert text.count("Next:") == 1
    assert "not configured" in text
    assert "Keyless ready" in text
    assert "\r" not in text
    assert "38;2" not in text


def test_keys_list_wraps_and_groups_without_exposing_secrets(monkeypatch, capsys):
    monkeypatch.setattr(cli_keys, "console", _console())
    from primr.config import env

    monkeypatch.setattr(env, "load_primr_env", lambda: None)
    secret = "sk-test-" + "a" * 64
    monkeypatch.setattr(
        env,
        "describe_key_source",
        lambda name: (
            (secret, "environment", None) if name == "OPENAI_API_KEY" else (None, None, None)
        ),
    )
    monkeypatch.setattr(env, "get_user_env_path", lambda: "/very/long/" + "path/" * 30 + ".env")
    monkeypatch.setattr(env, "get_local_env_path", lambda: None)
    monkeypatch.setattr(env, "keystore_sandbox_warning", lambda: None)
    assert cli_keys.run_keys(["keys", "list"]) == 0
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    lines = captured.out.splitlines()
    assert max(map(len, lines)) <= 60
    assert captured.out.count("Next:") == 1
    for group in ("research providers", "optional local", "search"):
        assert group in captured.out
    assert "not set" in captured.out
    assert "set" in captured.out


@pytest.mark.parametrize("method", ["status", "warn", "fail", "step"])
def test_diagnostics_go_to_stderr_and_results_stay_stdout(method, capsys):
    console = _console()
    getattr(console, method)("diagnostic message")
    console.result("Report", "output/report.docx")
    captured = capsys.readouterr()
    assert "diagnostic message" in captured.err
    assert "diagnostic message" not in captured.out
    assert "output/report.docx" in captured.out


def test_idle_clear_line_is_silent(capsys):
    console = _console(interactive=True)
    console.clear_line()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("method", ["status", "scrape_progress", "progress", "wrapped"])
def test_redaction_precedes_progress_truncation_and_wrapping(method, capsys):
    console = _console(interactive=True)
    secret = "sk-" + "a" * 100
    if method in {"progress", "scrape_progress"}:
        getattr(console, method)(1, 2, secret)
    else:
        getattr(console, method)(secret)
    captured = capsys.readouterr()
    assert "a" * 20 not in captured.out + captured.err


def test_provider_estimate_never_prompts_and_offers_free_path(monkeypatch, capsys):
    from primr.core import cli

    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("an estimate must not prompt"))
    validation = SimpleNamespace(valid=False, errors=["No provider key configured"], warnings=[])
    with (
        patch("primr.utils.config_validation.validate_config", return_value=validation),
        patch.object(
            cli, "_should_offer_interactive_key_setup", side_effect=AssertionError("no setup offer")
        ),
    ):
        assert cli.main(["ExampleCo", "https://example.co", "--dry-run"]) == 1
    captured = capsys.readouterr()
    assert "$0 now: primr prep" in captured.out
    assert "No provider key configured" in captured.err


def test_no_color_wins_over_force_color(monkeypatch):
    from primr.utils.console import _detect_terminal

    monkeypatch.setenv("NO_COLOR", "")
    monkeypatch.setenv("FORCE_COLOR", "1")
    _detect_terminal.cache_clear()
    try:
        assert not _detect_terminal().supports_color
    finally:
        _detect_terminal.cache_clear()
