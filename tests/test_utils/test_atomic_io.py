"""Tests for primr.utils.atomic_io.atomic_replace."""

from __future__ import annotations

import os

import pytest

from primr.utils.atomic_io import atomic_replace


def test_replaces_file_on_first_try(tmp_path):
    src = tmp_path / "src.tmp"
    dst = tmp_path / "dst.json"
    src.write_text("new", encoding="utf-8")
    dst.write_text("old", encoding="utf-8")

    atomic_replace(src, dst)

    assert dst.read_text(encoding="utf-8") == "new"
    assert not src.exists()


def test_accepts_str_and_pathlike(tmp_path):
    src = tmp_path / "src.tmp"
    dst = tmp_path / "dst.json"
    src.write_text("payload", encoding="utf-8")

    # str src, PathLike dst
    atomic_replace(str(src), dst)
    assert dst.read_text(encoding="utf-8") == "payload"


def test_retries_then_succeeds_on_transient_permission_error(tmp_path, monkeypatch):
    src = tmp_path / "src.tmp"
    dst = tmp_path / "dst.json"
    src.write_text("payload", encoding="utf-8")

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(a, b):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("WinError 32: file in use")
        return real_replace(a, b)

    monkeypatch.setattr(os, "replace", flaky_replace)
    atomic_replace(src, dst, base_delay=0.0)

    assert calls["n"] == 3
    assert dst.read_text(encoding="utf-8") == "payload"


def test_reraises_after_persistent_permission_error(tmp_path, monkeypatch):
    src = tmp_path / "src.tmp"
    dst = tmp_path / "dst.json"
    src.write_text("payload", encoding="utf-8")

    def always_locked(a, b):
        raise PermissionError("WinError 32: file in use")

    monkeypatch.setattr(os, "replace", always_locked)
    with pytest.raises(PermissionError):
        atomic_replace(src, dst, retries=3, base_delay=0.0)


def test_other_oserror_propagates_immediately(tmp_path, monkeypatch):
    src = tmp_path / "src.tmp"
    dst = tmp_path / "dst.json"
    src.write_text("payload", encoding="utf-8")

    calls = {"n": 0}

    def boom(a, b):
        calls["n"] += 1
        raise FileNotFoundError("missing")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(FileNotFoundError):
        atomic_replace(src, dst, base_delay=0.0)

    assert calls["n"] == 1  # not retried


def test_invalid_retries_rejected(tmp_path):
    with pytest.raises(ValueError):
        atomic_replace(tmp_path / "a", tmp_path / "b", retries=0)
