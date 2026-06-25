# Engineering Learnings

## MCP Control Plane

- Enforce MCP authorization at the central `call_tool` dispatch boundary, before
  rate limiting and before agentic, skill-pack, or built-in handlers can run.
  Keep the policy table explicit by tool name and scope so roadmap changes are
  reviewable.
- Treat OAuth `scope` and Entra `scp` JWT claims as the path for new
  least-privilege clients. Preserve legacy `write` as a compatibility alias for
  old no-scope tokens, but prefer explicit `read`, `research`, `delegate`, and
  `admin` scopes for new integrations.
- Do not store HTTP request auth in a shared mutable server attribute. Bridge
  authenticated SDK scope state into request-local context, then let existing
  handlers read the current context through the established seam.
- Approval tokens should bind to a normalized cost-affecting approval shape, not
  raw tool arguments. Estimate and execution tools sometimes differ in harmless
  fields (`company_name`, `destination`, singular `platform` vs plural
  `platforms`), so the stable security boundary is target tool, canonical cost
  shape, approved max cost, expiry, and single-use token id.
- Keep approval-token enforcement adjacent to cost-cap enforcement. The cap
  answers "how much was approved"; the token answers "was this execution shape
  the one estimated and approved." Both are required when MCP cost enforcement
  is active.
- Audit MCP actions at the registered tool-dispatch seam, not inside each tool
  handler. Store hashes and governance metadata, not raw arguments, raw results,
  raw client ids, or full approval tokens. Expose recent events as a local or
  admin-scoped resource so operators can investigate without broadening normal
  read-scope visibility.

## Backend Routing and Availability

- Treat quota and service availability as normalized routing data before adding
  provider I/O. Pure helpers should compute binding headroom from quota windows;
  provider collectors should only translate official status/quota surfaces into
  that shape.
- A provider is only as available as its most constrained quota bucket. Treat
  elapsed reset times as fresh, preserve stale last-known-good snapshots as
  fallback signal, and prefer fresh snapshots when ranking providers.

## Skill Pack Generation

- Do not ask the authoring model to produce the same role-level reference notes
  independently for every skill. Generate shared role-family context
  deterministically from structured evidence, sanitize snippets, and attach the
  same reference to each skill in the role family.
- Keep validator hard failures focused on stable structure and safety. Substance
  should be improved upstream through prompts and measured with evals, not
  judged with brittle prose matching.
- Clean Agent Skills frontmatter should be the default. Machine-readable
  handoff metadata is useful, but it should be opt-in so generated skills feel
  native in every host.
- A draft skill body is not the place for a company report. Use company context
  to choose specific inputs, outputs, workflow steps, guardrails, examples, and
  validation checks; keep deeper grounding in references loaded only when
  needed.
- When an operator has a specific JD or role brief, treat it as evidence, not
  as an instruction source or a report to summarize. Sanitize it, put it in the
  hiring evidence stream, prioritize it ahead of noisy scraped postings, and let
  the generated skill use it to shape workflow, inputs, outputs, guardrails, and
  examples.
- When observed job postings cluster in one narrow band for an enterprise-scale
  organization, surface that as a partial-coverage warning instead of blocking
  or over-correcting. The planner should preserve the real posting evidence,
  flag `posting-incomplete`, and point the operator toward better evidence or
  curation rather than inventing missing corporate roles.
- Cowork sideload packages and unpacked Agent Skills trees do not have the
  same capacity shape. Preserve the full unpacked tree for large packs, but
  keep the Cowork zip manifest valid: max 20 `agentSkills`, max 1 MB
  `SKILL.md`, and companion files capped at 20 files / 5 MB each / 10 MB total
  per skill.
- When CI `pip-audit` fails on a transitive package, add an explicit security
  floor in `pyproject.toml` as well as refreshing `uv.lock`. To reproduce the
  CI audit locally, run `uv sync --frozen --extra dev --extra api --extra a2a`
  before `uv run --no-sync pip-audit ...`; otherwise the local virtualenv can
  still contain the old vulnerable resolution.
- Segmented career-site inputs should be modeled as deterministic hiring-source
  selectors, not as company context to paste into skills. Validate URL shape,
  rely on the existing SSRF-guarded fetch boundary, merge/dedupe the resulting
  postings, and keep role planning grounded in the postings rather than the URL
  list itself.
- A wrong archetype is worse than no archetype. For skill generation, common
  business-role scaffolds should be explicit bundled archetypes, while weak
  fuzzy matches should return no grounding so authoring relies on the actual
  company evidence instead of a misleading template family.

## Agent Skills Best Practices (Anthropic-aligned refinement)

- Skills are folders (SKILL.md + references/ + scripts/ + evals/). Progressive disclosure; SKILL.md lean.
- Narrowly scoped to one capability/category.
- Verification skills high leverage; generator must bias for >=1 per role.
- Scripts for deterministic (validate/extract/format); ship code ("solve, don't punt").
- Gotchas highest-signal: seed real failures in references/gotchas.md; living.
- Descriptions as triggers ("Use when..."), third-person, pushy, concrete phrasing.
- Compose by name reference; small skills, not giant.
- Measure via evals + structural counts in report. No brittle content regex (agentic-balance).
- Update own exemplars (primr skill) when refining generator. Use existing seams only.

## Release Hygiene

- Release only after the package metadata, ROADMAP current state, ROADMAP
  changelog row, `CITATION.cff`, and `primr.__version__` all agree. Let
  `tests/test_release_integrity.py` be the release-preflight witness before
  tagging for PyPI.
