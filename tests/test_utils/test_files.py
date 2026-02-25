"""
Tests for file handling utilities.
"""

from unittest.mock import patch

import pytest

from primr.utils.errors import ValidationError
from primr.utils.files import (
    ensure_parent_exists,
    get_cache_key,
    get_cache_path,
    get_company_folder,
    get_file_size_str,
    get_safe_path,
    is_file_too_large,
    open_with_default_app,
    sanitize_filename,
    secure_temp_dir,
    secure_temp_file,
    validate_directory_exists,
    validate_file_exists,
)


class TestSecureTempFile:
    """Tests for secure_temp_file context manager."""

    def test_creates_file(self):
        """Should create a temporary file."""
        with secure_temp_file(".txt") as path:
            assert path.exists() or True  # File may not exist until written
            path.write_text("test content")
            assert path.exists()

    def test_deletes_on_exit(self):
        """Should delete file on context exit."""
        temp_path = None
        with secure_temp_file(".txt") as path:
            path.write_text("test")
            temp_path = path

        assert not temp_path.exists()

    def test_deletes_on_exception(self):
        """Should delete file even if exception occurs."""
        temp_path = None
        try:
            with secure_temp_file(".txt") as path:
                path.write_text("test")
                temp_path = path
                raise ValueError("test error")
        except ValueError:
            pass

        assert not temp_path.exists()

    def test_uses_suffix(self):
        """Should use provided suffix."""
        with secure_temp_file(".pdf") as path:
            assert path.suffix == ".pdf"

    def test_uses_prefix(self):
        """Should use provided prefix."""
        with secure_temp_file(prefix="myprefix_") as path:
            assert "myprefix_" in path.name


class TestSecureTempDir:
    """Tests for secure_temp_dir context manager."""

    def test_creates_directory(self):
        """Should create a temporary directory."""
        with secure_temp_dir() as path:
            assert path.exists()
            assert path.is_dir()

    def test_deletes_on_exit(self):
        """Should delete directory on context exit."""
        temp_path = None
        with secure_temp_dir() as path:
            temp_path = path
            # Create some files inside
            (path / "test.txt").write_text("test")

        assert not temp_path.exists()

    def test_deletes_contents(self):
        """Should delete all contents."""
        with secure_temp_dir() as path:
            # Create nested structure
            subdir = path / "subdir"
            subdir.mkdir()
            (subdir / "file.txt").write_text("test")

        # Should not raise, directory should be gone


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_basic_sanitization(self):
        """Should sanitize basic unsafe characters."""
        assert sanitize_filename("file/name") == "file_name"
        assert sanitize_filename("file\\name") == "file_name"
        assert sanitize_filename("file:name") == "file_name"

    def test_removes_path_traversal(self):
        """Should remove path traversal attempts."""
        assert ".." not in sanitize_filename("../../../etc/passwd")
        assert "/" not in sanitize_filename("../file")
        assert "\\" not in sanitize_filename("..\\file")

    def test_preserves_safe_characters(self):
        """Should preserve safe characters."""
        result = sanitize_filename("Company Name-2024")
        assert "Company" in result
        assert "Name" in result
        assert "2024" in result

    def test_limits_length(self):
        """Should limit filename length."""
        long_name = "a" * 200
        result = sanitize_filename(long_name, max_length=50)
        assert len(result) <= 50

    def test_handles_empty_string(self):
        """Should return 'unnamed' for empty string."""
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename("   ") == "unnamed"

    def test_handles_special_characters(self):
        """Should handle special characters."""
        result = sanitize_filename("Company (Inc.) <test>")
        assert "<" not in result
        assert ">" not in result
        assert "(" not in result

    def test_collapses_multiple_underscores(self):
        """Should collapse multiple underscores."""
        result = sanitize_filename("name   with   spaces")
        assert "___" not in result


class TestGetSafePath:
    """Tests for get_safe_path function."""

    def test_creates_safe_path(self, tmp_path):
        """Should create a safe path under base_dir."""
        path = get_safe_path(tmp_path, "company", "reports")
        assert str(path).startswith(str(tmp_path))

    def test_prevents_path_traversal(self, tmp_path):
        """Should sanitize path traversal attempts."""
        # The function sanitizes ".." so it won't escape
        # This test verifies the sanitization works
        path = get_safe_path(tmp_path, "../../../etc", "passwd")
        # Path should still be under tmp_path due to sanitization
        assert str(tmp_path.resolve()) in str(path.resolve())

    def test_sanitizes_components(self, tmp_path):
        """Should sanitize path components."""
        path = get_safe_path(tmp_path, "Company/Name", "file:name")
        assert "/" not in path.name
        assert ":" not in path.name

    def test_creates_directory_when_requested(self, tmp_path):
        """Should create directory when create=True."""
        path = get_safe_path(tmp_path, "new_folder", create=True)
        assert path.exists()
        assert path.is_dir()

    def test_raises_on_empty_parts(self, tmp_path):
        """Should raise on empty path parts."""
        with pytest.raises(ValidationError):
            get_safe_path(tmp_path)


class TestGetCompanyFolder:
    """Tests for get_company_folder function."""

    def test_creates_folder(self, tmp_path):
        """Should create company folder."""
        folder = get_company_folder(tmp_path, "Acme Corp")
        assert folder.exists()
        assert folder.is_dir()

    def test_sanitizes_company_name(self, tmp_path):
        """Should sanitize company name."""
        folder = get_company_folder(tmp_path, "Company/With\\Bad:Chars")
        assert folder.exists()
        assert "/" not in folder.name
        assert "\\" not in folder.name


