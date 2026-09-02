"""Unit tests for primr.core.cli_init.

Focused tests for the prompt/key-detection/key-validation helpers and the
Playwright + project-.env setup helpers extracted from cli.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.core.cli_init import (
    MODEL_PROVIDER_ENV_NAMES,
    _ensure_project_env_file,
    _install_playwright_browsers,
    _key_looks_configured,
    _playwright_browsers_ready,
    _prompt_yes_no,
    _should_offer_interactive_key_setup,
    _validate_key_live,
)


@pytest.fixture(autouse=True)
def _assume_supported_sync_runtime(monkeypatch):
    monkeypatch.setattr("primr.core.cli_init.sync_browser_runtime_supported", lambda: True)


# ---------------------------------------------------------------------------
# _prompt_yes_no
# ---------------------------------------------------------------------------


class TestPromptYesNo:
    @pytest.mark.parametrize("answer", ["y", "Y", "yes", "YES"])
    def test_yes_variants_return_true(self, answer):
        with patch("builtins.input", return_value=answer):
            assert _prompt_yes_no("?", default=False) is True

    @pytest.mark.parametrize("answer", ["n", "no", "anything"])
    def test_non_yes_returns_false(self, answer):
        with patch("builtins.input", return_value=answer):
            assert _prompt_yes_no("?", default=True) is False

    def test_empty_input_uses_default_true(self):
        with patch("builtins.input", return_value=""):
            assert _prompt_yes_no("?", default=True) is True

    def test_empty_input_uses_default_false(self):
        with patch("builtins.input", return_value=""):
            assert _prompt_yes_no("?", default=False) is False

    @pytest.mark.parametrize("prompt_error", [EOFError(), OSError("closed"), ValueError("closed")])
    def test_unavailable_input_fails_closed(self, prompt_error):
        with patch("builtins.input", side_effect=prompt_error):
            assert _prompt_yes_no("?", default=True) is False
            assert _prompt_yes_no("?", default=False) is False


# ---------------------------------------------------------------------------
# _should_offer_interactive_key_setup
# ---------------------------------------------------------------------------


class TestShouldOfferInteractiveKeySetup:
    def _result(self, *fields):
        errors = [SimpleNamespace(field=f) for f in fields]
        return SimpleNamespace(errors=errors)

    def test_returns_false_when_not_tty(self):
        with (
            patch("sys.stdin.isatty", return_value=False),
            patch("sys.stdout.isatty", return_value=True),
        ):
            assert _should_offer_interactive_key_setup(self._result("GEMINI_API_KEY")) is False

    def test_returns_false_when_output_is_not_tty(self):
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stdout.isatty", return_value=False),
        ):
            assert _should_offer_interactive_key_setup(self._result("GEMINI_API_KEY")) is False

    def test_returns_false_when_stream_is_damaged(self):
        with patch("sys.stdin.isatty", side_effect=ValueError("closed")):
            assert _should_offer_interactive_key_setup(self._result("GEMINI_API_KEY")) is False

    def test_returns_false_when_no_errors(self):
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stdout.isatty", return_value=True),
        ):
            assert _should_offer_interactive_key_setup(self._result()) is False

    def test_returns_true_for_key_only_errors(self):
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stdout.isatty", return_value=True),
        ):
            assert _should_offer_interactive_key_setup(self._result("MODEL_PROVIDER_API_KEY"))
            assert _should_offer_interactive_key_setup(
                self._result("GEMINI_API_KEY", "XAI_API_KEY")
            )

    def test_returns_false_when_other_error_field(self):
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stdout.isatty", return_value=True),
        ):
            assert (
                _should_offer_interactive_key_setup(self._result("GEMINI_API_KEY", "OTHER_FIELD"))
                is False
            )


# ---------------------------------------------------------------------------
# _key_looks_configured
# ---------------------------------------------------------------------------


class TestKeyLooksConfigured:
    def test_returns_false_when_unset(self, monkeypatch):
        monkeypatch.delenv("MY_TEST_KEY", raising=False)
        assert _key_looks_configured("MY_TEST_KEY") is False

    def test_returns_false_for_short_value(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_KEY", "short")
        assert _key_looks_configured("MY_TEST_KEY") is False

    def test_returns_true_for_long_value(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_KEY", "a-real-looking-key-1234567890")
        assert _key_looks_configured("MY_TEST_KEY") is True

    def test_returns_false_for_whitespace(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_KEY", "        ")
        # 8 chars of whitespace -> trims to 0 -> not >= 10
        assert _key_looks_configured("MY_TEST_KEY") is False


# ---------------------------------------------------------------------------
# _validate_key_live
# ---------------------------------------------------------------------------


class TestValidateKeyLive:
    def test_empty_value_rejected(self):
        ok, msg = _validate_key_live("gemini", "")
        assert ok is False
        assert "empty" in msg

    def test_unknown_provider_passes_with_no_verify(self):
        ok, msg = _validate_key_live("unknown_provider", "anything")
        assert ok is True
        assert "without verification" in msg

    def test_gemini_happy_path(self):
        client = MagicMock()
        client.models.list.return_value = iter([])
        fake_module = MagicMock()
        fake_module.Client.return_value = client
        with (
            patch.dict(
                "sys.modules",
                {"google": MagicMock(genai=fake_module), "google.genai": fake_module},
            ),
            patch("google.genai", fake_module, create=True),
        ):
            ok, msg = _validate_key_live("gemini", "real-key-1234567890")
        assert ok is True
        assert "verified" in msg

    def test_gemini_rejected_key(self):
        fake_module = MagicMock()
        fake_module.Client.side_effect = RuntimeError("invalid api key 401")
        with (
            patch.dict(
                "sys.modules",
                {"google": MagicMock(genai=fake_module), "google.genai": fake_module},
            ),
            patch("google.genai", fake_module, create=True),
        ):
            ok, msg = _validate_key_live("gemini", "bogus-1234567890")
        assert ok is False
        assert "rejected" in msg

    def test_xai_happy_path(self):
        client = MagicMock()
        client.models.list.return_value = iter([])
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = client
        with patch.dict("sys.modules", {"openai": fake_openai}):
            ok, msg = _validate_key_live("xai", "real-key-1234567890")
        assert ok is True
        assert "verified" in msg

    def test_xai_unauthorized(self):
        fake_openai = MagicMock()
        fake_openai.OpenAI.side_effect = RuntimeError("401 unauthorized")
        with patch.dict("sys.modules", {"openai": fake_openai}):
            ok, msg = _validate_key_live("xai", "bogus-1234567890")
        assert ok is False
        assert "rejected" in msg

    def test_openrouter_uses_authenticated_key_endpoint(self):
        response = MagicMock()
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response

        with patch("httpx.Client", return_value=client) as factory:
            ok, msg = _validate_key_live("openrouter", "real-key-1234567890")

        assert ok is True
        assert msg == "verified"
        factory.assert_called_once_with(follow_redirects=False, timeout=15.0)
        client.get.assert_called_once_with(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": "Bearer real-key-1234567890"},
        )
        response.raise_for_status.assert_called_once_with()

    def test_openrouter_rejects_unauthorized_key(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.side_effect = RuntimeError("401 unauthorized")

        with patch("httpx.Client", return_value=client):
            ok, msg = _validate_key_live("openrouter", "bogus-1234567890")

        assert ok is False
        assert "rejected" in msg


# ---------------------------------------------------------------------------
# _playwright_browsers_ready / _install_playwright_browsers
# ---------------------------------------------------------------------------


class TestPlaywrightHelpers:
    def test_browsers_ready_returns_false_when_import_fails(self):
        # Patching ImportError on the import path forces the except branch.
        with patch.dict("sys.modules", {"playwright.sync_api": None}):
            assert _playwright_browsers_ready() is False

    def test_browsers_ready_skips_unsupported_runtime(self, monkeypatch):
        monkeypatch.setattr("primr.core.cli_init.sync_browser_runtime_supported", lambda: False)
        with patch(
            "playwright.sync_api.sync_playwright",
            side_effect=RuntimeError("should not be called"),
        ) as sync_playwright:
            assert _playwright_browsers_ready() is False

        sync_playwright.assert_not_called()

    def test_install_runs_subprocess_command(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=0)
            assert _install_playwright_browsers() is True
            _args, kwargs = run_mock.call_args
            cmd = _args[0]
            assert "playwright" in cmd
            assert "install" in cmd
            assert "chromium" in cmd

    def test_install_returns_false_on_nonzero_exit(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=1)
            assert _install_playwright_browsers() is False


# ---------------------------------------------------------------------------
# _ensure_project_env_file
# ---------------------------------------------------------------------------


class TestEnsureProjectEnvFile:
    def test_returns_existing_when_env_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("EXISTING=1", encoding="utf-8")
        created, path = _ensure_project_env_file()
        assert created is False
        assert path == str(tmp_path / ".env")

    def test_creates_when_env_example_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env.example").write_text("# template", encoding="utf-8")
        created, path = _ensure_project_env_file()
        assert created is True
        assert path == str(tmp_path / ".env")
        content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "Primr project-specific overrides" in content
        assert "OPENAI_API_KEY=" in content
        assert "ANTHROPIC_API_KEY=" in content
        assert "OLLAMA_BASE_URL=" in content

    def test_creates_when_pyproject_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
        created, _ = _ensure_project_env_file()
        assert created is True

    def test_skips_when_no_markers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Empty directory: no .env, no .env.example, no pyproject.toml
        created, path = _ensure_project_env_file()
        assert created is False
        assert path is None


# ---------------------------------------------------------------------------
# _run_init_flow (integration paths)
# ---------------------------------------------------------------------------


class TestRunInitFlow:
    def _setup_fake_env(self, monkeypatch, tmp_path):
        """Patch all the side-effecty pieces so we drive the flow deterministically."""
        from primr.core import cli_init

        monkeypatch.chdir(tmp_path)
        for env_name in MODEL_PROVIDER_ENV_NAMES:
            monkeypatch.delenv(env_name, raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "real-looking-key-1234567890")
        monkeypatch.setenv("XAI_API_KEY", "another-real-key-1234567890")
        # Force Python version check to pass regardless of local interpreter.
        fake_version = SimpleNamespace(major=3, minor=11, micro=0)
        fake_version.__ge__ = lambda other: True  # type: ignore[attr-defined]
        # version_info supports tuple comparison; supply a real-tuple-like.
        from sys import version_info as real_vi

        class _VI(tuple):
            major = 3
            minor = 12
            micro = 0

        monkeypatch.setattr("sys.version_info", _VI((3, 12, 0, "final", 0)))
        del real_vi  # silence flake8

        fake_env = MagicMock()
        fake_env.get_user_env_path = lambda: str(tmp_path / "user.env")
        fake_env.load_primr_env = lambda: None
        fake_env.mask_secret = lambda v: "***"
        fake_env.set_user_key = lambda *a, **k: None
        monkeypatch.setattr("primr.config.env.get_user_env_path", fake_env.get_user_env_path)
        monkeypatch.setattr("primr.config.env.load_primr_env", fake_env.load_primr_env)
        monkeypatch.setattr("primr.config.env.mask_secret", fake_env.mask_secret)
        monkeypatch.setattr("primr.config.env.set_user_key", fake_env.set_user_key)

        # Stop the flow from touching the real Playwright install
        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: True)

    def test_non_interactive_all_keys_set_and_browsers_ready(self, tmp_path, monkeypatch):
        self._setup_fake_env(monkeypatch, tmp_path)
        from primr.core.cli_init import _run_init_flow

        result = _run_init_flow(
            non_interactive=True,
            assume_yes=False,
            skip_browsers=False,
            run_doctor_after=False,
        )
        assert result == 0

    def test_python_311_is_rejected(self, tmp_path, monkeypatch):
        self._setup_fake_env(monkeypatch, tmp_path)
        from primr.core.cli_init import _run_init_flow

        class _VI(tuple):
            major = 3
            minor = 11
            micro = 9

        monkeypatch.setattr("sys.version_info", _VI((3, 11, 9, "final", 0)))

        result = _run_init_flow(
            non_interactive=True,
            assume_yes=False,
            skip_browsers=False,
            run_doctor_after=False,
        )

        assert result == 1

    def test_non_interactive_missing_keys_returns_nonzero(self, tmp_path, monkeypatch):
        # No env vars set -> keys aren't configured, non-interactive can't fix it
        from primr.core import cli_init

        monkeypatch.chdir(tmp_path)
        for env_name in MODEL_PROVIDER_ENV_NAMES:
            monkeypatch.delenv(env_name, raising=False)
        monkeypatch.setattr("primr.config.env.get_user_env_path", lambda: str(tmp_path / "u.env"))
        monkeypatch.setattr("primr.config.env.load_primr_env", lambda: None)
        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: True)

        result = cli_init._run_init_flow(
            non_interactive=True,
            assume_yes=False,
            skip_browsers=False,
            run_doctor_after=False,
        )
        assert result == 1

    @pytest.mark.parametrize("env_name", ["XAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
    def test_non_interactive_single_provider_key_is_ready(self, env_name, tmp_path, monkeypatch):
        from primr.core import cli_init

        monkeypatch.chdir(tmp_path)
        for provider_env in MODEL_PROVIDER_ENV_NAMES:
            monkeypatch.delenv(provider_env, raising=False)
        monkeypatch.setenv(env_name, "real-looking-key-1234567890")
        monkeypatch.setattr("primr.config.env.get_user_env_path", lambda: str(tmp_path / "u.env"))
        monkeypatch.setattr("primr.config.env.load_primr_env", lambda: None)
        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: True)

        result = cli_init._run_init_flow(
            non_interactive=True,
            assume_yes=False,
            skip_browsers=False,
            run_doctor_after=False,
        )
        assert result == 0

    def test_skip_browsers_flag_respected(self, tmp_path, monkeypatch):
        self._setup_fake_env(monkeypatch, tmp_path)
        from primr.core import cli_init

        # Trip browsers_ready to fail; with skip_browsers=True, flow should NOT mark not-ready
        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: False)
        result = cli_init._run_init_flow(
            non_interactive=True,
            assume_yes=False,
            skip_browsers=True,
            run_doctor_after=False,
        )
        # Keys set + skip_browsers -> all_ready True -> 0
        assert result == 0

    def test_non_interactive_browsers_missing_returns_nonzero(self, tmp_path, monkeypatch):
        self._setup_fake_env(monkeypatch, tmp_path)
        from primr.core import cli_init

        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: False)
        result = cli_init._run_init_flow(
            non_interactive=True,
            assume_yes=False,
            skip_browsers=False,
            run_doctor_after=False,
        )
        assert result == 1

    def test_assume_yes_installs_browsers(self, tmp_path, monkeypatch):
        self._setup_fake_env(monkeypatch, tmp_path)
        from primr.core import cli_init

        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: False)
        install_mock = MagicMock(return_value=True)
        monkeypatch.setattr(cli_init, "_install_playwright_browsers", install_mock)

        result = cli_init._run_init_flow(
            non_interactive=False,
            assume_yes=True,
            skip_browsers=False,
            run_doctor_after=False,
        )
        install_mock.assert_called_once()
        assert result == 0

    def test_interactive_paste_key_path_success(self, tmp_path, monkeypatch):
        """User pastes a real key via interactive prompt and it validates."""
        from primr.core import cli_init

        monkeypatch.chdir(tmp_path)
        for env_name in MODEL_PROVIDER_ENV_NAMES:
            monkeypatch.delenv(env_name, raising=False)
        monkeypatch.setattr("primr.config.env.get_user_env_path", lambda: str(tmp_path / "u.env"))
        monkeypatch.setattr("primr.config.env.load_primr_env", lambda: None)
        monkeypatch.setattr("primr.config.env.mask_secret", lambda v: "***")
        monkeypatch.setattr("primr.config.env.set_user_key", lambda *a, **k: None)
        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: True)

        # Force Python version check to pass.
        class _VI(tuple):
            major = 3
            minor = 12
            micro = 0

        monkeypatch.setattr("sys.version_info", _VI((3, 12, 0, "final", 0)))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        # Validate-key always succeeds; getpass returns real-looking key.
        monkeypatch.setattr(cli_init, "_validate_key_live", lambda p, v: (True, "verified"))
        monkeypatch.setattr("getpass.getpass", lambda *a, **k: "real-looking-key-1234567890")

        # Don't prompt during init; assume_yes=True skips _prompt_yes_no entirely.
        result = cli_init._run_init_flow(
            non_interactive=False,
            assume_yes=True,
            skip_browsers=True,
            run_doctor_after=False,
        )
        assert result == 0

    def test_interactive_paste_key_path_rejected_3_times(self, tmp_path, monkeypatch):
        """User pastes an invalid key 3 times -> setup not ready."""
        from primr.core import cli_init

        monkeypatch.chdir(tmp_path)
        for env_name in MODEL_PROVIDER_ENV_NAMES:
            monkeypatch.delenv(env_name, raising=False)
        monkeypatch.setattr("primr.config.env.get_user_env_path", lambda: str(tmp_path / "u.env"))
        monkeypatch.setattr("primr.config.env.load_primr_env", lambda: None)
        monkeypatch.setattr("primr.config.env.mask_secret", lambda v: "***")
        monkeypatch.setattr("primr.config.env.set_user_key", lambda *a, **k: None)
        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: True)

        class _VI(tuple):
            major = 3
            minor = 12
            micro = 0

        monkeypatch.setattr("sys.version_info", _VI((3, 12, 0, "final", 0)))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        monkeypatch.setattr(cli_init, "_validate_key_live", lambda p, v: (False, "rejected"))
        monkeypatch.setattr("getpass.getpass", lambda *a, **k: "bogus-1234567890")

        result = cli_init._run_init_flow(
            non_interactive=False,
            assume_yes=True,
            skip_browsers=True,
            run_doctor_after=False,
        )
        # No provider key validated, so setup is not ready.
        assert result == 1

    def test_interactive_empty_key_skips_provider(self, tmp_path, monkeypatch):
        from primr.core import cli_init

        monkeypatch.chdir(tmp_path)
        for env_name in MODEL_PROVIDER_ENV_NAMES:
            monkeypatch.delenv(env_name, raising=False)
        monkeypatch.setattr("primr.config.env.get_user_env_path", lambda: str(tmp_path / "u.env"))
        monkeypatch.setattr("primr.config.env.load_primr_env", lambda: None)
        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: True)

        class _VI(tuple):
            major = 3
            minor = 12
            micro = 0

        monkeypatch.setattr("sys.version_info", _VI((3, 12, 0, "final", 0)))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        # User presses enter at the getpass prompt -> empty string -> skipped
        monkeypatch.setattr("getpass.getpass", lambda *a, **k: "")

        result = cli_init._run_init_flow(
            non_interactive=False,
            assume_yes=True,
            skip_browsers=True,
            run_doctor_after=False,
        )
        # All provider prompts were skipped, so setup is not ready.
        assert result == 1

    @pytest.mark.parametrize("prompt_error", [EOFError(), OSError("closed"), ValueError("closed")])
    def test_interactive_secret_input_failure_returns_nonzero(
        self, tmp_path, monkeypatch, prompt_error
    ):
        from primr.core import cli_init

        monkeypatch.chdir(tmp_path)
        for env_name in MODEL_PROVIDER_ENV_NAMES:
            monkeypatch.delenv(env_name, raising=False)
        monkeypatch.setattr("primr.config.env.get_user_env_path", lambda: str(tmp_path / "u.env"))
        monkeypatch.setattr("primr.config.env.load_primr_env", lambda: None)
        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: True)

        class _VI(tuple):
            major = 3
            minor = 12
            micro = 0

        monkeypatch.setattr("sys.version_info", _VI((3, 12, 0, "final", 0)))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.setattr("getpass.getpass", MagicMock(side_effect=prompt_error))

        result = cli_init._run_init_flow(
            non_interactive=False,
            assume_yes=True,
            skip_browsers=True,
            run_doctor_after=False,
        )

        assert result == 1

    def test_browser_install_failure_returns_nonzero(self, tmp_path, monkeypatch):
        self._setup_fake_env(monkeypatch, tmp_path)
        from primr.core import cli_init

        monkeypatch.setattr(cli_init, "_playwright_browsers_ready", lambda: False)
        monkeypatch.setattr(cli_init, "_install_playwright_browsers", lambda: False)

        result = cli_init._run_init_flow(
            non_interactive=False,
            assume_yes=True,
            skip_browsers=False,
            run_doctor_after=False,
        )
        assert result == 1

    def test_run_doctor_after_uses_injected_runner(self, tmp_path, monkeypatch):
        self._setup_fake_env(monkeypatch, tmp_path)
        from primr.core import cli_init

        # Make stdin/stdout look like a TTY so the interactive branch runs.
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        run_doctor_mock = MagicMock(return_value=42)

        result = cli_init._run_init_flow(
            non_interactive=False,
            assume_yes=True,
            skip_browsers=True,
            run_doctor_after=True,
            doctor_runner=run_doctor_mock,
        )
        run_doctor_mock.assert_called_once_with(fix=False)
        assert result == 42

    def test_run_doctor_after_requires_injected_runner(self, tmp_path, monkeypatch):
        self._setup_fake_env(monkeypatch, tmp_path)
        from primr.core import cli_init

        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        with pytest.raises(RuntimeError, match="doctor_runner is required"):
            cli_init._run_init_flow(
                non_interactive=False,
                assume_yes=True,
                skip_browsers=True,
                run_doctor_after=True,
            )
