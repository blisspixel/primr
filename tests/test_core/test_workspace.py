"""
Unit tests for the workspace module.

Tests working folder creation, consolidation, and file validation.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestWorkspaceConfig:
    """Tests for WorkspaceConfig dataclass."""

    def test_folder_name_from_company_name(self):
        """Folder name derived from company name with spaces replaced."""
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(
            base_dir=Path("/tmp"),
            company_name="Acme Corp",
            website=None
        )

        assert config.folder_name == "Acme_Corp"

    def test_folder_name_from_website(self):
        """Folder name derived from website when no company name."""
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(
            base_dir=Path("/tmp"),
            company_name="",
            website="https://www.example.com"
        )

        assert config.folder_name == "example_com"

    def test_folder_name_default(self):
        """Default folder name when neither company nor website provided."""
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(
            base_dir=Path("/tmp"),
            company_name="",
            website=None
        )

        assert config.folder_name == "Unknown_Company"

    def test_folder_path_combines_base_and_name(self):
        """Folder path combines base_dir and folder_name."""
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(
            base_dir=Path("/tmp/working"),
            company_name="Acme Corp",
            website=None
        )

        assert config.folder_path == Path("/tmp/working/Acme_Corp")


class TestCreateWorkingFolder:
    """Tests for create_working_folder function."""

    def test_creates_folder_with_company_name(self):
        """Creates folder using company name."""
        from primr.core.workspace import create_working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override WORKING_DIR
            import primr.core.workspace as ws
            original_dir = ws.WORKING_DIR
            ws.WORKING_DIR = tmpdir

            try:
                folder = create_working_folder("Test Company", None)
                assert os.path.exists(folder)
                assert "Test_Company" in folder
            finally:
                ws.WORKING_DIR = original_dir

    def test_creates_folder_from_website_when_no_name(self):
        """Creates folder from website domain when no company name."""
        from primr.core.workspace import create_working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            import primr.core.workspace as ws
            original_dir = ws.WORKING_DIR
            ws.WORKING_DIR = tmpdir

            try:
                folder = create_working_folder(None, "https://www.example.com")
                assert os.path.exists(folder)
                assert "example_com" in folder
            finally:
                ws.WORKING_DIR = original_dir


class TestWorkingFolderContextManager:
    """Tests for working_folder context manager."""

    def test_creates_folder_on_entry(self):
        """Context manager creates folder on entry."""
        from primr.core.workspace import working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            import primr.core.workspace as ws
            original_dir = ws.WORKING_DIR
            ws.WORKING_DIR = tmpdir

            try:
                with working_folder("Test", None) as folder:
                    assert folder.exists()
                    assert folder.is_dir()
            finally:
                ws.WORKING_DIR = original_dir

    def test_cleanup_on_exit_removes_folder(self):
        """Context manager removes folder when cleanup_on_exit=True."""
        from primr.core.workspace import working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            import primr.core.workspace as ws
            original_dir = ws.WORKING_DIR
            ws.WORKING_DIR = tmpdir

            try:
                with working_folder("Test", None, cleanup_on_exit=True) as folder:
                    folder_path = folder
                    assert folder.exists()

                # After context, folder should be removed
                assert not folder_path.exists()
            finally:
                ws.WORKING_DIR = original_dir


class TestSaveSectionOutput:
    """Tests for save_section_output function."""

    def test_saves_content_to_file(self):
        """Saves content to section file."""
        from primr.core.workspace import save_section_output

        with tempfile.TemporaryDirectory() as tmpdir:
            result = save_section_output(tmpdir, "industry", "Technology")

            assert result.exists()
            assert result.name == "industry.txt"
            assert result.read_text() == "Technology"

    def test_creates_parent_directories(self):
        """Creates parent directories if needed."""
        from primr.core.workspace import save_section_output

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = Path(tmpdir) / "nested" / "folder"
            result = save_section_output(nested_path, "test", "content")

            assert result.exists()


class TestConsolidateWorkingFolder:
    """Tests for consolidate_working_folder function."""

    def test_consolidates_txt_files(self):
        """Consolidates all .txt files into single document."""
        from primr.core.workspace import consolidate_working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "Test_Company"
            folder.mkdir()

            # Create some section files
            (folder / "industry.txt").write_text("Technology sector")
            (folder / "overview.txt").write_text("Company overview here")

            result = consolidate_working_folder(folder)

            assert os.path.exists(result)
            content = Path(result).read_text()
            assert "Technology sector" in content
            assert "Company overview here" in content
            assert "Test Company" in content  # Company name from folder

    def test_raises_on_missing_folder(self):
        """Raises ValueError for non-existent folder."""
        from primr.core.workspace import consolidate_working_folder

        with pytest.raises(ValueError, match="not found"):
            consolidate_working_folder("/nonexistent/folder")

    def test_raises_on_empty_folder(self):
        """Raises ValueError when folder has no research files (.txt or .md)."""
        from primr.core.workspace import consolidate_working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="No research files"):
                consolidate_working_folder(tmpdir)


class TestValidateContextFiles:
    """Tests for validate_context_files function."""

    def test_valid_txt_file(self):
        """Accepts valid .txt files."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.txt"
            filepath.write_text("test content")

            result = validate_context_files([str(filepath)])
            assert len(result.valid_files) == 1
            assert len(result.invalid_files) == 0

    def test_valid_pdf_file(self):
        """Accepts valid .pdf files."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.pdf"
            filepath.write_bytes(b"fake pdf content")

            result = validate_context_files([str(filepath)])
            assert len(result.valid_files) == 1

    def test_rejects_missing_file(self):
        """Rejects files that don't exist."""
        from primr.core.workspace import validate_context_files

        result = validate_context_files(["/nonexistent/file.txt"])

        assert len(result.valid_files) == 0
        assert len(result.invalid_files) == 1
        assert "not found" in result.invalid_files[0][1].lower()

    def test_rejects_empty_file(self):
        """Rejects empty files."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "empty.txt"
            filepath.touch()  # Create empty file

            result = validate_context_files([str(filepath)])
            assert len(result.valid_files) == 0
            assert len(result.invalid_files) == 1
            assert "empty" in result.invalid_files[0][1].lower()

    def test_rejects_docx_with_warning(self):
        """Rejects .docx files with helpful warning."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.docx"
            filepath.write_bytes(b"fake docx")

            result = validate_context_files([str(filepath)])
            assert len(result.valid_files) == 0
            assert len(result.invalid_files) == 1
            assert len(result.warnings) > 0
            assert "Word" in result.invalid_files[0][1]

    def test_all_valid_property(self):
        """all_valid property returns True when no invalid files."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.txt"
            filepath.write_text("content")

            result = validate_context_files([str(filepath)])
            assert result.all_valid is True

    def test_all_valid_false_when_invalid(self):
        """all_valid property returns False when there are invalid files."""
        from primr.core.workspace import validate_context_files

        result = validate_context_files(["/nonexistent.txt"])
        assert result.all_valid is False


class TestListSectionFiles:
    """Tests for list_section_files function."""

    def test_lists_txt_files(self):
        """Lists all .txt files in folder."""
        from primr.core.workspace import list_section_files

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.txt").write_text("a")
            (Path(tmpdir) / "b.txt").write_text("b")
            (Path(tmpdir) / "c.pdf").write_text("c")  # Should be excluded

            result = list_section_files(tmpdir)

            assert len(result) == 2
            assert all(f.suffix == ".txt" for f in result)

    def test_returns_sorted_list(self):
        """Returns files sorted alphabetically."""
        from primr.core.workspace import list_section_files

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "z.txt").write_text("z")
            (Path(tmpdir) / "a.txt").write_text("a")
            (Path(tmpdir) / "m.txt").write_text("m")

            result = list_section_files(tmpdir)

            names = [f.name for f in result]
            assert names == ["a.txt", "m.txt", "z.txt"]

    def test_returns_empty_for_missing_folder(self):
        """Returns empty list for non-existent folder."""
        from primr.core.workspace import list_section_files

        result = list_section_files("/nonexistent/folder")
        assert result == []


class TestGetSectionContent:
    """Tests for get_section_content function."""

    def test_reads_section_content(self):
        """Reads content from section file."""
        from primr.core.workspace import get_section_content

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "industry.txt").write_text("Technology")

            result = get_section_content(tmpdir, "industry")
            assert result == "Technology"

    def test_returns_none_for_missing_section(self):
        """Returns None when section file doesn't exist."""
        from primr.core.workspace import get_section_content

        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_section_content(tmpdir, "nonexistent")
            assert result is None
