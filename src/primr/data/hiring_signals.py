"""
Hiring-signal gathering: discover a company's open job postings and extract
strategic signals (tech stack, initiatives, org shape, culture) that aren't
in the marketing copy.

Pipeline
--------
1. **Discover** — try ATS board APIs (Greenhouse, Lever, Ashby,
   SmartRecruiters) in parallel against slug candidates derived from the
   company name and website. If all ATS probes miss, fall back to an HTML
   crawl of the company's careers page.
2. **Triage** — ask an LLM to pick the most signal-rich postings out of the
   discovered list (senior / engineering / product / platform roles are
   almost always more informative than retail / support / entry). Falls
   back to a deterministic title-based ranker if the LLM call fails.
3. **Fetch** — for ATS hits the posting body is usually already in the
   board-API response. For HTML discoveries fetch individual postings via
   the popup-free external orchestrator.
4. **Extract** — one batched LLM call over the aggregated JD text produces
   structured signals: tech-stack frequency, strategic initiatives,
   culture cues, hiring volume, and a one-paragraph synthesis.
5. **Persist** — write a human-readable markdown summary and a structured
   JSON artifact into `<working>/_hiring/`; individual JD bodies go into
   `<working>/_hiring/raw/` for auditability.

All stages are fail-open — missing / broken data at any point still
produces either a shorter artifact or None. The caller treats None as
"no hiring signals available, carry on."

Why this exists
---------------
Job posts are one of the most honest signals a company emits about what
they're building *right now*. "Hiring 5 engineers with Snowflake + dbt
+ Terraform experience" tells you more about the near-term data platform
direction than any marketing page will.
"""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


# =============================================================================
# Tunables
# =============================================================================

# Per-request HTTP timeouts. ATS board APIs are small JSON; HTML careers
# pages vary but shouldn't need more than a few seconds on a healthy site.
_ATS_TIMEOUT_S = 6.0
_HTML_LIST_TIMEOUT_S = 10.0
_HTML_POSTING_TIMEOUT_S = 12.0

# Caps. Keep these conservative — the signal saturates well before 20
# postings and LLM context costs scale linearly with JD volume.
MAX_SELECTED_POSTINGS = 15
MAX_DISCOVERED_POSTINGS = 80
MAX_HTML_LINKS_SCANNED = 60
MAX_SLUG_CANDIDATES = 6

# Bodies that look absurdly short are usually "apply via our ATS" redirects
# that didn't render — drop them.
_MIN_USEFUL_BODY_CHARS = 200

# Stale JDs (older than ~9 months) describe old strategy. Tag but don't drop.
_STALE_DAYS_THRESHOLD = 270

_USER_AGENT = "primr/1.0 (+https://github.com/blisspixel/primr; research fetcher)"


# =============================================================================
# Data types
# =============================================================================


@dataclass
class Posting:
    """A single discovered job posting.

    ATS providers fill in most fields from their board API response. HTML
    discovery fills ``url`` / ``title`` from the careers-page listing and
    populates ``body`` only after an individual fetch.
    """

    url: str
    title: str
    location: str = ""
    department: str = ""
    source: str = "html"  # "greenhouse" | "lever" | "ashby" | "smartrecruiters" | "html"
    updated_at: str | None = None  # ISO8601 if known
    body: str | None = None
    apply_url: str | None = None

    def age_days(self) -> int | None:
        if not self.updated_at:
            return None
        try:
            parsed = datetime.fromisoformat(self.updated_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        delta = datetime.now(parsed.tzinfo) - parsed
        return max(0, delta.days)

    def is_stale(self) -> bool:
        age = self.age_days()
        return age is not None and age > _STALE_DAYS_THRESHOLD


@dataclass
class HiringSignals:
    """Structured output of the extraction pass.

    ``roles`` is a best-effort role-and-location summary; ``tech_stack`` is
    a frequency map so downstream prompts can weight what was mentioned
    repeatedly (likely core stack) vs. once (likely stretch / aspirational).
    """

    company_slug: str
    source: str  # which discovery path produced the data
    postings_found: int
    postings_selected: int
    postings_extracted: int
    roles: list[dict[str, str]] = field(default_factory=list)
    tech_stack: dict[str, int] = field(default_factory=dict)
    strategic_initiatives: list[str] = field(default_factory=list)
    culture_signals: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    hiring_volume: str = "unknown"  # "low" | "moderate" | "high"
    notable_absences: list[str] = field(default_factory=list)
    summary: str = ""
    stale_fraction: float = 0.0  # portion of extracted postings older than threshold

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_empty(self) -> bool:
        return self.postings_extracted == 0


# =============================================================================
# Shared HTTP helper
# =============================================================================


def _http_get(
    url: str,
    timeout: float,
    headers: dict | None = None,
    params: dict | None = None,
) -> tuple[int | None, bytes | None, str | None]:
    """Plain httpx GET with follow_redirects. Returns (status, body, final_url).

    Mirrors the helper in ``fallback_sources.py`` so the two fail-open
    fan-outs behave consistently. Errors are logged at debug and returned
    as ``(None, None, None)`` — the caller decides what to do.

    SSRF protection: validates the initial URL and the final URL after
    redirects against the central SSRF blocklist (loopback / RFC1918 /
    link-local / cloud metadata). An attacker-controlled careers page that
    links to or redirects to internal infrastructure is dropped here, even
    though the original company_url passed the MCP URL validator. The
    fallback HTTP helper in ``fallback_sources.py`` applies the same
    checks; keep them in sync if either is updated.
    """
    from primr.utils.security import is_safe_url, validate_final_url_after_redirect

    safe, reason = is_safe_url(url)
    if not safe:
        logger.info("hiring-signals: blocked outbound request to %s (%s)", url, reason)
        return None, None, None

    try:
        import httpx

        base_headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            base_headers.update(headers)

        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=base_headers,
        ) as client:
            resp = client.get(url, params=params)
            final_url = str(resp.url)
            safe_final, reason = validate_final_url_after_redirect(final_url)
            if not safe_final:
                logger.info(
                    "hiring-signals: dropped response from %s — final URL %s blocked (%s)",
                    url,
                    final_url,
                    reason,
                )
                return None, None, None
            return resp.status_code, resp.content, final_url
    except Exception as e:
        logger.debug("hiring-signals HTTP GET failed for %s: %s", url, e)
        return None, None, None


# =============================================================================
# Slug guessing
# =============================================================================


_SLUG_STRIP_TOKENS = {
    "inc",
    "llc",
    "ltd",
    "co",
    "corp",
    "corporation",
    "holdings",
    "group",
    "company",
    "plc",
    "sa",
    "ag",
    "gmbh",
    "the",
}