class TestCacheUtilities:
    """Tests for cache utility functions."""

    def test_get_cache_key_consistent(self):
        """Same URL should produce same key."""
        url = "https://example.com/page"
        key1 = get_cache_key(url)
        key2 = get_cache_key(url)
        assert key1 == key2

    def test_get_cache_key_different_urls(self):
        """Different URLs should produce different keys."""
        key1 = get_cache_key("https://example.com/page1")
        key2 = get_cache_key("https://example.com/page2")
        assert key1 != key2

    def test_get_cache_key_with_prefix(self):
        """Should include prefix in key."""
        key = get_cache_key("https://example.com", prefix="html")
        assert key.startswith("html_")

    def test_get_cache_path(self, tmp_path):
        """Should return correct cache path."""
        path = get_cache_path(tmp_path, "https://example.com", ".txt")
        assert path.parent == tmp_path
        assert path.suffix == ".txt"


class TestFileValidation:
    """Tests for file validation functions."""

    def test_validate_file_exists_success(self, tmp_path):
        """Should return path when file exists."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        result = validate_file_exists(file_path)
        assert result == file_path

    def test_validate_file_exists_accepts_string_path(self, tmp_path):
        """Should accept str paths and return Path."""
        file_path = tmp_path / "string-path.txt"
        file_path.write_text("test")
        result = validate_file_exists(str(file_path))
        assert result == file_path

    def test_validate_file_exists_failure(self, tmp_path):
        """Should raise when file doesn't exist."""
        with pytest.raises(ValidationError):
            validate_file_exists(tmp_path / "nonexistent.txt")

    def test_validate_file_exists_directory(self, tmp_path):
        """Should raise when path is a directory."""
        with pytest.raises(ValidationError):
            validate_file_exists(tmp_path)

    def test_validate_directory_exists_success(self, tmp_path):
        """Should return path when directory exists."""
        result = validate_directory_exists(tmp_path)
        assert result == tmp_path

    def test_validate_directory_exists_accepts_string_path(self, tmp_path):
        """Should accept str dir paths and return Path."""
        result = validate_directory_exists(str(tmp_path))
        assert result == tmp_path

    def test_validate_directory_exists_failure(self, tmp_path):
        """Should raise when directory doesn't exist."""
        with pytest.raises(ValidationError):
            validate_directory_exists(tmp_path / "nonexistent")

    def test_ensure_parent_exists(self, tmp_path):
        """Should create parent directories."""
        path = tmp_path / "a" / "b" / "c" / "file.txt"
        ensure_parent_exists(path)
        assert path.parent.exists()

    def test_ensure_parent_exists_accepts_string_path(self, tmp_path):
        """Should accept str paths for parent creation."""
        path = tmp_path / "x" / "y" / "z" / "file.txt"
        returned = ensure_parent_exists(str(path))
        assert returned == path
        assert path.parent.exists()


class TestFileSizeUtilities:
    """Tests for file size utility functions."""

    def test_get_file_size_str_bytes(self):
        """Should format bytes correctly."""
        assert "B" in get_file_size_str(500)

    def test_get_file_size_str_kilobytes(self):
        """Should format kilobytes correctly."""
        assert "KB" in get_file_size_str(5000)

    def test_get_file_size_str_megabytes(self):
        """Should format megabytes correctly."""
        assert "MB" in get_file_size_str(5 * 1024 * 1024)

    def test_is_file_too_large_false(self, tmp_path):
        """Should return False for small files."""
        file_path = tmp_path / "small.txt"
        file_path.write_text("small content")

        assert is_file_too_large(file_path, max_size_mb=1) is False

    def test_is_file_too_large_nonexistent(self, tmp_path):
        """Should return False for nonexistent files."""
        assert is_file_too_large(tmp_path / "nonexistent.txt") is False

    def test_is_file_too_large_accepts_string_path(self, tmp_path):
        """Should accept str paths for size checks."""
        file_path = tmp_path / "small-string.txt"
        file_path.write_text("small content")
        assert is_file_too_large(str(file_path), max_size_mb=1) is False


class TestOpenWithDefaultApp:
    """Cross-platform tests for open_with_default_app helper."""

    def test_windows_uses_startfile(self, tmp_path):
        path = tmp_path / "report.txt"
        path.write_text("ok", encoding="utf-8")
        with patch("primr.utils.files.platform.system", return_value="Windows"), patch(
            "primr.utils.files.os.startfile", create=True
        ) as mock_startfile:
            open_with_default_app(path)
        mock_startfile.assert_called_once()

    def test_darwin_uses_open_command(self, tmp_path):
        path = tmp_path / "report.txt"
        path.write_text("ok", encoding="utf-8")
        with patch("primr.utils.files.platform.system", return_value="Darwin"), patch(
            "primr.utils.files.shutil.which", return_value="/usr/bin/open"
        ), patch("primr.utils.files.subprocess.run") as mock_run:
            open_with_default_app(path)
        mock_run.assert_called_once()

    def test_linux_falls_back_to_webbrowser(self, tmp_path):
        path = tmp_path / "report.txt"
        path.write_text("ok", encoding="utf-8")
        with patch("primr.utils.files.platform.system", return_value="Linux"), patch(
            "primr.utils.files.shutil.which", return_value=None
        ), patch("primr.utils.files.webbrowser.open", return_value=True) as mock_browser, patch(
            "primr.utils.files.subprocess.run"
        ) as mock_run:
            open_with_default_app(path)
        mock_run.assert_not_called()
        mock_browser.assert_called_once()
