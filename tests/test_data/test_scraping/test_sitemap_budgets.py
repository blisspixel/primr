"""Bound each sitemap representation and the work shared by recursive indexes."""

import gzip
from types import SimpleNamespace

import pytest

from primr.data.scraping.config import SitemapConfig
from primr.data.scraping.discovery import fetch_sitemap_links

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def xml_urls(count=1):
    return (
        f"<urlset {NS}>"
        + "".join(
            f"<url><loc>https://example.com/p{i}</loc><priority>0.8</priority><lastmod>2026-01-01</lastmod></url>"
            for i in range(count)
        )
        + "</urlset>"
    ).encode()


def run(monkeypatch, fetch, **budgets):
    monkeypatch.setattr("primr.data.scraping.discovery.make_request", fetch)
    return fetch_sitemap_links("https://example.com", config=SitemapConfig(**budgets))


@pytest.mark.parametrize("compressed", [False, True])
def test_oversized_document_is_rejected(monkeypatch, compressed):
    raw = xml_urls(500)
    content = gzip.compress(raw) if compressed else raw
    assert (
        run(
            monkeypatch,
            lambda *a, **k: SimpleNamespace(status_code=200, content=content),
            max_sitemap_size_mb=0.01,
        )
        == []
    )


def test_regular_and_gzip_metadata_remain_intact(monkeypatch):
    for content in (xml_urls(), gzip.compress(xml_urls())):
        result = run(
            monkeypatch,
            lambda *a, body=content, **k: SimpleNamespace(status_code=200, content=body),
        )
        assert len(result) == 1
        assert result[0].url == "https://example.com/p0"
        assert result[0].sitemap_priority == 0.8
        assert result[0].sitemap_lastmod == "2026-01-01"


def test_wide_empty_children_consume_one_shared_attempt_budget(monkeypatch):
    calls = []
    index = (
        f"<sitemapindex {NS}>"
        + "".join(
            f"<sitemap><loc>https://example.com/child{i}.xml</loc></sitemap>" for i in range(100)
        )
        + "</sitemapindex>"
    ).encode()

    def fetch(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(
            status_code=200, content=index if url.endswith("/sitemap.xml") else xml_urls(0)
        )

    assert run(monkeypatch, fetch, max_sitemap_documents=5) == []
    assert len(calls) == 5
    assert calls[1:] == [f"https://example.com/child{i}.xml" for i in range(4)]


def test_failed_root_candidates_share_the_same_budget(monkeypatch):
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        raise OSError("unavailable")

    assert run(monkeypatch, fetch, max_sitemap_documents=2) == []
    assert len(calls) == 2


def test_recursive_work_stops_when_deadline_expires(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("primr.data.scraping.sitemap.time.monotonic", lambda: now[0])
    calls = []

    def fetch(url, **kwargs):
        calls.append(kwargs["timeout"])
        now[0] += 2
        return SimpleNamespace(status_code=200, content=xml_urls(0))

    assert run(monkeypatch, fetch, max_sitemap_seconds=3) == []
    assert calls == [3, 1]


def test_xml_node_and_depth_limits_apply_before_url_result_limit(monkeypatch):
    assert (
        run(
            monkeypatch,
            lambda *a, **k: SimpleNamespace(status_code=200, content=xml_urls(4)),
            max_sitemap_elements=5,
        )
        == []
    )
    nested = ("<x>" * 20 + "<loc>https://example.com</loc>" + "</x>" * 20).encode()
    assert (
        run(
            monkeypatch,
            lambda *a, **k: SimpleNamespace(status_code=200, content=nested),
            max_sitemap_xml_depth=10,
        )
        == []
    )


def test_malformed_tail_does_not_publish_partial_records(monkeypatch):
    malformed = xml_urls().replace(b"</urlset>", b"<broken>")
    assert (
        run(monkeypatch, lambda *a, **k: SimpleNamespace(status_code=200, content=malformed)) == []
    )


def test_aggregate_wire_allowance_is_passed_to_each_fetch(monkeypatch):
    limits = []

    def fetch(url, **kwargs):
        limits.append(kwargs["max_body_bytes"])
        return SimpleNamespace(status_code=404, content=b"x" * 100)

    assert run(monkeypatch, fetch, max_total_sitemap_size_mb=300 / 1024**2) == []
    assert limits == [300, 200, 100]


def test_gzip_suffix_with_already_http_decoded_xml_is_not_decoded_twice(monkeypatch):
    def fetch(url, **kwargs):
        return SimpleNamespace(status_code=200 if url.endswith(".gz") else 404, content=xml_urls())

    assert len(run(monkeypatch, fetch)) == 1


@pytest.mark.parametrize("failure", ["gzip", "fetch"])
def test_rejected_documents_retain_reserved_aggregate_allowance(monkeypatch, failure):
    limits = []
    index = (
        f"<sitemapindex {NS}>"
        + "".join(
            f"<sitemap><loc>https://example.com/child{i}.xml</loc></sitemap>" for i in range(8)
        )
        + "</sitemapindex>"
    ).encode()

    def fetch(url, **kwargs):
        limits.append(kwargs["max_body_bytes"])
        assert kwargs["max_total_body_bytes"] == kwargs["max_body_bytes"]
        if len(limits) == 1:
            return SimpleNamespace(status_code=200, content=index)
        if failure == "fetch":
            raise OSError("Rejected HTTP body")
        return SimpleNamespace(status_code=200, content=gzip.compress(b"x" * 10_000))

    assert (
        run(
            monkeypatch,
            fetch,
            max_sitemap_size_mb=4096 / 1024**2,
            max_total_sitemap_size_mb=8192 / 1024**2,
        )
        == []
    )
    assert len(limits) == 3
    assert len(index) + sum(limits[1:]) == 8192


def test_redirect_body_accounting_reduces_next_document_allowance(monkeypatch):
    limits = []

    def fetch(url, **kwargs):
        limits.append(kwargs["max_body_bytes"])
        used = min(300, kwargs["max_body_bytes"])
        return SimpleNamespace(status_code=404, content=b"", primr_body_bytes=used)

    assert run(monkeypatch, fetch, max_total_sitemap_size_mb=700 / 1024**2) == []
    assert limits == [700, 400, 100]
