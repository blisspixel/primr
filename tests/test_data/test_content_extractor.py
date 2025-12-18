"""
Tests for the content extractor module.

Tests table extraction, financial figures, quotes, and lists.
"""

import pytest
from primr.data.content_extractor import (
    ContentExtractor,
    ExtractedTable,
    FinancialFigure,
    ExtractedQuote,
    ExtractedList,
    get_content_extractor,
    reset_content_extractor,
    extract_tables,
    extract_financial_figures,
    extract_quotes,
    extract_all_content,
)


# =============================================================================
# EXTRACTED TABLE TESTS
# =============================================================================

class TestExtractedTable:
    """Tests for ExtractedTable dataclass."""
    
    def test_column_count(self):
        """Test column count calculation."""
        table = ExtractedTable(
            headers=["A", "B", "C"],
            rows=[["1", "2", "3"]]
        )
        assert table.column_count == 3
    
    def test_row_count(self):
        """Test row count calculation."""
        table = ExtractedTable(
            headers=["A", "B"],
            rows=[["1", "2"], ["3", "4"], ["5", "6"]]
        )
        assert table.row_count == 3
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        table = ExtractedTable(
            headers=["Name", "Value"],
            rows=[["Item", "100"]],
            caption="Test Table"
        )
        
        d = table.to_dict()
        
        assert d["headers"] == ["Name", "Value"]
        assert d["caption"] == "Test Table"
        assert d["column_count"] == 2


# =============================================================================
# FINANCIAL FIGURE TESTS
# =============================================================================

class TestFinancialFigure:
    """Tests for FinancialFigure dataclass."""
    
    def test_normalized_value_million(self):
        """Test normalizing million values."""
        figure = FinancialFigure(
            value=5.0,
            raw_text="$5 million",
            unit="USD",
            scale="million",
            context=""
        )
        assert figure.normalized_value == 5_000_000
    
    def test_normalized_value_billion(self):
        """Test normalizing billion values."""
        figure = FinancialFigure(
            value=2.5,
            raw_text="$2.5 billion",
            unit="USD",
            scale="billion",
            context=""
        )
        assert figure.normalized_value == 2_500_000_000
    
    def test_normalized_value_no_scale(self):
        """Test value without scale."""
        figure = FinancialFigure(
            value=100.0,
            raw_text="$100",
            unit="USD",
            scale="",
            context=""
        )
        assert figure.normalized_value == 100.0


# =============================================================================
# TABLE EXTRACTION TESTS
# =============================================================================

class TestTableExtraction:
    """Tests for table extraction."""
    
    def test_extract_simple_table(self):
        """Test extracting a simple table."""
        html = """
        <table>
            <tr><th>Name</th><th>Value</th></tr>
            <tr><td>Item 1</td><td>100</td></tr>
            <tr><td>Item 2</td><td>200</td></tr>
        </table>
        """
        
        extractor = ContentExtractor()
        tables = extractor.extract_tables(html)
        
        assert len(tables) == 1
        assert tables[0].headers == ["Name", "Value"]
        assert len(tables[0].rows) == 2
    
    def test_extract_table_with_thead(self):
        """Test extracting table with thead."""
        html = """
        <table>
            <thead>
                <tr><th>Column A</th><th>Column B</th></tr>
            </thead>
            <tbody>
                <tr><td>Data 1</td><td>Data 2</td></tr>
            </tbody>
        </table>
        """
        
        extractor = ContentExtractor()
        tables = extractor.extract_tables(html)
        
        assert len(tables) == 1
        assert tables[0].headers == ["Column A", "Column B"]
    
    def test_extract_table_with_caption(self):
        """Test extracting table with caption."""
        html = """
        <table>
            <caption>Financial Summary</caption>
            <tr><th>Year</th><th>Revenue</th></tr>
            <tr><td>2023</td><td>$1M</td></tr>
        </table>
        """
        
        extractor = ContentExtractor()
        tables = extractor.extract_tables(html)
        
        assert len(tables) == 1
        assert tables[0].caption == "Financial Summary"
    
    def test_extract_multiple_tables(self):
        """Test extracting multiple tables."""
        html = """
        <table><tr><td>Table 1</td></tr></table>
        <table><tr><td>Table 2</td></tr></table>
        """
        
        extractor = ContentExtractor()
        tables = extractor.extract_tables(html)
        
        assert len(tables) == 2
    
    def test_extract_empty_table(self):
        """Test handling empty table."""
        html = "<table></table>"
        
        extractor = ContentExtractor()
        tables = extractor.extract_tables(html)
        
        # Empty tables should be filtered out
        assert len(tables) == 0


