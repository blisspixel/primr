"""
File handling utilities.

This module provides:
- Secure temporary file handling
- Path sanitization for safe filesystem operations
- Cache key generation
- File validation utilities
"""

import hashlib
import os
import platform
import re
import shutil
import subprocess
import tempfile
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from primr.utils.errors import ValidationError

# =============================================================================
# SECURE TEMP FILES
# =============================================================================

@contextmanager
def secure_temp_file(suffix: str = "", prefix: str = "research_") -> Iterator[Path]:
    """
    Create a secure temporary file that's automatically cleaned up.

    Uses Python's tempfile module for secure file creation with
    unpredictable names. File is automatically deleted on context exit.

    Args:
        suffix: File extension (e.g., ".pdf")
        prefix: Filename prefix

    Yields:
        Path to the temporary file

    Example:
        with secure_temp_file(".pdf") as pdf_path:
            page.pdf(path=str(pdf_path))
            with open(pdf_path, "rb") as f:
                content = f.read()
        # File is automatically deleted here
    """
    fd = None
    path = None
    try:
        fd, path_str = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        path = Path(path_str)
        os.close(fd)  # Close the file descriptor, we'll open it ourselves
        fd = None
        yield path
    finally:
        if fd is not None:
            with suppress(OSError):
                os.close(fd)
        if path is not None:
            with suppress(OSError, PermissionError):
                path.unlink(missing_ok=True)


@contextmanager
def secure_temp_dir(prefix: str = "research_") -> Iterator[Path]:
    """
    Create a secure temporary directory that's automatically cleaned up.

    Args:
        prefix: Directory name prefix

    Yields:
        Path to the temporary directory
    """
    import shutil

    path = None
    try:
        path = Path(tempfile.mkdtemp(prefix=prefix))
        yield path
    finally:
        if path is not None:
            with suppress(OSError, PermissionError):
                shutil.rmtree(path, ignore_errors=True)


# =============================================================================
# PATH SANITIZATION
# =============================================================================

def sanitize_filename(
    name: str,
    max_length: int = 100,
    replacement: str = "_"
) -> str:
    """
    Sanitize a string for safe use as a filename.

    Removes or replaces characters that are unsafe for filesystems:
    - Path traversal attempts (../, /)
    - Special characters
    - Control characters

    Args:
        name: The string to sanitize
        max_length: Maximum length of result
        replacement: Character to replace unsafe chars with

    Returns:
        Sanitized filename string

    Example:
        safe = sanitize_filename("Company Name (Inc.)")
        # Returns: "Company_Name_Inc"
    """
    if not name:
        return "unnamed"

    # Remove path traversal attempts
    name = name.replace("..", "")
    name = name.replace("/", replacement)
    name = name.replace("\\", replacement)

    # Remove or replace unsafe characters
    # Keep: alphanumeric, spaces, hyphens, underscores, dots
    name = re.sub(r'[^\w\s\-.]', replacement, name)

    # Replace multiple spaces/underscores with single
    name = re.sub(r'[\s_]+', replacement, name)

    # Remove leading/trailing special chars
    name = name.strip(f'{replacement}.-')

    # Limit length
    if len(name) > max_length:
        name = name[:max_length].rstrip(replacement)

    return name if name else "unnamed"


def get_safe_path(
    base_dir: Path,
    *parts: str,
    create: bool = False
) -> Path:
    """
    Get a safe path that's guaranteed to be under base_dir.

    Prevents path traversal attacks by resolving the path and
    verifying it's still under the base directory.

    Args:
        base_dir: The base directory (must exist)
        *parts: Path components to join
        create: If True, create the directory

    Returns:
        Safe resolved path

    Raises:
        ValidationError: If path would escape base_dir

    Example:
        path = get_safe_path(working_dir, company_name, "reports")
    """
    # Sanitize each part
    safe_parts = [sanitize_filename(p) for p in parts if p]

    if not safe_parts:
        raise ValidationError("No valid path components provided")

    # Build and resolve path
    base_resolved = base_dir.resolve()
    target = base_resolved.joinpath(*safe_parts).resolve()

    # Verify path is under base_dir
    try:
        target.relative_to(base_resolved)
    except ValueError as e:
        raise ValidationError(
            f"Path would escape base directory: {'/'.join(parts)}"
        ) from e

    if create:
        target.mkdir(parents=True, exist_ok=True)

    return target


