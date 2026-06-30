"""User-facing blocked-site summaries for scrape recovery paths."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from primr.data.scraping.models import ScrapeResult
from primr.utils.security import mask_sensitive_data

MAX_SNIPPET_CHARS = 180
MAX_EVIDENCE_SNIPPETS = 3
_URL_RE = re.compile(r"https?://[^\s)>\]\"']+", re.I)
_SPACE_RE = re.compile(r"\s+")


def _redact_url(match: re.Match[str]) -> str:
    url = match.group(0)
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not parsed.scheme or not host:
            return "<url>"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = host
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        return urlunparse((parsed.scheme, netloc, "", "", "", ""))
    except ValueError:
        return "<url>"


def _snippet(value: object) -> str:
    text = mask_sensitive_data(str(value or ""))
    text = _URL_RE.sub(_redact_url, text)
    text = _SPACE_RE.sub(" ", text).strip()
    if len(text) > MAX_SNIPPET_CHARS:
        return text[: MAX_SNIPPET_CHARS - 3].rstrip() + "..."
    return text


def _assessment_evidence(result: ScrapeResult) -> list[str]:
    assessment = getattr(result, "access_assessment", None)
    evidence = getattr(assessment, "evidence", []) if assessment else []
    if not isinstance(evidence, list):
        return []
    snippets: list[str] = []
    for item in evidence:
        snippet = _snippet(item)
        if snippet:
            snippets.append(snippet)
    return snippets


def build_blocked_site_summary(
    result: ScrapeResult,
    reason: str | None,
    recovery_count: int,
) -> list[str]:
    """Build compact evidence and next-action lines for a blocked origin."""
    reason_text = _snippet(reason or result.error or "no verified first-party page content")
    evidence = list(dict.fromkeys([reason_text, *_assessment_evidence(result)]))
    lines = [f"Evidence: {'; '.join(evidence[:MAX_EVIDENCE_SNIPPETS])}"]
    lines.append(
        f"First-party recovery: {max(0, recovery_count)} same-site candidate page(s) found"
    )
    lines.append(
        "Next: routing around the origin via Wayback, subdomains, EDGAR, and Wikipedia; "
        "if fallback content is still empty, check site availability or rerun with --mode deep"
    )
    return lines


def emit_blocked_site_summary(
    console,
    domain: str,
    result: ScrapeResult,
    reason: str | None,
    recovery_count: int,
) -> None:
    """Print the blocked-site summary through the existing console abstraction."""
    console.fail(f"Could not access {domain}")
    for line in build_blocked_site_summary(result, reason, recovery_count):
        console.muted(f"  {line}")
