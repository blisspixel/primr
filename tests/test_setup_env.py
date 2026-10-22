from __future__ import annotations

import pytest

import setup_env
from scripts import installer_trust


class _VersionInfo(tuple):
    def __new__(cls, major: int, minor: int, micro: int = 0):
        instance = super().__new__(cls, (major, minor, micro, "final", 0))
        instance.major = major
        instance.minor = minor
        instance.micro = micro
        return instance


def test_rich_setup_rejects_python_310(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(3, 10, 9))
    monkeypatch.setattr(setup_env, "find_best_python", lambda: None)
    monkeypatch.setattr(setup_env, "_print_python_install_guidance", lambda: None)

    with pytest.raises(SystemExit) as exc_info:
        setup_env._ensure_supported_python_or_exit()

    assert exc_info.value.code == 1


def test_rich_setup_accepts_python_311(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(3, 11))

    setup_env._ensure_supported_python_or_exit()


def test_rich_setup_accepts_future_major_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(4, 0))

    setup_env._ensure_supported_python_or_exit()


def test_basic_setup_rejects_python_310(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(3, 10, 9))

    with pytest.raises(SystemExit) as exc_info:
        setup_env.main_basic()

    assert exc_info.value.code == 1


def test_basic_setup_accepts_python_311(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(3, 11))
    monkeypatch.setattr(setup_env, "install_status", lambda _package: (True, "1.0", "1.0"))

    setup_env.main_basic()


@pytest.mark.parametrize("version", ["26.2.2", "26.3", "27.0.0"])
def test_patched_installer_preserves_current_versions(monkeypatch, version):
    monkeypatch.setattr(setup_env.metadata, "version", lambda _: version)
    monkeypatch.setattr(
        setup_env.subprocess, "run", lambda *a, **k: pytest.fail("unexpected install")
    )
    setup_env.ensure_patched_installer()


@pytest.mark.parametrize("version", ["26.2.1", "26.2", "25.1", "26.2.2rc1"])
def test_affected_installer_uses_hash_bootstrap_and_stops_on_failure(monkeypatch, version):
    import subprocess

    monkeypatch.setattr(setup_env.metadata, "version", lambda _: version)
    captured = []

    def fail(cmd, **kwargs):
        captured.append((cmd, kwargs))
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(setup_env.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        setup_env.ensure_patched_installer()
    cmd, kwargs = captured[0]
    assert cmd[-1] == installer_trust.PATCHED_PIP_URL
    assert "#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" in cmd[-1]
    assert "--no-deps" in cmd
    assert kwargs["check"] is True


@pytest.mark.parametrize("minor,expected", [(8, 1), (10, 1), (11, 37)])
def test_entrypoint_checks_python_before_any_installer_download(monkeypatch, minor, expected):
    import builtins
    from pathlib import Path

    from scripts import installer_trust

    original_import = builtins.__import__

    def without_rich(name, *args, **kwargs):
        if name == "rich" or name.startswith("rich."):
            raise ImportError("fixture without Rich")
        return original_import(name, *args, **kwargs)

    def bootstrap():
        # Supported Python must reach the secure bootstrap before any UI or
        # package install. Unsupported Python must stop before this point.
        raise SystemExit(37)

    monkeypatch.setattr(builtins, "__import__", without_rich)
    monkeypatch.setattr(setup_env.sys, "version_info", _VersionInfo(3, minor))
    monkeypatch.setattr(installer_trust, "ensure_patched_installer", bootstrap)
    monkeypatch.setattr(
        setup_env.subprocess, "run", lambda *a, **k: pytest.fail("package download before guard")
    )
    script = Path(setup_env.__file__)
    with pytest.raises(SystemExit) as outcome:
        exec(
            compile(script.read_text(), str(script), "exec"),
            {"__name__": "__main__", "__file__": str(script)},
        )
    assert outcome.value.code == expected
