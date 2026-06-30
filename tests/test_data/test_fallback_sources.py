"""Tests for the public-data fallback sources.

These tests use mocked HTTP responses so they run without network and don't
depend on any real company's website, Wikipedia article, or EDGAR filing.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from primr.data.fallback_sources import (
    FallbackPage,
    _discover_feed_urls,
    _normalize_company_name,
    _parse_feed,
    _same_site,
    _strip_html,
    fetch_feed_content,
    find_edgar_cik,
    find_wikipedia_title,
    gather_fallback_content,
)

# =============================================================================
# Normalization
# =============================================================================


def test_normalize_company_name_strips_trailing_suffix():
    assert _normalize_company_name("Example Inc.") == "example"
    assert _normalize_company_name("Global Corp.") == "global"
    assert _normalize_company_name("WidgetCo LLC") == "widgetco"
    assert _normalize_company_name("Example PLC") == "example"
    # One suffix stripped per call (last-suffix-wins); chained stripping
    # would risk mangling legitimate trailing words.
    assert _normalize_company_name("Acme Holdings Inc") == "acme holdings"


def test_normalize_company_name_preserves_core_name():
    assert _normalize_company_name("Example International") == "example international"
    assert _normalize_company_name("Alpha Beta Gamma") == "alpha beta gamma"


# =============================================================================
# EDGAR CIK resolution
# =============================================================================


def test_find_edgar_cik_exact_match():
    fake_index_body = json.dumps(
        {
            "0": {"cik_str": 1234567, "ticker": "EXMP", "title": "Example Holdings Inc."},
            "1": {"cik_str": 7654321, "ticker": "WGT", "title": "Widget Corp"},
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, fake_index_body, None),
    ):
        # Clear the module-level cache
        import primr.data.fallback_sources as fb

        fb._ticker_index_cache = None

        result = find_edgar_cik("Example Holdings Inc.")
        assert result is not None
        cik, ticker, canonical = result
        assert cik == "0001234567"
        assert ticker == "EXMP"
        assert canonical == "Example Holdings Inc."


def test_edgar_index_keeps_first_on_duplicate_title():
    """Multi-class share lines share a title; the FIRST (primary) row must win
    rather than being silently overwritten by a later secondary class."""
    body = json.dumps(
        {
            "0": {"cik_str": 111, "ticker": "PRIMARY", "title": "Dup Holdings Inc."},
            "1": {"cik_str": 111, "ticker": "SECONDARY", "title": "Dup Holdings Inc."},
        }
    ).encode()
    with patch("primr.data.fallback_sources._http_get", return_value=(200, body, None)):
        import primr.data.fallback_sources as fb

        fb._ticker_index_cache = None
        result = find_edgar_cik("Dup Holdings Inc.")
        assert result is not None
        _, ticker, _ = result
        assert ticker == "PRIMARY"


def test_gather_fallback_content_no_duplicates_on_timeout():
    """On the as_completed timeout path, a source drained by the loop must NOT
    be collected a second time by the timeout handler (which double-counted
    recovered pages into the corpus)."""
    import primr.data.fallback_sources as fb

    def _page(src):
        return [FallbackPage(url=f"https://{src}", source=src, content=f"{src} text " * 60)]

    real_as_completed = fb.as_completed

    def fake_as_completed(fmap, timeout=None):
        # Drain exactly one future in the loop (it finished before the
        # deadline), then trip the deadline with the rest still "pending" so
        # the timeout handler runs over every future.
        first = next(iter(fmap))
        # Make sure it has really completed before we hand it back.
        real_as_completed([first], timeout=5)
        yield first
        raise TimeoutError

    with (
        patch.object(fb, "as_completed", fake_as_completed),
        patch.object(fb, "fetch_subdomain_content", lambda *a, **k: _page("subdomain")),
        patch.object(fb, "fetch_feed_content", lambda *a, **k: _page("feed")),
        patch.object(
            fb,
            "fetch_structured_data_content",
            lambda *a, **k: _page("structured_data"),
        ),
        patch.object(fb, "fetch_edgar_content", lambda *a, **k: _page("edgar")),
        patch.object(fb, "fetch_wikipedia_content", lambda *a, **k: _page("wikipedia")),
    ):
        pages = gather_fallback_content(
            company_name="Example Inc.",
            website="https://example.com/",
            wayback_urls=None,
            grok_surrogate_urls=None,
        )

    sources = [p.source for p in pages]
    # Every source appears at most once — no duplication from the timeout path.
    assert len(sources) == len(set(sources)), f"duplicate sources: {sources}"


def test_find_edgar_cik_fuzzy_substring_match():
    fake_index_body = json.dumps(
        {
            "0": {"cik_str": 1234567, "ticker": "EXMP", "title": "Example Holdings Inc."},
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, fake_index_body, None),
    ):
        import primr.data.fallback_sources as fb

        fb._ticker_index_cache = None

        # Lookup with just "Example" should match "Example Holdings Inc."
        result = find_edgar_cik("Example")
        assert result is not None
        cik, ticker, _ = result
        assert ticker == "EXMP"


def test_find_edgar_cik_no_match_returns_none():
    fake_index_body = json.dumps(
        {
            "0": {"cik_str": 1234567, "ticker": "EXMP", "title": "Example Holdings Inc."},
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, fake_index_body, None),
    ):
        import primr.data.fallback_sources as fb

        fb._ticker_index_cache = None

        result = find_edgar_cik("Nonexistent Widget Company LLC")
        assert result is None


def test_find_edgar_cik_handles_index_fetch_failure():
    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(403, None, None),
    ):
        import primr.data.fallback_sources as fb

        fb._ticker_index_cache = None

        result = find_edgar_cik("Example Inc.")
        assert result is None


# =============================================================================
# Wikipedia lookup
# =============================================================================


def test_find_wikipedia_title_prefers_matching_title():
    search_response = json.dumps(
        {
            "query": {
                "search": [
                    {"title": "Unrelated Article", "snippet": "..."},
                    {"title": "Example Holdings", "snippet": "..."},
                ]
            }
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, search_response, None),
    ):
        title = find_wikipedia_title("Example Holdings Inc.")
        assert title == "Example Holdings"


def test_find_wikipedia_title_falls_back_to_top_hit():
    search_response = json.dumps(
        {
            "query": {
                "search": [
                    {"title": "Some Other Article", "snippet": "..."},
                ]
            }
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, search_response, None),
    ):
        title = find_wikipedia_title("Completely Unrelated Name")
        assert title == "Some Other Article"


def test_find_wikipedia_title_empty_results():
    search_response = json.dumps({"query": {"search": []}}).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, search_response, None),
    ):
        title = find_wikipedia_title("Anything")
        assert title is None


# =============================================================================
# Parallel fan-out contract
# =============================================================================


def test_gather_fallback_content_merges_all_sources():
    """Fan-out collects pages from every source that returns something."""
    fake_pages_by_source = {
        "wikipedia": [FallbackPage(url="https://w", source="wikipedia", content="wiki text " * 60)],
        "edgar": [FallbackPage(url="https://e", source="edgar", content="10-K text " * 300)],
        "subdomain": [FallbackPage(url="https://s", source="subdomain", content="IR text " * 80)],
        "feed": [FallbackPage(url="https://f", source="feed", content="feed text " * 40)],
        "structured_data": [
            FallbackPage(
                url="https://sd",
                source="structured_data",
                content="schema text " * 40,
            )
        ],
        "wayback": [FallbackPage(url="https://y", source="wayback", content="archive text " * 100)],
        "grok": [FallbackPage(url="https://g", source="grok", content="grok synth text " * 50)],
    }

    def fake_subdomain(base_host, **_kwargs):
        return fake_pages_by_source["subdomain"]

    def fake_feed(base_host, **_kwargs):
        return fake_pages_by_source["feed"]

    def fake_structured_data(base_host, **_kwargs):
        return fake_pages_by_source["structured_data"]

    def fake_edgar(name, **_kwargs):
        return fake_pages_by_source["edgar"]

    def fake_wikipedia(name, **_kwargs):
        return fake_pages_by_source["wikipedia"]

    def fake_wayback(urls, **_kwargs):
        return fake_pages_by_source["wayback"]

    def fake_grok(urls, name, **_kwargs):
        return fake_pages_by_source["grok"]

    with (
        patch("primr.data.fallback_sources.fetch_subdomain_content", side_effect=fake_subdomain),
        patch("primr.data.fallback_sources.fetch_feed_content", side_effect=fake_feed),
        patch(
            "primr.data.fallback_sources.fetch_structured_data_content",
            side_effect=fake_structured_data,
        ),
        patch("primr.data.fallback_sources.fetch_edgar_content", side_effect=fake_edgar),
        patch("primr.data.fallback_sources.fetch_wikipedia_content", side_effect=fake_wikipedia),
        patch("primr.data.fallback_sources.fetch_wayback_pages", side_effect=fake_wayback),
        patch("primr.data.fallback_sources.fetch_grok_surrogates", side_effect=fake_grok),
    ):
        pages = gather_fallback_content(
            company_name="Example Inc.",
            website="https://example.com/",
            wayback_urls=["https://example.com/about"],
            grok_surrogate_urls=["https://example.com/about"],
        )

    sources = sorted(p.source for p in pages)
    assert sources == [
        "edgar",
        "feed",
        "grok",
        "structured_data",
        "subdomain",
        "wayback",
        "wikipedia",
    ]


def test_gather_fallback_content_tolerates_individual_source_failure():
    """A raising source does not prevent others from contributing."""
    good_page = FallbackPage(url="https://w", source="wikipedia", content="wiki text " * 60)

    def raises(*_args, **_kwargs):
        raise RuntimeError("simulated outage")

    with (
        patch("primr.data.fallback_sources.fetch_subdomain_content", side_effect=raises),
        patch("primr.data.fallback_sources.fetch_feed_content", side_effect=raises),
        patch("primr.data.fallback_sources.fetch_structured_data_content", side_effect=raises),
        patch("primr.data.fallback_sources.fetch_edgar_content", side_effect=raises),
        patch("primr.data.fallback_sources.fetch_wikipedia_content", return_value=[good_page]),
        patch("primr.data.fallback_sources.fetch_wayback_pages", side_effect=raises),
    ):
        pages = gather_fallback_content(
            company_name="Example Inc.",
            website="https://example.com/",
            wayback_urls=[],
        )

    assert len(pages) == 1
    assert pages[0].source == "wikipedia"


def test_gather_fallback_content_returns_empty_when_all_sources_empty():
    with (
        patch("primr.data.fallback_sources.fetch_subdomain_content", return_value=[]),
        patch("primr.data.fallback_sources.fetch_feed_content", return_value=[]),
        patch("primr.data.fallback_sources.fetch_structured_data_content", return_value=[]),
        patch("primr.data.fallback_sources.fetch_edgar_content", return_value=[]),
        patch("primr.data.fallback_sources.fetch_wikipedia_content", return_value=[]),
        patch("primr.data.fallback_sources.fetch_wayback_pages", return_value=[]),
    ):
        pages = gather_fallback_content(
            company_name="Example Inc.",
            website="https://example.com/",
            wayback_urls=["https://example.com/about"],
        )

    assert pages == []


# =============================================================================
# RSS / Atom feed recovery
# =============================================================================

RSS_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Acme Newsroom</title>
    <link>https://acme.example/news</link>
    <item>
      <title>Acme launches widget</title>
      <link>https://acme.example/news/1</link>
      <description>&lt;p&gt;The new widget ships today.&lt;/p&gt;</description>
    </item>
    <item>
      <title>Acme hires CFO</title>
      <link>https://acme.example/news/2</link>
      <description>Leadership update.</description>
    </item>
  </channel>
</rss>
"""

