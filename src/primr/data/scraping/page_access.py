"""
Page-access classification for distinguishing real content from challenge shells.

This layer sits between transport success and content extraction. A page is only
considered a real success when we observe evidence of actual site content rather
than merely receiving HTML.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .content import extract_clean_text, extract_main_content
from .detection import detect_soft_block
from .models import PageAccessAssessment, PageAccessState, RenderSnapshotComparison
from .page_snapshots import (
    CHALLENGE_SCRIPT_MARKERS,
    CHALLENGE_TEXT_MARKERS,
)

_PAGE_KIND_MARKERS: dict[str, tuple[str, ...]] = {
    "homepage": (),
    "about": ("about", "our story", "company", "who we are", "overview"),
    "history": ("history", "heritage", "our story", "founded", "since"),
    "leadership": ("leadership", "executive", "board", "management", "team"),
    "investors": ("investor", "annual report", "earnings", "sec filings", "shareholder"),
    "sustainability": ("sustainability", "esg", "responsibility", "climate", "impact"),
    "contact": ("contact", "email", "phone", "address", "hours", "location"),
    "news": ("news", "press release", "media", "announcement", "blog"),
    "products": ("products", "shop", "collection", "category", "featured"),
    "support": ("support", "help", "faq", "customer service"),
}


def _parse_html(raw_content: bytes) -> BeautifulSoup | None:
    try:
        html = raw_content.decode("utf-8", errors="ignore")
    except Exception:
        return None

    try:
        return BeautifulSoup(html, "html.parser")
    except Exception:
        return None


def _score_text(text: str) -> int:
    if not text:
        return 0
    sentences = len([s for s in text.split(".") if len(s.strip()) > 20])
    paragraphs = max(1, len([line for line in text.splitlines() if len(line.strip()) > 60]))
    return min(len(text), 20_000) + (sentences * 120) + (paragraphs * 80)


def _best_visible_text(raw_content: bytes) -> str:
    candidates = [
        extract_main_content(raw_content) or "",
        extract_clean_text(raw_content, mode="aggressive") or "",
        extract_clean_text(raw_content, mode="conservative") or "",
    ]
    return max(candidates, key=_score_text).strip()


def infer_page_kind(url: str) -> str:
    path = (urlparse(url).path or "/").strip("/").lower()
    if not path:
        return "homepage"

    if any(token in path for token in ("history", "heritage")):
        return "history"
    if any(token in path for token in ("leadership", "executive", "board", "team", "management")):
        return "leadership"
    if any(token in path for token in ("investor", "financial", "earnings", "sec", "shareholder")):
        return "investors"
    if any(token in path for token in ("sustainability", "esg", "responsibility", "impact")):
        return "sustainability"
    if any(token in path for token in ("contact", "directory", "hours", "location")):
        return "contact"
    if any(token in path for token in ("news", "press", "media", "blog")):
        return "news"
    if any(token in path for token in ("product", "shop", "category", "collection")):
        return "products"
    if any(token in path for token in ("support", "help", "faq", "customer-service")):
        return "support"
    if any(token in path for token in ("about", "our-story", "company", "who-we-are")):
        return "about"
    return "generic"


def classify_page_access(
    raw_content: bytes,
    *,
    url: str,
    http_status: int | None = None,
    content_type: str | None = None,
    final_url: str | None = None,
    expected_markers: list[str] | None = None,
    render_snapshot: RenderSnapshotComparison | None = None,
) -> PageAccessAssessment:
    """
    Classify whether fetched content is likely a real page or a challenge shell.
    """
    page_kind = infer_page_kind(final_url or url)

    if not raw_content:
        return PageAccessAssessment(
            state=PageAccessState.UNKNOWN,
            reason="No response body",
            confidence=1.0,
            page_kind=page_kind,
            evidence=["empty_response"],
        )

    blocked, blocked_reason = detect_soft_block(
        raw_content,
        http_status=http_status,
        content_type=content_type,
        final_url=final_url,
        host=urlparse(url).netloc,
    )
    snapshot_positive = bool(
        render_snapshot and render_snapshot.state in {"cleared_challenge", "stable_real_page"}
    )
    if blocked and snapshot_positive and "content too short" in (blocked_reason or "").lower():
        blocked = False
        blocked_reason = None

    soup = _parse_html(raw_content)
    html = raw_content.decode("utf-8", errors="ignore")
    html_lower = html.lower()
    title = soup.title.get_text(" ", strip=True) if soup and soup.title else None
    title_lower = (title or "").lower()
    visible_text = _best_visible_text(raw_content)
    visible_lower = visible_text.lower()
    snapshot_visible_len = render_snapshot.final_text_length if render_snapshot else 0
    visible_len = max(len(visible_text), snapshot_visible_len)

    expected = [m.lower() for m in (expected_markers or [])]
    expected.extend(_PAGE_KIND_MARKERS.get(page_kind, ()))
    expected = [m for m in expected if m]

    matched_expected = sorted(
        {marker for marker in expected if marker in visible_lower or marker in title_lower}
    )
    matched_challenge = sorted(
        {
            marker
            for marker in CHALLENGE_TEXT_MARKERS
            if marker in visible_lower or marker in title_lower or marker in html_lower
        }
    )
    matched_challenge.extend(
        marker
        for marker in CHALLENGE_SCRIPT_MARKERS
        if marker in html_lower and marker not in matched_challenge
    )

    landmarks: list[str] = []
    if soup:
        if soup.find("main"):
            landmarks.append("main")
        if soup.find("article"):
            landmarks.append("article")
        if soup.find("nav"):
            landmarks.append("nav")
        if soup.find("header"):
            landmarks.append("header")
        if soup.find("footer"):
            landmarks.append("footer")
        if soup.find("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
            landmarks.append("json_ld")

    link_count = len(soup.find_all("a")) if soup else 0
    button_count = len(soup.find_all("button")) if soup else 0
    heading_count = len(soup.find_all(re.compile("^h[1-6]$"))) if soup else 0
    paragraph_count = len(soup.find_all("p")) if soup else 0
    script_count = len(soup.find_all("script")) if soup else 0
    iframe_count = len(soup.find_all("iframe")) if soup else 0

    evidence: list[str] = []
    if blocked and blocked_reason:
        evidence.append(f"soft_block_detector:{blocked_reason}")
    if matched_expected:
        evidence.append(f"expected_markers:{', '.join(matched_expected[:4])}")
    if matched_challenge:
        evidence.append(f"challenge_markers:{', '.join(matched_challenge[:4])}")
    if landmarks:
        evidence.append(f"landmarks:{', '.join(landmarks)}")
    if link_count or button_count:
        evidence.append(f"interaction_elements:{link_count} links, {button_count} buttons")
    if render_snapshot:
        evidence.extend(render_snapshot.evidence)
    evidence.append(f"visible_text_length:{visible_len}")

    real_structure_score = 0
    if "main" in landmarks or "article" in landmarks:
        real_structure_score += 2
    if "json_ld" in landmarks:
        real_structure_score += 1
    if heading_count >= 1:
        real_structure_score += 1
    if paragraph_count >= 2:
        real_structure_score += 1
    if link_count >= 8:
        real_structure_score += 1
    if matched_expected:
        real_structure_score += min(3, len(matched_expected))
    if snapshot_positive:
        real_structure_score += 2
    if visible_len >= 900:
        real_structure_score += 2
    elif visible_len >= 250:
        real_structure_score += 1

    shell_score = 0
    if blocked:
        shell_score += 3
    if matched_challenge:
        shell_score += min(3, len(matched_challenge))
    if visible_len < 120:
        shell_score += 2
    elif visible_len < 250:
        shell_score += 1
    if iframe_count > 0 and visible_len < 250:
        shell_score += 1
    if script_count >= 3 and visible_len < 250:
        shell_score += 1
    if render_snapshot and render_snapshot.state == "stable_interstitial":
        shell_score += 2

    if blocked or shell_score >= 3:
        return PageAccessAssessment(
            state=PageAccessState.SOFT_BLOCK,
            reason=blocked_reason or "Challenge/interstitial shell detected",
            confidence=min(1.0, 0.55 + 0.1 * shell_score),
            page_kind=page_kind,
            title=title,
            visible_text_length=visible_len,
            matched_expected_markers=matched_expected,
            matched_challenge_markers=matched_challenge,
            landmarks=landmarks,
            evidence=evidence,
        )

    if real_structure_score >= 4 and shell_score <= 1:
        return PageAccessAssessment(
            state=PageAccessState.SUCCESS,
            reason="Observed real page markers",
            confidence=min(1.0, 0.45 + 0.08 * real_structure_score),
            page_kind=page_kind,
            title=title,
            visible_text_length=visible_len,
            matched_expected_markers=matched_expected,
            matched_challenge_markers=matched_challenge,
            landmarks=landmarks,
            evidence=evidence,
        )

    if (
        real_structure_score >= 3
        and visible_len >= 80
        and not matched_challenge
        and ("main" in landmarks or "article" in landmarks or "json_ld" in landmarks)
    ):
        return PageAccessAssessment(
            state=PageAccessState.SUCCESS,
            reason="Observed structured page content",
            confidence=0.68,
            page_kind=page_kind,
            title=title,
            visible_text_length=visible_len,
            matched_expected_markers=matched_expected,
            matched_challenge_markers=matched_challenge,
            landmarks=landmarks,
            evidence=evidence,
        )

    if (
        page_kind
        in {
            "about",
            "history",
            "leadership",
            "investors",
            "sustainability",
            "contact",
            "news",
            "support",
        }
        and matched_expected
        and visible_len >= 120
    ):
        return PageAccessAssessment(
            state=PageAccessState.SUCCESS,
            reason=f"Matched {page_kind} page markers",
            confidence=0.72,
            page_kind=page_kind,
            title=title,
            visible_text_length=visible_len,
            matched_expected_markers=matched_expected,
            matched_challenge_markers=matched_challenge,
            landmarks=landmarks,
            evidence=evidence,
        )

    if visible_len < 120 and not matched_expected:
        return PageAccessAssessment(
            state=PageAccessState.THIN_CONTENT,
            reason="Page loaded but real content markers are too sparse",
            confidence=0.7,
            page_kind=page_kind,
            title=title,
            visible_text_length=visible_len,
            matched_expected_markers=matched_expected,
            matched_challenge_markers=matched_challenge,
            landmarks=landmarks,
            evidence=evidence,
        )

    return PageAccessAssessment(
        state=PageAccessState.UNKNOWN,
        reason="Content signals are inconclusive",
        confidence=0.45,
        page_kind=page_kind,
        title=title,
        visible_text_length=visible_len,
        matched_expected_markers=matched_expected,
        matched_challenge_markers=matched_challenge,
        landmarks=landmarks,
        evidence=evidence,
    )
