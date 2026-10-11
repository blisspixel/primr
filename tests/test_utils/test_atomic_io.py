"""Tests for primr.utils.atomic_io.atomic_replace."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from primr.utils import atomic_io
from primr.utils.atomic_io import (
    atomic_replace,
    atomic_write_bytes,
    atomic_write_text,
    file_mutation_lock,
)


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


def test_atomic_write_text_creates_parent_and_replaces_content(tmp_path):
    target = tmp_path / "nested" / "artifact.md"
    atomic_write_text(target, "first")
    atomic_write_text(target, "second")

    assert target.read_text(encoding="utf-8") == "second"
    assert not list(target.parent.glob("*.tmp"))


def test_atomic_write_bytes_preserves_binary_content(tmp_path):
    target = tmp_path / "artifact.bin"
    atomic_write_bytes(target, b"\x00\x01payload")

    assert target.read_bytes() == b"\x00\x01payload"


@pytest.mark.parametrize("platform", ["posix", "nt"])
def test_mutation_lock_uses_nonblocking_platform_lock_at_offset_zero(
    tmp_path, monkeypatch, platform
):
    backend = SimpleNamespace(
        locking=Mock(), flock=Mock(), LK_NBLCK=1, LK_UNLCK=2, LOCK_EX=4, LOCK_NB=8, LOCK_UN=16
    )
    with open(tmp_path / "lock", "w+b") as stream:
        stream.write(b"sentinel")
        stream.flush()
        with monkeypatch.context() as patch:
            patch.setattr(atomic_io.os, "name", platform)
            patch.setattr(atomic_io.importlib, "import_module", lambda name: backend)
            atomic_io._try_lock(stream)
            assert stream.tell() == 0
            stream.seek(4)
            atomic_io._unlock(stream)
            assert stream.tell() == 0
        if platform == "nt":
            assert backend.locking.call_args_list == [
                call(stream.fileno(), backend.LK_NBLCK, 1),
                call(stream.fileno(), backend.LK_UNLCK, 1),
            ]
            backend.flock.assert_not_called()
        else:
            assert backend.flock.call_args_list == [
                call(stream.fileno(), backend.LOCK_EX | backend.LOCK_NB),
                call(stream.fileno(), backend.LOCK_UN),
            ]
            backend.locking.assert_not_called()


def test_mutation_lock_timeout_leaves_persistent_file_and_closes_descriptor(tmp_path, monkeypatch):
    attempts = []

    def busy(stream):
        attempts.append(stream)
        raise BlockingIOError("another process holds the lock")

    monkeypatch.setattr(atomic_io, "_try_lock", busy)
    unlock = Mock()
    monkeypatch.setattr(atomic_io, "_unlock", unlock)
    with pytest.raises(TimeoutError, match="file mutation lock"):
        with file_mutation_lock(tmp_path / "history.json", timeout=0):
            pytest.fail("Entered critical section without the lock")
    assert len(attempts) == 1
    assert attempts[0].closed
    assert (tmp_path / "history.json.lock").read_bytes() == b"\0"
    unlock.assert_not_called()


def test_mutation_lock_retries_contention_and_releases_after_body_error(tmp_path, monkeypatch):
    original_lock = atomic_io._try_lock
    attempts = 0

    def temporarily_busy(stream):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise BlockingIOError("busy")
        original_lock(stream)

    monkeypatch.setattr(atomic_io, "_try_lock", temporarily_busy)
    monkeypatch.setattr(atomic_io.time, "sleep", lambda delay: None)
    target = tmp_path / "history.json"
    with pytest.raises(ValueError, match="body failed"):
        with file_mutation_lock(target):
            raise ValueError("body failed")
    assert attempts == 2
    with file_mutation_lock(target, timeout=0):
        assert target.with_name(f"{target.name}.lock").exists()


@pytest.mark.parametrize("kwargs", [{"timeout": -1}, {"poll_interval": 0}])
def test_mutation_lock_rejects_invalid_wait_settings(tmp_path, kwargs):
    with pytest.raises(ValueError):
        with file_mutation_lock(tmp_path / "history.json", **kwargs):
            pytest.fail("Invalid wait settings accepted")
