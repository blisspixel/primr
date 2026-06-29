"""Artifact rendering and persistence for hiring-signal extraction."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Sequence
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class PostingLike(Protocol):
    """Subset of posting fields needed for artifact rendering."""

    url: str
    title: str
    location: str
    department: str
    source: str
    updated_at: str | None
    body: str | None


class HiringSignalsLike(Protocol):
    """Subset of hiring-signal fields needed for artifact rendering."""

    company_slug: str
    source: str
    postings_found: int
    postings_selected: int
    postings_extracted: int
    roles: list[dict[str, str]]
    tech_stack: dict[str, int]
    strategic_initiatives: list[str]
    culture_signals: list[str]
    locations: list[str]
    hiring_volume: str
    notable_absences: list[str]
    summary: str
    stale_fraction: float

    def is_empty(self) -> bool: ...

    def to_dict(self) -> dict[str, Any]: ...


def _render_markdown(signals: HiringSignalsLike, selected: Sequence[PostingLike]) -> str:
    """Render a compact human-readable summary for hiring-signal artifacts."""

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
        for posting in selected:
            loc = f" — {posting.location}" if posting.location else ""
            dept = f" ({posting.department})" if posting.department else ""
            lines.append(f"- [{posting.title}{dept}{loc}]({posting.url})")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _persist(
    working_folder: str,
    signals: HiringSignalsLike,
    all_postings: Sequence[PostingLike],
    selected: Sequence[PostingLike],
) -> None:
    """Write hiring artifacts, logging but not propagating persistence failures."""

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
                "url": posting.url,
                "title": posting.title,
                "location": posting.location,
                "department": posting.department,
                "source": posting.source,
                "updated_at": posting.updated_at,
            }
            for posting in all_postings
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


def render_for_prompt(
    signals: HiringSignalsLike,
    char_budget: int = 6_000,
    *,
    stale_days_threshold: int,
) -> str:
    """Compact serialization for downstream LLM prompts."""

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
        for role in signals.roles[:10]:
            frag = role.get("title") or ""
            loc = role.get("location") or ""
            dept = role.get("department") or ""
            if dept:
                frag += f" [{dept}]"
            if loc:
                frag += f" — {loc}"
            if frag:
                role_lines.append(f"  - {frag}")
        if role_lines:
            parts.append("Representative roles:\n" + "\n".join(role_lines))
    if signals.stale_fraction > 0:
        parts.append(f"Stale fraction (>{stale_days_threshold}d): {signals.stale_fraction:.0%}")

    text = "\n\n".join(parts)
    if len(text) > char_budget:
        text = text[: char_budget - 3].rstrip() + "..."
    return text
