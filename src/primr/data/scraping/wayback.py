"""
Wayback Machine scrape tier.

Fetches the most recent archived snapshot of a URL from web.archive.org.
Used as a bypass when origin sites are bot-protected (Kasada, Akamai, etc.)
or return only challenge shells. The CDX API lists every capture; we pick
the most recent 200 with a reasonable payload size.

Wayback has no bot protection and serves plain HTML of the original page as
it appeared when archived. For public companies, snapshots are typically
within the last 1-30 days for high-traffic hosts.

Note: for heavily Kasada-protected hosts, Wayback's own crawler (Heritrix)
often gets blocked too, resulting in captures that are themselves challenge
shells. We filter those out by requiring a minimum payload size and rejecting
captures whose body still contains KPSDK markers.
"""

from __future__ import annotations

import json
import logging
import time
from urllib.parse import urlparse

from primr.utils.security import validate_final_url_after_redirect
from primr.utils.validators import validate_url_for_request

from .config import DEFAULT_TIMEOUT_HTTPX
from .models import Attempt, ErrorType, ScrapeResult

logger = logging.getLogger(__name__)

WAYBACK_CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_REPLAY_BASE = "https://web.archive.org/web"

# Skip captures smaller than this — almost certainly Kasada shells or errors.
MIN_USEFUL_CAPTURE_BYTES = 3_000


def _fetch(
    url: str, timeout: float, params: dict | None = None
) -> tuple[int | None, bytes | None, str | None]:
    """Tiny helper: plain HTTP GET, returns (status, body, final_url)."""
    try:
        import httpx

        is_valid, normalized_url, error = validate_url_for_request(url)
        if not is_valid:
            logger.debug("Wayback fetch URL blocked: %s", error)
            return None, None, None

        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; primr-wayback/1.0)",
                "Accept": "text/html,application/json,*/*",
            },
        ) as client:
            resp = client.get(normalized_url, params=params)
            final_url = str(resp.url)
            is_safe, redirect_error = validate_final_url_after_redirect(final_url)
            if not is_safe:
                logger.debug("Wayback fetch redirect blocked: %s", redirect_error)
                return None, None, None
            return resp.status_code, resp.content, final_url
    except Exception as e:
        logger.debug("Wayback fetch failed for %s: %s", url, e)
        return None, None, None


def _make_replay_url(timestamp: str, original_url: str) -> str:
    """Build a raw-content replay URL (id_ modifier returns body without toolbar)."""
    return f"{WAYBACK_REPLAY_BASE}/{timestamp}id_/{original_url}"


def find_wayback_snapshots(
    url: str,
    timeout: float = 60.0,
    limit: int = 40,
) -> list[tuple[str, str, int]]:
    """
    Query the CDX API for captures of a URL.

    Returns a list of (timestamp, original_url, byte_length) tuples, ordered
    most recent first. Only includes captures with status 200 and a payload
    over MIN_USEFUL_CAPTURE_BYTES.
    """
    # CDX expects the URL without scheme; pass scheme-stripped form to match
    # how their urlkey is computed. Keep query/path as-is.
    parsed = urlparse(url)
    cdx_url = url
    if parsed.scheme:
        cdx_url = url.split("://", 1)[1] if "://" in url else url

    params = {
        "url": cdx_url,
        "output": "json",
        "filter": "statuscode:200",
        "collapse": "digest",  # drop duplicate content
        "limit": str(limit),
    }
    status, body, _ = _fetch(WAYBACK_CDX_API, timeout=timeout, params=params)
    if status != 200 or not body:
        return []

    try:
        rows = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return []

    if not rows or len(rows) < 2:
        return []

    # First row is header
    header = rows[0]
    try:
        ts_idx = header.index("timestamp")
        orig_idx = header.index("original")
        len_idx = header.index("length")
    except ValueError:
        return []

    captures: list[tuple[str, str, int]] = []
    for row in rows[1:]:
        try:
            ts = row[ts_idx]
            orig = row[orig_idx]
            length = int(row[len_idx]) if row[len_idx] else 0
        except (IndexError, ValueError, TypeError):
            continue

        if length < MIN_USEFUL_CAPTURE_BYTES:
            continue

        captures.append((ts, orig, length))

    # CDX returns oldest first; we want newest first.
    captures.sort(key=lambda x: x[0], reverse=True)
    return captures


