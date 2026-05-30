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


class RoleProvenance(str, Enum):
    """How a role entered the plan.

    The authoring stage branches on this so observed roles ground their
    skills in actual posting evidence and plausible roles ground theirs in
    research / industry context. Consumers of the pack can also surface
    provenance to end users so a Confirmed posting-grounded role is
    visibly different from an Inferred research-grounded one.
    """

    POSTING = "posting"  # found in actual job postings
    RESEARCH = "research"  # inferred from company-specific research artifacts
    INDUSTRY = "industry"  # inferred from business-model + stage typicality
    OVERRIDE = "override"  # operator-supplied via --roles-override


@dataclass
class RoleEvidence:
    """Citations and grounding for one discovered role."""

    sources: list[str] = field(default_factory=list)  # e.g. "hiring:Ashby/Engineer-Platform"
    dns_signals: list[str] = field(default_factory=list)  # e.g. "Salesforce (DNS-confirmed)"
    posting_count: int = 0
    archetype: str | None = None  # canonical archetype slug, e.g. "ml-engineer"
    provenance: RoleProvenance = RoleProvenance.POSTING
    # Verbatim phrase-level citations from the input evidence that support
    # this role. Required for plausible roles; populated where available
    # for observed roles. Empty list for operator overrides.
    citations: list[str] = field(default_factory=list)


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
    # Populated by run_skill_pack_pipeline so the pack report can render
    # the observed / plausible split and link back to role_plan.md.
    plan: RolePlan | None = None

    @property
    def total_skills(self) -> int:
        return sum(len(r.skills) for r in self.roles)

    @property
    def observed_role_count(self) -> int:
        return sum(1 for r in self.roles if r.evidence.provenance == RoleProvenance.POSTING)

    @property
    def plausible_role_count(self) -> int:
        return sum(
            1
            for r in self.roles
            if r.evidence.provenance in (RoleProvenance.RESEARCH, RoleProvenance.INDUSTRY)
        )

    @property
    def operator_added_role_count(self) -> int:
        return sum(1 for r in self.roles if r.evidence.provenance == RoleProvenance.OVERRIDE)


@dataclass
class IndustryClassification:
    """Coarse industry / business-model classification used to gate which
    plausible roles are reasonable inferences for this company at this
    stage.

    Resolution order during planning (cheapest first):
      1. Pull structured fields from a primr strategic report when
         --from-report is set and the report exposes them.
      2. Fall back to a single cheap LLM classification call against
         recon + hiring + research evidence.

    `cited_evidence` carries the verbatim phrases from the inputs that
    justify the classification so downstream consumers can audit it.
    `source` records which path produced the classification.
    """

    business_model: str = "Unknown"
    industry_vertical: str = "Unknown"
    company_stage: str = "Unknown"
    employee_estimate: str = "Unknown"  # rough headcount band
    confidence: str = "Low"  # High | Medium | Low
    cited_evidence: list[str] = field(default_factory=list)
    source: str = "unknown"  # "report" | "llm" | "unavailable" | "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_model": self.business_model,
            "industry_vertical": self.industry_vertical,
            "company_stage": self.company_stage,
            "employee_estimate": self.employee_estimate,
            "confidence": self.confidence,
            "cited_evidence": list(self.cited_evidence),
            "source": self.source,
        }


@dataclass
class RolePlan:
    """The planning-step output. Persisted as role_plan.md + role_plan.json
    in the working directory before authoring begins.

    `observed` are roles whose existence is confirmed by actual job
    postings; their skills will be authored with posting-grounded prompts.
    `plausible` are roles inferred from research + industry context; their
    skills will be authored with research-grounded prompts that
    acknowledge the inference. `gap_flagged` are roles that the industry
    pattern suggests but were excluded from the final roster (no citation
    found, or the requested count was hit first); they appear in the plan
    artifact so the operator can re-run with overrides if needed.

    `final_roster` is `observed + plausible` deduped and capped at the
    requested `roles_count`. This is what feeds the authoring stage.
    """

    observed: list[Role] = field(default_factory=list)
    plausible: list[Role] = field(default_factory=list)
    gap_flagged: list[Role] = field(default_factory=list)
    # Operator-supplied roles that augmented the discovered set via
    # --roles-add. Materialized with provenance=override; subject to the
    # MAX_ROLES cap with operator-priority (plausible trims first).
    operator_added: list[Role] = field(default_factory=list)
    # Names the operator asked to drop via --roles-skip. Recorded so the
    # plan artifact preserves the curation history. Unmatched names are
    # logged at planning time and surfaced here.
    operator_skipped: list[str] = field(default_factory=list)
    final_roster: list[Role] = field(default_factory=list)
    industry: IndustryClassification = field(default_factory=IndustryClassification)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    plan_md_path: str | None = None
    plan_json_path: str | None = None

    @property
    def total_planned(self) -> int:
        return len(self.final_roster)

    def to_dict(self) -> dict[str, Any]:
        def _serialize_role(role: Role) -> dict[str, Any]:
            return {
                "name": role.name,
                "display_name": role.display_name,
                "confidence": role.confidence,
                "summary": role.summary,
                "evidence": {
                    "sources": list(role.evidence.sources),
                    "dns_signals": list(role.evidence.dns_signals),
                    "posting_count": role.evidence.posting_count,
                    "archetype": role.evidence.archetype,
                    "provenance": role.evidence.provenance.value,
                    "citations": list(role.evidence.citations),
                },
            }

        return {
            "observed": [_serialize_role(r) for r in self.observed],
            "plausible": [_serialize_role(r) for r in self.plausible],
            "gap_flagged": [_serialize_role(r) for r in self.gap_flagged],
            "operator_added": [_serialize_role(r) for r in self.operator_added],
            "operator_skipped": list(self.operator_skipped),
            "final_roster": [_serialize_role(r) for r in self.final_roster],
            "industry": self.industry.to_dict(),
            "evidence_summary": dict(self.evidence_summary),
            "plan_md_path": self.plan_md_path,
            "plan_json_path": self.plan_json_path,
        }


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
