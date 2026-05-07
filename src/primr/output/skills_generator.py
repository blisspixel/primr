"""
Skills Ideation SKILL.md generator.

Parses the generated skills strategy document to extract individual role blocks
and writes them as per-role SKILL.md files with YAML frontmatter.

Output structure:
    output/<Company>_Skills_Ideation_<date>/roles/<role-slug>/SKILL.md
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "generate_skill_md",
    "parse_role_blocks",
    "slugify",
    "write_skill_files",
]


def slugify(text: str) -> str:
    """Convert a role name to a URL-safe slug for directory names."""
    slug = text.lower().strip()
    # Replace underscores with spaces first (so they become hyphens)
    slug = slug.replace("_", " ")
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def parse_role_blocks(strategy_text: str) -> list[dict[str, str]]:
    """Parse the strategy document for structured role blocks.

    Looks for level-3 headings matching:
        ### Role: <Role Name>

    Returns a list of dicts with keys: name, confidence, evidence, skills_text
    """
    # Pattern: ### Role: <name> followed by content until next ### or end
    role_pattern = re.compile(
        r"###\s*Role:\s*(.+?)(?:\n)"
        r"(.*?)(?=###\s*Role:|##\s|\Z)",
        re.DOTALL,
    )

    roles: list[dict[str, str]] = []
    for match in role_pattern.finditer(strategy_text):
        name = match.group(1).strip()
        body = match.group(2).strip()

        # Extract confidence
        confidence_match = re.search(
            r"\*\*Confidence:\*\*\s*(Confirmed|Inferred|Speculated)", body
        )
        confidence = confidence_match.group(1) if confidence_match else "Inferred"

        # Extract evidence
        evidence_match = re.search(r"\*\*Evidence:\*\*\s*(.+?)(?:\n|$)", body)
        evidence = evidence_match.group(1).strip() if evidence_match else ""

        # Extract skills section
        skills_match = re.search(
            r"\*\*Skills:\*\*\s*\n((?:\d+\..+\n?)+)", body
        )
        skills_text = skills_match.group(1).strip() if skills_match else ""

        roles.append(
            {
                "name": name,
                "confidence": confidence,
                "evidence": evidence,
                "skills_text": skills_text,
                "body": body,
            }
        )

    return roles


def generate_skill_md(role: dict[str, str]) -> str:
    """Generate a SKILL.md file content for a single role.

    Includes YAML frontmatter with name and description fields.
    Escapes quotes in values to produce valid YAML.
    """
    name = role["name"]
    confidence = role["confidence"]
    evidence = role["evidence"]
    skills_text = role["skills_text"]

    description = f"{name} ({confidence})"
    if evidence:
        description += f" — {evidence}"

    # Escape double quotes for valid YAML frontmatter
    safe_name = name.replace('"', '\\"')
    safe_description = description.replace('"', '\\"')

    lines = [
        "---",
        f'name: "{safe_name}"',
        f'description: "{safe_description}"',
        "---",
        "",
        f"# {name}",
        "",
        f"**Confidence:** {confidence}",
    ]

    if evidence:
        lines.append(f"**Evidence:** {evidence}")

    if skills_text:
        lines.append("")
        lines.append("## Skills")
        lines.append("")
        lines.append(skills_text)

    return "\n".join(lines) + "\n"


def write_skill_files(
    strategy_text: str,
    output_dir: Path,
) -> list[Path]:
    """Parse strategy text and write per-role SKILL.md files.

    Args:
        strategy_text: The full generated skills strategy document text.
        output_dir: The base output directory (e.g., output/<Company>_Skills_Ideation_<date>/)

    Returns:
        List of paths to written SKILL.md files.

    Graceful degradation: if parsing fails, logs a warning and returns
    an empty list rather than raising.
    """
    try:
        roles = parse_role_blocks(strategy_text)
    except Exception as e:
        logger.warning(
            "Failed to parse role blocks from skills strategy: %s. "
            "Strategy document will still be produced.",
            e,
        )
        return []

    if not roles:
        logger.warning(
            "No role blocks found in skills strategy output. "
            "Strategy document will still be produced without per-role SKILL.md files."
        )
        return []

    written: list[Path] = []
    roles_dir = output_dir / "roles"

    for role in roles:
        slug = slugify(role["name"])
        if not slug:
            logger.warning("Could not slugify role name: %r, skipping", role["name"])
            continue

        role_dir = roles_dir / slug

        # Security: verify the resolved path is inside the expected output directory.
        # Prevents path traversal if slugify ever passes through unexpected characters.
        try:
            resolved = role_dir.resolve()
            expected_parent = roles_dir.resolve()
            if not str(resolved).startswith(str(expected_parent)):
                logger.warning(
                    "Path traversal detected for role %r (resolved to %s), skipping",
                    role["name"],
                    resolved,
                )
                continue
        except (OSError, ValueError):
            logger.warning("Could not resolve path for role %r, skipping", role["name"])
            continue

        role_dir.mkdir(parents=True, exist_ok=True)

        skill_path = role_dir / "SKILL.md"
        content = generate_skill_md(role)

        try:
            skill_path.write_text(content, encoding="utf-8")
            written.append(skill_path)
            logger.info("Wrote SKILL.md for role '%s' at %s", role["name"], skill_path)
        except OSError as e:
            logger.warning("Failed to write SKILL.md for role '%s': %s", role["name"], e)

    logger.info(
        "Skills ideation: wrote %d/%d role SKILL.md files to %s",
        len(written),
        len(roles),
        roles_dir,
    )
    return written
