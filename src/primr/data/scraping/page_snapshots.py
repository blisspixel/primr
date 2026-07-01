"""Browser render-snapshot comparison for page-access evidence."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import RenderSnapshotComparison

CHALLENGE_TEXT_MARKERS = (
    "verify you are human",
    "checking your browser",
    "enable javascript",
    "enable javascript and cookies",
    "press and hold",
    "security check",
    "browser check",
    "challenge",
    "access denied",
    "please wait while we verify",
    "please enable cookies",
)

CHALLENGE_SCRIPT_MARKERS = (
    "window.kpsdk",
    "kpsdk",
    "ips.js",
    "__cf_chl",
    "challenge-platform",
    "cf-browser-verification",
    "turnstile",
    "arkose",
    "funcaptcha",
    "datadome",
    "perimeterx",
    "_pxhd",
)

_WHITESPACE = re.compile(r"\s+")


def normalize_snapshot_text(text: str | None) -> str:
    """Collapse browser-visible text for bounded signal extraction."""
    return _WHITESPACE.sub(" ", text or "").strip()


def html_to_snapshot_text(html: str | bytes | None) -> str:
    """Extract visible-ish text from an HTML snapshot without retaining markup."""
    if not html:
        return ""
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="ignore")
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return normalize_snapshot_text(str(html))
    for tag in soup(("script", "style", "noscript")):
        tag.decompose()
    return normalize_snapshot_text(soup.get_text(" ", strip=True))


def find_challenge_markers(*, text: str = "", html: str | bytes | None = None) -> tuple[str, ...]:
    """Return challenge marker names found in visible text, title, or markup."""
    html_text = ""
    if html:
        html_text = html.decode("utf-8", errors="ignore") if isinstance(html, bytes) else html
    haystack = f"{text} {html_text}".lower()
    markers = [marker for marker in CHALLENGE_TEXT_MARKERS if marker in haystack]
    markers.extend(
        marker
        for marker in CHALLENGE_SCRIPT_MARKERS
        if marker in haystack and marker not in markers
    )
    return tuple(sorted(markers))


def compare_render_snapshots(
    *,
    initial_text: str | None = None,
    final_text: str | None = None,
    initial_html: str | bytes | None = None,
    final_html: str | bytes | None = None,
) -> RenderSnapshotComparison | None:
    """Compare initial and final browser-render snapshots as compact evidence."""
    initial = normalize_snapshot_text(initial_text) or html_to_snapshot_text(initial_html)
    final = normalize_snapshot_text(final_text) or html_to_snapshot_text(final_html)
    if not initial and not final:
        return None

    initial_markers = find_challenge_markers(text=initial, html=initial_html)
    final_markers = find_challenge_markers(text=final, html=final_html)
    initial_len = len(initial)
    final_len = len(final)
    delta = final_len - initial_len

    if initial_markers and not final_markers and final_len >= 250:
        state = "cleared_challenge"
    elif final_markers and final_len < 500:
        state = "stable_interstitial"
    elif final_len >= 650 and not final_markers:
        state = "stable_real_page"
    elif final_len < 120 and initial_len < 120:
        state = "stable_sparse"
    else:
        state = "inconclusive"

    evidence = [
        f"render_snapshot:{state}",
        f"render_text_lengths:{initial_len}->{final_len}",
    ]
    if initial_markers:
        evidence.append(f"render_initial_challenge:{', '.join(initial_markers[:4])}")
    if final_markers:
        evidence.append(f"render_final_challenge:{', '.join(final_markers[:4])}")
    if delta > 0:
        evidence.append(f"render_text_delta:+{delta}")

    return RenderSnapshotComparison(
        state=state,
        initial_text_length=initial_len,
        final_text_length=final_len,
        text_delta=delta,
        initial_challenge_markers=list(initial_markers),
        final_challenge_markers=list(final_markers),
        evidence=evidence,
    )
