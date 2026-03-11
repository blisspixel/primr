"""
Path traversal protection tests.

Tests that verify file path validation prevents directory traversal attacks.
"""

from pathlib import Path

import pytest

from primr.utils.validators import InputValidationError, validate_file_path


class TestPathTraversalProtection:
    """Test path traversal protection."""

    def test_validate_file_path_blocks_parent_directory(self):
        """Test that parent directory traversal is blocked."""
        test_cases = [
            "../../../etc/passwd",
            "../../sensitive/file.txt",
            "subdir/../../etc/passwd",
            "./../../etc/passwd",
        ]

        for path in test_cases:
            with pytest.raises(InputValidationError) as exc_info:
                validate_file_path(path, base_dir=Path("/safe/dir"))
            error_msg = str(exc_info.value).lower()
            assert "traversal" in error_msg or "not allowed" in error_msg, (
                f"Error should mention traversal: {exc_info.value}"
            )

    def test_validate_file_path_allows_safe_paths(self):
        """Test that safe paths are allowed."""
        base_dir = Path("/safe/dir")
        test_cases = [
            "file.txt",
            "subdir/file.txt",
            "./file.txt",
            "subdir/nested/file.txt",
        ]

        for path in test_cases:
            result = validate_file_path(path, base_dir=base_dir)
            assert result is not None

    def test_validate_file_path_blocks_absolute_outside_base(self):
        """Test that absolute paths outside base directory are blocked."""
        base_dir = Path("/safe/dir")
        test_cases = [
            "/etc/passwd",
            "/tmp/malicious.txt",
        ]

        for path in test_cases:
            with pytest.raises(InputValidationError):
                validate_file_path(path, base_dir=base_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
