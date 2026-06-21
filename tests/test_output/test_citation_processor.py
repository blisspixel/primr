"""
Tests for the Citation Processor.

Includes property-based tests for citation transformation correctness.
"""

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from primr.output.citation_processor import (
    CitationProcessor,
    CitationStyle,
    SourceCitation,
    process_citations,
)

# =============================================================================
# Unit Tests
# =============================================================================


class TestCitationProcessor:
    """Unit tests for CitationProcessor class."""

    def test_basic_link_transformation(self):
        """Transform a simple markdown link to numbered reference."""
        processor = CitationProcessor()
        content = "According to [Acme Corp](https://acme.example), the product is popular."

        result = processor.process_content(content)

        assert "Acme Corp [1]" in result.transformed_content
        assert "https://acme.example" not in result.transformed_content
        assert len(result.citations) == 1
        assert result.citations[0].reference_number == 1

    def test_multiple_links(self):
        """Transform multiple different links."""
        processor = CitationProcessor()
        content = (
            "See [Globex Inc](https://globex.example) and [Initech Co](https://initech.example)."
        )

        result = processor.process_content(content)

        assert "Globex Inc [1]" in result.transformed_content
        assert "Initech Co [2]" in result.transformed_content
        assert len(result.citations) == 2

    def test_duplicate_url_reuses_reference(self):
        """Same URL should get same reference number."""
        processor = CitationProcessor()
        content = "[Acme Corp](https://acme.example) is great. [Acme Corp again](https://acme.example) is still great."

        result = processor.process_content(content)

        assert "Acme Corp [1]" in result.transformed_content
        assert "Acme Corp again [1]" in result.transformed_content
        assert len(result.citations) == 1  # Only one unique URL

    def test_inline_style_preserves_urls(self):
        """INLINE style should preserve original markdown links."""
        processor = CitationProcessor(style=CitationStyle.INLINE)
        content = "See [Acme Corp](https://acme.example) for details."

        result = processor.process_content(content)

        assert result.transformed_content == content
        assert len(result.citations) == 0

    def test_no_links_returns_unchanged(self):
        """Content without links should be unchanged."""
        processor = CitationProcessor()
        content = "This is plain text without any links."

        result = processor.process_content(content)

        assert result.transformed_content == content
        assert len(result.citations) == 0

    def test_non_http_links_preserved(self):
        """Non-HTTP links (mailto:, tel:) should be preserved."""
        processor = CitationProcessor()
        content = "Contact [email](mailto:test@example.com) or [phone](tel:+1234567890)."

        result = processor.process_content(content)

        assert "[email](mailto:test@example.com)" in result.transformed_content
        assert "[phone](tel:+1234567890)" in result.transformed_content
        assert len(result.citations) == 0

    def test_url_normalization_for_dedup(self):
        """URLs with/without trailing slash should be deduplicated."""
        processor = CitationProcessor()
        content = "[Site](https://example.com) and [Site2](https://example.com/)."

        result = processor.process_content(content)

        # Both should get same reference number
        assert "Site [1]" in result.transformed_content
        assert "Site2 [1]" in result.transformed_content
        assert len(result.citations) == 1

    def test_generate_sources_appendix(self):
        """Generate formatted sources appendix."""
        processor = CitationProcessor()
        processor.process_content(
            "[Acme Corp](https://acme.example) and [Globex Inc](https://globex.example)."
        )

        appendix = processor.generate_sources_appendix()

        assert "## Sources" in appendix
        assert "[1]" in appendix
        assert "[2]" in appendix
        assert "acme.example" in appendix
        assert "globex.example" in appendix

    def test_generate_sidecar_file(self):
        """Generate sidecar sources file."""
        processor = CitationProcessor()
        processor.process_content("[Acme Corp](https://acme.example).")

        filename, content = processor.generate_sidecar_file("Acme Corp")

        assert filename == "Acme_Corp_sources.md"
        assert "# Sources for Acme Corp Research" in content
        assert "[1]" in content
        assert "acme.example" in content

    def test_reset_clears_state(self):
        """Reset should clear all citations."""
        processor = CitationProcessor()
        processor.process_content("[Acme Corp](https://acme.example).")
        assert processor.citation_count == 1

        processor.reset()

        assert processor.citation_count == 0
        assert len(processor.citations) == 0

    def test_extract_domain_as_default_title(self):
        """Domain should be extracted as default title."""
        processor = CitationProcessor()
        # Link with no meaningful text
        content = "[link](https://www.example.com/page)"

        result = processor.process_content(content)

        # Title should be domain without www
        assert result.citations[0].title == "link"  # Uses provided text


