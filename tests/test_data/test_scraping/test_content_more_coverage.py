"""Further coverage for content extraction helpers.

Targets branches still uncovered after test_content.py and
test_content_coverage.py: decode/parse failure paths, the XML-parser
FeatureNotFound fallback, reader-mode container selection
(``extract_main_content`` priority 1/2/3 and ``_find_content_rich_element``
link-penalty scoring), inline-text assembly in
``_extract_text_with_structure``, aggressive boilerplate stripping, and the
PyMuPDF / Gemini PDF paths. All pure logic — no network, no real browser.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.data.scraping.content import (
    _extract_text_with_structure,
    _find_content_rich_element,
    _parse_markup_document,
    detect_content_type,
    extract_clean_text,
    extract_main_content,
    extract_text_from_pdf,
    extract_text_from_pdf_via_llm,
    get_meta_description,
    get_page_title,
    reset_pdf_llm_budget,
)

# =============================================================================
# decode / parse failure paths (shared by several extractors)
# =============================================================================


class TestDecodeAndParseFailures:
    def test_extract_clean_text_high_control_char_ratio(self):
        """Mostly-binary bytes that still decode are rejected up front."""
        # >5% control chars in the first 2000-byte sample.
        blob = b"\x01\x02\x03\x04" * 500 + b"<p>text</p>"
        assert extract_clean_text(blob) == ""

    def test_extract_main_content_high_control_char_ratio(self):
        blob = b"\x01\x02\x03\x04" * 500 + b"<p>text</p>"
        assert extract_main_content(blob) == ""

    def test_extract_main_content_empty_bytes(self):
        assert extract_main_content(b"") == ""

    def test_get_page_title_none_for_empty(self):
        assert get_page_title(b"") is None

    def test_get_meta_description_none_for_empty(self):
        assert get_meta_description(b"") is None


class TestXmlParserFallback:
    def test_feature_not_found_falls_back_to_html_parser(self):
        """When lxml's XML parser is unavailable, fall back to html.parser."""
        import primr.data.scraping.content as content_mod

        xml = '<?xml version="1.0"?><urlset><url><loc>x</loc></url></urlset>'

        real_bs = content_mod.BeautifulSoup
        calls: list[str] = []

        def fake_bs(markup, parser):
            calls.append(parser)
            if parser == "xml":
                from bs4 import FeatureNotFound

                raise FeatureNotFound("no xml parser")
            return real_bs(markup, parser)

        with patch.object(content_mod, "BeautifulSoup", fake_bs):
            soup = _parse_markup_document(xml)

        # Tried xml first, then fell back to html.parser.
        assert calls == ["xml", "html.parser"]
        assert soup is not None

    def test_detect_content_type_decode_path_handles_garbage(self):
        """Bytes that are not valid markup decode but classify as unknown."""
        assert detect_content_type(b"\xff\xfe\x00random") == "unknown"


# =============================================================================
# extract_main_content container selection (priority 1 / 2 / 3 / fallback)
# =============================================================================


class TestExtractMainContentSelection:
    def test_priority1_prefers_main_tag(self):
        html = b"""
        <html><body>
        <div class="content"><p>Distractor div content here</p></div>
        <main><p>The real main content lives inside the main landmark element.</p></main>
        </body></html>
        """
        text = extract_main_content(html)
        assert "real main content" in text

    def test_priority2_content_class_div_when_no_main(self):
        """With no <main>/<article>, a div with a content-class is selected."""
        html = b"""
        <html><body>
        <div class="sidebar-widget"><p>noise widget</p></div>
        <div class="article-body"><p>This div carries the article body text we want extracted.</p></div>
        </body></html>
        """
        text = extract_main_content(html)
        assert "article body text" in text

    def test_priority3_content_rich_fallback(self):
        """No landmarks and no content classes -> richest element wins."""
        html = b"""
        <html><body>
        <div class="x">
            <p>This is a long paragraph with plenty of words so the content-rich
            scorer treats it as the dominant block of meaningful page text here.</p>
            <p>A second substantial paragraph adds more length and paragraph count
            to make this div clearly the richest element in the document tree.</p>
        </div>
        </body></html>
        """
        text = extract_main_content(html)
        assert "long paragraph" in text

    def test_falls_back_to_body_when_nothing_matches(self):
        html = b"<html><body>plain body text with no landmarks at all here</body></html>"
        text = extract_main_content(html)
        assert "plain body text" in text


class TestFindContentRichElement:
    def test_skips_small_elements(self):
        soup = _parse_markup_document("<div><p>tiny</p></div>")
        assert _find_content_rich_element(soup) is None

    def test_penalizes_link_heavy_navigation(self):
        """A link-dense block scores below a prose block of similar length."""
        link_block = "".join(
            f'<a href="/p{i}">Navigation link number {i} in the menu</a>' for i in range(20)
        )
        prose = "<p>" + "This paragraph contains substantial readable prose content. " * 10 + "</p>"
        html = f"<html><body><div id='nav'>{link_block}</div><div id='body'>{prose}</div></body></html>"
        soup = _parse_markup_document(html)
        best = _find_content_rich_element(soup)
        assert best is not None
        # The prose div should win over the link-heavy nav div.
        assert best.get("id") == "body"

    def test_none_when_no_rich_element(self):
        soup = _parse_markup_document("<html><body></body></html>")
        assert _find_content_rich_element(soup) is None


