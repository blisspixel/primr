"""Skill pack pipeline configuration.

User-facing knobs surfaced via CLI flags and the MCP tool inputSchema. Keep
this dataclass JSON-serializable so it can be passed through the MCP job
boundary unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from primr.data.hiring_career_urls import normalize_career_urls


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
MAX_REFINE_ITERATIONS = 5

# Pack-level coherence auto-resolution is a separate provider-call surface
# from per-skill refinement. Bound it so estimates and execution share one
# deterministic worst-case fan-out.
MAX_AUTO_RESOLVE_PAIRS = 10

# Per-role cost ceiling — pipeline aborts a role if its share exceeds this
# even before CostGuardHook fires at the global level.
DEFAULT_MAX_COST_PER_ROLE_USD = 0.08

# Conservative allowance for exactly one remote Cowork color-icon generation
# when the operator explicitly opts in with --remote-icons / remote_icons.
REMOTE_ICON_GENERATION_ESTIMATE_USD = 0.10


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

    # When the coherence pass finds overlapping / colliding skill pairs,
    # auto-resolve them by re-scoping one skill of each pair (conservative:
    # only the second skill is touched, reverted if it gains a HARD finding)
    # rather than only reporting them. Requires run_pack_coherence_pass.
    auto_resolve_overlaps: bool = True

    # Opt-in trigger-description optimization (Tier 2). For each skill,
    # generate should/should-not-trigger queries, MEASURE how well the
    # description triggers via a discovery simulator, and improve the
    # description when it scores below threshold (kept only if it beats the
    # original on a held-out split). Adds LLM calls per skill, so it is OFF
    # by default; enable with the CLI --optimize-triggers flag.
    optimize_triggers: bool = False
    trigger_accuracy_threshold: float = 0.8

    # Opt-in behavioral evaluation (Tier 4). For each skill, generate task
    # cases + assertions, run the task WITH the skill vs WITHOUT it, grade
    # both, and report the pass-rate delta — proving the skill changes
    # output, not just that it is well-formed. Also writes evals/evals.json
    # per skill. Expensive (~3 LLM calls per case per skill), so OFF by
    # default; enable with the CLI --with-evals flag.
    with_evals: bool = False
    eval_cases_per_skill: int = 3

    # Optional primr-namespaced `metadata` block in each SKILL.md frontmatter
    # (role, provenance, confidence, approx context-token budget, and refresh
    # hints). Off by default so generated skills are clean, portable artifacts
    # with only the Agent Skills standard name + description frontmatter.
    emit_agent_metadata: bool = False

    # Remote image-generation APIs are explicitly opt-in. The default Cowork
    # icon path is deterministic local Pillow/PNG generation so configured
    # provider keys do not accidentally create image API spend.
    remote_icon_generation: bool = False

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
    # validated plan final_roster. The global role cap and optional curation
    # are applied before cost approval and authoring. Supports the plan ->
    # inspect -> author workflow without re-running planning LLM calls.
    from_plan_path: str | None = None

    # Path to an operator-supplied job description or role brief. The pipeline
    # materializes this into the hiring evidence layer before planning and
    # authoring, so it augments discovered postings and also works as the sole
    # evidence source for hand-curated / single-role draft skill generation.
    from_jd_path: str | None = None

    # Operator-supplied career / ATS URLs. These are deterministic discovery
    # hints for segmented hiring sites, not research facts: each URL is fetched
    # through the hiring SSRF guard, direct ATS boards are parsed with their
    # provider adapter, and multiple valid boards are merged before planning.
    career_urls: list[str] = field(default_factory=list)

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
        if not MIN_SKILLS_PER_ROLE <= self.skills_per_role <= MAX_SKILLS_PER_ROLE:
            raise ValueError(
                f"skills_per_role must be {MIN_SKILLS_PER_ROLE}-{MAX_SKILLS_PER_ROLE}, "
                f"got {self.skills_per_role}"
            )
        if not 0 <= self.max_refine_iterations <= MAX_REFINE_ITERATIONS:
            raise ValueError(f"max_refine_iterations must be 0-{MAX_REFINE_ITERATIONS}")
        if not math.isfinite(self.max_cost_per_role_usd) or self.max_cost_per_role_usd <= 0:
            raise ValueError("max_cost_per_role_usd must be finite and > 0")
        if self.max_total_cost_usd is not None and (
            not math.isfinite(self.max_total_cost_usd) or self.max_total_cost_usd <= 0
        ):
            raise ValueError("max_total_cost_usd must be finite and > 0 when set")

        # Light hygiene on operator-supplied role names.
        def _clean(raw_list: list[str], flag_name: str) -> list[str]:
            cleaned: list[str] = []
            seen: set[str] = set()
            for index, raw in enumerate(raw_list):
                label = str(raw).strip()
                if not label or label.lower() in seen:
                    continue
                if len(label) > 80:
                    raise ValueError(f"{flag_name} entry {index + 1} exceeds 80 characters")
                seen.add(label.lower())
                cleaned.append(label)
            if len(cleaned) > MAX_ROLES:
                raise ValueError(
                    f"{flag_name} accepts at most {MAX_ROLES} role names, got {len(cleaned)}"
                )
            return cleaned

        self.roles_override = _clean(self.roles_override, "roles_override")
        self.roles_add = _clean(self.roles_add, "roles_add")
        self.roles_skip = _clean(self.roles_skip, "roles_skip")
        self.career_urls = normalize_career_urls(self.career_urls)

        # The validated, deduplicated override roster is authoritative. Keep
        # one normalized count so CLI estimates, MCP approval tokens, and the
        # pipeline cannot disagree when duplicate override labels were given.
        if self.roles_override:
            self.roles_count = len(self.roles_override)
        if not MIN_ROLES <= self.roles_count <= MAX_ROLES:
            raise ValueError(f"roles_count must be {MIN_ROLES}-{MAX_ROLES}, got {self.roles_count}")

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
    def effective_roles_count(self) -> int:
        """Return the maximum roster size used for cost estimation."""
        if self.roles_override:
            return len(self.roles_override)
        # Automatic planning treats roles_count as a final cap. Added roles
        # displace discovered roles instead of expanding that cap.
        return self.roles_count

    @property
    def emit_claude(self) -> bool:
        return self.formats in (SkillPackFormat.CLAUDE, SkillPackFormat.BOTH)

    @property
    def emit_cowork(self) -> bool:
        return self.formats in (SkillPackFormat.COWORK, SkillPackFormat.BOTH)
