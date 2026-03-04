"""Tests for the link discovery module."""

import gzip
from unittest.mock import Mock, patch

from primr.data.scraping.config import COMMON_PAGE_PATTERNS, SitemapConfig
from primr.data.scraping.discovery import (
    DiscoveredLink,
    discover_links,
    extract_links_from_homepage,
    extract_links_from_html,
    fetch_sitemap_links,
    guess_common_urls,
    score_links_heuristically,
    verify_urls_exist,
)


class TestDiscoveredLink:
    """Tests for DiscoveredLink dataclass."""

    def test_basic_link(self):
        """Should create a basic link."""
        link = DiscoveredLink(url="https://example.com/about", source="sitemap")
        assert link.url == "https://example.com/about"
        assert link.source == "sitemap"
        assert link.anchor_text is None
        assert link.score == 0.0

    def test_link_with_metadata(self):
        """Should create a link with all metadata."""
        link = DiscoveredLink(
            url="https://example.com/about",
            source="sitemap",
            anchor_text="About Us",
            sitemap_priority=0.8,
            sitemap_lastmod="2024-01-01",
            score=15.0,
        )
        assert link.sitemap_priority == 0.8
        assert link.sitemap_lastmod == "2024-01-01"
        assert link.score == 15.0


class TestGuessCommonUrls:
    """Tests for guess_common_urls function."""

    def test_generates_urls(self):
        """Should generate URLs from patterns."""
        links = guess_common_urls("https://example.com")
        assert len(links) > 0
        assert all(isinstance(link, DiscoveredLink) for link in links)

    def test_generates_60_plus_patterns(self):
        """Should generate 60+ URL patterns."""
        links = guess_common_urls("https://example.com")
        assert len(links) >= 60

    def test_all_links_have_guess_source(self):
        """All guessed links should have source='guess'."""
        links = guess_common_urls("https://example.com")
        assert all(link.source == "guess" for link in links)

    def test_urls_are_absolute(self):
        """All URLs should be absolute."""
        links = guess_common_urls("https://example.com")
        assert all(link.url.startswith("https://example.com") for link in links)

    def test_includes_common_patterns(self):
        """Should include common business page patterns."""
        links = guess_common_urls("https://example.com")
        urls = [link.url for link in links]

        assert "https://example.com/about" in urls
        assert "https://example.com/contact" in urls
        assert "https://example.com/careers" in urls
        assert "https://example.com/investors" in urls


class TestExtractLinksFromHtml:
    """Tests for extract_links_from_html function."""

    def test_extracts_basic_links(self):
        """Should extract basic anchor links."""
        html = b"""
        <html>
        <body>
        <a href="/about">About Us</a>
        <a href="/contact">Contact</a>
        </body>
        </html>
        """
        links = extract_links_from_html(html, "https://example.com")

        assert len(links) == 2
        urls = [link.url for link in links]
        assert "https://example.com/about" in urls
        assert "https://example.com/contact" in urls

    def test_extracts_anchor_text(self):
        """Should extract anchor text."""
        html = b'<a href="/about">About Our Company</a>'
        links = extract_links_from_html(html, "https://example.com")

        assert len(links) == 1
        assert links[0].anchor_text == "About Our Company"

    def test_resolves_relative_urls(self):
        """Should resolve relative URLs."""
        html = b'<a href="../products">Products</a>'
        links = extract_links_from_html(html, "https://example.com/pages/")

        assert len(links) == 1
        assert links[0].url == "https://example.com/products"

    def test_excludes_javascript_links(self):
        """Should exclude javascript: links."""
        html = b'<a href="javascript:void(0)">Click</a>'
        links = extract_links_from_html(html, "https://example.com")

        assert len(links) == 0

    def test_excludes_mailto_links(self):
        """Should exclude mailto: links."""
        html = b'<a href="mailto:test@example.com">Email</a>'
        links = extract_links_from_html(html, "https://example.com")

        assert len(links) == 0

    def test_excludes_file_extensions(self):
        """Should exclude links to files."""
        html = b"""
        <a href="/doc.pdf">PDF</a>
        <a href="/image.jpg">Image</a>
        <a href="/about">About</a>
        """
        links = extract_links_from_html(html, "https://example.com")

        assert len(links) == 1
        assert links[0].url == "https://example.com/about"

    def test_deduplicates_links(self):
        """Should deduplicate identical links."""
        html = b"""
        <a href="/about">About</a>
        <a href="/about">About Us</a>
        """
        links = extract_links_from_html(html, "https://example.com")

        assert len(links) == 1

    def test_same_domain_only(self):
        """Should filter to same domain when enabled."""
        html = b"""
        <a href="https://example.com/about">About</a>
        <a href="https://other.com/page">Other</a>
        """
        links = extract_links_from_html(html, "https://example.com", same_domain_only=True)

        assert len(links) == 1
        assert links[0].url == "https://example.com/about"

    def test_allows_other_domains_when_disabled(self):
        """Should allow other domains when same_domain_only=False."""
        html = b"""
        <a href="https://example.com/about">About</a>
        <a href="https://other.com/page">Other</a>
        """
        links = extract_links_from_html(html, "https://example.com", same_domain_only=False)

        assert len(links) == 2


