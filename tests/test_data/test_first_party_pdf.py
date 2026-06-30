"""Tests for first-party PDF fallback recovery."""

from __future__ import annotations

from unittest.mock import patch

from primr.data.first_party_pdf import (
    fetch_first_party_pdf_content,
    fetch_first_party_pdf_pages,
)


def test_fetch_first_party_pdf_pages_discovers_prioritized_same_site_links():
    homepage = b"""
    <html><body>
      <a href="/files/acme-annual-report.pdf">Annual report</a>
      <a href="https://evil.example/acme.pdf">Offsite report</a>
    </body></html>
    """
    calls: list[str] = []

    def fake_http(url: str, **_kwargs):
        calls.append(url)
        if url == "https://acme.example/":
            return 200, homepage, url
        if url == "https://acme.example/files/acme-annual-report.pdf":
            return 200, b"%PDF-1.7 annual report", url
        return 404, None, None

    with patch(
        "primr.data.scraping.content.extract_text_from_pdf",
        return_value="Annual report extracted text. " * 40,
    ) as extractor:
        pages = fetch_first_party_pdf_pages("acme.example", http_get=fake_http)

    assert len(pages) == 1
    assert pages[0].url == "https://acme.example/files/acme-annual-report.pdf"
    assert pages[0].title == "Annual report"
    assert pages[0].metadata["discovered_from"] == "https://acme.example/"
    assert pages[0].metadata["pdf_bytes"] == len(b"%PDF-1.7 annual report")
    assert "Annual report extracted text" in pages[0].content
    extractor.assert_called_once_with(b"%PDF-1.7 annual report")
    assert "https://evil.example/acme.pdf" not in calls


def test_fetch_first_party_pdf_pages_uses_direct_probe_when_landing_pages_miss():
    def fake_http(url: str, **_kwargs):
        if url == "https://acme.example/investors/annual-report.pdf":
            return 200, b"%PDF direct annual report", url
        return 404, None, None

    with patch(
        "primr.data.scraping.content.extract_text_from_pdf",
        return_value="Direct annual report extracted locally. " * 40,
    ):
        pages = fetch_first_party_pdf_pages(
            "acme.example",
            http_get=fake_http,
            max_landing_pages=1,
        )

    assert len(pages) == 1
    assert pages[0].url == "https://acme.example/investors/annual-report.pdf"
    assert pages[0].metadata["discovered_from"] == "direct-probe"


def test_fetch_first_party_pdf_pages_skips_non_pdf_and_short_extraction():
    homepage = b'<html><body><a href="/investors/annual-report.pdf">Report</a></body></html>'

    def fake_http(url: str, **_kwargs):
        if url == "https://acme.example/":
            return 200, homepage, url
        if url == "https://acme.example/investors/annual-report.pdf":
            return 200, b"<html>not a pdf</html>", url
        return 404, None, None

    pages = fetch_first_party_pdf_pages(
        "acme.example",
        http_get=fake_http,
        max_pdf_candidates=1,
    )

    assert pages == []


def test_fetch_first_party_pdf_pages_respects_byte_cap():
    homepage = b'<html><body><a href="/large.pdf">Large</a></body></html>'

    def fake_http(url: str, **_kwargs):
        if url == "https://acme.example/":
            return 200, homepage, url
        if url == "https://acme.example/large.pdf":
            return 200, b"%PDF" + b"x" * 50, url
        return 404, None, None

    with patch("primr.data.scraping.content.extract_text_from_pdf") as extractor:
        pages = fetch_first_party_pdf_pages(
            "acme.example",
            http_get=fake_http,
            max_pdf_candidates=1,
            max_pdf_bytes=10,
        )

    assert pages == []
    extractor.assert_not_called()


def test_fetch_first_party_pdf_content_returns_fallback_pages():
    def fake_http(url: str, **_kwargs):
        if url == "https://acme.example/investors/annual-report.pdf":
            return 200, b"%PDF report", url
        return 404, None, None

    with patch(
        "primr.data.scraping.content.extract_text_from_pdf",
        return_value="Fallback page PDF text. " * 40,
    ):
        pages = fetch_first_party_pdf_content("acme.example", http_get=fake_http)

    assert len(pages) == 1
    assert pages[0].source == "first_party_pdf"
    assert pages[0].title == "annual report"
    assert "Fallback page PDF text" in pages[0].content