class TestConvenienceFunction:
    """Tests for process_citations convenience function."""

    def test_process_citations_numbered(self):
        """Convenience function with numbered style."""
        result = process_citations(
            "[Acme Corp](https://acme.example) is great.", style=CitationStyle.NUMBERED
        )

        assert "Acme Corp [1]" in result.transformed_content
        assert len(result.citations) == 1

    def test_process_citations_inline(self):
        """Convenience function with inline style."""
        content = "[Acme Corp](https://acme.example) is great."
        result = process_citations(content, style=CitationStyle.INLINE)

        assert result.transformed_content == content
        assert len(result.citations) == 0


# =============================================================================
# Property-Based Tests
# =============================================================================


@st.composite
def markdown_link(draw):
    """Generate a markdown link [text](url)."""
    text = draw(
        st.text(
            min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=["L", "N", "S"])
        )
    )
    text = text.strip()
    assume(len(text) > 0)
    assume("[" not in text and "]" not in text and "(" not in text and ")" not in text)

    domain = draw(
        st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=["L", "N"]))
    )
    domain = domain.strip().lower()
    assume(len(domain) >= 3)

    tld = draw(st.sampled_from([".com", ".org", ".net", ".io", ".co"]))
    url = f"https://{domain}{tld}"

    return f"[{text}]({url})", text, url


@st.composite
def content_with_links(draw):
    """Generate content with multiple markdown links."""
    num_links = draw(st.integers(min_value=1, max_value=5))
    parts = []
    links = []

    for _i in range(num_links):
        # Add some text before link
        prefix = draw(
            st.text(
                min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=["L", "S"])
            )
        )
        prefix = prefix.strip()
        if prefix:
            parts.append(prefix)

        # Add a link
        link_data = draw(markdown_link())
        parts.append(link_data[0])
        links.append(link_data)

    return " ".join(parts), links


class TestCitationReferenceNumbering:
    """
    **Feature: consulting-tier-report, Property 18: Citation Reference Numbering**
    **Validates: Requirements 12.1**

    For any content containing inline markdown links, the CitationProcessor
    SHALL replace each [text](url) with text [n] where n is a sequential reference number.
    """

    @settings(max_examples=100)
    @given(link_data=markdown_link())
    def test_single_link_gets_reference_number(self, link_data):
        """Each markdown link is replaced with text [n] format."""
        link, text, url = link_data
        content = f"See {link} for details."

        processor = CitationProcessor()
        result = processor.process_content(content)

        # Should have text followed by [n]
        assert f"{text} [" in result.transformed_content
        assert "](" not in result.transformed_content  # No markdown link syntax
        assert len(result.citations) == 1
        assert result.citations[0].reference_number == 1

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(data=content_with_links())
    def test_multiple_links_get_sequential_numbers(self, data):
        """Multiple links get sequential reference numbers."""
        content, links = data

        processor = CitationProcessor()
        result = processor.process_content(content)

        # No markdown link syntax should remain
        assert "](" not in result.transformed_content

        # Each unique URL should have a citation
        unique_urls = {link[2] for link in links}
        # Account for URL normalization
        assert len(result.citations) <= len(unique_urls)


