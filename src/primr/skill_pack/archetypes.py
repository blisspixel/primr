"""Role archetype database.

Each `archetypes/*.yaml` file describes a canonical role: aliases for
fuzzy-matching whatever the role-discovery LLM emits, canonical skills,
authoritative references, and concrete AI-augmentation patterns.

Two roles for this module in the pipeline:

  1. **Match step** — given a free-form role name (e.g. "Senior Salesforce
     Administrator (Marketing Ops)"), find the closest bundled archetype.
     If nothing matches well, return None and let the caller decide whether
     to fall back to a DDG-grounded synthesis or proceed without grounding.

  2. **Grounding payload** — once matched, produce a prompt fragment that
     the authoring LLM gets as ground truth. This is what keeps generated
     skills aligned with real-world best practices rather than the model's
     imagination.

The bundled DB is intentionally small (curated, not exhaustive). DDG
fallback covers the long tail.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

ARCHETYPES_DIR = Path(__file__).parent / "archetypes"


@dataclass
class ArchetypeSkill:
    name: str
    display_name: str
    summary: str


@dataclass
class Archetype:
    slug: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    canonical_skills: list[ArchetypeSkill] = field(default_factory=list)
    ai_augmentation_patterns: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


def _parse_archetype(data: dict[str, Any]) -> Archetype:
    skills_raw = data.get("canonical_skills") or []
    skills = [
        ArchetypeSkill(
            name=s["name"],
            display_name=s.get("display_name", s["name"]),
            summary=s.get("summary", "").strip(),
        )
        for s in skills_raw
        if "name" in s
    ]
    return Archetype(
        slug=data["slug"],
        display_name=data.get("display_name", data["slug"]),
        aliases=[a.lower() for a in (data.get("aliases") or [])],
        keywords=[k.lower() for k in (data.get("keywords") or [])],
        canonical_skills=skills,
        ai_augmentation_patterns=list(data.get("ai_augmentation_patterns") or []),
        references=list(data.get("references") or []),
    )


@functools.lru_cache(maxsize=1)
def load_archetypes() -> dict[str, Archetype]:
    """Load all bundled archetypes from disk. Cached for the process lifetime."""
    archetypes: dict[str, Archetype] = {}
    if not ARCHETYPES_DIR.exists():
        logger.warning("Archetypes directory missing: %s", ARCHETYPES_DIR)
        return archetypes

    for yaml_path in sorted(ARCHETYPES_DIR.glob("*.yaml")):
        try:
            with open(yaml_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict) or "slug" not in raw:
                logger.warning("Skipping malformed archetype: %s", yaml_path)
                continue
            archetype = _parse_archetype(raw)
            archetypes[archetype.slug] = archetype
        except Exception as exc:
            logger.warning("Failed to load archetype %s: %s", yaml_path, exc)

    logger.info("Loaded %d role archetypes from %s", len(archetypes), ARCHETYPES_DIR)
    return archetypes


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# Match-quality thresholds. Above HIGH_MATCH_THRESHOLD we treat the match
# as authoritative grounding; below LOW_MATCH_THRESHOLD we treat the role
# as unknown and trigger DDG fallback (handled by the caller).
HIGH_MATCH_THRESHOLD = 0.78
LOW_MATCH_THRESHOLD = 0.55


@dataclass
class ArchetypeMatch:
    archetype: Archetype | None
    confidence: float  # 0.0 - 1.0
    matched_via: str  # "exact-slug", "alias", "display-name", "keyword", "none"


def match_archetype(role_name: str, hints: list[str] | None = None) -> ArchetypeMatch:
    """Find the best-matching archetype for a free-form role name.

    Match priority:
      1. Hints (explicit caller-supplied slug list) — exact match wins.
      2. Exact slug match.
      3. Alias substring match.
      4. Display-name similarity.
      5. Keyword presence in the role name.
    """
    archetypes = load_archetypes()
    if not archetypes:
        return ArchetypeMatch(None, 0.0, "none")

    role_lower = role_name.lower().strip()

    if hints:
        for hint in hints:
            if hint in archetypes:
                return ArchetypeMatch(archetypes[hint], 1.0, "exact-slug")

    if role_lower in archetypes:
        return ArchetypeMatch(archetypes[role_lower], 1.0, "exact-slug")

    # Alias: exact substring/equality
    for archetype in archetypes.values():
        for alias in archetype.aliases:
            if alias == role_lower or alias in role_lower:
                return ArchetypeMatch(archetype, 0.95, "alias")

    # Display-name similarity
    best: tuple[Archetype | None, float] = (None, 0.0)
    for archetype in archetypes.values():
        sim = _similarity(role_lower, archetype.display_name.lower())
        if sim > best[1]:
            best = (archetype, sim)

    if best[0] and best[1] >= HIGH_MATCH_THRESHOLD:
        return ArchetypeMatch(best[0], best[1], "display-name")

    # Keyword presence in the role name
    keyword_best: tuple[Archetype | None, int] = (None, 0)
    for archetype in archetypes.values():
        hits = sum(1 for kw in archetype.keywords if kw in role_lower)
        if hits > keyword_best[1]:
            keyword_best = (archetype, hits)
    if keyword_best[0] and keyword_best[1] >= 2:
        return ArchetypeMatch(keyword_best[0], 0.7, "keyword")

    # Fall back to the best display-name sim even if below HIGH threshold.
    if best[0] and best[1] >= LOW_MATCH_THRESHOLD:
        return ArchetypeMatch(best[0], best[1], "display-name")

    return ArchetypeMatch(None, 0.0, "none")


def grounding_prompt_fragment(archetype: Archetype, max_skills: int) -> str:
    """Render an archetype as a prompt fragment for the authoring LLM.

    Stays compact (<800 tokens) so multiple archetypes can co-exist in the
    pack-level coherence prompt without blowing the context.
    """
    skill_lines = []
    for skill in archetype.canonical_skills[:max_skills]:
        skill_lines.append(f"- {skill.name} — {skill.display_name}")
        if skill.summary:
            # Indent the summary so it visually belongs to the bullet.
            for line in skill.summary.strip().splitlines():
                skill_lines.append(f"    {line.strip()}")

    ai_lines = [f"- {p}" for p in archetype.ai_augmentation_patterns]
    ref_lines = [f"- {r}" for r in archetype.references]

    fragment = (
        f"Archetype: {archetype.display_name} (`{archetype.slug}`)\n"
        f"\n"
        f"Canonical skills for this archetype (use these as the basis when "
        f"selecting and naming skills; you may adapt names to be specific "
        f"to the target company's stack but the underlying capability should "
        f"map back to one of these):\n"
        + "\n".join(skill_lines)
        + "\n\n"
        + (
            "AI augmentation patterns (illustrative — incorporate where "
            "appropriate to the role and the company's signals):\n"
            + "\n".join(ai_lines)
            + "\n\n"
            if ai_lines
            else ""
        )
        + (
            "Authoritative references:\n" + "\n".join(ref_lines) + "\n"
            if ref_lines
            else ""
        )
    )
    return fragment


__all__ = [
    "HIGH_MATCH_THRESHOLD",
    "LOW_MATCH_THRESHOLD",
    "Archetype",
    "ArchetypeMatch",
    "ArchetypeSkill",
    "grounding_prompt_fragment",
    "load_archetypes",
    "match_archetype",
]
