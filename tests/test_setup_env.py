from __future__ import annotations

import pytest

import setup_env


class _VersionInfo(tuple):
    def __new__(cls, major: int, minor: int, micro: int = 0):
        instance = super().__new__(cls, (major, minor, micro, "final", 0))
        instance.major = major
        instance.minor = minor
        instance.micro = micro
        return instance


def test_rich_setup_rejects_python_311(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(3, 11, 9))
    monkeypatch.setattr(setup_env, "find_best_python", lambda: None)
    monkeypatch.setattr(setup_env, "_print_python_install_guidance", lambda: None)

    with pytest.raises(SystemExit) as exc_info:
        setup_env._ensure_supported_python_or_exit()

    assert exc_info.value.code == 1


def test_rich_setup_accepts_python_312(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(3, 12))

    setup_env._ensure_supported_python_or_exit()


def test_rich_setup_accepts_future_major_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(4, 0))

    setup_env._ensure_supported_python_or_exit()


def test_basic_setup_rejects_python_311(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(3, 11, 9))

    with pytest.raises(SystemExit) as exc_info:
        setup_env.main_basic()

    assert exc_info.value.code == 1


def test_basic_setup_accepts_python_312(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(3, 12))
    monkeypatch.setattr(setup_env, "install_status", lambda _package: (True, "1.0", "1.0"))

    setup_env.main_basic()
