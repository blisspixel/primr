"""Phase 1: role discovery.

Reads primr's existing evidence files (recon + hiring signals) and uses one
LLM call to identify the top N roles at the target company. Roles are
returned with confidence labels and citations.
"""

from __future__ import annotations

import logging
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

# Max evidence we forward to the LLM. Larger contexts cost tokens and
# rarely improve discovery quality past a saturation point.
_RECON_MAX_CHARS = 8_000
_HIRING_MAX_CHARS = 14_000


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

    Returns "(no evidence)" placeholders for any source that isn't on disk.
    The discovery prompt is built to handle sparse signal gracefully —
    it returns fewer roles flagged as Speculated rather than fabricating.
    """
    recon = _read_first_existing(working_dir, RECON_FILENAMES)
    hiring = _read_first_existing(working_dir, HIRING_FILENAMES)

    if recon is None and hiring is None:
        raise FileNotFoundError(
            f"No recon or hiring evidence found under {working_dir}. "
            "Run `primr <Company> <url> --mode scrape` first, or supply "
            "--from-report pointing at a directory that contains "
            "_recon_context.txt and _hiring/."
        )

    recon = (recon or "(no recon evidence available)")[:_RECON_MAX_CHARS]
    hiring = (hiring or "(no hiring evidence available)")[:_HIRING_MAX_CHARS]
    return recon, hiring


def discover_roles(
    company_name: str,
    company_url: str | None,
    working_dir: Path,
    roles_count: int,
    *,
    reasoning_session: Any | None = None,
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

    Returns a list of Role objects with empty `skills` (Phase 3 fills
    those in).
    """
    recon, hiring = load_evidence(working_dir)
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
        raise ValueError(
            f"discover_roles: expected `roles` array, got {type(roles_raw).__name__}"
        )

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
                    archetype=(
                        str(entry["archetype"]) if entry.get("archetype") else None
                    ),
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