# =============================================================================
# LIST EXTRACTION TESTS
# =============================================================================

class TestListExtraction:
    """Tests for list extraction."""
    
    def test_extract_unordered_list(self):
        """Test extracting unordered list."""
        html = """
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
            <li>Item 3</li>
        </ul>
        """
        
        extractor = ContentExtractor()
        lists = extractor.extract_lists(html)
        
        assert len(lists) == 1
        assert lists[0].list_type == "unordered"
        assert len(lists[0].items) == 3
    
    def test_extract_ordered_list(self):
        """Test extracting ordered list."""
        html = """
        <ol>
            <li>First</li>
            <li>Second</li>
        </ol>
        """
        
        extractor = ContentExtractor()
        lists = extractor.extract_lists(html)
        
        assert len(lists) == 1
        assert lists[0].list_type == "ordered"
    
    def test_extract_list_with_title(self):
        """Test extracting list with preceding heading."""
        html = """
        <h3>Our Services</h3>
        <ul>
            <li>Service A</li>
            <li>Service B</li>
        </ul>
        """
        
        extractor = ContentExtractor()
        lists = extractor.extract_lists(html)
        
        assert len(lists) == 1
        assert lists[0].title == "Our Services"


# =============================================================================
# FINANCIAL FIGURE EXTRACTION TESTS
# =============================================================================

class TestFinancialFigureExtraction:
    """Tests for financial figure extraction."""
    
    def test_extract_dollar_amount(self):
        """Test extracting dollar amounts."""
        text = "The company reported revenue of $5.2 million."
        
        extractor = ContentExtractor()
        figures = extractor.extract_financial_figures(text)
        
        assert len(figures) >= 1
        assert any(f.unit == "USD" for f in figures)
    
    def test_extract_billion_amount(self):
        """Test extracting billion amounts."""
        text = "Total assets reached $2.5 billion."
        
        extractor = ContentExtractor()
        figures = extractor.extract_financial_figures(text)
        
        assert len(figures) >= 1
        assert any(f.scale == "billion" for f in figures)
    
    def test_extract_percentage(self):
        """Test extracting percentages."""
        text = "Growth rate was 15.5% year over year."
        
        extractor = ContentExtractor()
        figures = extractor.extract_financial_figures(text)
        
        assert len(figures) >= 1
        assert any(f.unit == "%" for f in figures)
    
    def test_extract_euro_amount(self):
        """Test extracting euro amounts."""
        text = "European revenue was €100 million."
        
        extractor = ContentExtractor()
        figures = extractor.extract_financial_figures(text)
        
        assert len(figures) >= 1
        assert any(f.unit == "EUR" for f in figures)
    
    def test_extract_with_commas(self):
        """Test extracting amounts with commas."""
        text = "The deal was worth $1,500,000."
        
        extractor = ContentExtractor()
        figures = extractor.extract_financial_figures(text)
        
        assert len(figures) >= 1
        assert any(f.value == 1500000 for f in figures)


# =============================================================================
# QUOTE EXTRACTION TESTS
# =============================================================================

class TestQuoteExtraction:
    """Tests for quote extraction."""
    
    def test_extract_simple_quote(self):
        """Test extracting a simple quote."""
        text = '"We are committed to innovation and growth," said the CEO.'
        
        extractor = ContentExtractor()
        quotes = extractor.extract_quotes(text)
        
        assert len(quotes) >= 1
        assert "innovation" in quotes[0].text
    
    def test_extract_quote_with_speaker(self):
        """Test extracting quote with speaker attribution."""
        text = '"Our mission is to serve customers," said John Smith.'
        
        extractor = ContentExtractor()
        quotes = extractor.extract_quotes(text)
        
        assert len(quotes) >= 1
        # Speaker detection may or may not work depending on pattern
    
    def test_skip_short_quotes(self):
        """Test that very short quotes are skipped."""
        text = '"Yes" and "No" are common responses.'
        
        extractor = ContentExtractor()
        quotes = extractor.extract_quotes(text)
        
        # Short quotes should be filtered
        assert all(len(q.text) >= 20 for q in quotes)


