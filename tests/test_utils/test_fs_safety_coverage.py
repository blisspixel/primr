"""Coverage tests for primr.utils.fs_safety.

Adds the branches the existing test_fs_safety.py doesn't reach: the POSIX
``os.open``/chmod write path (forced via mocking ``os.name``), the chmod
failure debug branch, the ELOOP symlink-probe error mapping, and
write_text_secure delegating to write_bytes_secure.
"""

from __future__ import annotations

import errno
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from primr.utils import fs_safety
from primr.utils.fs_safety import (
    check_dir_atomic_writable,
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
        with patch.object(fs_safety.os, "open", side_effect=OSError(errno.ELOOP, "loop")):
            ok, err = check_dir_writable(tmp_path)
        assert ok is False
        assert "Symlink detected" in err

    def test_generic_open_error_returns_not_writable(self, tmp_path):
        with patch.object(fs_safety.os, "open", side_effect=OSError(errno.EACCES, "denied")):
            ok, err = check_dir_writable(tmp_path)
        assert ok is False
        assert "Not writable" in err

    def test_unlink_failure_still_returns_ok(self, tmp_path):
        # If the probe file can't be unlinked we still report writable.
        with patch.object(Path, "unlink", side_effect=OSError("busy")):
            ok, err = check_dir_writable(tmp_path)
        assert ok is True
        assert err is None

    def test_atomic_probe_cleanup_failure_is_not_hidden(self, tmp_path):
        real_unlink = Path.unlink

        def fail_atomic_probe(candidate, *args, **kwargs):
            if candidate.name.startswith(".primr_atomic_test_"):
                raise OSError("busy")
            return real_unlink(candidate, *args, **kwargs)

        with patch.object(Path, "unlink", fail_atomic_probe):
            ok, err = check_dir_atomic_writable(tmp_path)

        assert ok is False
        assert err == "Atomic cleanup failed: OSError"


class TestPathRedirectClassification:
    @pytest.mark.parametrize(
        ("alias", "destination"),
        [("var", "private/var"), ("tmp", "/private/tmp")],
    )
    def test_standard_darwin_root_alias_is_trusted(self, alias, destination):
        link_metadata = SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=0)
        root_metadata = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        with (
            patch.object(fs_safety.sys, "platform", "darwin"),
            patch.object(Path, "stat", return_value=root_metadata),
            patch.object(fs_safety.os, "readlink", return_value=destination),
        ):
            assert fs_safety._is_trusted_darwin_root_alias(Path(f"/{alias}"), link_metadata)

    def test_standard_darwin_var_alias_does_not_reject_descendant(self):
        link_metadata = SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=0)
        root_metadata = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)

        def metadata_for(candidate):
            if candidate == Path("/var"):
                return link_metadata
            if candidate == Path("/"):
                return root_metadata
            raise FileNotFoundError

        with (
            patch.object(fs_safety.sys, "platform", "darwin"),
            patch.object(Path, "absolute", return_value=Path("/var/folders/run/journal.json")),
            patch.object(Path, "lstat", metadata_for),
            patch.object(Path, "stat", return_value=root_metadata),
            patch.object(fs_safety.os, "readlink", return_value="private/var"),
        ):
            assert not fs_safety.path_contains_link_or_reparse_point(Path("journal.json"))

    @pytest.mark.parametrize(
        (
            "platform",
            "alias",
            "link_uid",
            "root_uid",
            "root_mode",
            "destination",
        ),
        [
            ("linux", "/var", 0, 0, 0o755, "private/var"),
            ("darwin", "/var", 501, 0, 0o755, "private/var"),
            ("darwin", "/var", 0, 501, 0o755, "private/var"),
            ("darwin", "/var", 0, 0, 0o775, "private/var"),
            ("darwin", "/var", 0, 0, 0o755, "private/elsewhere"),
            ("darwin", "/nested/var", 0, 0, 0o755, "private/var"),
        ],
    )
    def test_nonstandard_darwin_root_alias_is_rejected(
        self,
        platform,
        alias,
        link_uid,
        root_uid,
        root_mode,
        destination,
    ):
        link_metadata = SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=link_uid)
        root_metadata = SimpleNamespace(st_mode=stat.S_IFDIR | root_mode, st_uid=root_uid)
        with (
            patch.object(fs_safety.sys, "platform", platform),
            patch.object(Path, "stat", return_value=root_metadata),
            patch.object(fs_safety.os, "readlink", return_value=destination),
        ):
            assert not fs_safety._is_trusted_darwin_root_alias(Path(alias), link_metadata)

    def test_nested_link_below_trusted_alias_is_rejected(self):
        link_metadata = SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=501)
        root_metadata = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)

        def metadata_for(candidate):
            if candidate == Path("/var/folders/redirect"):
                return link_metadata
            if candidate == Path("/var"):
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=0)
            if candidate == Path("/"):
                return root_metadata
            raise FileNotFoundError

        with (
            patch.object(fs_safety.sys, "platform", "darwin"),
            patch.object(
                Path,
                "absolute",
                return_value=Path("/var/folders/redirect/journal.json"),
            ),
            patch.object(Path, "lstat", metadata_for),
            patch.object(Path, "stat", return_value=root_metadata),
            patch.object(fs_safety.os, "readlink", return_value="private/var"),
        ):
            assert fs_safety.path_contains_link_or_reparse_point(Path("journal.json"))
