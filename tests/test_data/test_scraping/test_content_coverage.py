"""Additional coverage for content extraction helpers.

Targets pure-logic branches not exercised by test_content.py: quality
gates, entity decoding edge cases, nav/body heuristics, PDF byte budget
fallbacks, content-type detection edges, and meta-description alt patterns.
No network.
"""

from __future__ import annotations

from unittest.mock import patch

from primr.data.scraping.content import (
    _decode_html_entities,
    _is_body_like_line,
    _is_nav_like_line,
    _looks_like_xml_document,
    _trim_leading_noise,
    detect_content_type,
    extract_text_from_pdf,
    extract_text_from_pdf_via_llm,
    get_meta_description,
    get_page_title,
    is_quality_content,
    reset_pdf_llm_budget,
)

# =============================================================================
# is_quality_content
# =============================================================================


class TestIsQualityContent:
    def test_empty_text(self):
        ok, reason = is_quality_content("")
        assert not ok
        assert reason == "Empty content"

    def test_garbage_pattern_detected(self):
        ok, reason = is_quality_content("Please enable javascript to continue. " * 20)
        assert not ok
        assert "Garbage pattern" in reason

    def test_too_short(self):
        ok, reason = is_quality_content("Short text.")
        assert not ok
        assert "Too short" in reason

    def test_too_few_words(self):
        # Long enough chars but few words (padded single long token)
        text = "word " + "x" * 300
        ok, reason = is_quality_content(text)
        assert not ok
        # Either word-count or sentence-count gate fires
        assert "Too few" in reason

    def test_too_few_sentences(self):
        text = "alpha beta gamma delta " * 30  # many words, no periods
        ok, reason = is_quality_content(text)
        assert not ok
        assert "sentence" in reason.lower()

    def test_repetitive_content(self):
        line = "This is a repeated sentence that appears over and over again here.\n"
        text = line * 30
        ok, reason = is_quality_content(text)
        assert not ok
        assert "Repetitive" in reason

    def test_good_content_passes(self):
        text = (
            "Acme Corporation builds enterprise software for logistics companies. "
            "The platform handles routing, scheduling, and fleet telemetry. "
            "Customers include several Fortune 500 carriers. "
            "Founded in 2010, the company is headquartered in Denver. "
            "It employs roughly four hundred people across three offices."
        )
        ok, reason = is_quality_content(text)
        assert ok
        assert reason == "OK"


# =============================================================================
# detect_content_type edges
# =============================================================================


class TestDetectContentType:
    def test_xml_header(self):
        assert detect_content_type(b"", "application/xml") == "xml"

    def test_text_header(self):
        assert detect_content_type(b"", "text/plain") == "text"

    def test_json_array_from_content(self):
        assert detect_content_type(b'[{"a": 1}]') == "json"

    def test_xml_from_content(self):
        assert detect_content_type(b'<?xml version="1.0"?><root/>') == "xml"

    def test_empty_returns_unknown(self):
        assert detect_content_type(b"") == "unknown"


# =============================================================================
# _looks_like_xml_document
# =============================================================================


class TestLooksLikeXml:
    def test_empty_returns_false(self):
        assert _looks_like_xml_document("") is False

    def test_html_doctype_returns_false(self):
        assert _looks_like_xml_document("<!DOCTYPE html><html></html>") is False

    def test_xml_prolog_returns_true(self):
        assert _looks_like_xml_document('<?xml version="1.0"?><a/>') is True

    def test_rss_token_returns_true(self):
        assert _looks_like_xml_document("<rss version='2.0'></rss>") is True


# =============================================================================
# _decode_html_entities
# =============================================================================


class TestDecodeEntities:
    def test_named_entities(self):
        assert _decode_html_entities("a &amp; b &lt; c &gt; d") == "a & b < c > d"

    def test_numeric_decimal(self):
        assert _decode_html_entities("&#65;&#66;") == "AB"

    def test_numeric_hex(self):
        assert _decode_html_entities("&#x41;&#x42;") == "AB"

    def test_out_of_range_decimal_preserved(self):
        # Code beyond valid range stays untouched
        out = _decode_html_entities("&#99999999999;")
        assert "&#99999999999;" in out

    def test_invalid_hex_preserved(self):
        out = _decode_html_entities("&#xZZZ;")
        assert "&#xZZZ;" in out

    def test_special_named_entities(self):
        assert "—" in _decode_html_entities("a &mdash; b")
        assert "©" in _decode_html_entities("&copy;")


