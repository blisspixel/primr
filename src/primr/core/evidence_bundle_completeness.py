"""Prep completeness: which collected pages count as current first-party coverage."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

_CURRENT_LOCALES = frozenset({"en", "en-us", "en-gb"})
_LOCALE_SEGMENTS = frozenset(
    {
        "ar",
        "ar-sa",
        "bg",
        "bg-bg",
        "ca",
        "ca-es",
        "cs",
        "cs-cz",
        "da",
        "da-dk",
        "de",
        "de-at",
        "de-ch",
        "de-de",
        "el",
        "el-gr",
        "en",
        "en-au",
        "en-ca",
        "en-gb",
        "en-ie",
        "en-nz",
        "en-us",
        "es",
        "es-ar",
        "es-es",
        "es-mx",
        "et",
        "fi",
        "fi-fi",
        "fr",
        "fr-be",
        "fr-ca",
        "fr-ch",
        "fr-fr",
        "he",
        "he-il",
        "hi",
        "hi-in",
        "hr",
        "hr-hr",
        "hu",
        "hu-hu",
        "id",
        "id-id",
        "it",
        "it-it",
        "ja",
        "ja-jp",
        "ko",
        "ko-kr",
        "lt",
        "lv",
        "ms",
        "ms-my",
        "nb",
        "nb-no",
        "nl",
        "nl-be",
        "nl-nl",
        "nn",
        "nn-no",
        "no",
        "pl",
        "pl-pl",
        "pt",
        "pt-br",
        "pt-pt",
        "ro",
        "ro-ro",
        "ru",
        "ru-ru",
        "sk",
        "sk-sk",
        "sl",
        "sl-si",
        "sv",
        "sv-se",
        "th",
        "th-th",
        "tr",
        "tr-tr",
        "uk",
        "uk-ua",
        "vi",
        "vi-vn",
        "zh",
        "zh-cn",
        "zh-hk",
        "zh-tw",
    }
)
_PLACEHOLDER_PHRASES = (
    "illustrative examples",
    "lorem ipsum",
    "coming soon",
    "under construction",
    "parked domain",
    "domain for sale",
)
_EXAMPLE_HOSTS = frozenset({"example.com", "example.net", "example.org"})
_EMPTY_COLLECTION_REASON = (
    "No first-party page content was collected; add public sources before synthesis."
)
_EMPTY_COLLECTION_NEXT = (
    "Retry `primr prep` for this company, or raise `--max-pages` "
    "if the site publishes more public pages."
)


def _url_path_segments(url: str) -> list[str]:
    try:
        path = urlparse(url).path or ""
    except ValueError:
        return []
    return [segment for segment in path.split("/") if segment]


def _readable_word_count(text: str) -> int:
    count = 0
    length = 0
    for char in text:
        if char.isalpha():
            length += 1
            continue
        if length >= 2:
            count += 1
        length = 0
    if length >= 2:
        count += 1
    return count


def _is_machine_endpoint(url: str, text: str) -> bool:
    segments = [segment.casefold() for segment in _url_path_segments(url)]
    if segments:
        last = segments[-1]
        if last == "robots.txt" or (last.startswith("sitemap") and last.endswith(".xml")):
            return True
        if last.endswith((".json", ".xml", ".rss", ".atom")):
            return True
        if any(segment in {"api", "feed", "graphql", "wp-json"} for segment in segments):
            return True
    stripped = (text or "").lstrip()
    return stripped.startswith(("{", "[", "<?xml", "<rss", "<feed"))


def _locale_segment(url: str) -> str | None:
    segments = _url_path_segments(url)
    if not segments:
        return None
    first = segments[0].casefold()
    if first in _LOCALE_SEGMENTS:
        return first
    return None


def _is_old_page(url: str) -> bool:
    cutoff = datetime.now(timezone.utc).year - 2
    for segment in _url_path_segments(url):
        if len(segment) == 4 and segment.isdigit() and 1900 <= int(segment) <= cutoff:
            return True
    return False


def _is_placeholder_page(url: str, text: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").casefold()
    except ValueError:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    if host in _EXAMPLE_HOSTS:
        return True
    folded = " ".join((text or "").casefold().split())
    return any(phrase in folded for phrase in _PLACEHOLDER_PHRASES)


def _classify_first_party_page(url: str, text: str, company_url: str) -> str:
    """Classify one direct first-party page for the prep completeness gate."""
    if _is_machine_endpoint(url, text):
        return "machine"
    requested = _locale_segment(company_url)
    page_locale = _locale_segment(url)
    allowed = set(_CURRENT_LOCALES)
    if requested:
        allowed.add(requested)
    if page_locale is not None and page_locale not in allowed:
        return "other_locale"
    if _is_old_page(url):
        return "old"
    if _is_placeholder_page(url, text):
        return "placeholder"
    if _readable_word_count(text) < 3:
        return "unreadable"
    return "qualifying"


def _assess_collected_pages(
    bundle_dir: Path,
    corpus: dict[str, str],
    company_url: str,
    *,
    fallback_source_map: Callable[[Path], dict[str, str]],
    clean_external_metadata: Callable[..., str],
    source_type_for_url: Callable[..., str],
) -> dict[str, int]:
    from primr.data.scraping.net import is_in_scope

    fallback_sources = fallback_source_map(bundle_dir)
    counts = {
        "qualifying": 0,
        "machine": 0,
        "other_locale": 0,
        "old": 0,
        "placeholder": 0,
        "unreadable": 0,
        "public": 0,
        "first_party": 0,
    }
    for url, text in corpus.items():
        collection_method = clean_external_metadata(fallback_sources.get(url) or "") or None
        source_type = source_type_for_url(
            url,
            company_url,
            collection_method=collection_method,
            is_in_scope_fn=is_in_scope,
        )
        if source_type != "first_party":
            counts["public"] += 1
            continue
        counts["first_party"] += 1
        kind = _classify_first_party_page(url, text or "", company_url)
        counts[kind] += 1
    return counts


def _scrape_trace_text(bundle_dir: Path) -> str:
    path = bundle_dir / "_raw_scrapes" / "_scrape_trace.log"
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _empty_corpus_guidance(trace: str) -> tuple[str, str, str]:
    """Return the empty-run reason, next step, and source-class state."""
    folded = trace.casefold()
    if "rate_limit_skip" in folded:
        return (
            "First-party collection was skipped because the host is rate-limited.",
            "Wait for the host cooldown, then rerun `primr prep` for this company.",
            "queried and failed",
        )
    if "toomanyredirects" in folded or ("exceeded" in folded and "redirect" in folded):
        return (
            "First-party collection stopped in a redirect loop.",
            "Retry `primr prep` after the site's canonical URL is requested directly.",
            "queried and failed",
        )
    if "403" in trace or "forbidden" in folded:
        return (
            "First-party collection was refused (HTTP 403).",
            "Retry `primr prep` later, or raise `--max-pages` if another public page exists.",
            "queried and failed",
        )
    return (_EMPTY_COLLECTION_REASON, _EMPTY_COLLECTION_NEXT, "queried and empty")


def _partial_collection_guidance(
    bundle_dir: Path,
    assessment: dict[str, int],
    *,
    corpus_empty: bool,
) -> tuple[str, str]:
    if assessment["qualifying"]:
        return "", ""
    if corpus_empty or (assessment["first_party"] == 0 and assessment["public"] == 0):
        reason, step, _state = _empty_corpus_guidance(_scrape_trace_text(bundle_dir))
        return reason, step
    if assessment["first_party"] == 0:
        return (
            "No current human-readable first-party page was captured.",
            "Retry `primr prep` for this company.",
        )
    first_party = assessment["first_party"]
    if assessment["machine"] == first_party:
        return (
            "Only machine endpoints were captured; no human-readable first-party page.",
            "Retry `primr prep` so collection can reach a human-readable company page.",
        )
    if assessment["other_locale"] == first_party:
        return (
            "Captured first-party pages are a different locale than the requested site.",
            "Retry `primr prep` against the locale in the company URL, or raise `--max-pages`.",
        )
    if assessment["old"] == first_party:
        return (
            "Captured first-party pages are old, not current.",
            "Retry `primr prep` so collection can reach a current page, or raise `--max-pages`.",
        )
    if assessment["placeholder"] == first_party:
        return (
            "Captured first-party text is placeholder content, not a human-readable company page.",
            "Retry `primr prep` against the company's public site.",
        )
    if assessment["unreadable"] == first_party:
        return (
            "Captured first-party pages are not human-readable.",
            "Retry `primr prep`, or raise `--max-pages` to collect a longer public page.",
        )
    return (
        "Captured first-party pages are not current human-readable coverage.",
        "Retry `primr prep`, or raise `--max-pages` to collect a current public page.",
    )


def _class_record(state: str, reason: str = "") -> dict[str, str]:
    if reason and state != "captured":
        return {"state": state, "reason": reason}
    return {"state": state}


def _source_class_report(
    bundle_dir: Path,
    assessment: dict[str, int],
    *,
    include_recon: bool,
    include_hiring: bool,
    recon_collected: bool,
    hiring_collected: bool,
    hiring_postings: int,
    partial_reason: str,
) -> dict[str, dict[str, str]]:
    """Record whether each prep source class was captured, empty, failed, or skipped."""
    if assessment["qualifying"]:
        first_party = _class_record("captured")
    elif assessment["first_party"] == 0 and assessment["public"] == 0:
        _reason, _step, state = _empty_corpus_guidance(_scrape_trace_text(bundle_dir))
        first_party = _class_record(state, partial_reason)
    elif assessment["first_party"] == 0:
        first_party = _class_record("queried and empty", partial_reason)
    else:
        first_party = _class_record("queried and failed", partial_reason)

    if assessment["public"]:
        public_fallbacks = _class_record("captured")
    elif "rate_limit_skip" in _scrape_trace_text(bundle_dir).casefold():
        public_fallbacks = _class_record("queried and empty", partial_reason)
    else:
        public_fallbacks = _class_record("not queried")

    if not include_recon:
        dns_recon = _class_record("not queried")
    elif recon_collected:
        dns_recon = _class_record("captured")
    else:
        dns_recon = _class_record(
            "queried and empty",
            "Requested DNS reconnaissance produced no artifact.",
        )

    if not include_hiring:
        hiring = _class_record("not queried")
    elif hiring_postings > 0:
        hiring = _class_record("captured")
    elif hiring_collected:
        hiring = _class_record("queried and empty", "Hiring collection produced no postings.")
    else:
        hiring = _class_record(
            "queried and empty",
            "Requested hiring-signal collection produced no artifact.",
        )

    return {
        "first_party_pages": first_party,
        "dns_recon": dns_recon,
        "hiring_signals": hiring,
        "public_fallbacks": public_fallbacks,
    }