ATOM_FIXTURE = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Acme Blog</title>
  <entry>
    <title>Engineering update</title>
    <link href="https://acme.example/blog/1" rel="alternate"/>
    <summary>We scaled the platform.</summary>
  </entry>
</feed>
"""

HOMEPAGE_WITH_AUTODISCOVERY = (
    b"<html><head>"
    b'<link rel="alternate" type="application/rss+xml" title="Acme" href="/news/rss.xml">'
    b"</head><body>hi</body></html>"
)


def test_strip_html_flattens_and_unescapes():
    assert _strip_html("<p>Hello &amp; welcome</p>") == "Hello & welcome"


def test_strip_html_caps_length():
    assert len(_strip_html("x" * 1000, limit=50)) == 50


def test_same_site_matches_apex_www_and_subdomain():
    assert _same_site("acme.example", "acme.example")
    assert _same_site("www.acme.example", "acme.example")
    assert _same_site("news.acme.example", "acme.example")


def test_same_site_rejects_offsite_and_lookalike():
    assert not _same_site("evil.example", "acme.example")
    assert not _same_site("acme.example.evil.com", "acme.example")
    assert not _same_site("", "acme.example")
    # endswith-style false match guard: must be a real subdomain, not a suffix.
    assert not _same_site("notacme.example", "acme.example")


def test_parse_feed_rss():
    title, items = _parse_feed(RSS_FIXTURE)
    assert title == "Acme Newsroom"
    assert len(items) == 2
    assert items[0]["title"] == "Acme launches widget"
    assert items[0]["link"] == "https://acme.example/news/1"
    assert "widget ships today" in items[0]["summary"]
    # HTML in the description is flattened out.
    assert "<p>" not in items[0]["summary"]


def test_parse_feed_atom():
    title, items = _parse_feed(ATOM_FIXTURE)
    assert title == "Acme Blog"
    assert len(items) == 1
    assert items[0]["title"] == "Engineering update"
    # Atom link is the rel=alternate href attribute, not element text.
    assert items[0]["link"] == "https://acme.example/blog/1"
    assert "scaled the platform" in items[0]["summary"]


def test_parse_feed_malformed_returns_empty():
    assert _parse_feed(b"<not valid xml <<<") == (None, [])


def test_parse_feed_non_feed_xml_returns_empty():
    assert _parse_feed(b"<html><body>nope</body></html>") == (None, [])


def test_discover_feed_urls_autodiscovery_first_and_deduped():
    urls = _discover_feed_urls("acme.example", HOMEPAGE_WITH_AUTODISCOVERY)
    # Autodiscovered feed ranks ahead of the common-path sweep.
    assert urls[0] == "https://acme.example/news/rss.xml"
    assert "https://acme.example/feed" in urls
    # /news/rss.xml is also a common path; it must appear exactly once.
    assert urls.count("https://acme.example/news/rss.xml") == 1


def test_discover_feed_urls_drops_offsite_autodiscovery():
    homepage = (
        b'<html><head><link rel="alternate" type="application/rss+xml" '
        b'href="https://evil.example/feed"></head></html>'
    )
    urls = _discover_feed_urls("acme.example", homepage)
    assert all("evil.example" not in u for u in urls)


def test_discover_feed_urls_no_html_uses_common_paths():
    urls = _discover_feed_urls("acme.example", None)
    assert "https://acme.example/feed" in urls
    assert "https://acme.example/index.xml" in urls


def test_fetch_feed_content_via_autodiscovery():
    def fake_http(url, **_kwargs):
        if url == "https://acme.example/":
            return (200, HOMEPAGE_WITH_AUTODISCOVERY, url)
        if url == "https://acme.example/news/rss.xml":
            return (200, RSS_FIXTURE, url)
        return (404, None, None)

    with patch("primr.data.fallback_sources._http_get", side_effect=fake_http):
        pages = fetch_feed_content("acme.example")

    assert len(pages) == 1
    assert pages[0].source == "feed"
    assert pages[0].title == "Acme Newsroom"
    assert "Acme launches widget" in pages[0].content
    assert pages[0].metadata["item_count"] == 2


def test_fetch_feed_content_via_common_path_when_no_autodiscovery():
    homepage = b"<html><head></head><body>no feed link</body></html>"

    def fake_http(url, **_kwargs):
        if url in ("https://acme.example/", "https://www.acme.example/"):
            return (200, homepage, url)
        if url == "https://acme.example/feed":
            return (200, ATOM_FIXTURE, url)
        return (404, None, None)

    with patch("primr.data.fallback_sources._http_get", side_effect=fake_http):
        pages = fetch_feed_content("acme.example")

    assert len(pages) == 1
    assert pages[0].source == "feed"
    assert "Engineering update" in pages[0].content


def test_fetch_feed_content_returns_empty_when_no_feeds():
    def fake_http(url, **_kwargs):
        if url in ("https://acme.example/", "https://www.acme.example/"):
            return (200, b"<html><head></head><body>hi</body></html>", url)
        return (404, None, None)

    with patch("primr.data.fallback_sources._http_get", side_effect=fake_http):
        pages = fetch_feed_content("acme.example")

    assert pages == []


def test_fetch_feed_content_dedupes_items_across_feeds():
    feed_b = (
        b'<?xml version="1.0"?><rss version="2.0"><channel><title>Mirror</title>'
        b"<item><title>Acme launches widget</title>"
        b"<link>https://acme.example/news/1</link><description>dup</description></item>"
        b"<item><title>Third story</title>"
        b"<link>https://acme.example/news/3</link><description>new</description></item>"
        b"</channel></rss>"
    )

    def fake_http(url, **_kwargs):
        if url == "https://acme.example/":
            return (200, HOMEPAGE_WITH_AUTODISCOVERY, url)
        if url == "https://acme.example/news/rss.xml":
            return (200, RSS_FIXTURE, url)  # news/1, news/2
        if url == "https://acme.example/feed":
            return (200, feed_b, url)  # news/1 (dup), news/3
        return (404, None, None)

    with patch("primr.data.fallback_sources._http_get", side_effect=fake_http):
        pages = fetch_feed_content("acme.example")

    assert len(pages) == 2
    # news/1 is counted once: the mirror feed contributes only news/3.
    total_items = sum(p.metadata["item_count"] for p in pages)
    assert total_items == 3


# =============================================================================
# Feed recovery — review hardening (body cap, RDF, content precedence, dedup)
# =============================================================================

RDF_FIXTURE = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://acme.example/">
    <title>Acme RDF Feed</title>
    <link>https://acme.example/</link>
  </channel>
  <item rdf:about="https://acme.example/news/rdf-1">
    <title>RDF story one</title>
    <link>https://acme.example/news/rdf-1</link>
    <description>First RDF item body.</description>
  </item>
  <item rdf:about="https://acme.example/news/rdf-2">
    <title>RDF story two</title>
    <link>https://acme.example/news/rdf-2</link>
    <description>Second RDF item body.</description>
  </item>
</rdf:RDF>
"""


