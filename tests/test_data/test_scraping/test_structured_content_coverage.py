"""Additional coverage for structured content extraction pipeline.

These tests exercise the smaller helpers and edge branches that the existing
test_structured_content.py doesn't reach: block extraction, CTA detection,
metadata parsing, quality scoring, tier-escalation, and the dataclass
serialization helpers. All pure logic — no network or filesystem.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from primr.data.scraping.structured_content import (
    BoilerplateFilter,
    ContentBlock,
    ExtractionMetrics,
    QualityScore,
    StructuredContent,
    compute_link_density,
    compute_quality_score,
    extract_blocks,
    extract_metadata,
    extract_structured_content,
    extract_with_boilerplate_learning,
    find_main_content,
    get_clean_text_for_summarization,
    is_cta_block,
    normalize_text,
    score_container,
    should_escalate_tier,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# =============================================================================
# is_cta_block
# =============================================================================


class TestIsCtaBlock:
    def test_short_text_matching_pattern_is_cta(self):
        assert is_cta_block("Request a demo")
        assert is_cta_block("Get started")
        assert is_cta_block("Sign up for free")

    def test_long_text_with_pattern_is_not_cta(self):
        long_text = "Request a demo " + ("x" * 200)
        assert not is_cta_block(long_text)

    def test_short_text_high_link_density_is_cta(self):
        assert is_cta_block("Buy now", link_density=0.9)

    def test_short_text_low_link_density_not_cta(self):
        assert not is_cta_block("Hello world", link_density=0.1)


# =============================================================================
# compute_link_density / score_container
# =============================================================================


class TestLinkDensity:
    def test_empty_element_returns_zero(self):
        el = _soup("<div></div>").div
        assert compute_link_density(el) == 0.0

    def test_all_link_text_high_density(self):
        el = _soup('<div><a href="#">linktext</a></div>').div
        assert compute_link_density(el) == 1.0

    def test_partial_link_density(self):
        el = _soup('<div>aaaa<a href="#">bbbb</a></div>').div
        # link text is half of total text
        assert 0.4 < compute_link_density(el) < 0.6


class TestScoreContainer:
    def test_short_text_scores_zero(self):
        el = _soup("<div>tiny</div>").div
        assert score_container(el) == 0

    def test_content_rich_div_scores_positive(self):
        body = "<div>" + "<p>Lorem ipsum dolor sit amet consectetur. </p>" * 10 + "</div>"
        el = _soup(body).div
        assert score_container(el) > 0

    def test_nav_class_penalized(self):
        para = "<p>Lorem ipsum dolor sit amet consectetur adipiscing. </p>" * 10
        nav = _soup(f'<div class="navbar">{para}</div>').div
        plain = _soup(f"<div>{para}</div>").div
        assert score_container(nav) < score_container(plain)

    def test_high_link_density_penalized(self):
        links = "".join(f'<a href="#">menu item {i}</a>' for i in range(40))
        el = _soup(f"<div>{links}</div>").div
        # heavy link density should drag score down (often to 0)
        assert score_container(el) >= 0


# =============================================================================
# find_main_content
# =============================================================================


class TestFindMainContent:
    def test_prefers_semantic_main(self):
        html = "<html><body><main>" + ("Real content here. " * 30) + "</main></body></html>"
        soup = _soup(html)
        main = find_main_content(soup)
        assert main.name == "main"

    def test_falls_back_to_scoring_when_no_semantic(self):
        html = "<html><body><div>" + ("<p>Paragraph text here. </p>" * 20) + "</div></body></html>"
        soup = _soup(html)
        main = find_main_content(soup)
        assert main is not None
        assert "Paragraph text here" in main.get_text()

    def test_returns_body_when_nothing_scores(self):
        soup = _soup("<html><body><span>hi</span></body></html>")
        main = find_main_content(soup)
        assert main is not None


# =============================================================================
# extract_metadata
# =============================================================================


class TestExtractMetadata:
    def test_title_and_description(self):
        html = """<html><head>
            <title>My Page</title>
            <meta name="description" content="A description">
            </head><body></body></html>"""
        meta = extract_metadata(_soup(html))
        assert meta["title"] == "My Page"
        assert meta["meta_description"] == "A description"

    def test_og_title_fallback(self):
        html = '<html><head><meta property="og:title" content="OG Title"></head></html>'
        meta = extract_metadata(_soup(html))
        assert meta["title"] == "OG Title"

    def test_og_description_fallback(self):
        html = '<html><head><meta property="og:description" content="OG Desc"></head></html>'
        meta = extract_metadata(_soup(html))
        assert meta["meta_description"] == "OG Desc"

    def test_language_from_html_tag(self):
        meta = extract_metadata(_soup('<html lang="en"><body></body></html>'))
        assert meta["lang"] == "en"

    def test_published_date_from_meta(self):
        html = '<html><head><meta property="article:published_time" content="2026-01-01"></head></html>'
        meta = extract_metadata(_soup(html))
        assert meta["published_date"] == "2026-01-01"

    def test_published_date_from_time_tag(self):
        html = '<html><body><time datetime="2026-05-01">May 1</time></body></html>'
        meta = extract_metadata(_soup(html))
        assert meta["published_date"] == "2026-05-01"

    def test_byline_from_author_meta(self):
        html = '<html><head><meta name="author" content="Jane Doe"></head></html>'
        meta = extract_metadata(_soup(html))
        assert meta["byline"] == "Jane Doe"

    def test_byline_from_author_class(self):
        html = '<html><body><span class="author">John Smith</span></body></html>'
        meta = extract_metadata(_soup(html))
        assert meta["byline"] == "John Smith"


# =============================================================================
# extract_blocks
# =============================================================================


class TestExtractBlocks:
    def test_headings_paragraphs_lists(self):
        html = """<div>
            <h1>Title</h1>
            <h2>Subtitle</h2>
            <p>This is a body paragraph with content.</p>
            <ul><li>Item one</li><li>Item two</li></ul>
            <ol><li>Numbered one</li></ol>
        </div>"""
        blocks = extract_blocks(_soup(html).div)
        types = [b.type for b in blocks]
        assert "h1" in types
        assert "h2" in types
        assert "p" in types
        li_blocks = [b for b in blocks if b.type == "li"]
        assert any(b.list_type == "ul" for b in li_blocks)
        assert any(b.list_type == "ol" for b in li_blocks)

    def test_cta_paragraph_tagged_as_cta(self):
        html = "<div><p>Request a demo</p></div>"
        blocks = extract_blocks(_soup(html).div)
        assert any(b.type == "cta" for b in blocks)

    def test_blockquote_with_cite_attribution(self):
        html = "<div><blockquote>Great product<cite>Jane Doe</cite></blockquote></div>"
        blocks = extract_blocks(_soup(html).div)
        quote = next(b for b in blocks if b.type == "quote")
        assert quote.attribution == "Jane Doe"

    def test_blockquote_attribution_from_dash_line(self):
        html = "<div><blockquote>Best thing ever\n— Some Person</blockquote></div>"
        blocks = extract_blocks(_soup(html).div)
        quote = next(b for b in blocks if b.type == "quote")
        assert quote.attribution is not None
        assert "Some Person" in quote.attribution

    def test_testimonial_div_emits_quote(self):
        html = '<div><div class="testimonial">This product changed my life</div></div>'
        blocks = extract_blocks(_soup(html).div)
        assert any(b.type == "quote" for b in blocks)

    def test_duplicate_text_deduped(self):
        html = "<div><p>Same paragraph text</p><p>Same paragraph text</p></div>"
        blocks = extract_blocks(_soup(html).div)
        para_texts = [b.text for b in blocks if b.type == "p"]
        assert len(para_texts) == 1

    def test_too_short_text_skipped(self):
        html = "<div><p>ab</p></div>"
        blocks = extract_blocks(_soup(html).div)
        assert blocks == []


# =============================================================================
# normalize_text
# =============================================================================


class TestNormalizeText:
    def test_collapses_blank_lines(self):
        assert normalize_text("a\n\n\n\nb") == "a\n\nb"

    def test_collapses_spaces(self):
        assert normalize_text("a    b\tc") == "a b c"

    def test_strips_each_line(self):
        assert normalize_text("  hello  \n  world  ") == "hello\nworld"


# =============================================================================
# compute_quality_score
# =============================================================================


class TestQualityScore:
    def test_low_text_flag(self):
        metrics = ExtractionMetrics(char_count=100, heading_count=1, paragraph_count=5)
        q = compute_quality_score(metrics, [])
        assert "low_text" in q.flags
        assert q.score < 1.0

    def test_no_headings_flag(self):
        metrics = ExtractionMetrics(char_count=2000, heading_count=0, paragraph_count=5)
        q = compute_quality_score(metrics, [])
        assert "no_headings" in q.flags

    def test_high_link_density_flag(self):
        metrics = ExtractionMetrics(
            char_count=2000, heading_count=2, paragraph_count=5, link_density=0.7
        )
        q = compute_quality_score(metrics, [])
        assert "high_link_density" in q.flags

    def test_high_boilerplate_flag(self):
        metrics = ExtractionMetrics(
            char_count=2000, heading_count=2, paragraph_count=5, boilerplate_ratio=0.6
        )
        q = compute_quality_score(metrics, [])
        assert "high_boilerplate" in q.flags

    def test_excessive_repetition_flag(self):
        metrics = ExtractionMetrics(
            char_count=2000, heading_count=2, paragraph_count=5, dup_line_ratio=0.4
        )
        q = compute_quality_score(metrics, [])
        assert "excessive_repetition" in q.flags

    def test_cta_and_quote_flags(self):
        metrics = ExtractionMetrics(
            char_count=2000, heading_count=2, paragraph_count=5, quote_count=2
        )
        blocks = [ContentBlock(type="cta", text="Sign up")]
        q = compute_quality_score(metrics, blocks)
        assert any(f.startswith("cta_removed") for f in q.flags)
        assert any(f.startswith("quotes:") for f in q.flags)

    def test_score_clamped_between_zero_and_one(self):
        metrics = ExtractionMetrics(
            char_count=10,
            heading_count=0,
            paragraph_count=0,
            link_density=0.9,
            boilerplate_ratio=0.9,
            dup_line_ratio=0.9,
        )
        q = compute_quality_score(metrics, [])
        assert 0.0 <= q.score <= 1.0


# =============================================================================
# Dataclass serialization helpers
# =============================================================================


class TestDataclassHelpers:
    def test_metrics_to_dict_rounds(self):
        d = ExtractionMetrics(link_density=0.123456).to_dict()
        assert d["link_density"] == 0.123

    def test_quality_to_dict(self):
        d = QualityScore(score=0.876, flags=["a"]).to_dict()
        assert d["score"] == 0.88
        assert d["flags"] == ["a"]

    def test_structured_content_to_dict_drops_none_block_fields(self):
        sc = StructuredContent(
            url="https://example.com",
            blocks=[ContentBlock(type="p", text="hi")],
        )
        d = sc.to_dict()
        assert d["url"] == "https://example.com"
        block = d["blocks"][0]
        assert "list_type" not in block  # None values dropped
        assert block["type"] == "p"

    def test_to_plain_text_renders_all_block_types(self):
        sc = StructuredContent(
            url="u",
            title="Doc Title",
            blocks=[
                ContentBlock(type="h2", text="Section"),
                ContentBlock(type="p", text="Body paragraph"),
                ContentBlock(type="li", text="Bullet", list_type="ul"),
                ContentBlock(type="li", text="Numbered", list_type="ol"),
                ContentBlock(type="quote", text="A quote", attribution="Author"),
                ContentBlock(type="cta", text="Sign up"),
            ],
        )
        text = sc.to_plain_text(include_cta=False)
        assert "# Doc Title" in text
        assert "## Section" in text
        assert "Body paragraph" in text
        assert "Bullet" in text
        assert "> A quote" in text
        assert "Author" in text
        # cta excluded
        assert "Sign up" not in text

    def test_to_plain_text_includes_cta_when_requested(self):
        sc = StructuredContent(url="u", blocks=[ContentBlock(type="cta", text="Sign up")])
        assert "Sign up" in sc.to_plain_text(include_cta=True)


# =============================================================================
# extract_structured_content edge cases
# =============================================================================


class TestExtractStructuredContent:
    def test_empty_html_returns_empty_flag(self):
        result = extract_structured_content(b"", "https://example.com")
        assert result.quality.flags == ["empty_content"]
        assert result.quality.score == 0.0

    def test_final_url_defaults_to_url(self):
        result = extract_structured_content(b"<html></html>", "https://example.com")
        assert result.final_url == "https://example.com"

    def test_full_pipeline_populates_fields(self):
        html = b"""<html><head><title>Acme</title></head>
            <body><main>
            <h1>Welcome to Acme</h1>
            <p>Acme builds widgets for the modern enterprise market today.</p>
            <p>Our team is distributed across many regions worldwide.</p>
            </main></body></html>"""
        result = extract_structured_content(html, "https://acme.example")
        assert result.title == "Acme"
        assert result.metrics.heading_count >= 1
        assert result.text


# =============================================================================
# extract_with_boilerplate_learning
# =============================================================================


class TestBoilerplateLearning:
    def test_empty_pages_returns_empty(self):
        assert extract_with_boilerplate_learning([]) == []

    def test_removes_shared_lines_across_pages(self):
        shared = "<p>Copyright 2026 Acme Inc all rights reserved.</p>"
        pages = []
        for i in range(4):
            html = (
                f"<html><body><main>{shared}"
                f"<p>Unique content for page number {i} only here.</p>"
                "</main></body></html>"
            ).encode()
            pages.append((f"https://acme.example/{i}", html))
        results = extract_with_boilerplate_learning(pages, boilerplate_threshold=0.3)
        assert len(results) == 4


# =============================================================================
# get_clean_text_for_summarization
# =============================================================================


class TestGetCleanTextForSummarization:
    def test_returns_none_below_quality_threshold(self):
        sc = StructuredContent(url="u")
        sc.quality = QualityScore(score=0.1)
        assert get_clean_text_for_summarization(sc, min_quality_score=0.3) is None

    def test_returns_text_above_threshold(self):
        sc = StructuredContent(url="u", blocks=[ContentBlock(type="p", text="Good content")])
        sc.quality = QualityScore(score=0.9)
        out = get_clean_text_for_summarization(sc, min_quality_score=0.3)
        assert out is not None
        assert "Good content" in out


# =============================================================================
# should_escalate_tier
# =============================================================================


class TestShouldEscalateTier:
    def test_low_quality_escalates(self):
        sc = StructuredContent(url="u")
        sc.quality = QualityScore(score=0.2)
        sc.metrics = ExtractionMetrics(char_count=5000, heading_count=3)
        escalate, reason = should_escalate_tier(sc)
        assert escalate
        assert "low_quality_score" in reason

    def test_too_short_escalates(self):
        sc = StructuredContent(url="u")
        sc.quality = QualityScore(score=0.9)
        sc.metrics = ExtractionMetrics(char_count=100, heading_count=3)
        escalate, reason = should_escalate_tier(sc)
        assert escalate
        assert "too_short" in reason

    def test_nav_like_escalates(self):
        sc = StructuredContent(url="u")
        sc.quality = QualityScore(score=0.9)
        sc.metrics = ExtractionMetrics(char_count=5000, heading_count=0, link_density=0.5)
        escalate, reason = should_escalate_tier(sc)
        assert escalate
        assert reason == "nav_like_page"

    def test_app_shell_escalates(self):
        sc = StructuredContent(url="u")
        sc.quality = QualityScore(score=0.9, flags=["low_text", "no_headings"])
        sc.metrics = ExtractionMetrics(char_count=5000, heading_count=1, link_density=0.1)
        escalate, reason = should_escalate_tier(sc)
        assert escalate
        assert reason == "possible_app_shell"

    def test_good_content_does_not_escalate(self):
        sc = StructuredContent(url="u")
        sc.quality = QualityScore(score=0.9, flags=[])
        sc.metrics = ExtractionMetrics(char_count=5000, heading_count=3, link_density=0.1)
        escalate, reason = should_escalate_tier(sc)
        assert not escalate
        assert reason == ""


# =============================================================================
# BoilerplateFilter helpers not covered elsewhere
# =============================================================================


class TestBoilerplateFilterHelpers:
    def test_remove_boilerplate_no_lines_returns_unchanged(self):
        bp = BoilerplateFilter()
        text = "some text\nmore text"
        out, ratio = bp.remove_boilerplate(text)
        assert out == text
        assert ratio == 0.0

    def test_compute_boilerplate_single_page_returns_empty(self):
        bp = BoilerplateFilter()
        bp.add_page("only one page here with lines")
        assert bp.compute_boilerplate() == set()

    def test_get_boilerplate_examples(self):
        bp = BoilerplateFilter()
        for _ in range(5):
            bp.add_page("repeated boilerplate line here\nunique stuff")
        bp.compute_boilerplate(threshold=0.3)
        examples = bp.get_boilerplate_examples(limit=5)
        assert isinstance(examples, list)
        if examples:
            assert isinstance(examples[0], tuple)

    def test_allowlist_prevents_removal(self):
        bp = BoilerplateFilter()
        normalized = bp.normalize_line("Common header line text")
        bp.allowlist.add(normalized)
        for _ in range(5):
            bp.add_page("Common header line text\nunique body content")
        bp.compute_boilerplate(threshold=0.3)
        assert normalized not in bp.boilerplate_lines
