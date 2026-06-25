# Current State Analysis

## Vision

Primr is a CLI-first, local-first company research system. The product value is
the full artifact pipeline: recon, scraping, hiring signals, research
deepening, synthesis, validation, packaging, and handoff. The user-facing bar is
not "a model wrote text"; it is a serious strategic artifact with evidence,
uncertainty labels, cost controls, and reusable outputs for humans and agents.

## Agentic Balance

The governing line is stable:

- Deterministic rules own structure, spend, egress, disk writes, packaging, and
  referential validity.
- Model judgment owns content decisions where a fixed path cannot generalize.
- Quality is measured with evals and calibration, not asserted by brittle prose
  regexes.
- Any billable run needs estimate-first approval. This cycle used only local
  tests and static checks, so spend is `$0.00`.

## Quality Standard

The development contract is `CLAUDE.md`: use the existing seams, do not grow
monster files, keep examples free of real company data, do not add authorship
attribution, and run the same gates CI runs. The relevant skill-pack standard is
to generate useful, grounded Agent Skills with clean frontmatter, substantive
workflow bodies, concrete output formats, role evidence, and safe bundled
resources.

## Current Roadmap Focus

Roadmap item 25 is the active skill-pack improvement lane. The completed slices
in this cycle are:

- Clean default skill frontmatter with optional metadata.
- Stronger authoring prompts for intake, scope guardrails, human checkpoints,
  and worked examples.
- Hard validation for bodies under 300 words and missing structural quality
  markers.
- Deterministic role-family references attached across each role's skills.

The next high-leverage item in the same lane is JD-as-evidence input, followed
by enterprise role-discovery honesty and the Cowork packaging refresh.

Update from the latest cycle: skill-pack output should be treated as a draft
skill generator, not a company-insight artifact generator. The skill body stays
compact and procedural: required inputs, produced artifact, workflow, guardrail,
human checkpoint, and worked example. Company context is used to make those
items specific, while role grounding stays in progressively loaded references.

Current cycle update: JD-as-evidence is now shipped, and enterprise
role-discovery honesty has its first shipped slice. `--from-jd` / MCP
`from_jd_path` adds a sanitized local role brief to the hiring evidence layer
before planning and authoring, and JD-only single-role draft generation is
supported without pretending discovery found broader company evidence. The
planner also records a non-blocking `posting-incomplete` warning when observed
postings for a mid-market-or-larger organization cluster in one narrow band.
The Cowork packaging refresh is also now aligned to current Microsoft limits:
plugin sideload manifests cap at 20 `agentSkills`, companions are allowed but
bounded, and larger packs keep the full unpacked tree while emitting a valid
20-skill Cowork slice. Segmented / multi-ATS career-site input support is now
shipped through repeatable `--career-url` / MCP `career_urls`: exact career
boards are source selectors for hiring evidence, merged before planning, and
usable without a company URL when only postings are available. The next
high-leverage work in this lane is broader live-quality evaluation of generated
packs against real operator workflows rather than adding more context volume.
Latest cycle update: common business-role archetypes are now bundled for sales,
marketing, people operations, finance, legal/compliance, and operations. Weak
display-name similarity no longer returns a usable archetype, so unknown roles
author from company evidence only instead of inheriting misleading technical
scaffolding.

Release cycle update: the accumulated skill-pack quality lane is being cut as
v1.32.8 so the package build and PyPI distribution carry the same shipped state
as `main`: clean skill frontmatter, stronger procedural bodies, role-family
references, JD and career-board evidence inputs, posting-coverage warnings,
Cowork packaging caps, and business-role archetype grounding.

## 2026-06-24 Refinement: Deeper Anthropic Agent Skills Best Practices
Approved plan executed for the skill_pack generator (primr skills). Changes embed
the exact patterns from research (Anthropic engineering post + best-practices
guide + user query):

- Skills as folders (SKILL.md + references/ + scripts/ + evals/).
- Narrowly scoped (one capability per skill, one category).
- Verification skills high leverage (bias for at least one verifier per role; planner updated to include in universal; authoring MUST + default script guarantee via seam).
- Use scripts for deterministic work ("solve, don't punt" - emit real .py; default verify script for verifiers).
- Gotchas section as highest-signal, seeded from real evidence/failures, living (update over time) - structural via attached references/gotchas.md (no body regex).
- Trigger descriptions ("Use when..." with concrete user phrasing, not summaries).
- Progressive disclosure (lean SKILL.md, point to extra files; we always attach role-family, gotchas, composition refs).
- Compose small skills (name references, no giant orchestrators).
- Measure usage (via trigger/behavioral evals, pack report adherence counts; structural for gotchas via attached files; no new mechanism per answer).

All changes strictly follow agentic-balance.md: determinism on structure/referential validity (validators only for kebab, injection, min length, required markers, bundled paths); judgment on content (prompt-driven); quality measured by evals (existing trigger + behavioral), not new brittle regex content gates. Recent pass removed body-scanning regex for Gotchas presence (now structural via deterministically attached references/gotchas.md).

primr self-suggestion (claude-code/skills/primr/SKILL.md + references/gotchas.md) aligned as exemplar: trigger-rich description, references/ dir with living Gotchas, modeling BP (cost gate, async, no brittle, folders, etc.). Root skills/ kept thin as designed.

Generator now produces production-grade, non-slop skills matching the condensed takeaway. No new giant files, use existing seams (BundledFile, role_references, prompt + structural validators + evals), zero external spend in this cycle, full tests + gates pass.