def test_parse_feed_rss10_rdf():
    title, items = _parse_feed(RDF_FIXTURE)
    assert title == "Acme RDF Feed"
    assert [i["title"] for i in items] == ["RDF story one", "RDF story two"]
    assert items[0]["link"] == "https://acme.example/news/rdf-1"
    assert "First RDF item body" in items[0]["summary"]


def test_parse_feed_oversized_body_refused():
    # A body over the cap is refused before parsing (DoS guard), even if valid XML.
    from primr.data.fallback_sources import _FEED_MAX_BYTES

    head = b'<?xml version="1.0"?><rss version="2.0"><channel><title>X</title>'
    padded = head + b"<!-- " + b"a" * (_FEED_MAX_BYTES + 1) + b" --></channel></rss>"
    assert _parse_feed(padded) == (None, [])


def test_parse_feed_prefers_content_encoded_over_short_description():
    # WordPress-style: short <description> teaser + full <content:encoded>.
    body = (
        b'<?xml version="1.0"?>'
        b'<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
        b"<channel><title>Blog</title>"
        b"<item><title>Post</title><link>https://acme.example/p/1</link>"
        b"<description>Short teaser.</description>"
        b"<content:encoded>&lt;p&gt;The full post body with much more detail than the teaser line.&lt;/p&gt;</content:encoded>"
        b"</item></channel></rss>"
    )
    _title, items = _parse_feed(body)
    assert len(items) == 1
    # The richer encoded body wins over the short teaser.
    assert "full post body" in items[0]["summary"]