def _slugify(raw: str) -> str:
    """Lowercase, collapse punctuation / whitespace to single hyphens."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return cleaned


def _candidate_slugs(
    company_name: str,
    website: str,
    recon_hints: dict | None = None,
) -> list[str]:
    """Produce up to MAX_SLUG_CANDIDATES ordered slug guesses.

    Priority: recon-detected ATS subdomain slugs > website hostname >
    company-name variants (with / without corp suffixes). Deduped while
    preserving order so the highest-quality guess is tried first.
    """
    seen: set[str] = set()
    out: list[str] = []

    def _add(slug: str) -> None:
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)

    # Recon-supplied ATS hints (e.g. "boards.greenhouse.io/acme" → "acme")
    if recon_hints:
        for slug in recon_hints.get("ats_slugs", []) or []:
            _add(_slugify(str(slug)))

    # Website hostname — "example.com" → "example", "acme-corp.io" → "acme-corp"
    try:
        host = urlparse(website).netloc.lower().removeprefix("www.")
        root = host.split(".")[0] if host else ""
        if root:
            _add(_slugify(root))
    except Exception:
        pass

    # Company name variants
    name = (company_name or "").strip()
    if name:
        tokens = [t for t in re.split(r"[^A-Za-z0-9]+", name.lower()) if t]
        # Full hyphenated: "Acme Corp Holdings" → "acme-corp-holdings"
        _add("-".join(tokens))
        # No separator: "acmecorpholdings"
        _add("".join(tokens))
        # Strip corporate suffixes: "acme-corp-holdings" → "acme"
        meaningful = [t for t in tokens if t not in _SLUG_STRIP_TOKENS]
        if meaningful:
            _add("-".join(meaningful))
            _add(meaningful[0])

    return out[:MAX_SLUG_CANDIDATES]


# =============================================================================
# ATS providers
# =============================================================================


def _strip_html(html: str) -> str:
    """Crude HTML-to-text. Good enough for board-API content fields."""
    if not html:
        return ""
    # Remove script/style blocks first
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block tags with newlines
    text = re.sub(r"</(p|div|li|h[1-6]|br|tr|td)\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode a few common entities
    replacements = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&apos;": "'",
    }
    for key, val in replacements.items():
        text = text.replace(key, val)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fetch_greenhouse(slug: str) -> list[Posting] | None:
    """Greenhouse public board API. Returns None on miss.

    Endpoint: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    status, body, _ = _http_get(url, timeout=_ATS_TIMEOUT_S, params={"content": "true"})
    if status != 200 or not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    jobs = data.get("jobs") or []
    if not jobs:
        return None
    out: list[Posting] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = str(job.get("title") or "").strip()
        link = str(job.get("absolute_url") or "").strip()
        if not title or not link:
            continue
        loc_field = job.get("location")
        location = str(loc_field.get("name") if isinstance(loc_field, dict) else "").strip()
        # Greenhouse puts the department hierarchy in "departments"
        dept = ""
        depts = job.get("departments") or []
        if depts and isinstance(depts, list) and isinstance(depts[0], dict):
            dept = str(depts[0].get("name") or "").strip()
        raw_content = job.get("content") or ""
        body_text = _strip_html(raw_content) if raw_content else None
        out.append(
            Posting(
                url=link,
                title=title,
                location=location,
                department=dept,
                source="greenhouse",
                updated_at=str(job.get("updated_at") or "") or None,
                body=body_text,
            )
        )
    return out or None


def _fetch_lever(slug: str) -> list[Posting] | None:
    """Lever public postings API. Returns None on miss.

    Endpoint: https://api.lever.co/v0/postings/{slug}?mode=json
    """
    url = f"https://api.lever.co/v0/postings/{slug}"
    status, body, _ = _http_get(url, timeout=_ATS_TIMEOUT_S, params={"mode": "json"})
    if status != 200 or not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list) or not data:
        return None
    out: list[Posting] = []
    for job in data:
        if not isinstance(job, dict):
            continue
        title = str(job.get("text") or "").strip()
        link = str(job.get("hostedUrl") or job.get("applyUrl") or "").strip()
        if not title or not link:
            continue
        cats = job.get("categories") or {}
        location = str(cats.get("location") or "").strip() if isinstance(cats, dict) else ""
        department = str(cats.get("department") or "").strip() if isinstance(cats, dict) else ""
        description = str(job.get("descriptionPlain") or "")
        lists = job.get("lists") or []
        if isinstance(lists, list):
            for section in lists:
                if isinstance(section, dict):
                    section_text = _strip_html(section.get("content") or "")
                    if section_text:
                        description += "\n\n" + section_text
        body_text = description.strip() or None
        created = job.get("createdAt")
        updated_iso: str | None = None
        if isinstance(created, (int, float)):
            # Lever uses ms since epoch
            try:
                updated_iso = datetime.fromtimestamp(created / 1000).isoformat()
            except (OSError, OverflowError, ValueError):
                updated_iso = None
        out.append(
            Posting(
                url=link,
                title=title,
                location=location,
                department=department,
                source="lever",
                updated_at=updated_iso,
                body=body_text,
                apply_url=str(job.get("applyUrl") or "") or None,
            )
        )
    return out or None


def _fetch_ashby(slug: str) -> list[Posting] | None:
    """Ashby public job-board API. Returns None on miss.

    Endpoint: https://api.ashbyhq.com/posting-api/job-board/{slug}
    (Includes rich posting bodies directly.)
    """
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    status, body, _ = _http_get(
        url, timeout=_ATS_TIMEOUT_S, params={"includeCompensation": "false"}
    )
    if status != 200 or not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list) or not jobs:
        return None
    out: list[Posting] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = str(job.get("title") or "").strip()
        link = str(job.get("jobUrl") or "").strip()
        if not title or not link:
            continue
        location = str(job.get("locationName") or "").strip()
        department = str(job.get("departmentName") or job.get("teamName") or "").strip()
        description_html = job.get("descriptionHtml") or job.get("descriptionPlainText") or ""
        body_text = _strip_html(description_html) if description_html else None
        out.append(
            Posting(
                url=link,
                title=title,
                location=location,
                department=department,
                source="ashby",
                updated_at=str(job.get("publishedAt") or "") or None,
                body=body_text,
            )
        )
    return out or None


_WORKDAY_HOST_RE = re.compile(
    r"https?://([A-Za-z0-9][A-Za-z0-9-]*)\.(wd\d+)\.myworkdayjobs\.com"
    r"(?:/[A-Za-z]{2}-[A-Za-z]{2})?/([A-Za-z0-9_\-]+)",
    re.IGNORECASE,
)

_WORKDAY_DEFAULT_DATACENTERS = ("wd1", "wd3", "wd5", "wd103")
_WORKDAY_DEFAULT_SITES = (
    "External",
    "Careers",
    "External_Careers",
    "External_Career_Site",
    "Global_External",
)


def _workday_endpoints(triple: tuple[str, str, str]) -> tuple[str, str]:
    """Return (jobs_post_url, posting_base_url) for a (tenant, dc, site) triple."""
    tenant, dc, site = triple
    jobs_url = f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    base_url = f"https://{tenant}.{dc}.myworkdayjobs.com/en-US/{site}"
    return jobs_url, base_url


def _discover_workday_triples(corpus: dict[str, str] | None) -> list[tuple[str, str, str]]:
    """Scan scraped corpus content for canonical Workday board URLs.

    Returns deduped (tenant, datacenter, site) triples. Empty when nothing
    matched. Reading the corpus first is dramatically cheaper than blind
    probing — a single match yields the exact URL we need.
    """
    if not corpus:
        return []
    triples: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for text in corpus.values():
        if not text or "myworkdayjobs.com" not in text.lower():
            continue
        for match in _WORKDAY_HOST_RE.finditer(text):
            triple = (match.group(1).lower(), match.group(2).lower(), match.group(3))
            if triple in seen:
                continue
            seen.add(triple)
            triples.append(triple)
            if len(triples) >= 4:
                return triples
    return triples


