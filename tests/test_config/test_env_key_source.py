"""Tests for primr.config.env.describe_key_source (env-var shadow detection)."""

from __future__ import annotations

from primr.config import env


def _write_env(path, **pairs):
    path.write_text("\n".join(f"{k}={v}" for k, v in pairs.items()) + "\n", encoding="utf-8")


def test_unset_returns_all_none(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "get_user_env_path", lambda: tmp_path / "missing.env")
    monkeypatch.setattr(env, "get_local_env_path", lambda: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert env.describe_key_source("GEMINI_API_KEY") == (None, None, None)


def test_value_from_user_config(monkeypatch, tmp_path):
    user = tmp_path / "user.env"
    _write_env(user, GEMINI_API_KEY="filevalue")
    monkeypatch.setattr(env, "get_user_env_path", lambda: user)
    monkeypatch.setattr(env, "get_local_env_path", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "filevalue")

    active, source, shadowed = env.describe_key_source("GEMINI_API_KEY")
    assert active == "filevalue"
    assert source == "user config"
    assert shadowed is None


def test_env_var_shadows_file_value(monkeypatch, tmp_path):
    """The real-world bug: a stale OS env var overrides the edited .env value."""
    user = tmp_path / "user.env"
    _write_env(user, GEMINI_API_KEY="new-from-file")
    monkeypatch.setattr(env, "get_user_env_path", lambda: user)
    monkeypatch.setattr(env, "get_local_env_path", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "stale-from-env")

    active, source, shadowed = env.describe_key_source("GEMINI_API_KEY")
    assert active == "stale-from-env"
    assert source == "OS environment variable"
    assert shadowed == "new-from-file"


def test_env_var_with_no_file_is_not_shadow(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "get_user_env_path", lambda: tmp_path / "missing.env")
    monkeypatch.setattr(env, "get_local_env_path", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "env-only")

    active, source, shadowed = env.describe_key_source("GEMINI_API_KEY")
    assert active == "env-only"
    assert source == "OS environment variable"
    assert shadowed is None


def test_local_env_takes_precedence_over_user(monkeypatch, tmp_path):
    user = tmp_path / "user.env"
    local = tmp_path / "local.env"
    _write_env(user, GEMINI_API_KEY="user-value")
    _write_env(local, GEMINI_API_KEY="local-value")
    monkeypatch.setattr(env, "get_user_env_path", lambda: user)
    monkeypatch.setattr(env, "get_local_env_path", lambda: local)
    monkeypatch.setenv("GEMINI_API_KEY", "local-value")

    active, source, shadowed = env.describe_key_source("GEMINI_API_KEY")
    assert active == "local-value"
    assert source == "local .env"
    assert shadowed is None
