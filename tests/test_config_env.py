"""Tests for Primr environment loading and key helpers."""

import os
from pathlib import Path

from primr.config import env as env_mod
from primr.config.env import load_primr_env, normalize_key_name


def test_keystore_sandbox_warning_detects_store_python(monkeypatch):
    # Store Python reports a normal Roaming path but realpath resolves into the
    # per-package LocalCache sandbox - that divergence is the signal.
    monkeypatch.setattr(env_mod.sys, "platform", "win32")
    reported = r"C:\Users\X\AppData\Roaming\primr\.env"
    real = (
        r"C:\Users\X\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_abc"
        r"\LocalCache\Roaming\primr\.env"
    )
    monkeypatch.setattr(env_mod, "get_user_env_path", lambda: Path(reported))
    monkeypatch.setattr(env_mod.os.path, "realpath", lambda _p: real)
    warning = env_mod.keystore_sandbox_warning()
    assert warning is not None
    assert "sandboxed" in warning
    assert "PRIMR_CONFIG_DIR" in warning


def test_keystore_sandbox_warning_quiet_for_normal_path(monkeypatch):
    monkeypatch.setattr(env_mod.sys, "platform", "win32")
    reported = r"C:\Users\X\AppData\Roaming\primr\.env"
    monkeypatch.setattr(env_mod, "get_user_env_path", lambda: Path(reported))
    monkeypatch.setattr(env_mod.os.path, "realpath", lambda _p: reported)
    assert env_mod.keystore_sandbox_warning() is None


def test_keystore_sandbox_warning_none_on_posix(monkeypatch):
    monkeypatch.setattr(env_mod.sys, "platform", "linux")
    assert env_mod.keystore_sandbox_warning() is None


def test_normalize_key_name_accepts_provider_aliases():
    assert normalize_key_name("xai") == "XAI_API_KEY"
    assert normalize_key_name("grok") == "XAI_API_KEY"
    assert normalize_key_name("gemini") == "GEMINI_API_KEY"
    assert normalize_key_name("GEMINI_API_KEY") == "GEMINI_API_KEY"
    # OpenAI + Anthropic providers are wired in ai.providers, so their keys must
    # be settable via `primr keys set` too.
    assert normalize_key_name("anthropic") == "ANTHROPIC_API_KEY"
    assert normalize_key_name("claude") == "ANTHROPIC_API_KEY"
    assert normalize_key_name("openai") == "OPENAI_API_KEY"
    assert normalize_key_name("gpt") == "OPENAI_API_KEY"


def test_keys_surface_covers_every_wired_provider():
    """No drift: every LLM provider in the registry that needs a real key must be
    settable via `primr keys set` (KEY_ALIASES) and shown by `keys list`
    (KEY_HELP). Providers with a default key (e.g. Ollama) are exempt."""
    from primr.ai.providers import KNOWN_PROVIDERS
    from primr.config.env import KEY_ALIASES, KEY_HELP

    settable = set(KEY_ALIASES.values())
    for provider in KNOWN_PROVIDERS:
        if provider.api_key_default is not None:
            continue  # local/default-key providers don't need `keys set`
        assert provider.api_key_env in settable, (
            f"{provider.name}: {provider.api_key_env} is a wired provider but not "
            f"settable via `primr keys set` (missing from KEY_ALIASES)"
        )
        assert provider.api_key_env in KEY_HELP, (
            f"{provider.name}: {provider.api_key_env} missing from KEY_HELP "
            f"(won't show in `primr keys list`)"
        )


def test_load_primr_env_uses_user_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("XAI_API_KEY=xai-user-key-12345\n", encoding="utf-8")
    monkeypatch.setenv("PRIMR_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    load_primr_env()

    assert os.environ["XAI_API_KEY"] == "xai-user-key-12345"


def test_load_primr_env_prefers_local_env_over_user_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    project_dir = tmp_path / "project"
    config_dir.mkdir()
    project_dir.mkdir()
    (config_dir / ".env").write_text("XAI_API_KEY=xai-user-key-12345\n", encoding="utf-8")
    (project_dir / ".env").write_text("XAI_API_KEY=xai-local-key-12345\n", encoding="utf-8")
    monkeypatch.setenv("PRIMR_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.chdir(project_dir)

    load_primr_env()

    assert os.environ["XAI_API_KEY"] == "xai-local-key-12345"


def test_load_primr_env_preserves_process_env(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    project_dir = tmp_path / "project"
    config_dir.mkdir()
    project_dir.mkdir()
    (config_dir / ".env").write_text("XAI_API_KEY=xai-user-key-12345\n", encoding="utf-8")
    (project_dir / ".env").write_text("XAI_API_KEY=xai-local-key-12345\n", encoding="utf-8")
    monkeypatch.setenv("PRIMR_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("XAI_API_KEY", "xai-shell-key-12345")
    monkeypatch.chdir(project_dir)

    load_primr_env()

    assert os.environ["XAI_API_KEY"] == "xai-shell-key-12345"
