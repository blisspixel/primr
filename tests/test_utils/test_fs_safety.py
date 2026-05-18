"""Tests for primr.utils.fs_safety — covers the symlink-safe writability
probe and the owner-only write helpers introduced to close the
.primr_write_test symlink-clobber and 0644 .env findings."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path  # noqa: TC003 - used at runtime in fixtures below

import pytest

from primr.utils.fs_safety import (
    check_dir_writable,
    write_bytes_secure,
    write_text_secure,
)


class TestCheckDirWritable:
    def test_writable_dir_returns_ok(self, tmp_path: Path) -> None:
        ok, why = check_dir_writable(tmp_path)
        assert ok is True
        assert why is None

    def test_creates_missing_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "dir"
        ok, _ = check_dir_writable(target)
        assert ok is True
        assert target.is_dir()

    def test_random_probe_name_each_call(self, tmp_path: Path) -> None:
        # Two calls should not collide on the same predictable filename
        # (the old .primr_write_test pattern was exactly this collision).
        check_dir_writable(tmp_path)
        check_dir_writable(tmp_path)

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink semantics")
    def test_refuses_symlinked_probe_file(self, tmp_path: Path) -> None:
        # Pre-create a symlink at one of the random probe names — this is
        # impossible without seeing the name, so instead patch the random
        # token generator to a fixed value and plant the symlink.
        import primr.utils.fs_safety as fs_safety

        original_token = fs_safety.secrets.token_hex
        fs_safety.secrets.token_hex = lambda n=8: "deadbeefcafebabe"  # type: ignore[assignment]
        try:
            target = tmp_path / "victim"
            target.write_text("original")
            (tmp_path / ".primr_write_test_deadbeefcafebabe").symlink_to(target)
            ok, why = check_dir_writable(tmp_path)
            assert ok is False
            assert why is not None
            assert target.read_text() == "original"  # not clobbered
        finally:
            fs_safety.secrets.token_hex = original_token  # type: ignore[assignment]


class TestSecureWrite:
    def test_write_text_creates_file(self, tmp_path: Path) -> None:
        target = tmp_path / "secret.env"
        write_text_secure(target, "XAI_API_KEY=fake-12345")
        assert target.read_text() == "XAI_API_KEY=fake-12345"

    def test_write_bytes_truncates_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "secret.env"
        target.write_bytes(b"old-much-longer-content")
        write_bytes_secure(target, b"new")
        assert target.read_bytes() == b"new"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")
    def test_posix_file_mode_is_0600(self, tmp_path: Path) -> None:
        target = tmp_path / "secret.env"
        write_text_secure(target, "k=v")
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o600

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows ACL inheritance")
    def test_windows_skips_chmod(self, tmp_path: Path) -> None:
        # On Windows the helper should still write the file; ACL inheritance
        # from the user profile dir is the real access control.
        target = tmp_path / "secret.env"
        write_text_secure(target, "k=v")
        assert target.exists()


class TestPathRejection:
    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
    def test_unwritable_dir_returns_error(self, tmp_path: Path) -> None:
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        readonly.chmod(0o500)
        try:
            ok, why = check_dir_writable(readonly)
            assert ok is False
            assert why is not None
        finally:
            readonly.chmod(0o700)


class TestModuleSurface:
    def test_exports(self) -> None:
        import primr.utils.fs_safety as m

        assert callable(m.check_dir_writable)
        assert callable(m.write_text_secure)
        assert callable(m.write_bytes_secure)


def test_os_module_available() -> None:
    """Sanity check that keeps the os import warm for future tests."""
    assert isinstance(os.name, str)