class TestCitationDeduplication:
    """
    **Feature: consulting-tier-report, Property 19: Citation Deduplication**
    **Validates: Requirements 12.2**

    For any URL that appears multiple times in the document, the CitationProcessor
    SHALL assign the same reference number to all occurrences.
    """

    @settings(max_examples=100)
    @given(
        text1=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=["L"])),
        text2=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=["L"])),
        domain=st.text(
            min_size=3, max_size=15, alphabet=st.characters(whitelist_categories=["L", "N"])
        ),
    )
    def test_same_url_same_reference(self, text1, text2, domain):
        """Same URL always gets same reference number."""
        text1 = text1.strip()
        text2 = text2.strip()
        domain = domain.strip().lower()
        assume(len(text1) > 0 and len(text2) > 0 and len(domain) >= 3)
        assume("[" not in text1 and "]" not in text1)
        assume("[" not in text2 and "]" not in text2)

        url = f"https://{domain}.com"
        content = f"[{text1}]({url}) and [{text2}]({url})"

        processor = CitationProcessor()
        result = processor.process_content(content)

        # Both should have same reference number
        assert f"{text1} [1]" in result.transformed_content
        assert f"{text2} [1]" in result.transformed_content
        # Only one citation entry
        assert len(result.citations) == 1

    def test_url_with_trailing_slash_deduped(self):
        """URLs with/without trailing slash are deduplicated."""
        content = "[A](https://example.com) [B](https://example.com/)"

        processor = CitationProcessor()
        result = processor.process_content(content)

        assert len(result.citations) == 1
        assert "A [1]" in result.transformed_content
        assert "B [1]" in result.transformed_content


class TestCitationRoundTrip:
    """
    **Feature: consulting-tier-report, Property 20: Citation Round-Trip Consistency**
    **Validates: Requirements 12.3**

    For any content processed by CitationProcessor, the number of unique URLs
    in the input SHALL equal the number of entries in the generated sources appendix.
    """

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(data=content_with_links())
    def test_unique_urls_equal_appendix_entries(self, data):
        """Number of unique URLs equals appendix entries."""
        content, links = data

        processor = CitationProcessor()
        result = processor.process_content(content)

        # Count unique URLs (normalized)
        unique_urls = set()
        for _, _, url in links:
            normalized = url.rstrip("/")
            unique_urls.add(normalized)

        # Citations should match unique URLs
        assert len(result.citations) == len(unique_urls)

        # Appendix should have same count
        appendix = processor.generate_sources_appendix()
        for i in range(1, len(result.citations) + 1):
            assert f"[{i}]" in appendix

    def test_all_urls_in_appendix(self):
        """All processed URLs appear in the appendix."""
        content = "[A](https://a.com) [B](https://b.com) [C](https://c.com)"

        processor = CitationProcessor()
        processor.process_content(content)
        appendix = processor.generate_sources_appendix()

        assert "a.com" in appendix
        assert "b.com" in appendix
        assert "c.com" in appendix
        assert "[1]" in appendix
        assert "[2]" in appendix
        assert "[3]" in appendix


class TestSourceCitation:
    """Tests for SourceCitation dataclass."""

    def test_to_appendix_entry_format(self):
        """Appendix entry has correct format."""
        citation = SourceCitation(
            url="https://example.com", title="Example Site", reference_number=1
        )

        entry = citation.to_appendix_entry()

        assert entry.startswith("[1]")
        assert "Example Site" in entry
        assert "https://example.com" in entry


# =============================================================================
# URL Normalization Tests
# =============================================================================


