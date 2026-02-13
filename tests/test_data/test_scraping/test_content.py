"""Tests for content extraction - Property 7: Text Extraction Cleanliness."""

import pytest
from pathlib import Path

from primr.data.scraping.content import (
    detect_content_type,
    extract_clean_text,
    extract_text_from_pdf,
    extract_text_from_pdf_via_llm,
    extract_main_content,
    get_page_title,
    get_meta_description,
)


# Path to fixtures
FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "html"


def load_fixture(name: str) -> bytes:
    """Load HTML fixture file."""
    return (FIXTURES_DIR / name).read_bytes()


class TestDetectContentType:
    """Tests for detect_content_type function."""
    
    def test_detects_html_from_header(self):
        """Should detect HTML from Content-Type header."""
        assert detect_content_type(b"", "text/html") == "html"
        assert detect_content_type(b"", "text/html; charset=utf-8") == "html"
    
    def test_detects_pdf_from_header(self):
        """Should detect PDF from Content-Type header."""
        assert detect_content_type(b"", "application/pdf") == "pdf"
    
    def test_detects_json_from_header(self):
        """Should detect JSON from Content-Type header."""
        assert detect_content_type(b"", "application/json") == "json"
    
    def test_detects_html_from_content(self):
        """Should detect HTML from content."""
        html = b"<!DOCTYPE html><html><body>Test</body></html>"
        assert detect_content_type(html) == "html"
    
    def test_detects_pdf_from_magic_bytes(self):
        """Should detect PDF from magic bytes."""
        pdf = b"%PDF-1.4 some content"
        assert detect_content_type(pdf) == "pdf"
    
    def test_detects_json_from_content(self):
        """Should detect JSON from content."""
        json_content = b'{"key": "value"}'
        assert detect_content_type(json_content) == "json"
    
    def test_unknown_content(self):
        """Should return unknown for unrecognized content."""
        assert detect_content_type(b"random binary data") == "unknown"


class TestExtractCleanText:
    """Tests for extract_clean_text function."""
    
    def test_removes_script_tags(self):
        """Should remove script tags and content."""
        html = b"<html><body><script>alert('test');</script><p>Content</p></body></html>"
        text = extract_clean_text(html)
        
        assert "alert" not in text
        assert "Content" in text
    
    def test_removes_style_tags(self):
        """Should remove style tags and content."""
        html = b"<html><body><style>.class { color: red; }</style><p>Content</p></body></html>"
        text = extract_clean_text(html)
        
        assert "color" not in text
        assert "Content" in text
    
    def test_removes_noscript_tags(self):
        """Should remove noscript tags and content."""
        html = b"<html><body><noscript>Enable JS</noscript><p>Content</p></body></html>"
        text = extract_clean_text(html)
        
        assert "Enable JS" not in text
        assert "Content" in text
    
    def test_conservative_mode_keeps_nav(self):
        """Conservative mode should keep nav content."""
        html = b"<html><body><nav>Home About</nav><p>Content</p></body></html>"
        text = extract_clean_text(html, mode="conservative")
        
        assert "Home" in text
        assert "Content" in text
    
    def test_aggressive_mode_removes_nav(self):
        """Aggressive mode should remove nav content."""
        html = b"<html><body><nav>Home About</nav><p>Content</p></body></html>"
        text = extract_clean_text(html, mode="aggressive")
        
        assert "Home" not in text
        assert "Content" in text
    
    def test_aggressive_mode_removes_header_footer(self):
        """Aggressive mode should remove header and footer."""
        html = b"""
        <html><body>
        <header>Site Header</header>
        <main><p>Main Content</p></main>
        <footer>Site Footer</footer>
        </body></html>
        """
        text = extract_clean_text(html, mode="aggressive")
        
        assert "Site Header" not in text
        assert "Site Footer" not in text
        assert "Main Content" in text
    
    def test_deduplicates_consecutive_lines(self):
        """Should deduplicate consecutive identical lines."""
        html = b"<html><body><p>Same</p><p>Same</p><p>Different</p><p>Same</p></body></html>"
        text = extract_clean_text(html)
        
        lines = [line for line in text.split("\n") if line.strip()]
        # Should have: Same, Different, Same (not Same, Same, Different, Same)
        assert lines.count("Same") == 2  # First and last
    
    def test_preserves_paragraph_structure(self):
        """Should preserve paragraph structure with newlines."""
        html = b"<html><body><p>Para 1</p><p>Para 2</p><p>Para 3</p></body></html>"
        text = extract_clean_text(html)
        
        assert "Para 1" in text
        assert "Para 2" in text
        assert "Para 3" in text
        # Should have newlines between paragraphs
        assert "\n" in text
    
    def test_decodes_html_entities(self):
        """Should decode HTML entities."""
        html = b"<html><body><p>Tom &amp; Jerry &copy; 2025</p></body></html>"
        text = extract_clean_text(html)
        
        assert "Tom & Jerry" in text
        assert "©" in text
    
    def test_handles_empty_input(self):
        """Should handle empty input."""
        assert extract_clean_text(b"") == ""
        assert extract_clean_text(None) == ""
    
    def test_extracts_from_normal_page(self):
        """Should extract text from normal content page."""
        html = load_fixture("normal_content.html")
        text = extract_clean_text(html)
        
        assert "Acme Corporation" in text
        assert "About" in text or "Leadership" in text
        assert len(text) > 500


