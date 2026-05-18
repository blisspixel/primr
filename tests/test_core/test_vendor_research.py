"""
Unit tests for the vendor_research module.

Tests vendor research path generation, caching, and metadata.
"""

from datetime import datetime
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestVendorResearchFile:
    """Tests for VendorResearchFile dataclass."""

    def test_exists_returns_true_for_existing_file(self):
        """exists property returns True when file exists."""
        from primr.core.vendor_research import VendorResearchFile

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.txt"
            filepath.write_text("content")

            file = VendorResearchFile(
                path=filepath, vendor="azure", month="2024-01", is_manual=False
            )

            assert file.exists is True

    def test_exists_returns_false_for_missing_file(self):
        """exists property returns False when file doesn't exist."""
        from primr.core.vendor_research import VendorResearchFile

        file = VendorResearchFile(
            path=Path("/nonexistent/file.txt"), vendor="azure", month="2024-01", is_manual=False
        )

        assert file.exists is False

    def test_age_days_returns_negative_for_missing(self):
        """age_days returns -1 for non-existent file."""
        from primr.core.vendor_research import VendorResearchFile

        file = VendorResearchFile(
            path=Path("/nonexistent/file.txt"), vendor="azure", month="2024-01", is_manual=False
        )

        assert file.age_days == -1


class TestVendorResearchResult:
    """Tests for VendorResearchResult dataclass."""

    def test_paths_returns_existing_files(self):
        """paths property returns only existing file paths."""
        from primr.core.vendor_research import VendorResearchFile, VendorResearchResult

        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir) / "exists.txt"
            existing.write_text("content")

            files = (
                VendorResearchFile(existing, "azure", "2024-01", False),
                VendorResearchFile(Path("/missing.txt"), "azure", "2024-01", False),
            )

            result = VendorResearchResult(files=files, generated=False, duration_seconds=1.0)

            assert len(result.paths) == 1
            assert result.paths[0] == existing


class TestGetVendorResearchPath:
    """Tests for get_vendor_research_path function."""

    def test_uses_current_month_by_default(self):
        """Uses current month when month not specified."""
        from primr.core.vendor_research import get_vendor_research_path

        path = get_vendor_research_path("azure")
        current_month = datetime.now().strftime("%Y-%m")

        assert current_month in str(path)
        assert "azure" in str(path).lower()

    def test_uses_specified_month(self):
        """Uses specified month when provided."""
        from primr.core.vendor_research import get_vendor_research_path

        path = get_vendor_research_path("aws", "2024-06")

        assert "2024-06" in str(path)
        assert "aws" in str(path).lower()

    def test_returns_path_in_vendor_research_folder(self):
        """Returns path in vendor-research folder."""
        from primr.core.vendor_research import get_vendor_research_path

        path = get_vendor_research_path("gcp")

        assert "vendor-research" in str(path)


class TestGetManualResearchPath:
    """Tests for get_manual_research_path function."""

    def test_returns_none_for_non_azure(self):
        """Returns None for non-Azure vendors."""
        from primr.core.vendor_research import get_manual_research_path

        assert get_manual_research_path("aws") is None
        assert get_manual_research_path("gcp") is None
        assert get_manual_research_path("agnostic") is None

    @patch("primr.core.vendor_research.Path.exists")
    def test_returns_path_for_azure_when_exists(self, mock_exists):
        """Returns path for Azure when manual file exists."""
        from primr.core.vendor_research import get_manual_research_path

        mock_exists.return_value = True

        result = get_manual_research_path("azure")

        assert result is not None
        assert "ignite" in str(result).lower()