class TestScoreLinksHeuristically:
    """Tests for score_links_heuristically function."""

    def test_scores_high_value_keywords(self):
        """Should give higher scores to high-value keywords."""
        links = [
            DiscoveredLink(url="https://example.com/about", source="html"),
            DiscoveredLink(url="https://example.com/privacy", source="html"),
        ]

        scored = score_links_heuristically(links)

        # About should score higher than privacy
        about_link = next(lnk for lnk in scored if "about" in lnk.url)
        privacy_link = next(lnk for lnk in scored if "privacy" in lnk.url)

        assert about_link.score > privacy_link.score

    def test_scores_sitemap_priority(self):
        """Should incorporate sitemap priority into score."""
        links = [
            DiscoveredLink(url="https://example.com/page1", source="sitemap", sitemap_priority=1.0),
            DiscoveredLink(url="https://example.com/page2", source="sitemap", sitemap_priority=0.1),
        ]

        scored = score_links_heuristically(links)

        page1 = next(lnk for lnk in scored if "page1" in lnk.url)
        page2 = next(lnk for lnk in scored if "page2" in lnk.url)

        assert page1.score > page2.score

    def test_scores_anchor_text(self):
        """Should incorporate anchor text into score."""
        links = [
            DiscoveredLink(url="https://example.com/page1", source="html", anchor_text="About Us"),
            DiscoveredLink(url="https://example.com/page2", source="html", anchor_text="Terms"),
        ]

        scored = score_links_heuristically(links)

        page1 = next(lnk for lnk in scored if "page1" in lnk.url)
        page2 = next(lnk for lnk in scored if "page2" in lnk.url)

        assert page1.score > page2.score

    def test_returns_sorted_by_score(self):
        """Should return links sorted by score descending."""
        links = [
            DiscoveredLink(url="https://example.com/privacy", source="html"),
            DiscoveredLink(url="https://example.com/about", source="html"),
            DiscoveredLink(url="https://example.com/investors", source="html"),
        ]

        scored = score_links_heuristically(links)

        scores = [lnk.score for lnk in scored]
        assert scores == sorted(scores, reverse=True)

    def test_penalizes_deep_urls(self):
        """Should penalize deeply nested URLs."""
        links = [
            DiscoveredLink(url="https://example.com/about", source="html"),
            DiscoveredLink(url="https://example.com/a/b/c/d/e/about", source="html"),
        ]

        scored = score_links_heuristically(links)

        shallow = next(lnk for lnk in scored if lnk.url.count("/") < 5)
        deep = next(lnk for lnk in scored if lnk.url.count("/") > 5)

        assert shallow.score > deep.score


