"""Phase 1: role discovery.

Reads primr's existing evidence files (recon + hiring signals) and uses one
LLM call to identify the top N roles at the target company. Roles are
returned with confidence labels and citations.

Job postings are the primary input to this stage. DNS recon is supporting
context. When hiring evidence is empty the pipeline fails closed by
default — see `EmptyHiringEvidenceError`. Operators can opt into the
degraded recon-only path with `allow_recon_only=True`, which the CLI
surfaces as `--allow-recon-only`.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from primr.skill_pack.archetypes import load_archetypes
from primr.skill_pack.prompts_loader import extract_json, load_skill_pack_prompt
from primr.skill_pack.schema import Role, RoleEvidence

logger = logging.getLogger(__name__)


# Filenames produced by the standard pipeline that we can read directly.
RECON_FILENAMES = ["_recon_context.txt", "_recon.txt"]
HIRING_FILENAMES = [
    "_hiring/hiring_signals.md",
    "_hiring/hiring_signals.txt",
    "_hiring/hiring_summary.md",
]
# Research evidence — the strategic report and scraped-content insights.
# When present these are the load-bearing input for plausible-role
# inference (Phase C-E) and the report-derived industry classification.
RESEARCH_FILENAMES = [
    "report.md",
    "insights.txt",
    "scraped_website_summary.txt",
    "analysis_workbook.md",
]

# Max evidence we forward to the LLM. Larger contexts cost tokens and
# rarely improve discovery quality past a saturation point.
_RECON_MAX_CHARS = 8_000
_HIRING_MAX_CHARS = 14_000
_RESEARCH_MAX_CHARS = 18_000

# Hiring-evidence text that looks like a populated artifact but reflects
# zero postings discovered. Both shapes can appear: the placeholder
# returned by load_evidence when no file exists, and the "Source: none"
# marker written by gather_hiring_signals when the full discovery chain
# came up empty.
#
# All markers anchor at line start (MULTILINE) to avoid false positives
# on legitimate hiring summaries that quote "0 postings" inline (e.g.,
# "year-over-year hiring grew from 0 postings found in Q1 to 40 in Q4").
_HIRING_PLACEHOLDER = "(no hiring evidence available)"
_HIRING_EMPTY_MARKERS = (
    re.compile(r"^\s*source:\s*\*?\*?none\*?\*?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*0\s+postings\s+found\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*0\s+(?:postings\s+)?analysed\s*$", re.IGNORECASE | re.MULTILINE),
)


class EmptyHiringEvidenceError(RuntimeError):
    """Raised when role discovery is asked to run with no job-posting input.

    Skill packs are job-posting-first. Failing closed here prevents the
    pipeline from silently shipping a recon-only pack that's structurally
    incomplete for services / reseller / consultancy companies where the
    revenue layer never shows up in DNS.
    """


def hiring_evidence_is_empty(text: str) -> bool:
    """True when the hiring evidence text represents zero postings."""
    if not text:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    if _HIRING_PLACEHOLDER in stripped.lower():
        return True
    return any(marker.search(stripped) for marker in _HIRING_EMPTY_MARKERS)


def _read_first_existing(base_dir: Path, candidates: list[str]) -> str | None:
    for relative in candidates:
        path = base_dir / relative
        if path.exists() and path.is_file():
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Could not read %s: %s", path, exc)
    return None


def load_evidence(working_dir: Path) -> tuple[str, str]:
    """Load (recon, hiring) evidence text from a working directory.

    Kept for backward compatibility with callers that only need the two
    primary evidence streams. New planning code should use
    ``load_full_evidence`` which also returns the research stream
    (insights + report) used by the plausible-roles inference.

    Returns "(no evidence)" placeholders for any source that isn't on disk.
    """
    recon, hiring, _ = load_full_evidence(working_dir)
    return recon, hiring


def load_full_evidence(working_dir: Path) -> tuple[str, str, str]:
    """Load (recon, hiring, research) evidence text from a working directory.

    Research evidence is drawn from the primr strategic report and the
    scraped-content insights when those files are present in the working
    dir (typical when --from-report points at a finished primr run).
    Returns "(no evidence)" placeholders for any source that isn't on
    disk so downstream prompts can render uniform inputs.

    Raises FileNotFoundError only when ALL three sources are missing — a
    working dir with at least one file is enough to proceed; the
    plan_roles caller decides whether the available signal is rich enough
    to justify running.
    """
    recon = _read_first_existing(working_dir, RECON_FILENAMES)
    hiring = _read_first_existing(working_dir, HIRING_FILENAMES)
    research = _read_first_existing(working_dir, RESEARCH_FILENAMES)

    if recon is None and hiring is None and research is None:
        raise FileNotFoundError(
            f"No recon, hiring, or research evidence found under {working_dir}. "
            "Run `primr <Company> <url> --mode scrape` first, or supply "
            "--from-report pointing at a directory that contains at least "
            "one of _recon_context.txt, _hiring/, report.md, or insights.txt."
        )

    recon = (recon or "(no recon evidence available)")[:_RECON_MAX_CHARS]
    hiring = (hiring or "(no hiring evidence available)")[:_HIRING_MAX_CHARS]
    research = (research or "(no research evidence available)")[:_RESEARCH_MAX_CHARS]
    return recon, hiring, research


def research_evidence_is_empty(text: str) -> bool:
    """True when the research evidence text represents no useful content."""
    if not text:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    return "(no research evidence available)" in stripped.lower()


def discover_roles(
    company_name: str,
    company_url: str | None,
    working_dir: Path,
    roles_count: int,
    *,
    reasoning_session: Any | None = None,
    allow_recon_only: bool = False,
) -> list[Role]:
    """Identify top `roles_count` roles at the company.

    Args:
        company_name: Display name.
        company_url: Optional URL — included in the prompt for context.
        working_dir: Directory containing recon + hiring evidence files.
        roles_count: Target number of roles to return (1-8).
        reasoning_session: Optional ContinuousReasoningSession to use
            instead of a fresh `grok_llm` call. When provided, the
            discovery turn becomes part of the shared session history.
        allow_recon_only: When False (default), raise
            EmptyHiringEvidenceError if the hiring evidence is empty.
            Set True to opt in to the degraded recon-only path.

    Returns a list of Role objects with empty `skills` (Phase 3 fills
    those in).

    Raises:
        EmptyHiringEvidenceError: when hiring evidence is empty and
            allow_recon_only is False.
    """
    recon, hiring, research = load_full_evidence(working_dir)
    if (
        hiring_evidence_is_empty(hiring)
        and research_evidence_is_empty(research)
        and not allow_recon_only
    ):
        raise EmptyHiringEvidenceError(
            "Role discovery refused: no job-posting evidence and no "
            "research evidence were gathered. Skill packs need either "
            "actual postings (primary) or strategic research (for "
            "plausible-role inference). DNS recon alone produces "
            "structurally incomplete packs. Pass --allow-recon-only "
            "(CLI) or allow_recon_only=True (API) to proceed with "
            "reduced confidence."
        )
    archetype_slugs = sorted(load_archetypes().keys())

    prompt = load_skill_pack_prompt("discover_roles")
    user_msg = prompt.render(
        company_name=company_name,
        company_url=company_url or "(not provided)",
        roles_count=roles_count,
        archetype_slugs=", ".join(archetype_slugs) or "(none bundled)",
        recon_evidence=recon,
        hiring_evidence=hiring,
    )

    response_text = _call_llm(prompt.system_prompt, user_msg, reasoning_session)
    parsed = extract_json(response_text)

    roles_raw = parsed.get("roles") or []
    if not isinstance(roles_raw, list):
        raise ValueError(f"discover_roles: expected `roles` array, got {type(roles_raw).__name__}")

    roles: list[Role] = []
    for entry in roles_raw[:roles_count]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        roles.append(
            Role(
                name=name,
                display_name=str(entry.get("display_name", name)).strip(),
                confidence=str(entry.get("confidence", "Inferred")).strip(),
                summary=str(entry.get("summary", "")).strip(),
                evidence=RoleEvidence(
                    sources=[str(s) for s in (entry.get("sources") or [])],
                    dns_signals=[str(s) for s in (entry.get("dns_signals") or [])],
                    posting_count=int(entry.get("posting_count") or 0),
                    archetype=(str(entry["archetype"]) if entry.get("archetype") else None),
                ),
            )
        )

    if not roles:
        raise RuntimeError(
            f"discover_roles returned no usable roles for {company_name}. "
            "Signal may be too sparse — check recon and hiring evidence."
        )

    logger.info(
        "Discovered %d roles for %s (signal=%s)",
        len(roles),
        company_name,
        parsed.get("signal_strength", "unknown"),
    )
    return roles


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    reasoning_session: Any | None,
) -> str:
    """Route the discovery call through the shared session if provided,
    otherwise use a fresh grok_llm() call."""
    if reasoning_session is not None and hasattr(reasoning_session, "send"):
        return reasoning_session.send(  # type: ignore[no-any-return]
            f"{system_prompt}\n\n{user_prompt}",
            temperature=0.3,
            max_tokens=8_000,
        )

    from primr.ai.grok_client import grok_llm

    return grok_llm(
        user_prompt,
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=8_000,
    )


__all__ = ["discover_roles", "load_evidence"]