def _workday_fetch_one(triple: tuple[str, str, str]) -> list[Posting] | None:
    """POST to a Workday `/wday/cxs/{tenant}/{site}/jobs` endpoint.

    Returns parsed postings or None on miss / shape mismatch (fail closed).
    The endpoint is undocumented; if Workday changes the response shape we
    drop through rather than crash, matching the rest of the module's
    fail-open posture.
    """
    import httpx

    from primr.utils.security import is_safe_url, validate_final_url_after_redirect

    jobs_url, base_url = _workday_endpoints(triple)
    safe, reason = is_safe_url(jobs_url)
    if not safe:
        logger.info("hiring-signals: blocked Workday request to %s (%s)", jobs_url, reason)
        return None

    payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=_ATS_TIMEOUT_S, follow_redirects=True, headers=headers) as client:
            resp = client.post(jobs_url, json=payload)
    except Exception as exc:
        logger.debug("Workday POST failed for %s: %s", jobs_url, exc)
        return None

    safe_final, reason = validate_final_url_after_redirect(str(resp.url))
    if not safe_final:
        logger.info("hiring-signals: dropped Workday response — final URL blocked (%s)", reason)
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    items = data.get("jobPostings")
    if not isinstance(items, list) or not items:
        return None

    out: list[Posting] = []
    for job in items:
        if not isinstance(job, dict):
            continue
        title = str(job.get("title") or "").strip()
        external_path = str(job.get("externalPath") or "").strip()
        if not title or not external_path:
            continue
        full_url = urljoin(base_url + "/", external_path.lstrip("/"))
        location = str(job.get("locationsText") or "").strip()
        posted_on = str(job.get("postedOn") or "").strip()
        out.append(
            Posting(
                url=full_url,
                title=title,
                location=location,
                department="",
                source="workday",
                updated_at=posted_on or None,
            )
        )
    return out or None


_WORKDAY_BLIND_DISCOVERY_BUDGET = 8


def _fetch_workday(slug: str) -> list[Posting] | None:
    """Workday provider with bounded blind discovery.

    Workday's board URL embeds two opaque components: the tenant subdomain
    (close to but not always the company slug) and the site path. When
    corpus-scanning has not pre-discovered a triple, fall back to a small
    cross product of common datacenters and site IDs.

    Budget guard: when called from the parallel ATS fan-out, this fires
    once per slug candidate (up to MAX_SLUG_CANDIDATES=6). The full
    cross-product is 4 datacenters * 5 sites = 20 POSTs per slug, which
    against a real Workday tenant becomes an aggressive probe pattern
    (one tenant could see 120+ POSTs across the parallel slugs). We cap
    the per-call probe budget at _WORKDAY_BLIND_DISCOVERY_BUDGET and
    rely on corpus-driven URL discovery for the canonical hit when one
    is recoverable from the scraped corpus.
    """
    for probes, triple in enumerate(_candidate_workday_triples(slug)):
        if probes >= _WORKDAY_BLIND_DISCOVERY_BUDGET:
            return None
        postings = _workday_fetch_one(triple)
        if postings:
            return postings
    return None


def _candidate_workday_triples(slug: str) -> list[tuple[str, str, str]]:
    """Bounded list of (tenant, dc, site) triples to probe for a slug."""
    triples: list[tuple[str, str, str]] = []
    for dc in _WORKDAY_DEFAULT_DATACENTERS:
        for site in _WORKDAY_DEFAULT_SITES:
            triples.append((slug, dc, site))
    return triples


def _fetch_workable(slug: str) -> list[Posting] | None:
    """Workable public widget API. Returns None on miss.

    Endpoint: https://apply.workable.com/api/v1/widget/accounts/{slug}
    Shape (when present): {"jobs": [{"title": "...", "shortcode": "...",
    "url": "...", "city": "...", "country": "...", "department": "..."}]}
    """
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
    status, body, _ = _http_get(url, timeout=_ATS_TIMEOUT_S)
    if status != 200 or not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    jobs = data.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        return None
    out: list[Posting] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = str(job.get("title") or "").strip()
        link = str(job.get("url") or "").strip()
        if not title or not link:
            continue
        city = str(job.get("city") or "").strip()
        country = str(job.get("country") or "").strip()
        location = ", ".join(p for p in (city, country) if p) or ""
        department = str(job.get("department") or "").strip()
        out.append(
            Posting(
                url=link,
                title=title,
                location=location,
                department=department,
                source="workable",
                updated_at=str(job.get("published") or "") or None,
            )
        )
    return out or None


def _fetch_recruitee(slug: str) -> list[Posting] | None:
    """Recruitee public offers API. Returns None on miss.

    Endpoint: https://{slug}.recruitee.com/api/offers/
    Shape: {"offers": [{"title": "...", "careers_url": "...",
    "city": "...", "country": "...", "department": "...", ...}]}
    """
    url = f"https://{slug}.recruitee.com/api/offers/"
    status, body, _ = _http_get(url, timeout=_ATS_TIMEOUT_S)
    if status != 200 or not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    offers = data.get("offers")
    if not isinstance(offers, list) or not offers:
        return None
    out: list[Posting] = []
    for job in offers:
        if not isinstance(job, dict):
            continue
        title = str(job.get("title") or "").strip()
        link = str(job.get("careers_url") or job.get("careers_apply_url") or "").strip()
        if not title or not link:
            continue
        city = str(job.get("city") or "").strip()
        country = str(job.get("country") or "").strip()
        location = ", ".join(p for p in (city, country) if p) or ""
        department = str(job.get("department") or "").strip()
        description_html = job.get("description") or ""
        body_text = _strip_html(description_html) if description_html else None
        out.append(
            Posting(
                url=link,
                title=title,
                location=location,
                department=department,
                source="recruitee",
                updated_at=str(job.get("published_at") or "") or None,
                body=body_text,
            )
        )
    return out or None


def _fetch_jobvite(slug: str) -> list[Posting] | None:
    """Jobvite public RSS feed. Returns None on miss.

    Jobvite doesn't expose a stable JSON board API, but the RSS feed at
    https://jobs.jobvite.com/{slug}/jobs?format=rss is widely deployed.
    We parse it loosely and convert each item into a Posting.
    """
    url = f"https://jobs.jobvite.com/{slug}/jobs"
    status, body, _ = _http_get(url, timeout=_ATS_TIMEOUT_S, params={"format": "rss"})
    if status != 200 or not body:
        return None
    text = body.decode("utf-8", errors="ignore")
    if "<item" not in text.lower():
        return None
    out: list[Posting] = []
    for match in re.finditer(r"<item\b[^>]*>(.*?)</item>", text, re.DOTALL | re.IGNORECASE):
        block = match.group(1)
        title_match = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.DOTALL)
        link_match = re.search(r"<link>(.*?)</link>", block, re.DOTALL)
        if not title_match or not link_match:
            continue
        title = title_match.group(1).strip()
        link = link_match.group(1).strip()
        if not title or not link:
            continue
        out.append(
            Posting(
                url=link,
                title=title,
                location="",
                department="",
                source="jobvite",
            )
        )
        if len(out) >= MAX_DISCOVERED_POSTINGS:
            break
    return out or None


def _fetch_smartrecruiters(slug: str) -> list[Posting] | None:
    """SmartRecruiters public postings API. Returns None on miss.

    Endpoint: https://api.smartrecruiters.com/v1/companies/{slug}/postings
    Note: initial response has no body — we only harvest metadata here
    and let the extraction path fetch bodies if needed.
    """
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    status, body, _ = _http_get(url, timeout=_ATS_TIMEOUT_S, params={"limit": "100"})
    if status != 200 or not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    items = data.get("content") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        return None
    out: list[Posting] = []
    for job in items:
        if not isinstance(job, dict):
            continue
        title = str(job.get("name") or "").strip()
        uuid = str(job.get("id") or "").strip()
        if not title or not uuid:
            continue
        link = f"https://jobs.smartrecruiters.com/{slug}/{uuid}"
        loc_field = job.get("location") or {}
        city = loc_field.get("city") if isinstance(loc_field, dict) else ""
        country = loc_field.get("country") if isinstance(loc_field, dict) else ""
        location = ", ".join(p for p in (city, country) if p) or ""
        department = ""
        dept_field = job.get("department")
        if isinstance(dept_field, dict):
            department = str(dept_field.get("label") or "").strip()
        out.append(
            Posting(
                url=link,
                title=title,
                location=location,
                department=department,
                source="smartrecruiters",
                updated_at=str(job.get("releasedDate") or "") or None,
            )
        )
    return out or None


