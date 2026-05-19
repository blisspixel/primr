"""Tests for primr.data.scraping.wayback.

Covers find_wayback_snapshots CDX parsing, _looks_like_challenge_shell
detection, and scrape_with_wayback's flow control (CDX miss, all-shells,
success on first valid capture). Brings a previously 0%-covered module
to near-full coverage by mocking the HTTP layer at _fetch.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from primr.data.scraping.models import ErrorType
from primr.data.scraping.wayback import (
    MIN_USEFUL_CAPTURE_BYTES,
    _looks_like_challenge_shell,
    _make_replay_url,
    find_wayback_snapshots,
    scrape_with_wayback,
)


def _cdx_json(captures: list[tuple[str, str, int]]) -> bytes:
    """Build a CDX-formatted JSON body from (timestamp, url, length) tuples."""
    header = ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"]
    rows = [
        ["key", ts, orig, "text/html", "200", "digest", str(length)]
        for ts, orig, length in captures
    ]
    return json.dumps([header, *rows]).encode("utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestMakeReplayUrl:
    def test_uses_id_modifier(self):
        url = _make_replay_url("20240101000000", "https://example.com/x")
        assert "20240101000000id_" in url
        assert url.endswith("https://example.com/x")


class TestChallengeShellDetector:
    def test_empty_body_is_shell(self):
        assert _looks_like_challenge_shell(b"") is True

    def test_short_body_is_shell(self):
        assert _looks_like_challenge_shell(b"x" * 100) is True

    def test_kpsdk_marker_is_shell(self):
        # Marker must appear within the first 4000 bytes — that's where the
        # detector scans.
        body = b"<html>window.kpsdk = '...'; " + b"x" * 5000
        assert _looks_like_challenge_shell(body) is True

    def test_cloudflare_marker_is_shell(self):
        body = b"<html>cf_chl_opt = {...}; " + b"x" * 5000
        assert _looks_like_challenge_shell(body) is True

    def test_clean_long_body_not_shell(self):
        body = b"<html><body>" + b"real content " * 1000 + b"</body></html>"
        assert _looks_like_challenge_shell(body) is False


# ---------------------------------------------------------------------------
# find_wayback_snapshots
# ---------------------------------------------------------------------------


class TestFindWaybackSnapshots:
    def test_returns_empty_when_cdx_404(self):
        with patch(
            "primr.data.scraping.wayback._fetch",
            return_value=(404, None, None),
        ):
            assert find_wayback_snapshots("https://example.com") == []

    def test_returns_empty_when_invalid_json(self):
        with patch(
            "primr.data.scraping.wayback._fetch",
            return_value=(200, b"not json {", None),
        ):
            assert find_wayback_snapshots("https://example.com") == []

    def test_returns_empty_when_only_header(self):
        body = json.dumps([["urlkey", "timestamp", "original", "length"]]).encode()
        with patch("primr.data.scraping.wayback._fetch", return_value=(200, body, None)):
            assert find_wayback_snapshots("https://example.com") == []

    def test_parses_valid_captures(self):
        captures = [
            ("20240301120000", "https://example.com/a", 10_000),
            ("20240201120000", "https://example.com/a", 8_000),
        ]
        with patch(
            "primr.data.scraping.wayback._fetch",
            return_value=(200, _cdx_json(captures), None),
        ):
            result = find_wayback_snapshots("https://example.com/a")
        assert len(result) == 2
        # Newest first
        assert result[0][0] == "20240301120000"
        assert result[1][0] == "20240201120000"

    def test_filters_tiny_captures(self):
        captures = [
            ("20240301120000", "https://example.com", MIN_USEFUL_CAPTURE_BYTES - 100),
        ]
        with patch(
            "primr.data.scraping.wayback._fetch",
            return_value=(200, _cdx_json(captures), None),
        ):
            assert find_wayback_snapshots("https://example.com") == []

    def test_handles_missing_header_fields(self):
        body = json.dumps([["urlkey", "digest"], ["key", "abc"]]).encode()
        with patch("primr.data.scraping.wayback._fetch", return_value=(200, body, None)):
            assert find_wayback_snapshots("https://example.com") == []

    def test_skips_rows_with_malformed_length(self):
        body = json.dumps(
            [
                ["urlkey", "timestamp", "original", "length"],
                ["key", "20240301120000", "https://example.com", "not-a-number"],
            ]
        ).encode()
        with patch("primr.data.scraping.wayback._fetch", return_value=(200, body, None)):
            assert find_wayback_snapshots("https://example.com") == []

    def test_url_without_scheme_handled(self):
        captures = [("20240301120000", "example.com", 5_000)]
        with patch(
            "primr.data.scraping.wayback._fetch",
            return_value=(200, _cdx_json(captures), None),
        ):
            # No-scheme URL also returns captures
            result = find_wayback_snapshots("example.com")
            assert len(result) == 1


# ---------------------------------------------------------------------------
# scrape_with_wayback
# ---------------------------------------------------------------------------


class TestScrapeWithWayback:
    def test_rejects_non_http_scheme(self):
        result = scrape_with_wayback("file:///etc/passwd")
        assert result.success is False
        assert result.error_type is ErrorType.NETWORK_ERROR

    def test_rejects_url_without_host(self):
        result = scrape_with_wayback("https://")
        assert result.success is False

    def test_returns_failure_when_no_snapshots(self):
        with patch(
            "primr.data.scraping.wayback.find_wayback_snapshots",
            return_value=[],
        ):
            result = scrape_with_wayback("https://example.com")
        assert result.success is False
        assert "no captures" in (result.attempts[0].error or "").lower()

    def test_success_on_first_clean_capture(self):
        captures = [("20240301120000", "https://example.com/x", 50_000)]
        valid_body = b"<html><body>" + b"real content " * 1000 + b"</body></html>"
        with (
            patch(
                "primr.data.scraping.wayback.find_wayback_snapshots",
                return_value=captures,
            ),
            patch(
                "primr.data.scraping.wayback._fetch",
                return_value=(200, valid_body, "https://archive.org/x"),
            ),
        ):
            result = scrape_with_wayback("https://example.com/x")
        assert result.success is True
        assert result.raw_content == valid_body
        assert result.tier == "wayback"
        assert result.content_type == "text/html"

    def test_skips_shell_captures_continues_to_next(self):
        captures = [
            ("20240301120000", "https://example.com", 50_000),  # shell
            ("20240201120000", "https://example.com", 50_000),  # real
        ]
        shell = b"<html>window.kpsdk = ...;" + b"x" * 5000
        real = b"<html>" + b"real content " * 1000 + b"</html>"
        fetch_results = [(200, shell, None), (200, real, None)]
        fetch_iter = iter(fetch_results)

        with (
            patch(
                "primr.data.scraping.wayback.find_wayback_snapshots",
                return_value=captures,
            ),
            patch(
                "primr.data.scraping.wayback._fetch",
                side_effect=lambda *a, **kw: next(fetch_iter),
            ),
        ):
            result = scrape_with_wayback("https://example.com")
        assert result.success is True
        assert result.raw_content == real

    def test_returns_failure_when_all_captures_are_shells(self):
        captures = [
            ("20240301120000", "https://example.com", 50_000),
            ("20240201120000", "https://example.com", 50_000),
            ("20240101120000", "https://example.com", 50_000),
        ]
        shell = b"<html>window.kpsdk = ...;" + b"x" * 5000
        with (
            patch(
                "primr.data.scraping.wayback.find_wayback_snapshots",
                return_value=captures,
            ),
            patch(
                "primr.data.scraping.wayback._fetch",
                return_value=(200, shell, None),
            ),
        ):
            result = scrape_with_wayback("https://example.com")
        assert result.success is False
        assert result.error_type is ErrorType.SOFT_BLOCK

    def test_replay_non_200_recorded_as_failure(self):
        captures = [("20240301120000", "https://example.com", 50_000)]
        with (
            patch(
                "primr.data.scraping.wayback.find_wayback_snapshots",
                return_value=captures,
            ),
            patch(
                "primr.data.scraping.wayback._fetch",
                return_value=(500, None, None),
            ),
        ):
            result = scrape_with_wayback("https://example.com")
        assert result.success is False
        # The single attempt should record the 500
        failed = [a for a in result.attempts if a.http_status == 500]
        assert failed, f"Expected attempt with http_status=500, got {result.attempts}"


# ---------------------------------------------------------------------------
# _fetch helper indirectly exercised by mocking
# ---------------------------------------------------------------------------


class TestFetchHelperRaisesAreSwallowed:
    def test_fetch_returns_none_on_exception(self):
        from primr.data.scraping.wayback import _fetch

        # Patch httpx to raise; the helper should return (None, None, None)
        # without propagating.
        with patch("httpx.Client", side_effect=RuntimeError("net")):
            assert _fetch("https://example.com", timeout=1.0) == (None, None, None)


def test_module_constants_present():
    """Sanity: the module exposes its core constants."""
    from primr.data.scraping import wayback

    assert wayback.WAYBACK_CDX_API.startswith("https://web.archive.org")
    assert wayback.WAYBACK_REPLAY_BASE.startswith("https://web.archive.org")
    assert wayback.MIN_USEFUL_CAPTURE_BYTES > 0


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_valid_schemes_accepted(scheme):
    """Both http and https URLs should pass the scheme guard."""
    with patch("primr.data.scraping.wayback.find_wayback_snapshots", return_value=[]):
        result = scrape_with_wayback(f"{scheme}://example.com")
        # Falls through to "no snapshots" path, not the scheme rejection
        assert "no captures" in (result.attempts[0].error or "").lower()
