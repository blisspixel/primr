"""Hiring-signal LLM extraction helpers (extracted from ``hiring_signals``).

The JSON-blob parser, the batched extraction call, and the output coercion
moved here verbatim when ``hiring_signals`` hit its architecture line
ceiling; behavior is unchanged and ``hiring_signals`` re-exports the names.

Posting titles and bodies are scraped verbatim from careers pages / ATS
boards - the T1 prompt-injection boundary - so the extraction prompt fences
them as data.
"""

from __future__ import annotations

import json
import re
from abc import abstractmethod
from collections.abc import Sequence
from typing import Any, Protocol

from primr.ai.provider_availability import LocalCapacityBusyError
from primr.utils.content_sanitizer import fence_untrusted
from primr.utils.logging_config import get_logger

logger = get_logger("data.hiring_extraction")

__all__ = ["_coerce_extraction", "_extract_signals", "_parse_json_blob"]


class _PostingLike(Protocol):
    """Posting fields consumed by extraction without importing orchestration."""

    body: str | None
    department: str
    location: str
    title: str
    url: str

    @abstractmethod
    def age_days(self) -> int | None:
        """Return the posting age when its source provides a timestamp."""

        raise NotImplementedError

    @abstractmethod
    def is_stale(self) -> bool:
        """Return whether the posting is older than the accepted window."""

        raise NotImplementedError


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
    postings: Sequence[_PostingLike],
    company_name: str,
    *,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Run the batched extraction LLM call. Returns a dict that mirrors
    the HiringSignals schema fields, or None on failure.
    """
    from primr.utils.model_policy import model_calls_disabled

    if model_calls_disabled():
        return None
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

    # T1 boundary: posting titles and bodies are scraped verbatim from careers
    # pages / ATS boards and enter the extraction prompt only as fenced data
    # (a planted "ignore instructions" JD must be read as content, not obeyed).
    aggregated = fence_untrusted("JOB_POSTINGS", "\n\n".join(body_blocks))

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
            model=model or "grok-4.3",
            temperature=0.3,
            max_tokens=4_000,
            retries=1,
        )
    except LocalCapacityBusyError:
        raise
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