_ATS_PROVIDERS: list[tuple[str, Any]] = [
    ("greenhouse", _fetch_greenhouse),
    ("lever", _fetch_lever),
    ("ashby", _fetch_ashby),
    ("smartrecruiters", _fetch_smartrecruiters),
    ("workday", _fetch_workday),
    ("workable", _fetch_workable),
    ("recruitee", _fetch_recruitee),
    ("jobvite", _fetch_jobvite),
]


def _discover_via_ats(
    slugs: list[str],
    max_workers: int = 8,
) -> tuple[list[Posting], str | None]:
    """Fan out every (provider, slug) combo in parallel. First provider
    that returns a non-empty listing wins; we don't merge across providers
    because the slug spaces aren't interchangeable (acme on Greenhouse is
    not necessarily the same company as acme on Lever).

    Returns (postings, provider_name) or ([], None) on total miss.
    """
    results: dict[str, list[Posting]] = {}

    def _probe(provider: str, fetcher: Any, slug: str) -> tuple[str, str, list[Posting] | None]:
        try:
            return provider, slug, fetcher(slug)
        except Exception as e:
            logger.debug("ATS probe %s/%s failed: %s", provider, slug, e)
            return provider, slug, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(_probe, provider, fetcher, slug)
            for provider, fetcher in _ATS_PROVIDERS
            for slug in slugs
        ]
        for fut in as_completed(futures):
            try:
                provider, _, postings = fut.result()
            except Exception:
                continue
            if postings and provider not in results:
                results[provider] = postings

    # Prefer the provider that returned the most postings — on the rare
    # occasion two providers both match, that's our best tiebreak signal.
    if not results:
        return [], None
    provider = max(results.keys(), key=lambda p: len(results[p]))
    return results[provider], provider


# =============================================================================
# Web-search fallback — when ATS and careers HTML both come up short
# =============================================================================


_WEB_SEARCH_POSTING_HOST_HINTS = (
    "linkedin.com/jobs",
    "indeed.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "builtin.com",
    "monster.com",
    "dice.com",
    "myworkdayjobs.com",
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "jobs.smartrecruiters.com",
    "apply.workable.com",
    "jobs.jobvite.com",
    "recruitee.com",
    "careers-",  # iCIMS pattern: careers-{tenant}.icims.com
    ".bamboohr.com/jobs",
)

# Lowercase pattern used to strip board-name suffixes from search result
# titles so the role label is what's left. Each entry is matched at the
# end of the title only.
_WEB_SEARCH_TITLE_SUFFIXES = (
    r"\s+\|\s+linkedin.*$",
    r"\s+-\s+linkedin.*$",
    r"\s+\|\s+indeed.*$",
    r"\s+-\s+indeed.*$",
    r"\s+\|\s+glassdoor.*$",
    r"\s+-\s+glassdoor.*$",
    r"\s+\|\s+ziprecruiter.*$",
    r"\s+at\s+.+\s+\|\s+.+$",
    r"\s+\|\s+.+careers.*$",
)


def _looks_like_posting_url(url: str) -> bool:
    lower = url.lower()
    return any(hint in lower for hint in _WEB_SEARCH_POSTING_HOST_HINTS)


def _clean_web_search_title(title: str) -> str:
    """Strip common job-board suffixes from a search result title."""
    cleaned = title.strip()
    for pattern in _WEB_SEARCH_TITLE_SUFFIXES:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    # "Senior Engineer at Acme" -> "Senior Engineer"
    cleaned = re.sub(r"\s+at\s+[A-Z][^|]*$", "", cleaned)
    return cleaned.strip(" -|·")


