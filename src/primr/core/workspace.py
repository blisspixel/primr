"""
Working folder operations for research artifacts.

This module provides utilities for:
- Creating and managing working folders for research
- Consolidating section files into context documents
- Validating context files for Deep Research upload
- Saving and reading section outputs

Usage:
    from primr.core.workspace import (
        create_working_folder,
        consolidate_working_folder,
        validate_context_files,
        save_section_output,
    )

    # Create a working folder
    folder = create_working_folder("Tesla", "https://tesla.com")

    # Save section content
    save_section_output(folder, "industry", "Electric vehicles and clean energy")

    # Consolidate for context
    context_file = consolidate_working_folder(folder)
"""
import glob
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from primr.config.config import WORKING_DIR
from primr.utils.logging_config import get_logger

logger = get_logger("workspace")


# =============================================================================
# CONSTANTS
# =============================================================================

# Supported file types for Deep Research File Search
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({'.txt', '.pdf', '.md', '.json', '.csv'})


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass(frozen=True)
class WorkspaceConfig:
    """Configuration for workspace operations."""
    base_dir: Path
    company_name: str
    website: str | None = None

    @property
    def folder_name(self) -> str:
        """Derive folder name from company name or website."""
        if self.company_name:
            return self.company_name.replace(" ", "_")
        if self.website:
            netloc = urlparse(self.website).netloc
            return netloc.replace("www.", "").replace(".", "_")
        return "Unknown_Company"

    @property
    def folder_path(self) -> Path:
        return self.base_dir / self.folder_name


@dataclass
class ConsolidationResult:
    """Result of folder consolidation."""
    output_path: Path
    files_processed: int
    total_size_bytes: int
    sections: list[str] = field(default_factory=list)


@dataclass
class FileValidationResult:
    """Result of file validation."""
    valid_files: tuple[Path, ...]
    invalid_files: tuple[tuple[Path, str], ...]  # (path, reason)
    warnings: tuple[str, ...]

    @property
    def all_valid(self) -> bool:
        return len(self.invalid_files) == 0


# =============================================================================
# PUBLIC INTERFACE
# =============================================================================

