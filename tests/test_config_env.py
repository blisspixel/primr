"""Tests for Primr environment loading and key helpers."""

import os

from primr.config.env import load_primr_env, normalize_key_name


def test_normalize_key_name_accepts_provider_aliases():
    assert normalize_key_name("xai") == "XAI_API_KEY"
    assert normalize_key_name("grok") == "XAI_API_KEY"
    assert normalize_key_name("gemini") == "GEMINI_API_KEY"
    assert normalize_key_name("GEMINI_API_KEY") == "GEMINI_API_KEY"


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