def _discover_via_web_search(
    company_name: str,
    website: str,
    *,
    max_results: int = 20,
) -> list[Posting]:
    """Search the web for job postings when ATS + HTML chain comes up short.

    Uses DuckDuckGo directly (no API key) and filters for URLs that look
    like job postings. Returns metadata-only Postings — bodies are not
    fetched because most of these hosts block automated scraping. The
    downstream extraction is fail-open and degrades gracefully when no
    bodies are available.
    """
    try:
        from ddgs import DDGS
        from ddgs.exceptions import DDGSException
    except ImportError:
        logger.debug("ddgs not available — skipping web-search posting fallback")
        return []

    domain_hint = ""
    try:
        host = urlparse(website).netloc.lower().removeprefix("www.")
        if host:
            domain_hint = f" {host}"
    except Exception:
        pass

    query = f'"{company_name}" jobs OR careers OR hiring{domain_hint}'
    out: list[Posting] = []
    seen_urls: set[str] = set()
    try:
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except DDGSException as exc:
        logger.debug("Web-search posting fallback failed: %s", exc)
        return []
    except Exception as exc:
        logger.debug("Web-search posting fallback errored: %s", exc)
        return []

    for hit in results:
        if not isinstance(hit, dict):
            continue
        url = str(hit.get("href") or hit.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        if not _looks_like_posting_url(url):
            continue
        title = _clean_web_search_title(str(hit.get("title") or "").strip())
        if not title or len(title) > 200:
            continue
        seen_urls.add(url)
        out.append(
            Posting(
                url=url,
                title=title,
                location="",
                department="",
                source="web-search",
            )
        )
        if len(out) >= MAX_DISCOVERED_POSTINGS:
            break
    return out


# =============================================================================
# HTML fallback — discover via a careers page
# =============================================================================


_CAREERS_PATHS = ("/careers", "/jobs", "/company/careers", "/about/careers")

# Common subdomain prefixes companies use to host job boards. Probed
# alongside the on-path /careers and /jobs URLs so we catch the very
# common jobs.{company}.com / careers.{company}.com pattern that often
# masks an ATS-hosted board behind a vanity subdomain.
_CAREERS_SUBDOMAIN_PREFIXES = (
    "jobs",
    "careers",
    "work",
    "talent",
    "apply",
    "recruit",
)

# Regex hints for "this link probably points at an individual job posting."
# Broadened to include /apply/, /role/, /open-roles/, /talent/ patterns
# common on company-hosted careers sites.
_POSTING_URL_HINTS = re.compile(
    r"/(?:jobs?|careers?|positions?|openings?|roles?|opportunities?|"
    r"apply|role|open[\-_]roles?|open[\-_]positions?|talent|listings?)/"
    r"(?:[a-z0-9][a-z0-9\-_]+)",
    re.IGNORECASE,
)


def _careers_url_candidates(website: str, corpus: dict[str, str] | None) -> list[str]:
    """Return careers-page URLs worth probing.

    Priority order:
      1. Any URL already in the scraped corpus whose path looks like a
         careers page (no second HTTP call needed).
      2. Subdomain probes: jobs.{domain}, careers.{domain}, work.{domain},
         talent.{domain}, apply.{domain}, recruit.{domain}. These are the
         most common public-facing entry points for company job boards
         even when the backend is Workday / Greenhouse / etc.
      3. On-path probes: {root}/careers, {root}/jobs, etc.

    Capped at a small budget so the parallel HTTP fan-out doesn't blow up
    against companies whose careers site is at a non-standard location.
    """
    urls: list[str] = []
    seen: set[str] = set()

    if corpus:
        for url in corpus:
            path = urlparse(url).path.lower()
            host = urlparse(url).netloc.lower()
            if any(p in path for p in ("/careers", "/jobs")) and url not in seen:
                seen.add(url)
                urls.append(url)
            elif any(host.startswith(p + ".") for p in _CAREERS_SUBDOMAIN_PREFIXES) and url not in seen:
                # Corpus pages on a careers subdomain are also candidates.
                seen.add(url)
                urls.append(url)

    try:
        parsed = urlparse(website)
        root_host = parsed.netloc.lower().removeprefix("www.") if parsed.netloc else ""
        scheme = parsed.scheme or "https"

        # Subdomain candidates first — they're often the canonical
        # company-facing careers URL and frequently redirect to the
        # backing ATS in a way that lets us discover the tenant slug.
        if root_host:
            for prefix in _CAREERS_SUBDOMAIN_PREFIXES:
                candidate = f"{scheme}://{prefix}.{root_host}/"
                if candidate not in seen:
                    seen.add(candidate)
                    urls.append(candidate)

        # On-path candidates against the supplied website root.
        root = f"{scheme}://{parsed.netloc}" if parsed.netloc else website
        for path in _CAREERS_PATHS:
            candidate = urljoin(root.rstrip("/") + "/", path.lstrip("/"))
            if candidate not in seen:
                seen.add(candidate)
                urls.append(candidate)
    except Exception:
        pass

    # Bumped from 6 to 14 to accommodate the 6 subdomain probes plus the
    # 4 on-path probes plus a handful of corpus carryovers.
    return urls[:14]


def _extract_posting_links(html: bytes, base_url: str) -> list[tuple[str, str]]:
    """Scan a careers-page HTML body for links that look like individual
    job postings. Returns (absolute_url, anchor_text) tuples, deduped by
    URL and capped at MAX_HTML_LINKS_SCANNED.
    """
    try:
        text = html.decode("utf-8", errors="ignore")
    except Exception:
        return []

    # <a href="..." ...>LABEL</a>
    pattern = re.compile(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
    )
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        href, label_html = match.group(1), match.group(2)
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if not _POSTING_URL_HINTS.search(href):
            continue
        absolute = urljoin(base_url, href.split("#")[0])
        if absolute in seen:
            continue
        seen.add(absolute)
        label = _strip_html(label_html).strip()
        if not label or len(label) > 200:
            continue
        out.append((absolute, label))
        if len(out) >= MAX_HTML_LINKS_SCANNED:
            break
    return out


# Maps ATS hostnames to the name of a fetcher function that takes the
# slug extracted from the final URL and returns postings. The function
# is looked up via `globals()[fetcher_name]` at call time rather than
# captured by reference — this way `patch.object(hs, "_fetch_greenhouse")`
# in tests reaches the dispatch path. Workday is special: it needs
# (tenant, dc, site) extracted from both host and path, so it gets
# inline handling below.
_ATS_HOST_FETCHERS: tuple[tuple[re.Pattern[str], str, str | None], ...] = (
    (
        re.compile(
            r"^(?:[a-z]{2}-[a-z]{2}\.)?([A-Za-z0-9][A-Za-z0-9-]*)"
            r"\.(wd\d+)\.myworkdayjobs\.com",
            re.IGNORECASE,
        ),
        "workday",
        None,
    ),
    (re.compile(r"^boards\.greenhouse\.io", re.IGNORECASE), "greenhouse", "_fetch_greenhouse"),
    (re.compile(r"^jobs\.lever\.co", re.IGNORECASE), "lever", "_fetch_lever"),
    (re.compile(r"^jobs\.ashbyhq\.com", re.IGNORECASE), "ashby", "_fetch_ashby"),
    (re.compile(r"^jobs\.smartrecruiters\.com", re.IGNORECASE), "smartrecruiters", "_fetch_smartrecruiters"),
    (re.compile(r"^apply\.workable\.com", re.IGNORECASE), "workable", "_fetch_workable"),
    (re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)\.recruitee\.com", re.IGNORECASE), "recruitee", "_fetch_recruitee"),
    (re.compile(r"^jobs\.jobvite\.com", re.IGNORECASE), "jobvite", "_fetch_jobvite"),
)


def _detect_ats_redirect(
    final_url: str,
) -> tuple[str, list[Posting]] | None:
    """If `final_url` lives on a known ATS host, extract the tenant slug
    from the URL path and call the matching provider directly. Returns
    (provider_name, postings) on success, None on no match or empty fetch.

    Lets us turn "jobs.acme.com redirects to acmecorp.wd5.myworkdayjobs.com"
    into a direct Workday tenant hit without running the bounded-but-still-
    expensive blind discovery cross product.
    """
    parsed = urlparse(final_url)
    host = parsed.netloc.lower().removeprefix("www.")
    if not host:
        return None

    for host_re, provider_name, fetcher_name in _ATS_HOST_FETCHERS:
        host_match = host_re.match(host)
        if not host_match:
            continue

        if provider_name == "workday":
            # Workday's redirect target encodes tenant + datacenter in
            # the host AND the site id in the path; pull all three.
            tenant = host_match.group(1).lower()
            dc = host_match.group(2).lower()
            path_match = re.search(
                r"^(?:/[A-Za-z]{2}-[A-Za-z]{2})?/([A-Za-z0-9_\-]+)",
                parsed.path,
            )
            if not path_match:
                continue
            site = path_match.group(1)
            postings = _workday_fetch_one((tenant, dc, site))
            if postings:
                return provider_name, postings
            continue

        # Greenhouse / Lever / Ashby / SmartRecruiters / Workable / Jobvite
        # take a slug from the path's first segment.
        path_match = re.match(r"^/([A-Za-z0-9][A-Za-z0-9_\-]*)", parsed.path)
        if provider_name == "recruitee":
            # Recruitee tenant is in the subdomain, not the path.
            slug = host_match.group(1).lower()
        elif path_match:
            slug = path_match.group(1)
        else:
            continue

        # Look up the fetcher by name at call time so test patches like
        # patch.object(hs, "_fetch_greenhouse") reach this code path.
        fetcher = globals().get(fetcher_name) if fetcher_name else None
        try:
            postings = fetcher(slug) if callable(fetcher) else None
        except Exception as exc:
            logger.debug(
                "ATS-redirect dispatch failed for %s/%s: %s",
                provider_name,
                slug,
                exc,
            )
            postings = None
        if postings:
            return provider_name, postings

    return None


def _discover_via_html(
    website: str,
    corpus: dict[str, str] | None,
) -> tuple[list[Posting], str | None]:
    """Crawl the company's own careers page for individual posting links.
    Does not fetch posting bodies — that happens later for the selected
    subset only.

    When a careers URL probe redirects to a known ATS host, the redirect
    detector takes over and returns ATS-sourced postings instead of
    HTML-extracted ones. The second return value is the source label
    (ATS provider name when the redirect path fired, "html" when we
    extracted links from a careers HTML body, None when nothing matched).
    """
    postings: list[Posting] = []
    seen_urls: set[str] = set()
    source: str | None = None

    for careers_url in _careers_url_candidates(website, corpus):
        # Reuse corpus content if we already scraped this URL during the
        # main pass — saves a redundant HTTP call.
        html_bytes: bytes | None = None
        final_url: str | None = None
        if corpus and careers_url in corpus:
            html_bytes = corpus[careers_url].encode("utf-8", errors="ignore")
            final_url = careers_url
        else:
            status, body, resolved = _http_get(
                careers_url, timeout=_HTML_LIST_TIMEOUT_S
            )
            if status == 200 and body:
                html_bytes = body
                final_url = resolved or careers_url

        if not html_bytes or not final_url:
            continue

        # ATS-redirect short-circuit: if jobs.{company}.com (or any of the
        # subdomain probes) redirects to a known ATS host, dispatch to
        # the provider directly with the slug extracted from the final
        # URL. Avoids both the HTML parse and the Workday blind discovery
        # loop when we already know the canonical board.
        redirect_hit = _detect_ats_redirect(final_url)
        if redirect_hit is not None:
            provider_name, redirect_postings = redirect_hit
            new = [p for p in redirect_postings if p.url not in seen_urls]
            for p in new:
                seen_urls.add(p.url)
            postings.extend(new)
            source = provider_name
            # ATS hits dominate — return immediately so we don't pollute
            # with lower-quality HTML matches from other candidates.
            return postings[:MAX_DISCOVERED_POSTINGS], source

        for url, label in _extract_posting_links(html_bytes, final_url):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            postings.append(
                Posting(
                    url=url,
                    title=label,
                    location="",
                    department="",
                    source="html",
                )
            )
            if len(postings) >= MAX_DISCOVERED_POSTINGS:
                return postings, "html"

    if postings:
        source = "html"
    return postings, source


# =============================================================================
# LLM-backed triage
# =============================================================================


def _deterministic_triage(postings: list[Posting], k: int) -> list[int]:
    """Fallback ranking when the LLM call fails. Boosts senior / engineering
    / product / data / security / platform roles; demotes retail / sales
    SDR / support / intern / entry-level roles. Ties broken by original
    order so providers that put strategic jobs first are respected.
    """
    boost = re.compile(
        r"\b(chief|vp|vice\s+president|head\s+of|director|principal|staff|"
        r"lead|senior|sr\.?|architect|engineer|data|ml|ai|security|"
        r"platform|product\s+manager|cto|ciso|cpo|gm|general\s+manager)\b",
        re.IGNORECASE,
    )
    demote = re.compile(
        r"\b(intern|co[-\s]op|apprentice|associate|jr\.?|junior|entry|"
        r"retail|store|barista|cashier|warehouse|delivery|support\s+rep|"
        r"sdr|bdr|sales\s+dev|customer\s+support|customer\s+service)\b",
        re.IGNORECASE,
    )
    scored: list[tuple[int, int]] = []
    for i, posting in enumerate(postings):
        score = 0
        if boost.search(posting.title):
            score += 3
        if demote.search(posting.title):
            score -= 4
        if posting.department and re.search(
            r"engineering|product|data|platform|security|infrastructure",
            posting.department,
            re.IGNORECASE,
        ):
            score += 2
        # Slight age preference: fresher first
        age = posting.age_days()
        if age is not None and age > _STALE_DAYS_THRESHOLD:
            score -= 2
        scored.append((i, score))

    scored.sort(key=lambda p: (-p[1], p[0]))
    return [i for i, _ in scored[:k]]


def _llm_triage(
    postings: list[Posting],
    company_name: str,
    k: int,
) -> list[int]:
    """Ask Grok to pick up to ``k`` indices that yield the richest signals.
    Falls back to the deterministic ranker on any parse / API failure.
    """
    from primr.ai.grok_client import grok_llm

    # Show the model a compact list, not full JDs — we want a selection,
    # not a summary.
    listing_lines: list[str] = []
    for i, p in enumerate(postings):
        dept_frag = f" [{p.department}]" if p.department else ""
        loc_frag = f" — {p.location}" if p.location else ""
        listing_lines.append(f"{i}. {p.title}{dept_frag}{loc_frag}")
    listing = "\n".join(listing_lines)

    prompt = f"""You are triaging open job postings at {company_name or "a target company"} for a strategic research brief.

Pick up to {k} postings whose descriptions are most likely to reveal:
- Tech stack and platforms in use
- Strategic initiatives ("building AI/ML platform", "expanding EMEA")
- Organizational shape (who reports to whom, maturity of the function)
- Culture and operating model signals

Prefer senior, engineering, product, platform, data, security, and leadership roles.
Down-weight retail, entry-level, support, and high-volume sales roles unless no other signal exists.

Respond with ONLY valid JSON matching this schema:
{{"selected": [<index>, <index>, ...]}}

Postings:
{listing}
"""
    try:
        raw = grok_llm(
            prompt,
            model="grok-4.20-non-reasoning",
            temperature=0.2,
            max_tokens=1_500,
            retries=1,
        )
    except Exception as e:
        logger.info("Hiring-signals triage LLM call failed: %s — using deterministic fallback", e)
        return _deterministic_triage(postings, k)

    parsed = _parse_json_blob(raw)
    if not isinstance(parsed, dict):
        return _deterministic_triage(postings, k)
    selected = parsed.get("selected")
    if not isinstance(selected, list):
        return _deterministic_triage(postings, k)
    valid = [int(i) for i in selected if isinstance(i, int) and 0 <= int(i) < len(postings)]
    if not valid:
        return _deterministic_triage(postings, k)
    # Respect the user-facing cap even if the LLM overshoots.
    return valid[:k]


# =============================================================================
# Body fetch for selected HTML postings
# =============================================================================


def _fetch_html_posting_bodies(
    postings: list[Posting],
    max_workers: int = 4,
) -> None:
    """Populate `.body` in-place for HTML-source postings that don't have
    one yet. ATS postings already have bodies from the listing API.
    """
    targets = [p for p in postings if p.source == "html" and not p.body]
    if not targets:
        return

    def _fetch_one(post: Posting) -> None:
        status, body, _ = _http_get(post.url, timeout=_HTML_POSTING_TIMEOUT_S)
        if status == 200 and body:
            text = _strip_html(body.decode("utf-8", errors="ignore"))
            if len(text) >= _MIN_USEFUL_BODY_CHARS:
                post.body = text

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_fetch_one, p) for p in targets]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                logger.debug("HTML posting fetch failed: %s", e)


