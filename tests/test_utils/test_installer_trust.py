"""Exercise the actual update guards without network or package installation."""

from __future__ import annotations

import json
import subprocess

import pytest

from primr.utils import installer_trust as trust


@pytest.mark.parametrize(
    "version,allowed",
    [
        ("0.11.33", False),
        ("0.13.3", False),
        ("0.13.4rc1", False),
        ("0.13.4", True),
        ("0.13.5", True),
        ("1.0.0", True),
        ("unknown", False),
    ],
)
def test_uv_floor_before_update(monkeypatch, version, allowed):
    monkeypatch.setattr(
        trust.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="uv " + version + " (fixture)"),
    )
    if allowed:
        trust.require_safe_update_installer("uv")
    else:
        with pytest.raises(ValueError, match="0.13.4"):
            trust.require_safe_update_installer("uv")


@pytest.mark.parametrize(
    "version,allowed", [("26.2.1", False), ("26.2.2rc1", False), ("26.2.2", True), ("26.3", True)]
)
def test_pip_floor_is_independent_of_application_certifi(monkeypatch, version, allowed):
    monkeypatch.setattr(trust.metadata, "version", lambda _: version)
    if allowed:
        trust.require_safe_update_installer("pip")
    else:
        with pytest.raises(ValueError, match="26.2.2"):
            trust.require_safe_update_installer("pip")


@pytest.mark.parametrize("layout", ["Lib/site-packages", "lib/python3.15/site-packages"])
@pytest.mark.parametrize("version", ["26.2.1", "26.2.2"])
def test_pipx_uses_its_shared_bundle_not_application_pip(tmp_path, monkeypatch, layout, version):
    prefix = tmp_path / "app"
    prefix.mkdir()
    monkeypatch.setattr(trust.sys, "prefix", str(prefix))
    monkeypatch.setattr(trust.shutil, "which", lambda _: None)
    shared = tmp_path / "shared installer"
    info = shared / layout / f"pip-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: pip\nVersion: {version}\n")
    monkeypatch.setattr(
        trust.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=str(shared) + "\n"),
    )
    if version == "26.2.2":
        trust.require_safe_update_installer("pipx")
    else:
        with pytest.raises(ValueError, match="26.2.2"):
            trust.require_safe_update_installer("pipx")


def test_uv_backed_pipx_needs_no_shared_pip(tmp_path, monkeypatch):
    (tmp_path / "pipx_metadata.json").write_text(json.dumps({"backend": "uv"}))
    monkeypatch.setattr(trust.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(trust.shutil, "which", lambda _: "/fixture/uv")
    commands = []

    def run(command, **_):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="uv 0.13.5")

    monkeypatch.setattr(trust.subprocess, "run", run)
    trust.require_safe_update_installer("pipx")
    assert commands == [["uv", "--version"]]


@pytest.mark.parametrize("output", ["", "/does-not-exist"])
def test_unverifiable_pipx_shared_installer_fails_closed(tmp_path, monkeypatch, output):
    monkeypatch.setattr(trust.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(trust.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        trust.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=output)
    )
    with pytest.raises(ValueError):
        trust.require_safe_update_installer("pipx")
