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
    folder = create_working_folder("Acme Corp", "https://acme.example")

    # Save section content
    save_section_output(folder, "industry", "Industrial products and manufacturing")

    # Consolidate for context
    context_file = consolidate_working_folder(folder)
"""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from primr.config.config import WORKING_DIR
from primr.utils.logging_config import get_logger
from primr.utils.url_helpers import normalized_hostname
from primr.utils.validators import company_path_component, sanitize_for_filename

logger = get_logger("workspace")


def derive_working_folder_name(company_name: str | None, website: str | None = None) -> str:
    """Return one portable working-directory component for a research target."""
    if company_name:
        return company_path_component(company_name)
    if website:
        hostname = normalized_hostname(website, strip_www=True)
        if hostname:
            domain = hostname.replace(".", "_")
            return sanitize_for_filename(domain)
    return "Unknown_Company"


# =============================================================================
# CONSTANTS
# =============================================================================

# Supported file types for Deep Research File Search
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".txt", ".pdf", ".md", ".json", ".csv"})


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
        return derive_working_folder_name(self.company_name, self.website)

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


def create_working_folder(
    company_name: str | None, website: str | None, use_run_id: bool = True
) -> str:
    """
    Create working folder for research artifacts.

    Creates the folder if it does not exist. When use_run_id is True (default),
    creates a timestamped subfolder for each run to avoid mixing old/new data.

    Args:
        company_name: Name of the company
        website: Company website URL
        use_run_id: If True, create timestamped subfolder (default: True)

    Returns:
        Path to the created folder as string (for backward compatibility)
    """
    from datetime import datetime

    folder_name = derive_working_folder_name(company_name, website)

    if use_run_id:
        # Create timestamped run folder: Company_Name/2026-01-09_0845
        run_id = datetime.now().strftime("%Y-%m-%d_%H%M")
        folder_path = os.path.join(WORKING_DIR, folder_name, run_id)
    else:
        folder_path = os.path.join(WORKING_DIR, folder_name)

    # Defense-in-depth: company_name is sanitized at the input boundary
    # (validate_company_name rejects path separators and traversal), but this
    # is the sink that creates directories. Refuse anything that resolves
    # outside WORKING_DIR so a name that bypassed validation can't escape.
    base = Path(WORKING_DIR).resolve()
    resolved = Path(folder_path).resolve()
    if base not in resolved.parents:
        raise ValueError(
            f"Refusing to create a working folder outside WORKING_DIR for "
            f"company name {company_name!r}"
        )

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
    cleanup_on_exit: bool = False,
    use_run_id: bool = True,
) -> Iterator[Path]:
    """
    Context manager for working folder operations.

    Creates folder on entry, optionally cleans up on exit.

    Args:
        company_name: Name of the company
        website: Company website URL
        cleanup_on_exit: If True, remove folder contents on exit
        use_run_id: If True, create timestamped subfolder (default: True)

    Yields:
        Path to the working folder
    """
    folder_path = Path(create_working_folder(company_name, website, use_run_id=use_run_id))
    try:
        yield folder_path
    finally:
        if cleanup_on_exit:
            import shutil

            try:
                shutil.rmtree(folder_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup working folder: {e}")


def _read_file_content(file_path: Path) -> tuple[str, int]:
    """Read file content, return (content, size) or ("", 0) on error."""
    try:
        content = file_path.read_text(encoding="utf-8").strip()
        return content, len(content)
    except Exception as e:
        logger.warning(f"Failed to read {file_path}: {e}")
        return "", 0


def _append_primary_report(lines: list[str], deep_research_file: Path, total_size: int) -> int:
    """Append the primary strategic report to the consolidated context."""
    content, size = _read_file_content(deep_research_file)
    total_size += size
    if content:
        lines.extend(
            [
                "# STRATEGIC COMPANY REPORT (PRIMARY SOURCE)",
                "",
                "This comprehensive analysis is your PRIMARY source. Read it thoroughly.",
                "Every AI recommendation should connect to insights from this report.",
                "",
                content,
                "",
                "---",
                "",
            ]
        )
        logger.info(f"Included strategic report ({size:,} chars)")
    return total_size


def consolidate_working_folder(folder_path: str | Path) -> str:
    """
    Consolidate research files from a working folder into a single context file.

    Prioritizes the strategic report (deep_research_output.md) as the primary source,
    then includes key supporting files. Avoids redundancy by not including all 20+
    section files when the strategic report already synthesizes them.

    Args:
        folder_path: Path to working folder (e.g., working/Parts_Town)

    Returns:
        Path to the consolidated temporary file

    Raises:
        ValueError: If folder doesn't exist or contains no research files
    """
    folder_path = Path(folder_path) if isinstance(folder_path, str) else folder_path

    if not folder_path.is_dir():
        raise ValueError(f"Working folder not found: {folder_path}")

    deep_research_file = folder_path / "deep_research_output.md"
    has_deep_research = deep_research_file.exists()

    # Key supporting files (raw data not fully captured in strategic report)
    key_files = ["scraped_website_summary.txt", "financial_overview.txt", "industry_insights.txt"]
    txt_files = [folder_path / f for f in key_files if (folder_path / f).exists()]

    # If no strategic report, fall back to all .txt files
    if not has_deep_research:
        txt_files = list(folder_path.glob("*.txt"))

    if not txt_files and not has_deep_research:
        raise ValueError(f"No research files found in {folder_path}")

    company_name = folder_path.name.replace("_", " ")
    lines = [f"# Research Context: {company_name}", f"Source: {folder_path}", ""]
    total_size = 0

    # PRIMARY: Include strategic report first
    if has_deep_research:
        total_size = _append_primary_report(lines, deep_research_file, total_size)

    # SECONDARY: Include key supporting files only
    if txt_files:
        lines.extend(["# SUPPORTING DATA", "", "---", ""])
        for txt_file in txt_files:
            content, size = _read_file_content(txt_file)
            total_size += size
            if content:
                section_name = txt_file.stem.replace("_", " ").title()
                lines.extend([f"## {section_name}", "", content, "", "---", ""])

    # Write consolidated file
    # NOTE: We must close the fd from mkstemp before opening the file by path
    fd, filepath = tempfile.mkstemp(
        suffix=".txt", prefix=f"{company_name.replace(' ', '_')}_context_"
    )
    os.close(fd)  # Close the fd - we'll open by path
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    file_count = len(txt_files) + (1 if has_deep_research else 0)
    logger.info(f"Consolidated {file_count} files ({total_size:,} chars) into {filepath}")
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
        elif ext in {".docx", ".doc"}:
            invalid_files.append(
                (path, "Word docs not directly supported. Convert to PDF or use .txt output")
            )
            warnings.append("Tip: Use the _Company_Overview.txt file from output/ instead of .docx")
        elif ext in {".xlsx", ".xls"}:
            invalid_files.append((path, "Excel files not supported. Export to CSV"))
        else:
            invalid_files.append((path, f"Unsupported file type: {ext}"))

    return FileValidationResult(
        valid_files=tuple(valid_files), invalid_files=tuple(invalid_files), warnings=tuple(warnings)
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