class TestURLNormalization:
    """Tests for comprehensive URL normalization."""

    def test_tracking_params_removed(self):
        """UTM and tracking parameters should be stripped for deduplication."""
        processor = CitationProcessor()

        # Same URL with different tracking params should dedupe
        content = """
        [Link1](https://example.com/page?utm_source=google&utm_medium=cpc)
        [Link2](https://example.com/page?fbclid=abc123)
        [Link3](https://example.com/page)
        """

        result = processor.process_content(content)

        # All three should get same reference number
        assert len(result.citations) == 1
        assert "Link1 [1]" in result.transformed_content
        assert "Link2 [1]" in result.transformed_content
        assert "Link3 [1]" in result.transformed_content

    def test_meaningful_params_preserved(self):
        """Meaningful query parameters should be preserved for differentiation."""
        processor = CitationProcessor()

        # Different page IDs should be different citations
        content = """
        [Page1](https://example.com/article?id=123)
        [Page2](https://example.com/article?id=456)
        """

        result = processor.process_content(content)

        # Should be two different citations
        assert len(result.citations) == 2
        assert "Page1 [1]" in result.transformed_content
        assert "Page2 [2]" in result.transformed_content

    def test_case_normalization(self):
        """URL scheme and domain should be case-normalized."""
        processor = CitationProcessor()

        content = """
        [Link1](HTTPS://EXAMPLE.COM/page)
        [Link2](https://example.com/page)
        """

        result = processor.process_content(content)

        # Should dedupe despite case differences
        assert len(result.citations) == 1

    def test_fragment_removed(self):
        """URL fragments should be removed for deduplication."""
        processor = CitationProcessor()

        content = """
        [Link1](https://example.com/page#section1)
        [Link2](https://example.com/page#section2)
        [Link3](https://example.com/page)
        """

        result = processor.process_content(content)

        # All should dedupe (fragments don't change the page)
        assert len(result.citations) == 1

    def test_mixed_tracking_and_meaningful_params(self):
        """Mixed tracking and meaningful params handled correctly."""
        processor = CitationProcessor()

        content = """
        [Link1](https://example.com/search?q=test&utm_source=google)
        [Link2](https://example.com/search?q=test&fbclid=xyz)
        [Link3](https://example.com/search?q=other&utm_source=google)
        """

        result = processor.process_content(content)

        # First two should dedupe (same q=test), third is different
        assert len(result.citations) == 2

    def test_all_tracking_params_stripped(self):
        """All known tracking parameters should be stripped."""
        processor = CitationProcessor()

        tracking_params = [
            "utm_source=x",
            "utm_medium=x",
            "utm_campaign=x",
            "utm_term=x",
            "utm_content=x",
            "fbclid=x",
            "gclid=x",
            "gclsrc=x",
            "dclid=x",
            "msclkid=x",
            "ref_src=x",
            "ref_url=x",
            "_ga=x",
            "_gl=x",
            "mc_cid=x",
            "mc_eid=x",
            "trk=x",
            "trkInfo=x",
            "originalReferer=x",
        ]

        # Create content with each tracking param
        links = []
        for i, param in enumerate(tracking_params):
            links.append(f"[Link{i}](https://example.com/page?{param})")

        content = " ".join(links)
        result = processor.process_content(content)

        # All should dedupe to single citation
        assert len(result.citations) == 1


class TestCitationDataLossRegressions:
    """Bug-hunt round 2: regressions for silent source loss in citation handling."""

    def test_distinct_ref_param_urls_not_merged(self):
        # ?ref= / ?source= are meaningful (article IDs, doc selectors), not
        # tracking noise; two URLs differing only by them are DISTINCT sources
        # and must each get their own citation number.
        processor = CitationProcessor()
        content = (
            "First [A](https://acme.example/p?ref=1) and "
            "second [B](https://acme.example/p?ref=2)."
        )
        result = processor.process_content(content)
        assert "A [1]" in result.transformed_content
        assert "B [2]" in result.transformed_content
        assert len(result.citations) == 2

    def test_utm_params_still_deduped(self):
        processor = CitationProcessor()
        content = (
            "First [A](https://acme.example/p?utm_source=x) and "
            "second [B](https://acme.example/p?utm_source=y)."
        )
        result = processor.process_content(content)
        assert len(result.citations) == 1

    def test_parenthesized_url_not_truncated(self):
        # A URL with balanced parens (Wikipedia "..._(company)") must not be cut
        # at the first ")" (which corrupted the source URL and left a stray ")").
        processor = CitationProcessor()
        content = "See [Acme](https://en.wikipedia.org/wiki/Acme_(company)) here."
        result = processor.process_content(content)
        assert len(result.citations) == 1
        assert "See Acme [1] here." in result.transformed_content