# =============================================================================
# _extract_text_with_structure inline assembly
# =============================================================================


class TestExtractTextWithStructure:
    def test_none_element_returns_empty(self):
        assert _extract_text_with_structure(None) == ""

    def test_inline_text_appended_to_previous_line(self):
        """Inline (non-block) text is folded into the preceding line."""
        soup = _parse_markup_document(
            "<div><p>The headline paragraph introduces the topic.</p>"
            "<span>inline trailing fragment</span></div>"
        )
        out = _extract_text_with_structure(soup.find("div"))
        # The span text is inline; it should attach to the paragraph line.
        assert "inline trailing fragment" in out

    def test_block_parents_produce_separate_lines(self):
        soup = _parse_markup_document(
            "<div><h2>Leadership and Governance</h2>"
            "<p>The executive team brings decades of operating experience.</p></div>"
        )
        out = _extract_text_with_structure(soup.find("div"))
        lines = [line for line in out.split("\n") if line]
        assert any("Leadership" in line for line in lines)
        assert any("executive team" in line for line in lines)


# =============================================================================
# aggressive boilerplate stripping
# =============================================================================


class TestAggressiveBoilerplate:
    def test_aggressive_strips_boilerplate_class(self):
        html = b"""
        <html><body>
        <div class="cookie-consent">We use cookies. Accept all.</div>
        <div class="article"><p>Genuine article body content that should survive aggressive cleaning.</p></div>
        </body></html>
        """
        text = extract_clean_text(html, mode="aggressive")
        assert "Genuine article body content" in text
        assert "cookies" not in text.lower()

    def test_word_boundary_avoids_false_positive(self):
        """Class 'ddpadding' must not match the 'ad' boilerplate token."""
        html = b"""
        <html><body>
        <div class="ddpadding"><p>This sidebar-free block keeps its useful informative paragraph text.</p></div>
        </body></html>
        """
        text = extract_clean_text(html, mode="aggressive")
        assert "useful informative paragraph" in text


# =============================================================================
# PDF: PyMuPDF + Gemini LLM paths
# =============================================================================


class TestPdfPyMuPdf:
    def test_returns_none_when_fitz_missing(self):
        """If PyMuPDF (fitz) is not importable, returns None gracefully."""
        with patch.dict("sys.modules", {"fitz": None}):
            assert extract_text_from_pdf(b"%PDF-1.4 fake") is None

    def test_extracts_text_via_mocked_fitz(self):
        """Drive the happy path with a stubbed fitz module."""
        fake_page = MagicMock()
        fake_page.get_text.return_value = "Page one body text"
        fake_doc = MagicMock()
        fake_doc.__iter__.return_value = iter([fake_page])
        fake_fitz = MagicMock()
        fake_fitz.open.return_value = fake_doc

        with patch.dict("sys.modules", {"fitz": fake_fitz}):
            out = extract_text_from_pdf(b"%PDF-1.4 real-ish")

        assert out == "Page one body text"
        fake_doc.close.assert_called_once()

    def test_returns_none_when_extracted_empty(self):
        fake_page = MagicMock()
        fake_page.get_text.return_value = "   "
        fake_doc = MagicMock()
        fake_doc.__iter__.return_value = iter([fake_page])
        fake_fitz = MagicMock()
        fake_fitz.open.return_value = fake_doc

        with patch.dict("sys.modules", {"fitz": fake_fitz}):
            out = extract_text_from_pdf(b"%PDF-1.4")

        assert out is None

    def test_open_failure_returns_none(self):
        fake_fitz = MagicMock()
        fake_fitz.open.side_effect = RuntimeError("corrupt pdf")
        with patch.dict("sys.modules", {"fitz": fake_fitz}):
            assert extract_text_from_pdf(b"%PDF-broken") is None


class TestPdfViaLlm:
    def test_oversized_pdf_falls_back_to_pymupdf(self):
        reset_pdf_llm_budget()
        import primr.data.scraping.content as content_mod

        huge = b"%PDF" + b"\x00" * (21 * 1024 * 1024)
        with patch.object(content_mod, "extract_text_from_pdf", return_value="fallback"):
            out = extract_text_from_pdf_via_llm(huge)
        assert out == "fallback"
        reset_pdf_llm_budget()

    def test_no_gemini_key_falls_back(self):
        reset_pdf_llm_budget()
        import primr.data.scraping.content as content_mod

        fake_settings = MagicMock()
        fake_settings.api.gemini_key = ""
        fake_genai = MagicMock()

        with (
            patch.dict("sys.modules", {"google.genai": fake_genai, "google": MagicMock()}),
            patch("primr.config.settings.get_settings", return_value=fake_settings),
            patch.object(content_mod, "extract_text_from_pdf", return_value="pymupdf"),
        ):
            out = extract_text_from_pdf_via_llm(b"%PDF-1.4 small")

        assert out == "pymupdf"
        reset_pdf_llm_budget()


@pytest.mark.parametrize(
    "header,expected",
    [
        ("text/html", "html"),
        ("application/pdf", "pdf"),
        ("application/json", "json"),
        ("application/xml", "xml"),
        ("text/plain", "text"),
    ],
)
def test_detect_content_type_header_branches(header, expected):
    assert detect_content_type(b"", header) == expected
