"""
Unit tests for the structured_research module.

Tests dataclasses, phase functions, and section research.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestScrapedData:
    """Tests for ScrapedData dataclass."""

    def test_all_content_combines_sources(self):
        """all_content combines website and external sources."""
        from primr.core.structured_research import ScrapedData

        data = ScrapedData(
            website_pages={"page1": "content1"},
            external_sources={"source1": "content2"}
        )

        assert data.all_content == {"page1": "content1", "source1": "content2"}

    def test_page_count_returns_website_pages(self):
        """page_count returns number of website pages."""
        from primr.core.structured_research import ScrapedData

        data = ScrapedData(
            website_pages={"p1": "c1", "p2": "c2", "p3": "c3"},
            external_sources={}
        )

        assert data.page_count == 3

    def test_source_count_returns_external_sources(self):
        """source_count returns number of external sources."""
        from primr.core.structured_research import ScrapedData

        data = ScrapedData(
            website_pages={},
            external_sources={"s1": "c1", "s2": "c2"}
        )

        assert data.source_count == 2

    def test_empty_data(self):
        """Handles empty data correctly."""
        from primr.core.structured_research import ScrapedData

        data = ScrapedData()

        assert data.all_content == {}
        assert data.page_count == 0
        assert data.source_count == 0


class TestAnalysisResult:
    """Tests for AnalysisResult dataclass."""

    def test_stores_all_fields(self):
        """Stores all analysis fields."""
        from primr.core.structured_research import AnalysisResult

        result = AnalysisResult(
            summarized_content="Summary here",
            industry="Technology",
            overview="Overview text"
        )

        assert result.summarized_content == "Summary here"
        assert result.industry == "Technology"
        assert result.overview == "Overview text"


class TestResearchContext:
    """Tests for ResearchContext dataclass."""

    def test_stores_all_context(self):
        """Stores all context fields."""
        from primr.core.structured_research import ResearchContext

        context = ResearchContext(
            company_name="Acme Corp",
            website="https://acme.example",
            folder_path="/tmp/Acme_Corp",
            industry="Manufacturing",
            overview="Overview",
            summarized_insights="Insights"
        )

        assert context.company_name == "Acme Corp"
        assert context.website == "https://acme.example"
        assert context.folder_path == "/tmp/Acme_Corp"
        assert context.industry == "Manufacturing"
        assert context.overview == "Overview"
        assert context.summarized_insights == "Insights"


class TestGetMetadataValue:
    """Tests for _get_metadata_value helper."""

    def test_returns_company_name(self):
        """Returns company name for Company Name section."""
        from primr.core.structured_research import _get_metadata_value

        result = _get_metadata_value("Company Name", "Acme Corp", "https://acme.example", "Manufacturing")
        assert result == "Acme Corp"

    def test_returns_website(self):
        """Returns website for Website section."""
        from primr.core.structured_research import _get_metadata_value

        result = _get_metadata_value("Website", "Acme Corp", "https://acme.example", "Manufacturing")
        assert result == "https://acme.example"

    def test_returns_na_for_missing_website(self):
        """Returns N/A when website is None."""
        from primr.core.structured_research import _get_metadata_value

        result = _get_metadata_value("Website", "Acme Corp", None, "Manufacturing")
        assert result == "N/A"

    def test_returns_industry(self):
        """Returns industry for Industry section."""
        from primr.core.structured_research import _get_metadata_value

        result = _get_metadata_value("Industry", "Acme Corp", "https://acme.example", "Manufacturing")
        assert result == "Manufacturing"

    def test_returns_na_for_unknown_section(self):
        """Returns N/A for unknown section."""
        from primr.core.structured_research import _get_metadata_value

        result = _get_metadata_value("Unknown", "Acme Corp", "https://acme.example", "Manufacturing")
        assert result == "N/A"


class TestProgressReporterProtocol:
    """Tests for ProgressReporter protocol."""

    def test_protocol_defines_methods(self):
        """Protocol defines required methods."""
        from primr.core.structured_research import ProgressReporter

        # Create a mock that implements the protocol
        mock_reporter = MagicMock(spec=ProgressReporter)

        # Should have these methods
        assert hasattr(mock_reporter, 'report')
        assert hasattr(mock_reporter, 'phase_start')
        assert hasattr(mock_reporter, 'phase_complete')


class TestCollectDataPhase:
    """Tests for _collect_data phase function."""

    @patch('primr.core.structured_research.fetch_web_content')
    @patch('primr.core.structured_research.search_web')
    @patch('primr.core.structured_research.scrape_external_sources_validated')
    def test_collects_website_pages(self, mock_scrape, mock_search, mock_fetch):
        """Collects website pages when website provided."""
        from primr.core.structured_research import _collect_data

        mock_fetch.return_value = {"page1": "content1"}
        mock_search.return_value = []

        result = _collect_data("Acme Corp", "https://acme.example", None)

        mock_fetch.assert_called_once()
        assert result.page_count == 1

    @patch('primr.core.structured_research.fetch_web_content')
    @patch('primr.core.structured_research.search_web')
    def test_skips_website_when_none(self, mock_search, mock_fetch):
        """Skips website scraping when website is None."""
        from primr.core.structured_research import _collect_data

        mock_search.return_value = []

        result = _collect_data("Acme Corp", None, None)

        mock_fetch.assert_not_called()
        assert result.page_count == 0


class TestAnalyzeContentPhase:
    """Tests for _analyze_content phase function."""

    @patch('primr.core.structured_research.summarize_scraped_content')
    @patch('primr.core.structured_research.llm')
    @patch('primr.core.structured_research.generate_initial_overview')
    def test_returns_analysis_result(self, mock_overview, mock_llm, mock_summarize):
        """Returns AnalysisResult with all fields."""
        from primr.core.structured_research import ScrapedData, _analyze_content

        mock_summarize.return_value = "Summary"
        mock_llm.return_value = "Technology"
        mock_overview.return_value = "Overview"

        scraped = ScrapedData(website_pages={"p1": "c1"})
        result = _analyze_content("Acme Corp", "https://acme.example", scraped, "/tmp", None)

        assert result.summarized_content == "Summary"
        assert result.industry == "Technology"
        assert result.overview == "Overview"

    @patch('primr.core.structured_research.summarize_scraped_content')
    @patch('primr.core.structured_research.llm')
    @patch('primr.core.structured_research.generate_initial_overview')
    def test_handles_empty_summary(self, mock_overview, mock_llm, mock_summarize):
        """Handles empty summary gracefully."""
        from primr.core.structured_research import ScrapedData, _analyze_content

        mock_summarize.return_value = "   "  # Whitespace only
        mock_llm.return_value = "Unknown"
        mock_overview.return_value = "Overview"

        scraped = ScrapedData()
        result = _analyze_content("Acme Corp", None, scraped, "/tmp", None)

        assert result.summarized_content == "No insights extracted."


class TestGenerateSectionsPhase:
    """Tests for _generate_sections phase function."""

    @patch('primr.core.structured_research.research_section')
    def test_generates_all_sections(self, mock_research):
        """Generates content for all sections."""
        from primr.core.structured_research import ResearchContext, _generate_sections

        mock_research.return_value = "Section content"

        context = ResearchContext(
            company_name="Acme Corp",
            website="https://acme.example",
            folder_path="/tmp/Acme_Corp",
            industry="Manufacturing",
            overview="Overview",
            summarized_insights="Insights"
        )

        result = _generate_sections(context, None)

        # Should have called research_section for each section
        assert mock_research.call_count > 0
        # Should return dict with section results
        assert isinstance(result, dict)


class TestResearchSection:
    """Tests for research_section function."""

    @patch('primr.core.structured_research.save_section_output')
    def test_handles_company_name_section(self, mock_save):
        """Handles Company Name section without AI."""
        from primr.core.structured_research import research_section

        result = research_section(
            "Company Name", "Acme Corp", "https://acme.example",
            "Manufacturing", "/tmp", "Overview", "Insights"
        )

        assert result == "Acme Corp"
        mock_save.assert_called_once()

    @patch('primr.core.structured_research.save_section_output')
    def test_handles_website_section(self, mock_save):
        """Handles Website section without AI."""
        from primr.core.structured_research import research_section

        result = research_section(
            "Website", "Acme Corp", "https://acme.example",
            "Manufacturing", "/tmp", "Overview", "Insights"
        )

        assert result == "https://acme.example"

    @patch('primr.core.structured_research.save_section_output')
    def test_handles_industry_section(self, mock_save):
        """Handles Industry section without AI."""
        from primr.core.structured_research import research_section

        result = research_section(
            "Industry", "Acme Corp", "https://acme.example",
            "Manufacturing", "/tmp", "Overview", "Insights"
        )

        assert result == "Manufacturing"

    def test_returns_empty_for_unknown_section(self):
        """Returns empty string for unknown section."""
        from primr.core.structured_research import research_section

        result = research_section(
            "Unknown Section XYZ", "Acme Corp", "https://acme.example",
            "Manufacturing", "/tmp", "Overview", "Insights"
        )

        assert result == ""