def test_parse_feed_atom_xhtml_content_recovered():
    # Atom xhtml content lives in child elements; .text is whitespace-only.
    body = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Blog</title>'
        b"<entry><title>Post</title>"
        b'<link href="https://acme.example/p/1" rel="alternate"/>'
        b'<content type="xhtml">\n  <div>Real xhtml body content.</div>\n</content>'
        b"</entry></feed>"
    )
    _title, items = _parse_feed(body)
    assert len(items) == 1
    assert "Real xhtml body content" in items[0]["summary"]


def test_fetch_feed_content_keeps_summary_only_item():
    # An item with no title and no link but a real summary must survive (its
    # dedup key falls back to the summary).
    body = (
        b'<?xml version="1.0"?><rss version="2.0"><channel><title>News</title>'
        b"<item><description>Acme acquired Foo for two billion dollars.</description></item>"
        b"</channel></rss>"
    )

    def fake_http(url, **_kwargs):
        if url == "https://acme.example/":
            return (200, b"<html><head></head><body>hi</body></html>", url)
        if url == "https://acme.example/feed":
            return (200, body, url)
        return (404, None, None)

    with patch("primr.data.fallback_sources._http_get", side_effect=fake_http):
        pages = fetch_feed_content("acme.example")

    assert len(pages) == 1
    assert "acquired Foo" in pages[0].content