def create_working_folder(company_name: str | None, website: str | None) -> str:
    """
    Create working folder for research artifacts.

    Creates the folder if it does not exist.

    Args:
        company_name: Name of the company
        website: Company website URL

    Returns:
        Path to the created folder as string (for backward compatibility)
    """
    if not company_name and website:
        parsed_url = urlparse(website)
        company_name = parsed_url.netloc.replace("www.", "").replace(".", "_")

    folder_name = company_name.replace(" ", "_") if company_name else "Unknown_Company"
    folder_path = os.path.join(WORKING_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def create_working_folder_from_config(config: WorkspaceConfig) -> Path:
    """
    Create working folder from WorkspaceConfig.

    Args:
        config: Workspace configuration

    Returns:
        Path to the created folder
    """
    folder_path = config.folder_path
    folder_path.mkdir(parents=True, exist_ok=True)
    return folder_path


@contextmanager
def working_folder(
    company_name: str | None,
    website: str | None,
    cleanup_on_exit: bool = False
) -> Iterator[Path]:
    """
    Context manager for working folder operations.

    Creates folder on entry, optionally cleans up on exit.

    Args:
        company_name: Name of the company
        website: Company website URL
        cleanup_on_exit: If True, remove folder contents on exit

    Yields:
        Path to the working folder
    """
    folder_path = Path(create_working_folder(company_name, website))
    try:
        yield folder_path
    finally:
        if cleanup_on_exit:
            import shutil
            try:
                shutil.rmtree(folder_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup working folder: {e}")


def consolidate_working_folder(folder_path: str | Path) -> str:
    """
    Consolidate all .txt files from a working folder into a single context file.

    Args:
        folder_path: Path to working folder (e.g., working/Parts_Town)

    Returns:
        Path to the consolidated temporary file

    Raises:
        ValueError: If folder doesn't exist or contains no .txt files
    """
    folder_path = Path(folder_path) if isinstance(folder_path, str) else folder_path

    if not folder_path.is_dir():
        raise ValueError(f"Working folder not found: {folder_path}")

    # Find all .txt files
    txt_files = list(folder_path.glob("*.txt"))
    if not txt_files:
        raise ValueError(f"No .txt files found in {folder_path}")

    # Extract company name from folder
    company_name = folder_path.name.replace("_", " ")

    # Build consolidated document
    lines = [
        f"# Research Context: {company_name}",
        f"Source: {folder_path}",
        "",
        "This document contains research findings from the Structured Pipeline.",
        "",
        "---",
        ""
    ]

    sections_processed = []
    total_size = 0

    # Read each file and add to document
    for txt_file in sorted(txt_files):
        filename = txt_file.name
        section_name = filename.replace(".txt", "").replace("_", " ").title()

        try:
            content = txt_file.read_text(encoding="utf-8").strip()
            total_size += len(content)

            if content:
                lines.extend([
                    f"## {section_name}",
                    "",
                    content,
                    "",
                    "---",
                    ""
                ])
                sections_processed.append(section_name)
        except Exception as e:
            logger.warning(f"Failed to read {txt_file}: {e}")

    # Write to temp file
    content = '\n'.join(lines)
    fd, filepath = tempfile.mkstemp(
        suffix='.txt',
        prefix=f'{company_name.replace(" ", "_")}_context_'
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    logger.info(f"Consolidated {len(txt_files)} files into {filepath}")
    return filepath


def save_section_output(folder_path: str | Path, section_key: str, content: str) -> Path:
    """
    Save section content to file.

    Writes content to {folder_path}/{section_key}.txt.
    Creates parent directories if needed.

    Args:
        folder_path: Path to working folder
        section_key: Section identifier (used as filename)
        content: Content to save

    Returns:
        Path to the saved file
    """
    folder_path = Path(folder_path) if isinstance(folder_path, str) else folder_path
    filepath = folder_path / f"{section_key}.txt"

    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return filepath
    except OSError as e:
        logger.error(f"Failed to save section {section_key}: {e}")
        raise


def validate_context_files(file_paths: list[str | Path]) -> FileValidationResult:
    """
    Validate context files for Deep Research upload.

    Checks:
    - File exists
    - File is readable
    - Extension is supported
    - File is not empty

    Args:
        file_paths: List of file paths to validate

    Returns:
        FileValidationResult with categorized results
    """
    valid_files: list[Path] = []
    invalid_files: list[tuple[Path, str]] = []
    warnings: list[str] = []

    for file_path in file_paths:
        path = Path(file_path) if isinstance(file_path, str) else file_path

        if not path.exists():
            invalid_files.append((path, "File not found"))
            continue

        if not path.is_file():
            invalid_files.append((path, "Not a file"))
            continue

        ext = path.suffix.lower()

        if ext in SUPPORTED_EXTENSIONS:
            # Check if file is empty
            if path.stat().st_size == 0:
                invalid_files.append((path, "File is empty"))
            else:
                valid_files.append(path)
        elif ext in {'.docx', '.doc'}:
            invalid_files.append((
                path,
                "Word docs not directly supported. Convert to PDF or use .txt output"
            ))
            warnings.append(
                "Tip: Use the _Company_Overview.txt file from output/ instead of .docx"
            )
        elif ext in {'.xlsx', '.xls'}:
            invalid_files.append((path, "Excel files not supported. Export to CSV"))
        else:
            invalid_files.append((path, f"Unsupported file type: {ext}"))

    return FileValidationResult(
        valid_files=tuple(valid_files),
        invalid_files=tuple(invalid_files),
        warnings=tuple(warnings)
    )


def list_section_files(folder_path: str | Path) -> list[Path]:
    """
    List all .txt section files in a working folder.

    Args:
        folder_path: Path to working folder

    Returns:
        List of paths to .txt files, sorted alphabetically
    """
    folder_path = Path(folder_path) if isinstance(folder_path, str) else folder_path

    if not folder_path.is_dir():
        return []

    return sorted(folder_path.glob("*.txt"))


def get_section_content(folder_path: str | Path, section_key: str) -> str | None:
    """
    Read content of a specific section file.

    Args:
        folder_path: Path to working folder
        section_key: Section identifier

    Returns:
        Content of the section file, or None if not found
    """
    folder_path = Path(folder_path) if isinstance(folder_path, str) else folder_path
    filepath = folder_path / f"{section_key}.txt"

    if not filepath.exists():
        return None

    try:
        return filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read section {section_key}: {e}")
        return None