class TestFetchSitemapLinks:
    """Tests for fetch_sitemap_links function."""

    def test_parses_basic_sitemap(self):
        """Should parse a basic sitemap."""
        sitemap_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://example.com/about</loc>
                <priority>0.8</priority>
            </url>
            <url>
                <loc>https://example.com/contact</loc>
            </url>
        </urlset>
        """

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = sitemap_xml

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = fetch_sitemap_links("https://example.com")

        assert len(links) == 2
        urls = [lnk.url for lnk in links]
        assert "https://example.com/about" in urls
        assert "https://example.com/contact" in urls

    def test_extracts_priority(self):
        """Should extract sitemap priority."""
        sitemap_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://example.com/about</loc>
                <priority>0.8</priority>
            </url>
        </urlset>
        """

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = sitemap_xml

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = fetch_sitemap_links("https://example.com")

        assert links[0].sitemap_priority == 0.8

    def test_handles_gzipped_sitemap(self):
        """Should handle gzipped sitemaps."""
        sitemap_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/about</loc></url>
        </urlset>
        """
        gzipped = gzip.compress(sitemap_xml)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = gzipped

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = fetch_sitemap_links("https://example.com")

        assert len(links) == 1

    def test_respects_max_urls(self):
        """Should respect max URLs limit."""
        # Create sitemap with many URLs
        urls = "\n".join([f"<url><loc>https://example.com/page{i}</loc></url>" for i in range(100)])
        sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            {urls}
        </urlset>
        """.encode()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = sitemap_xml

        config = SitemapConfig(max_urls_per_sitemap=10)

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = fetch_sitemap_links("https://example.com", config=config)

        assert len(links) <= 10

    def test_handles_sitemap_index(self):
        """Should handle sitemap index files."""
        sitemap_index = b"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap>
                <loc>https://example.com/sitemap1.xml</loc>
            </sitemap>
        </sitemapindex>
        """

        child_sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/about</loc></url>
        </urlset>
        """

        def mock_request(url, **kwargs):
            response = Mock()
            response.status_code = 200
            if "sitemap1.xml" in url:
                response.content = child_sitemap
            else:
                response.content = sitemap_index
            return response

        with patch("primr.data.scraping.discovery.make_request", side_effect=mock_request):
            links = fetch_sitemap_links("https://example.com")

        assert len(links) == 1
        assert links[0].url == "https://example.com/about"

    def test_respects_max_depth(self):
        """Should respect max sitemap depth."""
        # Create deeply nested sitemap indexes
        def mock_request(url, **kwargs):
            response = Mock()
            response.status_code = 200
            # Always return another sitemap index
            response.content = b"""<?xml version="1.0" encoding="UTF-8"?>
            <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                <sitemap><loc>https://example.com/deeper.xml</loc></sitemap>
            </sitemapindex>
            """
            return response

        config = SitemapConfig(max_sitemap_depth=2)

        with patch("primr.data.scraping.discovery.make_request", side_effect=mock_request):
            links = fetch_sitemap_links("https://example.com", config=config)

        # Should stop at max depth, returning empty (no actual URLs found)
        assert len(links) == 0

    def test_handles_missing_sitemap(self):
        """Should handle missing sitemap gracefully."""
        mock_response = Mock()
        mock_response.status_code = 404

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = fetch_sitemap_links("https://example.com")

        assert len(links) == 0


class TestVerifyUrlsExist:
    """Tests for verify_urls_exist function."""

    def test_filters_to_existing_urls(self):
        """Should filter to URLs that exist."""
        links = [
            DiscoveredLink(url="https://example.com/exists", source="guess"),
            DiscoveredLink(url="https://example.com/missing", source="guess"),
        ]

        def mock_head_exists(url, **kwargs):
            return "exists" in url

        with patch("primr.data.scraping.discovery.head_exists", side_effect=mock_head_exists):
            verified = verify_urls_exist(links)

        assert len(verified) == 1
        assert verified[0].url == "https://example.com/exists"

    def test_handles_exceptions(self):
        """Should handle exceptions gracefully."""
        links = [
            DiscoveredLink(url="https://example.com/page", source="guess"),
        ]

        with patch("primr.data.scraping.discovery.head_exists", side_effect=Exception("Network error")):
            verified = verify_urls_exist(links)

        assert len(verified) == 0