def get_company_folder(
    base_dir: Path,
    company_name: str,
    create: bool = True
) -> Path:
    """
    Get a safe folder path for company data.

    Args:
        base_dir: Base directory for company folders
        company_name: Company name to create folder for
        create: If True, create the directory

    Returns:
        Path to company folder

    Example:
        folder = get_company_folder(working_dir, "Acme Corp")
        # Returns: working_dir / "Acme_Corp"
    """
    return get_safe_path(base_dir, company_name, create=create)


# =============================================================================
# CACHE UTILITIES
# =============================================================================

def get_cache_key(url: str, prefix: str = "") -> str:
    """
    Generate a cache key for a URL.

    Uses SHA-256 hash truncated to 32 characters for a good
    balance of uniqueness and readability.

    Args:
        url: URL to generate key for
        prefix: Optional prefix for the key

    Returns:
        Cache key string
    """
    hash_value = hashlib.sha256(url.encode()).hexdigest()[:32]
    if prefix:
        return f"{prefix}_{hash_value}"
    return hash_value


def get_cache_path(
    cache_dir: Path,
    url: str,
    extension: str = ".txt"
) -> Path:
    """
    Get the cache file path for a URL.

    Args:
        cache_dir: Directory for cache files
        url: URL being cached
        extension: File extension for cache file

    Returns:
        Path to cache file
    """
    key = get_cache_key(url)
    return cache_dir / f"{key}{extension}"


# =============================================================================
# FILE VALIDATION
# =============================================================================

def validate_file_exists(path: Path, description: str = "File") -> Path:
    """
    Validate that a file exists.

    Args:
        path: Path to validate
        description: Description for error message

    Returns:
        The validated path

    Raises:
        ValidationError: If file doesn't exist
    """
    if not path.exists():
        raise ValidationError(f"{description} not found: {path}")
    if not path.is_file():
        raise ValidationError(f"{description} is not a file: {path}")
    return path


def validate_directory_exists(path: Path, description: str = "Directory") -> Path:
    """
    Validate that a directory exists.

    Args:
        path: Path to validate
        description: Description for error message

    Returns:
        The validated path

    Raises:
        ValidationError: If directory doesn't exist
    """
    if not path.exists():
        raise ValidationError(f"{description} not found: {path}")
    if not path.is_dir():
        raise ValidationError(f"{description} is not a directory: {path}")
    return path


def ensure_parent_exists(path: Path) -> Path:
    """
    Ensure the parent directory of a path exists.

    Args:
        path: Path whose parent should exist

    Returns:
        The original path
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def open_with_default_app(path: str | Path) -> None:
    """
    Open a file using the current platform's default application.

    Falls back to the ``webbrowser`` module when desktop open commands are
    unavailable (common on minimal Linux environments).
    """
    file_path = Path(path).expanduser()
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    resolved = str(file_path.resolve())
    system = platform.system()

    if system == "Windows":
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise RuntimeError("Windows startfile is unavailable in this environment")
        startfile(resolved)
        return

    commands: list[list[str]] = []
    if system == "Darwin":
        commands = [["open", resolved]]
    else:
        commands = [
            ["xdg-open", resolved],
            ["gio", "open", resolved],
            ["gnome-open", resolved],
            ["kde-open", resolved],
        ]

    for cmd in commands:
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=True)
            return

    if webbrowser.open(file_path.resolve().as_uri()):
        return

    raise RuntimeError("Could not find a platform opener command for this environment")


# =============================================================================
# FILE SIZE UTILITIES
# =============================================================================

def get_file_size_str(size_bytes: int) -> str:
    """
    Convert file size to human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 MB")
    """
    size: float = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def is_file_too_large(path: Path, max_size_mb: float = 100) -> bool:
    """
    Check if a file exceeds the maximum size.

    Args:
        path: Path to file
        max_size_mb: Maximum size in megabytes

    Returns:
        True if file is too large
    """
    if not path.exists():
        return False
    size_mb = path.stat().st_size / (1024 * 1024)
    return size_mb > max_size_mb