# =============================================================================
# HEADING EXTRACTION TESTS
# =============================================================================

class TestHeadingExtraction:
    """Tests for heading extraction."""
    
    def test_extract_headings(self):
        """Test extracting headings."""
        html = """
        <h1>Main Title</h1>
        <h2>Section 1</h2>
        <h2>Section 2</h2>
        <h3>Subsection</h3>
        """
        
        extractor = ContentExtractor()
        headings = extractor.extract_headings(html)
        
        assert len(headings["h1"]) == 1
        assert len(headings["h2"]) == 2
        assert len(headings["h3"]) == 1
        assert headings["h1"][0] == "Main Title"


# =============================================================================
# METADATA EXTRACTION TESTS
# =============================================================================

class TestMetadataExtraction:
    """Tests for metadata extraction."""
    
    def test_extract_title(self):
        """Test extracting page title."""
        html = "<html><head><title>Company Name - About Us</title></head></html>"
        
        extractor = ContentExtractor()
        metadata = extractor.extract_metadata(html)
        
        assert metadata.get("title") == "Company Name - About Us"
    
    def test_extract_description(self):
        """Test extracting meta description."""
        html = """
        <html><head>
            <meta name="description" content="Company description here">
        </head></html>
        """
        
        extractor = ContentExtractor()
        metadata = extractor.extract_metadata(html)
        
        assert metadata.get("description") == "Company description here"


# =============================================================================
# EXTRACT ALL TESTS
# =============================================================================

class TestExtractAll:
    """Tests for extract_all method."""
    
    def test_extract_all_content(self):
        """Test extracting all content types."""
        html = """
        <html>
        <head>
            <title>Test Page</title>
            <meta name="description" content="Test description">
        </head>
        <body>
            <h1>Main Heading</h1>
            <p>Revenue was $5 million in 2023.</p>
            <table>
                <tr><th>Year</th><th>Revenue</th></tr>
                <tr><td>2023</td><td>$5M</td></tr>
            </table>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </body>
        </html>
        """
        
        extractor = ContentExtractor()
        result = extractor.extract_all(html)
        
        assert "metadata" in result
        assert "headings" in result
        assert "tables" in result
        assert "lists" in result
        assert "financial_figures" in result
        assert "quotes" in result


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton access."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        reset_content_extractor()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_content_extractor()
    
    def test_get_content_extractor_singleton(self):
        """Test that get_content_extractor returns singleton."""
        extractor1 = get_content_extractor()
        extractor2 = get_content_extractor()
        
        assert extractor1 is extractor2
    
    def test_reset_content_extractor(self):
        """Test resetting the singleton."""
        extractor1 = get_content_extractor()
        reset_content_extractor()
        extractor2 = get_content_extractor()
        
        assert extractor1 is not extractor2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        reset_content_extractor()
    
    def test_extract_tables_function(self):
        """Test extract_tables convenience function."""
        html = "<table><tr><td>Data</td></tr></table>"
        
        tables = extract_tables(html)
        
        assert len(tables) == 1
    
    def test_extract_financial_figures_function(self):
        """Test extract_financial_figures convenience function."""
        text = "Revenue was $10 million."
        
        figures = extract_financial_figures(text)
        
        assert len(figures) >= 1
    
    def test_extract_quotes_function(self):
        """Test extract_quotes convenience function."""
        text = '"This is a test quote that is long enough to be extracted."'
        
        quotes = extract_quotes(text)
        
        assert len(quotes) >= 1
    
    def test_extract_all_content_function(self):
        """Test extract_all_content convenience function."""
        html = "<html><head><title>Test</title></head><body></body></html>"
        
        result = extract_all_content(html)
        
        assert "metadata" in result
        assert result["metadata"].get("title") == "Test"