def test_fetch_feed_content_probes_www_when_apex_dead():
    # Apex returns nothing; www serves the homepage AND the feed. Common-path
    # probing must target the host that actually served the homepage (www).
    rss = (
        b'<?xml version="1.0"?><rss version="2.0"><channel><title>WWW Feed</title>'
        b"<item><title>WWW story</title><link>https://www.acme.example/n/1</link>"
        b"<description>body</description></item></channel></rss>"
    )

    def fake_http(url, **_kwargs):
        if url == "https://acme.example/":
            return (None, None, None)  # apex dead
        if url == "https://www.acme.example/":
            return (200, b"<html><head></head><body>hi</body></html>", url)
        if url == "https://www.acme.example/feed":
            return (200, rss, url)
        return (404, None, None)

    with patch("primr.data.fallback_sources._http_get", side_effect=fake_http):
        pages = fetch_feed_content("acme.example")

    assert len(pages) == 1
    assert pages[0].title == "WWW Feed"


def test_discover_feed_urls_drops_userinfo_offsite_href():
    # https://acme.example@evil.example/feed has hostname evil.example -> dropped.
    homepage = (
        b'<html><head><link rel="alternate" type="application/rss+xml" '
        b'href="https://acme.example@evil.example/feed"></head></html>'
    )
    urls = _discover_feed_urls("acme.example", homepage)
    assert all("evil.example" not in u for u in urls)


def test_find_edgar_cik_skips_empty_normalizing_title():
    """Regression (bug-hunt round): a ticker-index title that normalizes to ""
    used to match every short query ("" in target is always True), returning a
    wrong CIK. The empty-normalizing entry must be skipped."""
    index = {
        "": {"cik_str": 111, "ticker": "BAD", "title": ""},
        "acme widgets inc": {"cik_str": 222, "ticker": "ACME", "title": "Acme Widgets Inc"},
    }
    with patch("primr.data.fallback_sources._load_edgar_ticker_index", return_value=index):
        result = find_edgar_cik("Acme")
    assert result is not None
    _cik, ticker, _title = result
    assert ticker == "ACME"