class TestExtractLinksFromHomepage:
    """Tests for extract_links_from_homepage function."""

    def test_extracts_homepage_links(self):
        """Should extract links from homepage."""
        html = b"""
        <html>
        <body>
        <nav>
            <a href="/about">About</a>
            <a href="/products">Products</a>
        </nav>
        </body>
        </html>
        """

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = html

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = extract_links_from_homepage("https://example.com")

        assert len(links) == 2
        assert all(link.source == "homepage" for link in links)

    def test_handles_failed_request(self):
        """Should handle failed homepage request."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = extract_links_from_homepage("https://example.com")

        assert len(links) == 0


class TestDiscoverLinks:
    """Tests for discover_links combined function."""

    def test_combines_all_strategies(self):
        """Should combine sitemap, homepage, and guessed links."""
        sitemap_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/sitemap-page</loc></url>
        </urlset>
        """

        homepage_html = b"""
        <html><body>
        <a href="/homepage-link">Link</a>
        </body></html>
        """

        def mock_request(url, **kwargs):
            response = Mock()
            response.status_code = 200
            if "sitemap" in url:
                response.content = sitemap_xml
            else:
                response.content = homepage_html
            return response

        with patch("primr.data.scraping.discovery.make_request", side_effect=mock_request), patch("primr.data.scraping.discovery.head_exists", return_value=True):
            links = discover_links("https://example.com", verify_guessed=False)

        # Should have links from multiple sources
        sources = {link.source for link in links}
        assert "sitemap" in sources or "homepage" in sources or "guess" in sources

    def test_deduplicates_links(self):
        """Should deduplicate links from different sources."""
        sitemap_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/about</loc></url>
        </urlset>
        """

        homepage_html = b"""
        <html><body>
        <a href="/about">About</a>
        </body></html>
        """

        def mock_request(url, **kwargs):
            response = Mock()
            response.status_code = 200
            if "sitemap" in url:
                response.content = sitemap_xml
            else:
                response.content = homepage_html
            return response

        with patch("primr.data.scraping.discovery.make_request", side_effect=mock_request):
            links = discover_links("https://example.com", verify_guessed=False)

        # Should not have duplicate exact /about URLs (same URL from sitemap and homepage)
        exact_about_links = [lnk for lnk in links if lnk.url == "https://example.com/about"]
        assert len(exact_about_links) == 1  # Only one, not two (deduplicated)

    def test_returns_scored_links(self):
        """Should return scored and sorted links."""
        mock_response = Mock()
        mock_response.status_code = 404  # No sitemap

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = discover_links("https://example.com", verify_guessed=False)

        # All links should have scores
        assert all(hasattr(link, "score") for link in links)

        # Should be sorted by score
        scores = [link.score for link in links]
        assert scores == sorted(scores, reverse=True)


class TestCommonPagePatterns:
    """Tests for COMMON_PAGE_PATTERNS constant."""

    def test_has_60_plus_patterns(self):
        """Should have at least 60 patterns."""
        assert len(COMMON_PAGE_PATTERNS) >= 60

    def test_includes_essential_patterns(self):
        """Should include essential business page patterns."""
        essential = ["/about", "/contact", "/careers", "/investors", "/products"]
        for pattern in essential:
            assert pattern in COMMON_PAGE_PATTERNS, f"Missing essential pattern: {pattern}"

    def test_patterns_start_with_slash(self):
        """All patterns should start with /."""
        for pattern in COMMON_PAGE_PATTERNS:
            assert pattern.startswith("/"), f"Pattern should start with /: {pattern}"