Current focus (loop continuing): complete any remaining PLANNED from ROADMAP §15 (e.g. verifiable intermediate outputs), update additional root skills if fits, full folder + verification by default in generator.

Alignment confirmed with README (skill pack as first-class), ROADMAP (deeper BP, anti-brittle), CLAUDE.md (one seam, no monster, verify APIs, tests with code), agentic-balance (no brittle, prompt + eval).

## 2026-06-24 Control Plane Slice: MCP Per-Tool Authorization

After re-reading README, ROADMAP, `CLAUDE.md`, `docs/design/agentic-balance.md`,
`docs/design/2.0-agent-control-plane.md`, and `docs/SECURITY.md`, the highest
leverage next slice is the first 2.0 control-plane stage: enforce capability
scopes at the actual MCP tool-dispatch boundary.

Shipped in this slice:

- New central MCP tool policy for `read`, `research`, `delegate`, and `admin`.
- OAuth `scope` and Entra `scp` JWT claims honored for least-privilege tokens.
- Legacy no-scope `read` / `write` JWTs retained through a compatibility alias,
  so existing authenticated clients do not break while new clients can be
  explicitly read-only.
- HTTP auth context now bridges the SDK-authenticated user into tool dispatch
  through request-local context storage instead of a shared mutable server
  field.
- Structured `insufficient_scope` tool responses include required, granted, and
  missing scopes.
- Security docs and ROADMAP now mark T8 MCP Stage 1 shipped while leaving
  approval tokens, structured invocation audit, and A2A parity as next work.

Current estimate:

- Next patch release readiness: this is a coherent `1.33.x` patch slice once
  full CI gates are green.
- 2.0 control-plane pillar: about 35% complete. Per-tool authz is the required
  base. Approval provenance and invocation audit remain.
- Full 2.0 release: about 20-25% complete. Control-plane Stage 1 helps, but
  backend freedom and the research-memory layers still carry most of the
  remaining release mass.

Spend: `$0.00`. Full local validation now passes: `git diff --check`,
`ruff check src/primr/`, `ruff format --check src/ tests/`, full `mypy`,
Bandit, `pip-audit`, and `uv run pytest tests/ -q` (10119 passed, 42 skipped).

## 2026-06-25 Control Plane Slice: MCP Approval Tokens

The next control-plane slice is now implemented for MCP cost-cap-governed
execution tools. This follows the roadmap order: scope authz first, approval
provenance second, audit later.

Shipped in this slice:

- `estimate_run`, `estimate_strategy`, and `estimate_skill_pack` return
  short-lived server-issued `approval_token` fields.
- `research_company`, `generate_strategy`, and `generate_skill_pack` require a
  matching token when server-side MCP cost-cap enforcement is active.
- Tokens are HMAC-signed, single-use, TTL-bound, and tied to the target tool,
  cost-affecting approval-shape hash, and approved max cost.
- Argument-swap and replay attempts return structured MCP errors before paid
  execution starts.
- Platform alias normalization moved out of the pinned `tools.py` module, and
  `tools.py` stays within its pinned architecture ceiling.

Current estimate:

- 2.0 control-plane pillar: about 60% complete. MCP per-tool authz and approval
  provenance are shipped for the primary paid execution paths. Structured audit,
  A2A parity, and approval coverage for any non-cost-cap-governed paid paths
  remain.
- Full 2.0 release: about 25-30% complete. Control-plane work is advancing, but
  backend freedom and durable research memory still carry most release mass.

Spend: `$0.00`. Latest online check aligned this priority with current MCP
authorization guidance and OWASP agentic guidance: least-privilege scopes,
approval for high-impact actions, and complete mediation in downstream systems.
Full local validation passes: ruff, format check, mypy, Bandit, pip-audit, and
`uv run pytest tests/ -q` (10126 passed, 42 skipped).

Follow-up: PyPI latest is `1.33.1`, matching `pyproject.toml`, so no
same-version publish is appropriate. The release workflow now builds under
Python 3.12, matching the declared package floor, and
`tests/test_release_integrity.py` pins that the PyPI workflow cannot drift back
to Python 3.11.

Release follow-up: current source is now bumped to `1.33.2` for publication.
The done work is represented in both `docs/CHANGELOG.md` and the ROADMAP
changelog table, and PyPI metadata uses the modern Apache 2.0 SPDX expression
without deprecated license classifiers.

The supplied agentic-systems guide reinforces the next control-plane step:
structured invocation audit logging. Approval tokens already cover bounded
action for spend-governed MCP tools; the next slice should persist who invoked
which tool, granted scopes, approval token id, normalized argument hash,
estimated cost, result status, and job id. That addresses idempotency,
approval provenance, execution traces, and side-effect visibility without
adding brittle content-quality gates.

## Quality Rubric for this work
- Correctness: structural + prompt + tests.
- No brittle: only prose-invariant checks.
- Simplicity: incremental on existing.
- Maintainability: comments reference agentic-balance.
- All changes TDD-ish, self-reviewed as senior principal (HATE slop).

All via existing seams (BundledFile, role_references, authoring prompt +
body_quality markers, validator signals, packager report). No new giants, no
second seams, deterministic structure preserved, zero external spend. Tests +
full gates (ruff/mypy/pytest) updated. This advances ROADMAP §15 and directly
implements the user's condensed takeaway for higher-leverage, higher-quality
emitted skills. CURRENT-STATE now reflects the generator produces skills that
are small, composable, trigger-clear, script-equipped, verifier-rich, Gotchas-
living, and progressively disclosed.