class TestIsVendorResearchCurrent:
    """Tests for is_vendor_research_current function."""

    @patch("primr.core.vendor_research.get_manual_research_path")
    def test_returns_true_for_azure_with_manual(self, mock_manual, tmp_path):
        """Returns True for Azure when manual file exists and is fresh."""
        from primr.core.vendor_research import is_vendor_research_current

        manual_file = tmp_path / "vendor-research-azure.txt"
        manual_file.write_text("content")
        mock_manual.return_value = manual_file

        assert is_vendor_research_current("azure") is True

    @patch("primr.core.vendor_research.get_manual_research_path")
    @patch("primr.core.vendor_research.get_vendor_research_path")
    def test_returns_true_when_current_month_exists(self, mock_path, mock_manual):
        """Returns True when current month's research exists."""
        from primr.core.vendor_research import is_vendor_research_current

        mock_manual.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "research.txt"
            filepath.write_text("content")
            mock_path.return_value = filepath

            assert is_vendor_research_current("aws") is True

    @patch("primr.core.vendor_research.get_manual_research_path")
    @patch("primr.core.vendor_research.get_vendor_research_path")
    def test_returns_false_when_no_research(self, mock_path, mock_manual):
        """Returns False when no research exists."""
        from primr.core.vendor_research import is_vendor_research_current

        mock_manual.return_value = None
        mock_path.return_value = Path("/nonexistent/file.txt")

        assert is_vendor_research_current("gcp") is False


class TestGetVendorMetadata:
    """Tests for _get_vendor_metadata function."""

    def test_returns_azure_metadata(self):
        """Returns correct metadata for Azure."""
        from primr.core.vendor_research import _get_vendor_metadata

        meta = _get_vendor_metadata("azure")

        assert "Microsoft Azure" in meta["name"]
        assert "Ignite" in meta["conference"]

    def test_returns_aws_metadata(self):
        """Returns correct metadata for AWS."""
        from primr.core.vendor_research import _get_vendor_metadata

        meta = _get_vendor_metadata("aws")

        assert "AWS" in meta["name"]
        assert "re:Invent" in meta["conference"]

    def test_returns_gcp_metadata(self):
        """Returns correct metadata for GCP."""
        from primr.core.vendor_research import _get_vendor_metadata

        meta = _get_vendor_metadata("gcp")

        assert "Google Cloud" in meta["name"]
        assert "Cloud Next" in meta["conference"]

    def test_returns_agnostic_metadata(self):
        """Returns correct metadata for agnostic."""
        from primr.core.vendor_research import _get_vendor_metadata

        meta = _get_vendor_metadata("agnostic")

        assert "cross-vendor" in meta["name"]

    def test_handles_unknown_vendor(self):
        """Returns agnostic metadata for unknown vendor."""
        from primr.core.vendor_research import _get_vendor_metadata

        meta = _get_vendor_metadata("unknown")

        assert "cross-vendor" in meta["name"]


class TestBuildVendorPrompt:
    """Tests for _build_vendor_prompt function."""

    def test_includes_vendor_name(self):
        """Prompt includes vendor name."""
        from primr.core.vendor_research import _build_vendor_prompt

        prompt = _build_vendor_prompt("azure")

        assert "Microsoft Azure" in prompt

    def test_includes_current_date(self):
        """Prompt includes current date."""
        from primr.core.vendor_research import _build_vendor_prompt

        prompt = _build_vendor_prompt("aws")
        current_month = datetime.now().strftime("%B %Y")

        assert current_month in prompt

    def test_includes_required_sections(self):
        """Prompt includes required section headers."""
        from primr.core.vendor_research import _build_vendor_prompt

        prompt = _build_vendor_prompt("gcp")

        assert "Executive Summary" in prompt
        assert "Foundation Models" in prompt
        assert "Security and Governance" in prompt


class TestValidateVendorResearchPreflight:
    """Tests for _validate_vendor_research_preflight function."""

    @patch("primr.config.settings.get_settings")
    def test_rejects_invalid_vendor(self, mock_settings):
        """Rejects invalid vendor name."""
        from unittest.mock import MagicMock

        from primr.core.vendor_research import _validate_vendor_research_preflight

        mock_api = MagicMock()
        mock_api.gemini_key = "fake-key"
        mock_settings.return_value.api = mock_api

        errors = _validate_vendor_research_preflight("invalid_vendor")

        assert len(errors) > 0
        assert any("Invalid vendor" in e for e in errors)

    @patch("primr.config.settings.get_settings")
    def test_rejects_missing_api_key(self, mock_settings):
        """Rejects when API key is missing."""
        from unittest.mock import MagicMock

        from primr.core.vendor_research import _validate_vendor_research_preflight

        mock_api = MagicMock()
        mock_api.gemini_key = None
        mock_settings.return_value.api = mock_api

        errors = _validate_vendor_research_preflight("azure")

        assert any("GEMINI_API_KEY" in e for e in errors)
