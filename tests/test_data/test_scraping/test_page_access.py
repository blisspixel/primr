"""Tests for page-access classification."""

from primr.data.scraping.models import PageAccessState
from primr.data.scraping.page_access import classify_page_access, infer_page_kind
from primr.data.scraping.page_snapshots import compare_render_snapshots

REAL_HOMEPAGE = b"""<!DOCTYPE html>
<html>
<head>
  <title>ExampleCo | Official Site</title>
  <script type="application/ld+json">{"@type":"Organization"}</script>
</head>
<body>
  <header><nav><a>Shop</a><a>Men</a><a>Women</a><a>Sustainability</a></nav></header>
  <main>
    <h1>Performance Luxury Apparel</h1>
    <p>ExampleCo makes outerwear and apparel built for extreme conditions and everyday wear.</p>
    <p>Explore new arrivals, heritage parkas, and seasonal collections.</p>
  </main>
  <footer><a>Contact</a><a>Stores</a></footer>
</body>
</html>"""


KASADA_SHELL = b"""<!DOCTYPE html>
<html><head><title>Please wait</title></head>
<body>
<script>window.KPSDK={};</script>
<script src="/challenge/ips.js?x-kpsdk-im=test"></script>
<iframe src="javascript:;" style="display:none;"></iframe>
</body></html>"""


THIN_BUT_REAL_HISTORY = b"""<!DOCTYPE html>
<html>
<head><title>Our History</title></head>
<body>
  <main>
    <h1>Our History</h1>
    <p>Founded in 1957, ExampleCo grew from a local workshop into a global brand.</p>
    <p>Our heritage continues to shape the products we build today.</p>
  </main>
</body>
</html>"""


def test_infer_page_kind():
    assert infer_page_kind("https://example.com") == "homepage"
    assert infer_page_kind("https://example.com/about-us") == "about"
    assert infer_page_kind("https://example.com/our-history") == "history"
    assert infer_page_kind("https://example.com/investors/results") == "investors"


def test_classifies_real_homepage_as_success():
    result = classify_page_access(
        REAL_HOMEPAGE,
        url="https://www.example.com/",
        http_status=200,
        content_type="text/html",
        expected_markers=["exampleco"],
    )

    assert result.state == PageAccessState.SUCCESS
    assert "exampleco" in result.matched_expected_markers
    assert result.visible_text_length > 100


def test_classifies_kasada_shell_as_soft_block():
    result = classify_page_access(
        KASADA_SHELL,
        url="https://www.example.com/",
        http_status=200,
        content_type="text/html",
    )

    assert result.state == PageAccessState.SOFT_BLOCK
    assert any("kpsdk" in marker for marker in result.matched_challenge_markers)


def test_classifies_thin_history_page_as_success():
    result = classify_page_access(
        THIN_BUT_REAL_HISTORY,
        url="https://example.com/history",
        http_status=200,
        content_type="text/html",
    )

    assert result.state == PageAccessState.SUCCESS
    assert "history" in result.matched_expected_markers


def test_render_snapshot_can_confirm_sparse_browser_homepage():
    snapshot = compare_render_snapshots(
        initial_html="<html><body>Checking your browser</body></html>",
        final_html="<html><body>"
        + ("ExampleCo product catalog and support. " * 30)
        + "</body></html>",
    )

    result = classify_page_access(
        b"<html><body><main><h1>ExampleCo</h1></main></body></html>",
        url="https://www.example.com/",
        http_status=200,
        content_type="text/html",
        expected_markers=["exampleco"],
        render_snapshot=snapshot,
    )

    assert result.state == PageAccessState.SUCCESS
    assert "render_snapshot:cleared_challenge" in result.evidence


def test_render_snapshot_interstitial_keeps_sparse_browser_page_blocked():
    snapshot = compare_render_snapshots(
        initial_html="<html><body>Please wait while we verify your browser</body></html>",
        final_html="<html><body>Please wait while we verify your browser</body></html>",
    )

    result = classify_page_access(
        b"<html><body>Please wait while we verify your browser</body></html>",
        url="https://www.example.com/",
        http_status=200,
        content_type="text/html",
        render_snapshot=snapshot,
    )

    assert result.state == PageAccessState.SOFT_BLOCK
    assert "render_snapshot:stable_interstitial" in result.evidence