# =============================================================================
# LLM extraction
# =============================================================================


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL | re.IGNORECASE)
_FIRST_JSON_OBJECT_RE = re.compile(r"(\{.*\})", re.DOTALL)


def _parse_json_blob(raw: str) -> Any:
    """Best-effort JSON parse over LLM output. Handles raw JSON, fenced
    JSON, and JSON embedded in prose.
    """
    if not raw:
        return None
    candidates: list[str] = [raw.strip()]
    fence = _JSON_FENCE_RE.search(raw)
    if fence:
        candidates.insert(0, fence.group(1).strip())
    obj = _FIRST_JSON_OBJECT_RE.search(raw)
    if obj:
        candidates.append(obj.group(1).strip())
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _extract_signals(
    postings: list[Posting],
    company_name: str,
) -> dict[str, Any] | None:
    """Run the batched extraction LLM call. Returns a dict that mirrors
    the HiringSignals schema fields, or None on failure.
    """
    from primr.ai.grok_client import grok_llm

    body_blocks: list[str] = []
    for i, p in enumerate(postings, start=1):
        if not p.body:
            continue
        # Cap individual JDs so one very long posting can't dominate context.
        snippet = p.body[:6_000]
        dept_frag = f" | Department: {p.department}" if p.department else ""
        loc_frag = f" | Location: {p.location}" if p.location else ""
        age = p.age_days()
        age_frag = f" | Posted ~{age}d ago" if age is not None else ""
        stale_frag = " [STALE]" if p.is_stale() else ""
        body_blocks.append(
            f"--- POSTING {i}{stale_frag} ---\n"
            f"Title: {p.title}{dept_frag}{loc_frag}{age_frag}\n"
            f"URL: {p.url}\n\n"
            f"{snippet}"
        )
    if not body_blocks:
        return None

    aggregated = "\n\n".join(body_blocks)

    prompt = f"""You are analysing open job postings at {company_name or "a target company"} to surface strategic signals for a consultant brief.

Return ONLY valid JSON matching this schema:
{{
  "roles": [{{"title": "...", "location": "...", "department": "..."}}],
  "tech_stack": {{"Snowflake": 4, "dbt": 2, ...}},
  "strategic_initiatives": ["Building AI/ML platform", "Expanding EMEA presence"],
  "culture_signals": ["Remote-first", "Fast-paced scale-up"],
  "locations": ["New York, NY", "London, UK"],
  "hiring_volume": "low" | "moderate" | "high",
  "notable_absences": ["No dedicated security roles", "No data engineering"],
  "summary": "One paragraph synthesising what these postings reveal about near-term direction."
}}

Guidance:
- ``tech_stack`` values are the number of distinct postings that mention the technology. Count each posting at most once per technology.
- ``strategic_initiatives`` must be grounded in specific phrases from the postings, not guessed.
- ``notable_absences`` is optional — only populate when the overall posting mix reveals a gap worth flagging (e.g., heavy product hiring but no security or data engineering).
- ``summary`` must be one paragraph, under 150 words, factual, and avoid marketing language.

Postings follow. Tags in [brackets] like [STALE] are hints — consider them.

{aggregated}
"""
    try:
        raw = grok_llm(
            prompt,
            model="grok-4.3",
            temperature=0.3,
            max_tokens=4_000,
            retries=1,
        )
    except Exception as e:
        logger.warning("Hiring-signals extraction LLM call failed: %s", e)
        return None

    parsed = _parse_json_blob(raw)
    if not isinstance(parsed, dict):
        logger.info("Hiring-signals extraction: could not parse JSON from LLM output")
        return None
    return parsed


