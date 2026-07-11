"""Deterministic hiring-posting selection helpers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from primr.ai.provider_availability import LocalCapacityBusyError
from primr.utils.content_sanitizer import fence_untrusted
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


class PostingLike(Protocol):
    title: str
    location: str
    department: str

    def age_days(self) -> int | None: ...


# Job-board and search result pages often append board / company suffixes to
# titles, so the role label is what remains. Each entry is matched at the end.
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


def clean_web_search_title(title: str) -> str:
    """Strip common job-board suffixes from a search result title."""
    cleaned = title.strip()
    for pattern in _WEB_SEARCH_TITLE_SUFFIXES:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+at\s+[A-Z][^|]*$", "", cleaned)
    return cleaned.strip(" -|\u00b7")


def deterministic_triage(
    postings: Sequence[PostingLike], k: int, *, stale_days_threshold: int
) -> list[int]:
    """Rank postings locally when a model is unavailable or a triage call fails."""
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
        age = posting.age_days()
        if age is not None and age > stale_days_threshold:
            score -= 2
        scored.append((i, score))

    scored.sort(key=lambda p: (-p[1], p[0]))
    return [i for i, _ in scored[:k]]


def llm_triage(
    postings: Sequence[PostingLike],
    company_name: str,
    k: int,
    *,
    model: str | None = None,
    stale_days_threshold: int,
) -> list[int]:
    """Select signal-rich postings, preserving typed local-capacity failures."""

    from primr.utils.model_policy import model_calls_disabled

    if model_calls_disabled():
        return deterministic_triage(postings, k, stale_days_threshold=stale_days_threshold)

    from primr.ai.grok_client import grok_llm
    from primr.data.hiring_extraction import _parse_json_blob

    listing_lines: list[str] = []
    for i, posting in enumerate(postings):
        department = f" [{posting.department}]" if posting.department else ""
        location = f" - {posting.location}" if posting.location else ""
        listing_lines.append(f"{i}. {posting.title}{department}{location}")
    listing = fence_untrusted("JOB_POSTING_TITLES", "\n".join(listing_lines))

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
            model=model or "grok-4.20-non-reasoning",
            temperature=0.2,
            max_tokens=1_500,
            retries=1,
        )
    except LocalCapacityBusyError:
        raise
    except Exception as error:
        logger.info(
            "Hiring-signals triage LLM call failed: %s; using deterministic fallback",
            error,
        )
        return deterministic_triage(postings, k, stale_days_threshold=stale_days_threshold)

    parsed = _parse_json_blob(raw)
    if not isinstance(parsed, dict):
        return deterministic_triage(postings, k, stale_days_threshold=stale_days_threshold)
    selected = parsed.get("selected")
    if not isinstance(selected, list):
        return deterministic_triage(postings, k, stale_days_threshold=stale_days_threshold)
    valid = [int(i) for i in selected if isinstance(i, int) and 0 <= int(i) < len(postings)]
    return (
        valid[:k]
        if valid
        else deterministic_triage(
            postings,
            k,
            stale_days_threshold=stale_days_threshold,
        )
    )


def metadata_roles_from_postings(
    postings: Sequence[PostingLike], *, cap: int = 30
) -> list[dict[str, str]]:
    roles: list[dict[str, str]] = []
    for posting in postings[:cap]:
        cleaned = clean_web_search_title(posting.title).strip()
        if not cleaned:
            continue
        roles.append(
            {
                "title": cleaned,
                "location": posting.location,
                "department": posting.department,
            }
        )
    return roles
