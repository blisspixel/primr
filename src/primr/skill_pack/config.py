"""Skill pack pipeline configuration.

User-facing knobs surfaced via CLI flags and the MCP tool inputSchema. Keep
this dataclass JSON-serializable so it can be passed through the MCP job
boundary unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SkillPackFormat(str, Enum):
    CLAUDE = "claude"
    COWORK = "cowork"
    BOTH = "both"


# Bounds chosen to match the design plan's "configurable but not infinite"
# guarantee. Going above MAX_ROLES degrades grounding quality observed in
# eval; below MIN_ROLES yields a pack too thin to be useful.
MIN_ROLES = 1
MAX_ROLES = 8
MIN_SKILLS_PER_ROLE = 1
MAX_SKILLS_PER_ROLE = 5
DEFAULT_ROLES = 5
DEFAULT_SKILLS_PER_ROLE = 3

# Per-skill refinement iteration cap. Beyond 2, diminishing-returns dominate
# (validated in the broader QA refinement design — same cap as the planned
# report-refinement loop).
DEFAULT_MAX_REFINE_ITERATIONS = 2

# Per-role cost ceiling — pipeline aborts a role if its share exceeds this
# even before CostGuardHook fires at the global level.
DEFAULT_MAX_COST_PER_ROLE_USD = 0.08


@dataclass
class SkillPackConfig:
    """Tuning knobs for one skill pack run."""

    roles_count: int = DEFAULT_ROLES
    skills_per_role: int = DEFAULT_SKILLS_PER_ROLE
    formats: SkillPackFormat = SkillPackFormat.BOTH
    max_refine_iterations: int = DEFAULT_MAX_REFINE_ITERATIONS
    max_cost_per_role_usd: float = DEFAULT_MAX_COST_PER_ROLE_USD
    max_total_cost_usd: float | None = None  # None = no cap (CostGuardHook still applies)

    # Pack-level coherence pass is on by default — it's what gives the pack
    # its "no overlapping skills, distinct triggers" quality.
    run_pack_coherence_pass: bool = True

    # Skip evidence-collection scrape; assume recon + hiring already exist
    # in the working dir (set by --from-report and by MCP when report_path
    # is supplied).
    reuse_existing_evidence: bool = False

    # Comma-separated list of canonical archetype slugs to prefer (advanced).
    archetype_hints: list[str] = field(default_factory=list)

    def validate(self) -> None:
        """Raise ValueError on out-of-bounds config."""
        if not MIN_ROLES <= self.roles_count <= MAX_ROLES:
            raise ValueError(
                f"roles_count must be {MIN_ROLES}-{MAX_ROLES}, got {self.roles_count}"
            )
        if not MIN_SKILLS_PER_ROLE <= self.skills_per_role <= MAX_SKILLS_PER_ROLE:
            raise ValueError(
                f"skills_per_role must be {MIN_SKILLS_PER_ROLE}-{MAX_SKILLS_PER_ROLE}, "
                f"got {self.skills_per_role}"
            )
        if self.max_refine_iterations < 0:
            raise ValueError("max_refine_iterations must be >= 0")
        if self.max_cost_per_role_usd <= 0:
            raise ValueError("max_cost_per_role_usd must be > 0")
        if self.max_total_cost_usd is not None and self.max_total_cost_usd <= 0:
            raise ValueError("max_total_cost_usd must be > 0 when set")

    @property
    def emit_claude(self) -> bool:
        return self.formats in (SkillPackFormat.CLAUDE, SkillPackFormat.BOTH)

    @property
    def emit_cowork(self) -> bool:
        return self.formats in (SkillPackFormat.COWORK, SkillPackFormat.BOTH)
