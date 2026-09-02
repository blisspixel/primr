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
    assert normalize_key_name("openrouter") == "OPENROUTER_API_KEY"
    assert normalize_key_name("router") == "OPENROUTER_API_KEY"
    assert normalize_key_name("ollama") == "OLLAMA_API_KEY"
    assert normalize_key_name("local") == "OLLAMA_API_KEY"
    assert normalize_key_name("OLLAMA_API_KEY") == "OLLAMA_API_KEY"


def test_keys_surface_covers_every_wired_provider():
    """No drift: every LLM provider in the registry must be settable via
    `primr keys set` (KEY_ALIASES) and shown by `keys list` (KEY_HELP)."""
    from primr.ai.providers import KNOWN_PROVIDERS
    from primr.config.env import KEY_ALIASES, KEY_HELP

    settable = set(KEY_ALIASES.values())
    for provider in KNOWN_PROVIDERS:
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


def test_supervised_worker_env_never_restores_controller_secrets(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    project_dir = tmp_path / "project"
    config_dir.mkdir()
    project_dir.mkdir()
    (config_dir / ".env").write_text(
        "MCP_JWT_SECRET=user-secret\n"
        "XAI_API_KEY=xai-user-key-12345\n"
        "AWS_SECRET_ACCESS_KEY=unrelated-cloud-secret\n",
        encoding="utf-8",
    )
    (project_dir / ".env").write_text(
        "PRIMR_MCP_APPROVAL_TOKEN_SECRET=project-secret\n"
        "PRIMR_CONTROL_PLANE_PRIVATE=project-secret\n"
        "PRIMR_WORKER_JOB_ID=forged-job\n"
        "PRIMR_WORKER_JOB_OBJECT=forged-object\n"
        "GITHUB_TOKEN=unrelated-ci-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PRIMR_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("PRIMR_SUPERVISED_WORKER", "1")
    monkeypatch.setattr(env_mod, "_SUPERVISED_ENV_LOADING", True)
    monkeypatch.delenv("MCP_JWT_SECRET", raising=False)
    monkeypatch.delenv("PRIMR_MCP_APPROVAL_TOKEN_SECRET", raising=False)
    monkeypatch.delenv("PRIMR_CONTROL_PLANE_PRIVATE", raising=False)
    monkeypatch.delenv("PRIMR_WORKER_JOB_ID", raising=False)
    monkeypatch.delenv("PRIMR_WORKER_JOB_OBJECT", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.chdir(project_dir)

    load_primr_env()

    assert "MCP_JWT_SECRET" not in os.environ
    assert "PRIMR_MCP_APPROVAL_TOKEN_SECRET" not in os.environ
    assert "PRIMR_CONTROL_PLANE_PRIVATE" not in os.environ
    assert "PRIMR_WORKER_JOB_ID" not in os.environ
    assert "PRIMR_WORKER_JOB_OBJECT" not in os.environ
    assert "AWS_SECRET_ACCESS_KEY" not in os.environ
    assert "GITHUB_TOKEN" not in os.environ
    assert os.environ["XAI_API_KEY"] == "xai-user-key-12345"


def test_supervised_worker_env_rejects_secret_interpolation(tmp_path, monkeypatch):
    """A blocked assignment cannot be expanded into an allowed provider key."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text(
        "MCP_JWT_SECRET=controller-secret\nXAI_API_KEY=${MCP_JWT_SECRET}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PRIMR_CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(env_mod, "_SUPERVISED_ENV_LOADING", True)
    monkeypatch.delenv("MCP_JWT_SECRET", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    load_primr_env()

    assert "MCP_JWT_SECRET" not in os.environ
    assert "XAI_API_KEY" not in os.environ