# =============================================================================
# nav / body line heuristics
# =============================================================================


class TestLineHeuristics:
    def test_skip_to_content_is_nav(self):
        assert _is_nav_like_line("Skip to content and other navigation items here please") is True

    def test_short_line_not_nav(self):
        assert _is_nav_like_line("Home") is False

    def test_sentence_with_punctuation_not_nav(self):
        assert _is_nav_like_line("This is a real sentence about the company's products.") is False

    def test_megamenu_token_list_is_nav(self):
        line = "Products Solutions Integrations Resources Careers Contact Demo Login Assessment"
        assert _is_nav_like_line(line) is True

    def test_body_like_paragraph(self):
        text = "the company has been growing steadily over the past several years across markets"
        assert _is_body_like_line(text) is True

    def test_cookie_line_not_body(self):
        assert (
            _is_body_like_line("we use cookies to improve your experience on our website ok")
            is False
        )

    def test_short_line_not_body(self):
        assert _is_body_like_line("short") is False


# =============================================================================
# _trim_leading_noise
# =============================================================================


class TestTrimLeadingNoise:
    def test_drops_leading_nav_keeps_body(self):
        lines = [
            "Home About Products",
            "Login",
            "the company builds widgets for enterprise customers around the world today",
        ]
        out = _trim_leading_noise(lines)
        assert out[-1].startswith("the company builds widgets")

    def test_no_body_returns_input(self):
        lines = ["Home", "About"]
        out = _trim_leading_noise(lines)
        assert out == lines

    def test_preserves_heading_before_body(self):
        lines = [
            "Login",
            "Our Story",
            "the company builds widgets for enterprise customers around the world today",
        ]
        out = _trim_leading_noise(lines)
        assert "Our Story" in out


# =============================================================================
# get_page_title / get_meta_description edges
# =============================================================================


class TestTitleAndMeta:
    def test_title_none_for_empty_bytes(self):
        assert get_page_title(b"") is None

    def test_meta_none_for_empty_bytes(self):
        assert get_meta_description(b"") is None

    def test_meta_description_single_quotes(self):
        html = b"<html><head><meta name='description' content='Single quoted desc'></head></html>"
        assert get_meta_description(html) == "Single quoted desc"

    def test_meta_description_reversed_attr_order(self):
        html = b'<html><head><meta content="Reversed order desc" name="description"></head></html>'
        assert get_meta_description(html) == "Reversed order desc"

    def test_title_collapses_whitespace(self):
        html = b"<html><head><title>  Multi\n  Line   Title  </title></head></html>"
        assert get_page_title(html) == "Multi Line Title"


# =============================================================================
# PDF extraction budget / fallbacks
# =============================================================================


class TestPdfExtraction:
    def test_extract_text_from_pdf_empty(self):
        assert extract_text_from_pdf(b"") is None

    def test_via_llm_empty_returns_none(self):
        assert extract_text_from_pdf_via_llm(b"") is None

    def test_via_llm_call_budget_exhausted_falls_back(self):
        reset_pdf_llm_budget()
        import primr.data.scraping.content as content_mod

        # Force the call budget to zero so the next call falls straight back to PyMuPDF.
        with (
            patch.object(content_mod, "_PDF_LLM_CALL_BUDGET", 0),
            patch.object(content_mod, "extract_text_from_pdf", return_value="fallback text"),
        ):
            out = extract_text_from_pdf_via_llm(b"%PDF-1.4 fake")
        assert out == "fallback text"
        reset_pdf_llm_budget()

    def test_via_llm_byte_budget_exhausted_falls_back(self):
        reset_pdf_llm_budget()
        import primr.data.scraping.content as content_mod

        with (
            patch.object(content_mod, "_PDF_LLM_CALL_BUDGET", 100),
            patch.object(content_mod, "_PDF_LLM_BYTE_BUDGET", 1),
            patch.object(content_mod, "extract_text_from_pdf", return_value="pymupdf out"),
        ):
            out = extract_text_from_pdf_via_llm(b"%PDF-1.4 some content here")
        assert out == "pymupdf out"
        reset_pdf_llm_budget()

    def test_reset_budget_clears_counters(self):
        import primr.data.scraping.content as content_mod

        content_mod._pdf_llm_calls_made = 5
        content_mod._pdf_llm_bytes_sent = 1234
        reset_pdf_llm_budget()
        assert content_mod._pdf_llm_calls_made == 0
        assert content_mod._pdf_llm_bytes_sent == 0