def _coerce_extraction(parsed: dict[str, Any]) -> dict[str, Any]:
    """Clamp / coerce LLM output into the shapes HiringSignals expects.
    Accepts missing fields, wrong-typed fields, etc. — always returns a
    dict with every expected key present.
    """

    def _string_list(val: Any, cap: int = 20) -> list[str]:
        if not isinstance(val, list):
            return []
        return [str(x).strip() for x in val if str(x).strip()][:cap]

    stack_raw = parsed.get("tech_stack")
    tech_stack: dict[str, int] = {}
    if isinstance(stack_raw, dict):
        for k, v in stack_raw.items():
            try:
                tech_stack[str(k).strip()] = max(1, int(v))
            except (TypeError, ValueError):
                continue

    roles_raw = parsed.get("roles")
    roles: list[dict[str, str]] = []
    if isinstance(roles_raw, list):
        for item in roles_raw[:30]:
            if not isinstance(item, dict):
                continue
            roles.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "location": str(item.get("location") or "").strip(),
                    "department": str(item.get("department") or "").strip(),
                }
            )

    volume = str(parsed.get("hiring_volume") or "unknown").strip().lower()
    if volume not in {"low", "moderate", "high", "unknown"}:
        volume = "unknown"

    return {
        "roles": roles,
        "tech_stack": tech_stack,
        "strategic_initiatives": _string_list(parsed.get("strategic_initiatives")),
        "culture_signals": _string_list(parsed.get("culture_signals")),
        "locations": _string_list(parsed.get("locations")),
        "hiring_volume": volume,
        "notable_absences": _string_list(parsed.get("notable_absences")),
        "summary": str(parsed.get("summary") or "").strip(),
    }


# =============================================================================
# Artifact persistence
# =============================================================================


