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
# eval; below MIN_ROLES yields a pack too thin to be useful. Raised from 8
# to 15 to support holistic packs that mix observed (posting-grounded) and
# plausible (research/industry-grounded) roles in one artifact.
MIN_ROLES = 1
MAX_ROLES = 15
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

    # When no job-posting evidence was gathered, fail loudly instead of
    # silently shipping a thin recon-only pack. Set True to opt in to the
    # degraded path explicitly. Job postings are the primary input to the
    # skill pack pipeline — DNS recon and scraped research are supporting
    # context, not substitutes.
    allow_recon_only: bool = False

    # Operator-supplied role names that bypass automatic discovery. When
    # non-empty, discovery is skipped and these names are fed straight to
    # the authoring stage with archetype matching applied. Trim and dedupe
    # before assignment; values must be human-readable role labels, not
    # archetype slugs.
    roles_override: list[str] = field(default_factory=list)

    # Plan + inspect only: run through the planning step and persist the
    # role_plan.md / role_plan.json artifacts, then exit before authoring.
    # Useful for inspecting the planned roster before paying for skill
    # authoring.
    plan_only: bool = False

    # Path to a previously-persisted role_plan.json. When set, the
    # planning step is skipped and the pipeline authors against the
    # plan's final_roster verbatim. Supports the plan -> inspect -> author
    # workflow without re-running the planning LLM calls.
    from_plan_path: str | None = None

    # Operator-supplied role names that AUGMENT automatic discovery (or a
    # loaded plan via `from_plan_path`). After planning + merge, these
    # entries are materialized as operator-supplied roles and added to
    # the final roster. Subject to MAX_ROLES cap with operator-priority:
    # plausible roles trim first, then observed, never the added roles.
    # Composes with `from_plan_path`; mutually exclusive with
    # `roles_override` (override wins, add+skip warned).
    roles_add: list[str] = field(default_factory=list)

    # Operator-supplied role names to REMOVE from the planned roster.
    # Matches against role.name (kebab-case slug) or role.display_name,
    # case-insensitive, exact match. Unmatched names log a warning so
    # typos are visible. Hard error if curation leaves an empty roster.
    # Composes with `from_plan_path`; mutually exclusive with
    # `roles_override` (override wins, add+skip warned).
    roles_skip: list[str] = field(default_factory=list)

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
        # Light hygiene on operator-supplied role names.
        def _clean(raw_list: list[str], flag_name: str) -> list[str]:
            cleaned: list[str] = []
            seen: set[str] = set()
            for raw in raw_list:
                label = str(raw).strip()
                if not label or label.lower() in seen:
                    continue
                if len(label) > 80:
                    raise ValueError(
                        f"{flag_name} entry exceeds 80 characters: {label!r}"
                    )
                seen.add(label.lower())
                cleaned.append(label)
            if len(cleaned) > MAX_ROLES:
                raise ValueError(
                    f"{flag_name} accepts at most {MAX_ROLES} role names, "
                    f"got {len(cleaned)}"
                )
            return cleaned

        self.roles_override = _clean(self.roles_override, "roles_override")
        self.roles_add = _clean(self.roles_add, "roles_add")
        self.roles_skip = _clean(self.roles_skip, "roles_skip")

        # Clash detection across all three list flags. Operator intent is
        # ambiguous when the same label appears in more than one list:
        #   * add + skip → "add then skip" or "skip then add"?
        #   * override + add → override bypasses planning, add augments it
        #   * override + skip → override bypasses planning, skip is a no-op
        # Rather than guess intent or silently drop, we reject the config
        # at validation time so the operator can clarify.
        override_lower = {o.lower() for o in self.roles_override}
        add_lower = {a.lower() for a in self.roles_add}
        skip_lower = {s.lower() for s in self.roles_skip}
        for left_name, left, right_name, right in (
            ("roles_add", add_lower, "roles_skip", skip_lower),
            ("roles_override", override_lower, "roles_add", add_lower),
            ("roles_override", override_lower, "roles_skip", skip_lower),
        ):
            clashes = left & right
            if clashes:
                raise ValueError(
                    f"{left_name} and {right_name} share entries: "
                    f"{sorted(clashes)}. A role cannot appear in both."
                )

    @property
    def emit_claude(self) -> bool:
        return self.formats in (SkillPackFormat.CLAUDE, SkillPackFormat.BOTH)

    @property
    def emit_cowork(self) -> bool:
        return self.formats in (SkillPackFormat.COWORK, SkillPackFormat.BOTH)