class TestExtractMainContent:
    """Tests for extract_main_content function."""
    
    def test_extracts_main_tag(self):
        """Should extract content from main tag."""
        html = b"""
        <html><body>
        <header>Header</header>
        <main><p>Main content here</p></main>
        <footer>Footer</footer>
        </body></html>
        """
        text = extract_main_content(html)
        
        assert "Main content here" in text
        # Header/footer may or may not be included depending on fallback
    
    def test_extracts_article_tag(self):
        """Should extract content from article tag."""
        html = b"""
        <html><body>
        <nav>Navigation</nav>
        <article><p>Article content</p></article>
        <aside>Sidebar</aside>
        </body></html>
        """
        text = extract_main_content(html)
        
        assert "Article content" in text
    
    def test_falls_back_to_aggressive(self):
        """Should fall back to aggressive extraction if no main/article."""
        html = b"""
        <html><body>
        <div><p>Some content</p></div>
        </body></html>
        """
        text = extract_main_content(html)

        assert "Some content" in text

    def test_returns_empty_for_binary_content(self):
        """Should return empty string for binary/non-HTML content."""
        # Simulate the exact crash scenario: binary garbage with control chars
        binary_data = b'\x00\x01\x02\x03\x04\x05\x06\x07\x08' * 50
        assert extract_main_content(binary_data) == ""

    def test_returns_empty_for_mixed_binary_html(self):
        """Should return empty for content that looks like garbled binary."""
        # This mimics the actual error: bytes that decode but have high control char ratio
        garbled = bytes(range(0, 128)) * 5
        assert extract_main_content(garbled) == ""

    def test_handles_valid_html_with_some_control_chars(self):
        """Valid HTML with occasional whitespace control chars should still work."""
        html = b"<html><body><main><p>Real content here</p></main></body></html>"
        text = extract_main_content(html)
        assert "Real content here" in text


class TestExtractCleanTextBinary:
    """Tests that extract_clean_text handles binary content gracefully."""

    def test_returns_empty_for_binary_content(self):
        """Should return empty string for binary data."""
        binary_data = b'\x00\x01\x02\x03\x04\x05' * 100
        assert extract_clean_text(binary_data) == ""


class TestExtractTextFromPdfViaLlm:
    """Tests for extract_text_from_pdf_via_llm function."""

    def test_returns_none_for_empty_input(self):
        """Should return None for empty bytes."""
        assert extract_text_from_pdf_via_llm(b"") is None
        assert extract_text_from_pdf_via_llm(None) is None

    def test_falls_back_to_pymupdf_for_oversized_pdf(self):
        """Should fall back to PyMuPDF for PDFs over 20MB."""
        # Create fake oversized content (won't parse as valid PDF)
        huge = b"%PDF" + b"\x00" * (21 * 1024 * 1024)
        # Should not crash - returns None since it's not a valid PDF
        result = extract_text_from_pdf_via_llm(huge)
        assert result is None

    def test_falls_back_when_no_api_key(self):
        """Should fall back to PyMuPDF when Gemini key is unavailable."""
        # With invalid PDF bytes, both paths return None
        result = extract_text_from_pdf_via_llm(b"not a real pdf")
        assert result is None


class TestGetPageTitle:
    """Tests for get_page_title function."""
    
    def test_extracts_title(self):
        """Should extract page title."""
        html = b"<html><head><title>Page Title</title></head><body></body></html>"
        
        assert get_page_title(html) == "Page Title"
    
    def test_handles_missing_title(self):
        """Should return None for missing title."""
        html = b"<html><head></head><body></body></html>"
        
        assert get_page_title(html) is None
    
    def test_decodes_entities_in_title(self):
        """Should decode HTML entities in title."""
        html = b"<html><head><title>Tom &amp; Jerry</title></head></html>"
        
        assert get_page_title(html) == "Tom & Jerry"
    
    def test_extracts_from_fixture(self):
        """Should extract title from fixture."""
        html = load_fixture("normal_content.html")
        title = get_page_title(html)
        
        assert title is not None
        assert "Acme" in title


class TestGetMetaDescription:
    """Tests for get_meta_description function."""
    
    def test_extracts_description(self):
        """Should extract meta description."""
        html = b'<html><head><meta name="description" content="Page description"></head></html>'
        
        assert get_meta_description(html) == "Page description"
    
    def test_handles_missing_description(self):
        """Should return None for missing description."""
        html = b"<html><head></head><body></body></html>"
        
        assert get_meta_description(html) is None
    
    def test_extracts_from_fixture(self):
        """Should extract description from fixture."""
        html = load_fixture("normal_content.html")
        desc = get_meta_description(html)
        
        assert desc is not None
        assert len(desc) > 10


class TestOperatesOnRawBytes:
    """Tests that extraction operates on raw bytes (not pre-parsed)."""
    
    def test_accepts_bytes_input(self):
        """Should accept bytes input."""
        html = b"<html><body><p>Content</p></body></html>"
        text = extract_clean_text(html)
        
        assert isinstance(text, str)
        assert "Content" in text
    
    def test_handles_utf8_encoding(self):
        """Should handle UTF-8 encoded content."""
        html = "<html><body><p>Café résumé naïve</p></body></html>".encode("utf-8")
        text = extract_clean_text(html)
        
        assert "Café" in text
        assert "résumé" in text
    
    def test_handles_encoding_errors(self):
        """Should handle encoding errors gracefully."""
        # Invalid UTF-8 sequence
        html = b"<html><body><p>Content \xff\xfe</p></body></html>"
        text = extract_clean_text(html)
        
        # Should not crash, should extract what it can
        assert "Content" in text
