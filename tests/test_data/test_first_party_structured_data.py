"""Tests for first-party JSON-LD fallback recovery."""

from __future__ import annotations

import json

from primr.data.first_party_structured_data import (
    fetch_structured_data_content,
    fetch_structured_data_pages,
)


def _json_ld_html(payload: object) -> bytes:
    return (
        '<html><head><script type="application/ld+json">'
        + json.dumps(payload)
        + "</script></head><body>ok</body></html>"
    ).encode()


def test_fetch_structured_data_pages_reads_graph_and_filters_offsite_urls():
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "name": "Acme Corp",
                "url": "https://acme.example/",
                "sameAs": ["https://evil.example/acme"],
                "description": "Acme builds durable industrial widgets for regulated manufacturers.",
            },
            {
                "@type": "NewsArticle",
                "headline": "Acme launches resilient widget platform",
                "mainEntityOfPage": {"@id": "https://acme.example/news/widget-platform"},
                "datePublished": "2026-06-01",
                "publisher": {"name": "Acme Newsroom"},
                "description": "The platform launch expands Acme's automation portfolio globally.",
            },
        ],
    }

    def fake_http(url: str, **_kwargs):
        if url == "https://acme.example/":
            return 200, _json_ld_html(payload), url
        return 404, None, None

    pages = fetch_structured_data_pages("acme.example", http_get=fake_http)

    assert len(pages) == 1
    assert pages[0].url == "https://acme.example/"
    assert pages[0].metadata["entity_count"] == 2
    assert pages[0].metadata["json_ld_blocks"] == 1
    assert "Organization" in pages[0].content
    assert "Acme Corp" in pages[0].content
    assert "NewsArticle" in pages[0].content
    assert "Acme launches resilient widget platform" in pages[0].content
    assert "2026-06-01" in pages[0].content
    assert "evil.example" not in pages[0].content


def test_fetch_structured_data_pages_probes_common_paths_when_homepage_has_none():
    about_payload = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Acme Industrial",
        "url": "https://acme.example/about",
        "description": "Acme Industrial supplies plant operators with monitoring hardware, analytics, and services.",
    }
    calls: list[str] = []

    def fake_http(url: str, **_kwargs):
        calls.append(url)
        if url == "https://acme.example/":
            return 200, b"<html><body>no structured data</body></html>", url
        if url == "https://acme.example/about":
            return 200, _json_ld_html(about_payload), url
        return 404, None, None

    pages = fetch_structured_data_pages("acme.example", http_get=fake_http)

    assert len(pages) == 1
    assert pages[0].metadata["path"] == "/about"
    assert "Acme Industrial" in pages[0].content
    assert "https://acme.example/about" in pages[0].content
    assert calls[:3] == [
        "https://acme.example/",
        "https://www.acme.example/",
        "https://acme.example/about",
    ]


def test_fetch_structured_data_pages_ignores_malformed_json():
    malformed = b"""
    <html><head><script type="application/ld+json">{not json</script></head></html>
    """

    def fake_http(url: str, **_kwargs):
        return 200, malformed, url

    pages = fetch_structured_data_pages("acme.example", http_get=fake_http, max_probe_urls=1)

    assert pages == []


def test_fetch_structured_data_pages_drops_offsite_url_only_entities():
    payload = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Mirror Listing",
        "url": "https://evil.example/acme",
    }

    def fake_http(url: str, **_kwargs):
        return 200, _json_ld_html(payload), url

    pages = fetch_structured_data_pages("acme.example", http_get=fake_http, max_probe_urls=1)

    assert pages == []


def test_fetch_structured_data_content_returns_fallback_pages():
    payload = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Acme Fallback",
        "url": "https://acme.example/",
        "description": "Acme Fallback publishes machine-readable company facts on its public homepage.",
    }

    def fake_http(url: str, **_kwargs):
        return 200, _json_ld_html(payload), url

    pages = fetch_structured_data_content("acme.example", http_get=fake_http)

    assert len(pages) == 1
    assert pages[0].source == "structured_data"
    assert pages[0].title == "First-party structured data"
    assert "Acme Fallback" in pages[0].content