def _looks_like_challenge_shell(body: bytes) -> bool:
    """Detect Kasada/similar challenge pages that made it into the archive."""
    if not body or len(body) < 2000:
        return True
    head = body[:4000].decode("utf-8", errors="ignore").lower()
    markers = ("kpsdk", "ips.js", "_abck", "cf_chl_opt", "challenge-platform")
    return any(m in head for m in markers)


def scrape_with_wayback(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_HTTPX,
) -> ScrapeResult:
    """
    Fetch a URL from the Wayback Machine.

    Flow:
    1. Query CDX for recent 200-status captures of the URL.
    2. Try each capture (newest first) until we get real content.
    3. Skip captures that are themselves challenge shells.
    4. Return raw HTML as ScrapeResult.

    This tier never tries for fresh real-time content — it serves the most
    recent archive, which may be days or weeks old. For "About Us" / "History"
    / "Leadership" type pages that change infrequently, this is acceptable.
    """
    start_time = time.time()
    tier_name = "wayback"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL for Wayback: {url}",
            tier=tier_name,
            elapsed_ms=(time.time() - start_time) * 1000,
        )

    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL for Wayback: {error}",
            tier=tier_name,
            elapsed_ms=(time.time() - start_time) * 1000,
        )

    url = normalized_url

    # Step 1: find snapshots (most recent first).
    # CDX can be slow; cap at 30s to leave room for replay fetches.
    cdx_budget = min(max(timeout * 0.5, 20.0), 30.0)
    captures = find_wayback_snapshots(url, timeout=cdx_budget)
    attempts: list[Attempt] = []

    if not captures:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error="No usable Wayback snapshots found",
            tier=tier_name,
            elapsed_ms=(time.time() - start_time) * 1000,
            attempts=[
                Attempt(
                    tier=tier_name,
                    success=False,
                    error="no captures from CDX",
                    error_type=ErrorType.NETWORK_ERROR,
                )
            ],
        )

    # Step 2: try captures newest-first
    for ts, original_url, _ in captures[:3]:
        remaining = max(5.0, timeout - (time.time() - start_time))
        if remaining < 3.0:
            break

        replay_url = _make_replay_url(ts, original_url)
        status, body, final_url = _fetch(replay_url, timeout=remaining)

        if status != 200 or not body:
            attempts.append(
                Attempt(
                    tier=tier_name,
                    success=False,
                    error=f"replay status={status}",
                    error_type=ErrorType.NETWORK_ERROR,
                    http_status=status,
                )
            )
            continue

        if _looks_like_challenge_shell(body):
            attempts.append(
                Attempt(
                    tier=tier_name,
                    success=False,
                    error=f"capture is challenge shell ({ts})",
                    error_type=ErrorType.SOFT_BLOCK,
                    http_status=status,
                )
            )
            continue

        elapsed_ms = (time.time() - start_time) * 1000
        attempts.append(
            Attempt(
                tier=tier_name,
                success=True,
                http_status=status,
                elapsed_ms=elapsed_ms,
            )
        )
        logger.info("Wayback snapshot %s served for %s (%d bytes)", ts, url, len(body))
        return ScrapeResult(
            url=url,
            success=True,
            raw_content=body,
            tier=tier_name,
            http_status=status,
            content_type="text/html",
            final_url=final_url or replay_url,
            elapsed_ms=elapsed_ms,
            attempts=attempts,
        )

    return ScrapeResult(
        url=url,
        success=False,
        error_type=ErrorType.SOFT_BLOCK,
        error="All Wayback captures were challenge shells or failed",
        tier=tier_name,
        elapsed_ms=(time.time() - start_time) * 1000,
        attempts=attempts,
    )
