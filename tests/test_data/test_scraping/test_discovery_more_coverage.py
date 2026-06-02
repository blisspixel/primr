"""Further coverage for the link-discovery module.

Targets branches still uncovered after test_discovery.py: the SPA / JS
link-extraction families (Angular, Vue, React, data-*, JS path strings,
onclick handlers, non-anchor href), ``is_probably_content_url`` edge cases,
sitemap failure / size / max-url paths, and the ``discover_links``
organization-type branches (government skip, sitemap fallback, guess
verification skip). All pure logic or fully mocked network — no real HTTP.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from primr.data.scraping.config import SitemapConfig
from primr.data.scraping.discovery import (
    DiscoveredLink,
    discover_links,
    extract_links_from_html,
    fetch_sitemap_links,
    is_probably_content_url,
    score_links_heuristically,
    verify_urls_exist,
)

# =============================================================================
# is_probably_content_url edges
# =============================================================================


class TestIsProbablyContentUrl:
    def test_malformed_url_returns_false(self):
        # urlparse raises ValueError on some bracketed IPv6-ish garbage.
        assert is_probably_content_url("http://[::1") is False

    def test_excluded_extension_rejected(self):
        assert is_probably_content_url("https://example.com/file.pdf") is False

    def test_manifest_rejected(self):
        assert is_probably_content_url("https://example.com/manifest.json") is False

    def test_query_preserved_in_normalization(self):
        # A normal content page with a query string is still content.
        assert is_probably_content_url("https://example.com/about?ref=nav") is True


# =============================================================================
# SPA / JS link-extraction families
# =============================================================================


class TestSpaLinkExtraction:
    def test_angular_routerlink(self):
        html = b'<div routerLink="/products" ng-href="/about">x</div>'
        links = extract_links_from_html(html, "https://example.com")
        urls = {lnk.url for lnk in links}
        assert "https://example.com/products" in urls
        assert "https://example.com/about" in urls

    def test_angular_array_routerlink(self):
        html = b"<div [routerLink]=\"['/leadership']\">x</div>"
        links = extract_links_from_html(html, "https://example.com")
        urls = {lnk.url for lnk in links}
        assert "https://example.com/leadership" in urls

    def test_vue_bindings(self):
        html = b'<router-link to="/solutions">x</router-link><a :href="/news">n</a>'
        links = extract_links_from_html(html, "https://example.com")
        urls = {lnk.url for lnk in links}
        assert "https://example.com/solutions" in urls
        assert "https://example.com/news" in urls

    def test_vue_colon_to_binding(self):
        html = b'<a :to="/platform">Platform</a>'
        links = extract_links_from_html(html, "https://example.com")
        urls = {lnk.url for lnk in links}
        assert "https://example.com/platform" in urls

    def test_react_link_to(self):
        html = b'<Link to="/customers">x</Link><NavLink to="/team">t</NavLink>'
        links = extract_links_from_html(html, "https://example.com")
        urls = {lnk.url for lnk in links}
        assert "https://example.com/customers" in urls
        assert "https://example.com/team" in urls

    def test_data_attributes(self):
        html = b'<div data-href="/about" data-url="/contact" data-path="/blog">x</div>'
        links = extract_links_from_html(html, "https://example.com")
        urls = {lnk.url for lnk in links}
        assert "https://example.com/about" in urls
        assert "https://example.com/contact" in urls
        assert "https://example.com/blog" in urls

    def test_js_path_strings(self):
        html = b'<script>const routes = ["/about", "/products/cloud"];</script>'
        links = extract_links_from_html(html, "https://example.com")
        urls = {lnk.url for lnk in links}
        assert "https://example.com/about" in urls
        assert "https://example.com/products/cloud" in urls

    def test_js_path_skips_assets_and_api(self):
        html = b'<script>x = ["/static/app.js", "/api/v1/users", "/_next/data"];</script>'
        links = extract_links_from_html(html, "https://example.com")
        assert links == []

    def test_onclick_navigation(self):
        html = b"<button onclick=\"window.location='/careers'\">Jobs</button>"
        links = extract_links_from_html(html, "https://example.com")
        urls = {lnk.url for lnk in links}
        assert "https://example.com/careers" in urls

    def test_non_anchor_href(self):
        html = b'<button href="/investor">Investors</button>'
        links = extract_links_from_html(html, "https://example.com")
        urls = {lnk.url for lnk in links}
        assert "https://example.com/investor" in urls

    def test_decode_failure_returns_empty(self):
        class Bad:
            def decode(self, *a, **k):
                raise AttributeError("boom")

        assert extract_links_from_html(Bad(), "https://example.com") == []

    def test_trailing_slash_normalized(self):
        html = b'<a href="/about/">About</a>'
        links = extract_links_from_html(html, "https://example.com")
        assert links[0].url == "https://example.com/about"

    def test_too_short_href_skipped(self):
        html = b'<a href="/">root</a>'
        links = extract_links_from_html(html, "https://example.com")
        # "/" is length 1 -> skipped by the len < 2 guard.
        assert links == []


# =============================================================================
# Heuristic scoring extra branches
# =============================================================================


class TestScoringBranches:
    def test_non_government_rewards_public_sector_tokens(self):
        links = [
            DiscoveredLink(url="https://example.com/procurement", source="html"),
            DiscoveredLink(url="https://example.com/random", source="html"),
        ]
        scored = score_links_heuristically(links, organization_type="commercial")
        proc = next(lnk for lnk in scored if "procurement" in lnk.url)
        rand = next(lnk for lnk in scored if "random" in lnk.url)
        assert proc.score > rand.score

    def test_homepage_source_bonus(self):
        links = [
            DiscoveredLink(url="https://example.com/page", source="homepage"),
            DiscoveredLink(url="https://example.com/page", source="guess"),
        ]
        scored = score_links_heuristically(links)
        # Same URL/keywords; homepage source gets +3 vs guess +0.
        homepage = next(lnk for lnk in scored if lnk.source == "homepage")
        guess = next(lnk for lnk in scored if lnk.source == "guess")
        assert homepage.score > guess.score

    def test_org_specific_high_value_keyword(self):
        links = [
            DiscoveredLink(url="https://uni.example/research", source="html"),
            DiscoveredLink(url="https://uni.example/misc", source="html"),
        ]
        scored = score_links_heuristically(links, organization_type="education")
        research = next(lnk for lnk in scored if "research" in lnk.url)
        misc = next(lnk for lnk in scored if "misc" in lnk.url)
        assert research.score > misc.score


# =============================================================================
# Sitemap failure / size / cap paths
# =============================================================================


class TestSitemapEdges:
    def test_fetch_exception_returns_empty(self):
        with patch(
            "primr.data.scraping.discovery.make_request",
            side_effect=Exception("connection reset"),
        ):
            assert fetch_sitemap_links("https://example.com") == []

    def test_parse_error_returns_empty(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"<<<not valid xml at all>>>"
        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            assert fetch_sitemap_links("https://example.com") == []

    def test_bad_gzip_returns_empty(self):
        mock_response = Mock()
        mock_response.status_code = 200
        # .gz URL but not actually gzipped -> decompress fails -> empty.
        mock_response.content = b"\x1f\x8bnot really gzip"
        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = fetch_sitemap_links("https://example.com")
        assert links == []

    def test_large_sitemap_logs_but_parses(self):
        # Build a >0.001MB sitemap and set the cap tiny so the size warning fires.
        urls = "".join(f"<url><loc>https://example.com/p{i}</loc></url>" for i in range(50))
        xml = (
            '<?xml version="1.0"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{urls}</urlset>"
        ).encode()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = xml
        config = SitemapConfig(max_sitemap_size_mb=0.00001)
        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = fetch_sitemap_links("https://example.com", config=config)
        assert len(links) == 50

    def test_loc_missing_text_skipped(self):
        xml = (
            b'<?xml version="1.0"?>'
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b"<url><loc></loc></url>"
            b"<url><loc>https://example.com/good</loc></url>"
            b"</urlset>"
        )
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = xml
        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = fetch_sitemap_links("https://example.com")
        assert [lnk.url for lnk in links] == ["https://example.com/good"]


class TestVerifyUrlsEmpty:
    def test_empty_input_returns_empty(self):
        assert verify_urls_exist([]) == []


# =============================================================================
# discover_links organization-type branches
# =============================================================================


class TestDiscoverLinksOrgBranches:
    def test_government_skips_guessing(self):
        """Government org-type should not emit 'guess'-sourced links."""
        homepage_html = b'<html><body><a href="/budget">Budget</a></body></html>'
        mock_response = Mock()
        mock_response.status_code = 404  # no sitemap

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = discover_links(
                "https://agency.example",
                homepage_html=homepage_html,
                organization_type="government",
            )

        assert all(lnk.source != "guess" for lnk in links)

    def test_commercial_adds_guesses_when_few_links(self):
        """With few homepage links, commercial sites add guessed URLs."""
        homepage_html = b'<html><body><a href="/about">About</a></body></html>'
        mock_response = Mock()
        mock_response.status_code = 404

        with patch("primr.data.scraping.discovery.make_request", return_value=mock_response):
            links = discover_links(
                "https://example.com",
                homepage_html=homepage_html,
                organization_type="commercial",
                verify_guessed=False,
            )

        assert any(lnk.source == "guess" for lnk in links)

    def test_skips_sitemap_when_enough_links(self):
        """With many homepage links, the sitemap fetch is skipped entirely."""
        anchors = "".join(f'<a href="/page{i}">Page {i} about products</a>' for i in range(30))
        homepage_html = f"<html><body>{anchors}</body></html>".encode()

        called = {"n": 0}

        def mock_request(url, **kwargs):
            called["n"] += 1
            resp = Mock()
            resp.status_code = 404
            return resp

        with patch("primr.data.scraping.discovery.make_request", side_effect=mock_request):
            links = discover_links(
                "https://example.com",
                homepage_html=homepage_html,
                organization_type="commercial",
                min_links_before_sitemap=20,
            )

        # >=20 homepage links -> no make_request calls for sitemap/guess.
        assert called["n"] == 0
        assert len(links) >= 20

    def test_verify_guessed_skips_when_already_have_links(self):
        """verify_guessed=True but enough links -> unverified guesses dropped."""
        anchors = "".join(
            f'<a href="/p{i}">Page {i} about company leadership news</a>' for i in range(16)
        )
        homepage_html = f"<html><body>{anchors}</body></html>".encode()
        mock_response = Mock()
        mock_response.status_code = 404

        with (
            patch("primr.data.scraping.discovery.make_request", return_value=mock_response),
            patch("primr.data.scraping.discovery.verify_urls_exist") as mock_verify,
        ):
            links = discover_links(
                "https://example.com",
                homepage_html=homepage_html,
                organization_type="commercial",
                verify_guessed=True,
                min_links_to_skip_verify=15,
                min_links_before_sitemap=20,
            )

        # 16 homepage links >= min_links_to_skip_verify(15): verification skipped,
        # guesses dropped.
        mock_verify.assert_not_called()
        assert all(lnk.source != "guess" for lnk in links)
