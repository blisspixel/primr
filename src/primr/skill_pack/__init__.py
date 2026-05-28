"""Skill Pack generation subsystem.

Produces sideload-ready Agent Skills artifacts for both Claude (unpacked
roles/ tree) and Microsoft 365 Copilot Cowork (manifest.json + .zip) from
primr research evidence. Not a strategy — its own first-class pipeline.

Public entry points:
    - SkillPackConfig: tuning knobs
    - run_skill_pack_pipeline(): the orchestrator
    - SkillPack, Role, Skill: result schema
"""

from primr.skill_pack.config import SkillPackConfig, SkillPackFormat
from primr.skill_pack.schema import (
    Role,
    RoleEvidence,
    Skill,
    SkillIssue,
    SkillPack,
    SkillPackArtifacts,
    ValidationReport,
)

__all__ = [
    "Role",
    "RoleEvidence",
    "Skill",
    "SkillIssue",
    "SkillPack",
    "SkillPackArtifacts",
    "SkillPackConfig",
    "SkillPackFormat",
    "ValidationReport",
]
