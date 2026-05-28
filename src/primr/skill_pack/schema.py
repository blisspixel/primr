"""Skill pack data model.

Dataclasses for the pipeline's intermediate and final results. JSON-friendly
(no Pydantic dep — primr is conservative about adding hard deps).

Naming note: the `name` field on Role and Skill is the kebab-case identifier
that doubles as the folder name (Agent Skills standard / ASKILL-P006); the
human display name lives in `display_name`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IssueSeverity(str, Enum):
    HARD = "hard"
    SOFT = "soft"


@dataclass
class SkillIssue:
    """A single validator finding against a Skill or pack.

    Mirrors the shape of primr.qa.models.ClassifiedIssue but stays standalone
    so the skill_pack module has no QA import dependency at parse time.
    """

    code: str
    severity: IssueSeverity
    message: str
    role_name: str | None = None  # None for pack-level findings
    field: str | None = None  # which field of the skill (name, description, body)
    excerpt: str | None = None  # short snippet of the offending content

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "role_name": self.role_name,
            "field": self.field,
            "excerpt": self.excerpt,
        }


@dataclass
class RoleEvidence:
    """Citations and grounding for one discovered role."""

    sources: list[str] = field(default_factory=list)  # e.g. "hiring:Ashby/Engineer-Platform"
    dns_signals: list[str] = field(default_factory=list)  # e.g. "Salesforce (DNS-confirmed)"
    posting_count: int = 0
    archetype: str | None = None  # canonical archetype slug, e.g. "ml-engineer"


@dataclass
class Skill:
    """One skill within a role. Maps 1:1 to a SKILL.md file when authored."""

    name: str  # kebab-case identifier, matches folder name
    display_name: str
    description: str  # 1-1024 chars, includes trigger phrase
    body: str  # the SKILL.md body (post-frontmatter)
    references: list[str] = field(default_factory=list)
    canonical_skill_basis: str | None = None  # archetype skill this was grounded in


@dataclass
class Role:
    """A role at the target company with N skills attached."""

    name: str  # kebab-case
    display_name: str
    confidence: str  # Confirmed | Inferred | Speculated
    evidence: RoleEvidence
    summary: str = ""  # one-line role summary
    skills: list[Skill] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Output of the deterministic validator for a Skill or pack."""

    issues: list[SkillIssue] = field(default_factory=list)

    @property
    def hard_issues(self) -> list[SkillIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.HARD]

    @property
    def soft_issues(self) -> list[SkillIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.SOFT]

    @property
    def passed(self) -> bool:
        return not self.hard_issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "hard_count": len(self.hard_issues),
            "soft_count": len(self.soft_issues),
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass
class SkillPack:
    """The complete in-memory result of the skill pack pipeline."""

    company_name: str
    company_url: str | None
    generated_at: str  # ISO-8601 UTC
    roles: list[Role] = field(default_factory=list)
    validation: ValidationReport = field(default_factory=ValidationReport)
    refinement_iterations_used: dict[str, int] = field(default_factory=dict)  # role name -> count
    dropped_roles: list[tuple[str, str]] = field(default_factory=list)  # (name, reason)

    @property
    def total_skills(self) -> int:
        return sum(len(r.skills) for r in self.roles)


@dataclass
class SkillPackArtifacts:
    """Filesystem outputs produced by the packager."""

    output_dir: str  # output/<Company>_Skills_Pack_<date>/
    claude_tree_root: str | None = None  # output_dir/roles/
    cowork_zip_path: str | None = None  # output_dir/<Company>_Cowork_Pack.zip
    report_md_path: str | None = None  # output_dir/<Company>_Skills_Pack_Report.md
    manifest_uuid: str | None = None
    skill_md_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "claude_tree_root": self.claude_tree_root,
            "cowork_zip_path": self.cowork_zip_path,
            "report_md_path": self.report_md_path,
            "manifest_uuid": self.manifest_uuid,
            "skill_md_paths": list(self.skill_md_paths),
        }