def _render_markdown(signals: HiringSignals, selected: list[Posting]) -> str:
    """Render a compact human-readable summary. Mirrors the tone of other
    primr research artifacts — no headers the final report would copy.
    """
    lines: list[str] = []
    lines.append(f"# Hiring Signals — {signals.company_slug}")
    lines.append("")
    lines.append(
        f"Source: **{signals.source}** · "
        f"{signals.postings_found} postings found · "
        f"{signals.postings_extracted} analysed"
        + (f" · {signals.stale_fraction:.0%} stale" if signals.stale_fraction > 0 else "")
    )
    lines.append("")
    if signals.summary:
        lines.append("## Summary")
        lines.append(signals.summary)
        lines.append("")
    if signals.tech_stack:
        lines.append("## Tech Stack (postings mentioning)")
        ordered = sorted(signals.tech_stack.items(), key=lambda p: (-p[1], p[0].lower()))
        for tech, count in ordered[:25]:
            lines.append(f"- {tech}: {count}")
        lines.append("")
    if signals.strategic_initiatives:
        lines.append("## Strategic Initiatives")
        for item in signals.strategic_initiatives:
            lines.append(f"- {item}")
        lines.append("")
    if signals.culture_signals:
        lines.append("## Culture & Operating Model")
        for item in signals.culture_signals:
            lines.append(f"- {item}")
        lines.append("")
    if signals.notable_absences:
        lines.append("## Notable Absences")
        for item in signals.notable_absences:
            lines.append(f"- {item}")
        lines.append("")
    if signals.locations:
        lines.append("## Locations Advertised")
        lines.append(", ".join(signals.locations))
        lines.append("")
    lines.append(f"Hiring volume: **{signals.hiring_volume}**")
    lines.append("")
    if selected:
        lines.append("## Postings Analysed")
        for p in selected:
            loc = f" — {p.location}" if p.location else ""
            dept = f" ({p.department})" if p.department else ""
            lines.append(f"- [{p.title}{dept}{loc}]({p.url})")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _persist(
    working_folder: str,
    signals: HiringSignals,
    all_postings: list[Posting],
    selected: list[Posting],
) -> None:
    """Write `<working>/_hiring/` artifacts. Errors are logged; they do
    not propagate — persistence failure shouldn't abort the research run.
    """
    hiring_dir = os.path.join(working_folder, "_hiring")
    raw_dir = os.path.join(hiring_dir, "raw")
    try:
        os.makedirs(raw_dir, exist_ok=True)
    except Exception as e:
        logger.warning("Could not create hiring-signals directory: %s", e)
        return

    try:
        with open(os.path.join(hiring_dir, "hiring_signals.json"), "w", encoding="utf-8") as f:
            json.dump(signals.to_dict(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("hiring_signals.json write failed: %s", e)

    try:
        md = _render_markdown(signals, selected)
        with open(os.path.join(hiring_dir, "hiring_signals.md"), "w", encoding="utf-8") as f:
            f.write(md)
    except Exception as e:
        logger.warning("hiring_signals.md write failed: %s", e)

    try:
        index = [
            {
                "url": p.url,
                "title": p.title,
                "location": p.location,
                "department": p.department,
                "source": p.source,
                "updated_at": p.updated_at,
            }
            for p in all_postings
        ]
        with open(os.path.join(hiring_dir, "postings_index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("postings_index.json write failed: %s", e)

    for i, posting in enumerate(selected, start=1):
        if not posting.body:
            continue
        safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", posting.title)[:60] or "posting"
        fname = f"jd_{i:03d}_{safe_title}.txt"
        try:
            with open(os.path.join(raw_dir, fname), "w", encoding="utf-8") as f:
                f.write(f"URL: {posting.url}\n")
                f.write(f"Title: {posting.title}\n")
                f.write(f"Location: {posting.location}\n")
                f.write(f"Department: {posting.department}\n")
                f.write(f"Source: {posting.source}\n")
                if posting.updated_at:
                    f.write(f"Updated: {posting.updated_at}\n")
                f.write("-" * 60 + "\n\n")
                f.write(posting.body)
        except Exception as e:
            logger.debug("Could not persist raw JD %s: %s", fname, e)


def render_for_prompt(signals: HiringSignals, char_budget: int = 6_000) -> str:
    """Compact serialization for downstream LLM prompts.

    Produces a plain-text block that can be appended to insights / external
    sources without blowing up token budgets. Respects ``char_budget`` by
    truncating low-signal sections first.
    """
    if signals.is_empty():
        return ""

    parts: list[str] = []
    parts.append(
        f"Source: {signals.source} · "
        f"{signals.postings_extracted}/{signals.postings_found} postings analysed · "
        f"Hiring volume: {signals.hiring_volume}"
    )
    if signals.summary:
        parts.append(f"Summary: {signals.summary}")
    if signals.tech_stack:
        ordered = sorted(signals.tech_stack.items(), key=lambda p: (-p[1], p[0].lower()))
        top = ", ".join(f"{tech} (×{count})" for tech, count in ordered[:20])
        parts.append(f"Tech stack mentioned: {top}")
    if signals.strategic_initiatives:
        bullets = "\n".join(f"  - {item}" for item in signals.strategic_initiatives[:10])
        parts.append(f"Strategic initiatives:\n{bullets}")
    if signals.culture_signals:
        bullets = "\n".join(f"  - {item}" for item in signals.culture_signals[:8])
        parts.append(f"Culture / operating model:\n{bullets}")
    if signals.notable_absences:
        bullets = "\n".join(f"  - {item}" for item in signals.notable_absences[:6])
        parts.append(f"Notable absences:\n{bullets}")
    if signals.locations:
        parts.append("Locations: " + ", ".join(signals.locations[:15]))
    if signals.roles:
        role_lines = []
        for r in signals.roles[:10]:
            frag = r.get("title") or ""
            loc = r.get("location") or ""
            dept = r.get("department") or ""
            if dept:
                frag += f" [{dept}]"
            if loc:
                frag += f" — {loc}"
            if frag:
                role_lines.append(f"  - {frag}")
        if role_lines:
            parts.append("Representative roles:\n" + "\n".join(role_lines))
    if signals.stale_fraction > 0:
        parts.append(f"Stale fraction (>{_STALE_DAYS_THRESHOLD}d): {signals.stale_fraction:.0%}")

    text = "\n\n".join(parts)
    if len(text) > char_budget:
        text = text[: char_budget - 3].rstrip() + "..."
    return text


# =============================================================================
# Public entry point
# =============================================================================


def gather_hiring_signals(
    company_name: str,
    website: str,
    *,
    corpus: dict[str, str] | None = None,
    working_folder: str | None = None,
    max_selected: int = MAX_SELECTED_POSTINGS,
    recon_hints: dict | None = None,
) -> HiringSignals | None:
    """Discover open postings, triage them, extract strategic signals.

    Returns None when no usable postings are found. The caller should
    treat None as "company doesn't publish jobs / ATS not public / HTML
    fallback didn't find anything" — not as an error.

    ``corpus`` is the already-scraped main-site content (URL -> text) from
    ``fetch_web_content``. Passing it lets the HTML fallback skip re-fetching
    a careers page we already have in memory.

    ``recon_hints`` is an optional dict that may contain ``ats_slugs`` — a
    list of slugs extracted from recon-detected ATS subdomains. These are
    tried before name-based guesses.
    """
    if os.getenv("PRIMR_SKIP_HIRING_SIGNALS", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("Hiring signals disabled via PRIMR_SKIP_HIRING_SIGNALS")
        return None

    slugs = _candidate_slugs(company_name, website, recon_hints)
    if not slugs:
        logger.info("No slug candidates for hiring signals (company=%r)", company_name)
        return None

    # If the scraped corpus already revealed an explicit Workday board URL,
    # hit those endpoints directly before the slug-based fan-out. This
    # avoids the bounded blind-discovery cost when we have ground truth.
    corpus_workday_triples = _discover_workday_triples(corpus)
    postings: list[Posting] = []
    ats_source: str | None = None
    if corpus_workday_triples:
        logger.info(
            "Hiring signals: corpus revealed %d Workday triple(s); fetching directly",
            len(corpus_workday_triples),
        )
        for triple in corpus_workday_triples:
            direct = _workday_fetch_one(triple)
            if direct:
                postings = direct
                ats_source = "workday"
                break

    if not postings:
        logger.info("Hiring signals: trying ATS slugs %s", slugs)
        postings, ats_source = _discover_via_ats(slugs)

    discovery_source: str
    if postings:
        discovery_source = ats_source or "ats"
        logger.info(
            "Hiring signals: %d postings via %s (slugs=%s)",
            len(postings),
            discovery_source,
            slugs,
        )
    else:
        logger.info("Hiring signals: no ATS match, falling back to HTML discovery")
        postings, html_source = _discover_via_html(website, corpus)
        if postings:
            discovery_source = html_source or "html"
            logger.info(
                "Hiring signals: %d postings via %s (HTML / subdomain probe)",
                len(postings),
                discovery_source,
            )
        else:
            discovery_source = "none"

    # Web-search fallback: when ATS providers + careers-page crawl both
    # came up empty, sweep DDG across major job-board hosts to pick up
    # roles. Metadata-only — bodies rarely return useful content from
    # these hosts, and we degrade gracefully through the no-bodies branch
    # below. Only triggered when truly empty so we don't augment a
    # working ATS hit with noisier web-search rows.
    if not postings:
        web_hits = _discover_via_web_search(company_name, website)
        if web_hits:
            logger.info(
                "Hiring signals: web-search fallback found %d postings",
                len(web_hits),
            )
            postings = web_hits
            discovery_source = "web-search"

    chosen_slug = slugs[0] if slugs else ""

    if not postings:
        logger.info("Hiring signals: no postings discovered — skipping extraction")
        return HiringSignals(
            company_slug=chosen_slug,
            source="none",
            postings_found=0,
            postings_selected=0,
            postings_extracted=0,
        )

    # Cap discovered list before triage — the LLM doesn't need to see 500.
    postings = postings[:MAX_DISCOVERED_POSTINGS]

    selected_idx = _llm_triage(postings, company_name, max_selected)
    selected = [postings[i] for i in selected_idx]

    _fetch_html_posting_bodies(selected)
    selected_with_body = [p for p in selected if p.body and len(p.body) >= _MIN_USEFUL_BODY_CHARS]

    if not selected_with_body:
        logger.info("Hiring signals: no bodies recovered for selected postings")
        # When bodies were unrecoverable but we still have role titles
        # (typical for the web-search fallback against rate-limited job
        # boards), populate the roles list from posting metadata so the
        # downstream discovery prompt still sees role-type signal. Run
        # the web-search title cleaner on every title here — ATS / HTML
        # discoveries that fail body fetch can also have noisy suffixes
        # (board names, company labels) bolted on, and the cleaner is
        # safe to run on already-clean strings.
        metadata_roles: list[dict[str, str]] = []
        for posting in selected[:30]:
            cleaned = _clean_web_search_title(posting.title).strip()
            if not cleaned:
                continue
            metadata_roles.append(
                {
                    "title": cleaned,
                    "location": posting.location,
                    "department": posting.department,
                }
            )
        skeleton = HiringSignals(
            company_slug=chosen_slug,
            source=discovery_source,
            postings_found=len(postings),
            postings_selected=len(selected),
            postings_extracted=len(metadata_roles),
            roles=metadata_roles,
        )
        if working_folder:
            _persist(working_folder, skeleton, postings, selected)
        return skeleton

    parsed = _extract_signals(selected_with_body, company_name)
    coerced = (
        _coerce_extraction(parsed)
        if isinstance(parsed, dict)
        else {
            "roles": [],
            "tech_stack": {},
            "strategic_initiatives": [],
            "culture_signals": [],
            "locations": [],
            "hiring_volume": "unknown",
            "notable_absences": [],
            "summary": "",
        }
    )

    stale_count = sum(1 for p in selected_with_body if p.is_stale())
    stale_fraction = stale_count / len(selected_with_body) if selected_with_body else 0.0

    signals = HiringSignals(
        company_slug=chosen_slug,
        source=discovery_source,
        postings_found=len(postings),
        postings_selected=len(selected),
        postings_extracted=len(selected_with_body),
        stale_fraction=stale_fraction,
        **coerced,
    )

    if working_folder:
        _persist(working_folder, signals, postings, selected_with_body)

    return signals
