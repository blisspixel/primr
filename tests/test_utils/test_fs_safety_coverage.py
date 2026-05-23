"""Coverage tests for primr.utils.fs_safety.

Adds the branches the existing test_fs_safety.py doesn't reach: the POSIX
``os.open``/chmod write path (forced via mocking ``os.name``), the chmod
failure debug branch, the ELOOP symlink-probe error mapping, and
write_text_secure delegating to write_bytes_secure.
"""

from __future__ import annotations

import errno
from pathlib import Path
from unittest.mock import patch

from primr.utils import fs_safety
from primr.utils.fs_safety import (
    check_dir_writable,
    write_bytes_secure,
    write_text_secure,
)


class TestWriteBytesSecurePosixPath:
    def test_posix_uses_os_open_and_chmod(self, tmp_path):
        target = tmp_path / "secret.bin"
        with patch.object(fs_safety.os, "name", "posix"):
            write_bytes_secure(target, b"payload", mode=0o600)
        assert target.read_bytes() == b"payload"

    def test_posix_chmod_failure_is_swallowed(self, tmp_path, caplog):
        import logging

        target = tmp_path / "secret2.bin"
        real_chmod = Path.chmod

        def flaky_chmod(self, mode, *args, **kwargs):
            if self == target:
                raise OSError("no chmod")
            return real_chmod(self, mode, *args, **kwargs)

        with (
            patch.object(fs_safety.os, "name", "posix"),
            patch.object(Path, "chmod", flaky_chmod),
            caplog.at_level(logging.DEBUG),
        ):
            # Should not raise even though chmod fails.
            write_bytes_secure(target, b"data")
        assert target.read_bytes() == b"data"

    def test_non_posix_uses_write_bytes(self, tmp_path):
        target = tmp_path / "win.bin"
        with patch.object(fs_safety.os, "name", "nt"):
            write_bytes_secure(target, b"abc")
        assert target.read_bytes() == b"abc"


class TestWriteTextSecure:
    def test_writes_utf8(self, tmp_path):
        target = tmp_path / "note.txt"
        write_text_secure(target, "héllo")
        assert target.read_text(encoding="utf-8") == "héllo"


class TestCheckDirWritableErrors:
    def test_mkdir_failure_returns_error(self, tmp_path):
        d = tmp_path / "sub"
        with patch.object(Path, "mkdir", side_effect=OSError("denied")):
            ok, err = check_dir_writable(d)
        assert ok is False
        assert "Cannot create directory" in err

    def test_eloop_maps_to_symlink_message(self, tmp_path):
        with patch.object(
            fs_safety.os, "open", side_effect=OSError(errno.ELOOP, "loop")
        ):
            ok, err = check_dir_writable(tmp_path)
        assert ok is False
        assert "Symlink detected" in err

    def test_generic_open_error_returns_not_writable(self, tmp_path):
        with patch.object(
            fs_safety.os, "open", side_effect=OSError(errno.EACCES, "denied")
        ):
            ok, err = check_dir_writable(tmp_path)
        assert ok is False
        assert "Not writable" in err

    def test_unlink_failure_still_returns_ok(self, tmp_path):
        # If the probe file can't be unlinked we still report writable.
        with patch.object(Path, "unlink", side_effect=OSError("busy")):
            ok, err = check_dir_writable(tmp_path)
        assert ok is True
        assert err is None
