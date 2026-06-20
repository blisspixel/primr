# Progress Log

## 2026-06-20

### Cycle: v1.32.8 Build And Release Prep

Re-read and aligned against the active reference set for this release cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/CONTRIBUTING.md`,
`docs/design/agentic-balance.md`, `docs/design/engineering-excellence.md`,
`docs/CHANGELOG.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`. Re-read the release workflow and version-integrity
test before editing because this cycle updates the package build and PyPI
release path.

Implemented:

- Promoted the accumulated skill-pack quality work from `Unreleased` to
  `v1.32.8`.
- Modernized package license metadata and raised the build backend floor so the
  local wheel/sdist build no longer emits the setuptools license deprecation
  warning.
- Bumped the single version truth across `pyproject.toml`, `primr.__version__`,
  ROADMAP current state, ROADMAP changelog row, `CITATION.cff`, and `uv.lock`.
- Updated current-state analysis and engineering learnings to record the release
  metadata requirement.

Validation:

- `uv sync --frozen --extra dev --extra api --extra a2a` confirmed the local
  environment matches the CI extras.
- `uv run pytest tests/test_release_integrity.py -q` passed with 6 tests.
- `uv run --no-sync ruff check src/primr/` passed.
- `uv run --no-sync ruff format --check src/ tests/` passed after formatting
  `src/primr/__init__.py`.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run --no-sync bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10081 passed, 38 skipped`, branch coverage `85.06%`.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict link warnings.
- `uv run --with build python -m build --outdir dist-check` built the
  `primr-1.32.8` wheel and sdist.
- `uv run --with twine twine check dist-check/*` passed for both distributions.
- Added-line scans found no em dash or AI/tool attribution phrases.

Cost:

- `$0.00`. No cloud or paid validation was used.

## 2026-06-19

### Cycle: Business Role Archetypes For Draft Skills

Re-read and aligned against the active reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `docs/design/23-orchestrator-refactor-map.md`,
`docs/design/eval-plan.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`. Re-read the local `skill-creator` guidance before
editing because this work changes how primr drafts Agent Skills. Kept the scope
on concise, procedural skill creation rather than broad company-background
content.

Implemented:

- Added curated archetypes for common business functions: account executive,
  marketing manager, people operations manager, finance manager,
  legal/compliance manager, and operations manager.
- Tightened archetype matching so exact slugs, aliases, and keywords are token
  normalized, while weak display-name similarity no longer returns usable
  archetype grounding.
- Added regression coverage for common business titles and the previous bad
  match class where a retail operations role could inherit an unrelated
  technical or product archetype.
- Updated README, roadmap, changelog, the skill-pack guide, architecture notes,
  current-state analysis, and engineering learnings.

Validation:

- Confirmed the previous bad behavior before the fix: `Sales Director` matched
  `salesforce-admin`; `Marketing Manager`, `Finance Manager`, and
  `Operations Manager` matched `product-manager`; `Retail Floor Supervisor`
  received a weak display-name match.
- `uv run pytest tests/skill_pack/test_archetypes.py tests/skill_pack/test_curation.py tests/skill_pack/test_planner.py -q`
  passed with 66 tests.
- `uv run pytest tests/skill_pack/test_archetypes.py tests/skill_pack/test_curation.py tests/skill_pack/test_planner.py tests/skill_pack/test_pipeline.py -q`
  passed with 69 tests after formatting.
- `uv run pytest tests/skill_pack -q` passed with 297 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/test_architecture.py tests/test_no_brand_leak.py -q`
  passed with 6 tests.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10081 passed, 38 skipped`, branch coverage `85.06%`.
- Investigated the visible failed GitHub Actions CI run on `df4c747`. Root
  cause was `pip-audit` reporting `msgpack 1.1.2` and
  `pydantic-settings 2.14.1`; that was fixed by the later dependency-floor
  commit, and subsequent `main` CI runs passed.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Segmented Career URL Evidence For Draft Skills

Re-read and aligned against the active reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`. Kept the scope intentionally focused on draft
skill generation: narrow, explicit, evidence-backed `SKILL.md` artifacts rather
than broad public-facts dossiers.

Implemented:

- Added repeatable `--career-url` inputs for `primr skills`, allowing operators
  to seed draft skill-pack generation from specific segmented career pages or
  direct ATS URLs without requiring a company landing page.
- Added MCP parity through `career_urls` on `estimate_skill_pack` and
  `generate_skill_pack`, including normalized structured estimates that report
  when explicit career URLs are being used.
- Added a shared career-URL discovery helper that normalizes, deduplicates, and
  caps operator-supplied URLs, then routes direct ATS URLs, ATS redirects, and
  HTML career pages through the existing guarded hiring-signal collectors.
- Updated evidence collection so career URLs can be the primary source, while
  still preserving SSRF guards in the fetch path and provenance labels for
  downstream role planning.
- Updated README, roadmap, changelog, the skill-pack guide, architecture notes,
  current-state analysis, and engineering learnings.

Validation:

- `uv run pytest tests/test_data/test_hiring_signals_more_coverage.py tests/skill_pack/test_evidence_more_coverage.py tests/skill_pack/test_cli.py tests/mcp_server/test_skill_pack_tools_more_coverage.py tests/test_architecture.py -q`
  passed with 170 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed after formatting the updated
  architecture ratchet test.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10073 passed, 38 skipped`, branch coverage `85.06%`.
- Confirmed the latest pushed main commit before this cycle had green Docs,
  Scorecard, CodeQL, and CI runs. The visible failed CI run was on the previous
  dependency-audit commit and was fixed by the subsequent dependency-floor
  commit.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Cowork Packaging Limits

Re-read and aligned against the project reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`. Refreshed the Cowork packaging assumptions
against current Microsoft Learn documentation before changing the packager.

Implemented:

- Added explicit Cowork packaging constants for manifest, `SKILL.md`, and
  companion-file limits.
- Limited the Cowork sideload manifest and zip payload to the first valid
  20-skill slice while preserving the full unpacked Agent Skills tree for
  Claude/Cursor/VS Code style consumers.
- Split bundled-file handling into shared safety filtering and Cowork-only
  packaging filtering, so safe companion files remain in the unpacked tree even
  when they exceed Cowork's sideload caps.
- Surfaced Cowork packaging counts and limits in the pack report.
- Updated README, roadmap, changelog, the skill-pack guide, current-state
  analysis, and engineering learnings.

Validation:

- `uv run pytest tests/skill_pack/test_packager.py -q` passed with 21 tests.
- `uv run pytest tests/skill_pack -q` passed with 285 tests.
- `uv run pytest tests/test_architecture.py -q` passed with 5 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10060 passed, 38 skipped`, branch coverage `85.07%`.
- Remote CI initially failed on Python 3.13 because `pip-audit` reported newly
  published transitive advisories for `msgpack 1.1.2` and
  `pydantic-settings 2.14.1`. Added explicit dependency floors
  (`msgpack>=1.2.1`, `pydantic-settings>=2.14.2`), refreshed `uv.lock`, synced
  locally with the same extras as CI, and confirmed
  `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passes. Re-ran
  full coverage after the dependency refresh; it still passed with
  `10060 passed, 38 skipped`, branch coverage `85.07%`.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Enterprise Posting Coverage Honesty

Re-read and aligned against the project reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`.

Implemented:

- Added a pure skill-pack posting-coverage assessor that flags
  `posting-incomplete` when observed postings for a mid-market-or-larger
  organization cluster in one narrow role band.
- Surfaced the warning in `role_plan.md` and the skill-pack report with
  concrete operator actions: provide `--from-jd`, curate with `--roles-add` or
  `--roles-override`, or rerun from richer segmented evidence.
- Extracted role-plan rendering into `skill_pack.plan_artifacts`, reducing
  `planner.py` from the file-size ceiling to 830 lines while preserving the
  existing role-plan artifact contract.
- Updated README, roadmap, architecture, changelog, skill-pack guide,
  current-state analysis, and engineering learnings.

Validation:

- `uv run pytest tests/skill_pack/test_posting_coverage.py tests/skill_pack/test_planner.py tests/skill_pack/test_packager.py -q`
  passed with 35 tests.
- `uv run pytest tests/skill_pack -q` passed with 283 tests.
- `uv run pytest tests/test_architecture.py -q` passed with 5 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed after one transient
  remote connection reset.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10058 passed, 38 skipped`, branch coverage `85.07%`.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: JD Evidence For Draft Skill Generation

Re-read and aligned against the active reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/CONTRIBUTING.md`,
`docs/design/agentic-balance.md`, `docs/design/engineering-excellence.md`,
`docs/design/1x-completion.md`, `docs/design/23-orchestrator-refactor-map.md`,
`PROGRESS-LOG.md`, `SKILLS.md`, and `CURRENT-STATE-ANALYSIS.md`. Also checked
current official Agent Skills / Cowork docs to keep the implementation aligned
with the shared SKILL.md format and progressive-disclosure model.

Implemented:

- Added `primr skills --from-jd PATH` for local job-description / role-brief
  evidence. The CLI now allows JD-only draft-skill generation without a company
  URL when the supplied brief is the evidence source.
- Added MCP parity through `from_jd_path` on `estimate_skill_pack` and
  `generate_skill_pack`, including path validation through the shared MCP
  `PathValidator`.
- Added `skill_pack.role_brief`, which size-limits, sanitizes, and materializes
  the local JD into `_hiring/operator_role_brief.md` before planning and
  authoring.
- Updated evidence loading so operator role briefs are prepended to hiring
  evidence and override empty-hiring markers like `Source: none` / `0 postings
  found`.
- Updated planning and authoring prompts so operator-provided role briefs are
  treated as evidence, never instructions.
- Updated README, roadmap, architecture notes, and the skill-pack guide for the
  new input layer.

Validation so far:

- `uv run pytest tests/skill_pack/test_role_brief.py tests/skill_pack/test_cli.py tests/skill_pack/test_pipeline.py tests/mcp_server/test_skill_pack_tools_more_coverage.py -q`
  passed with 69 tests.
- `uv run ruff check src/primr/skill_pack src/primr/mcp_server/skill_pack_tools.py tests/skill_pack/test_role_brief.py tests/skill_pack/test_cli.py tests/skill_pack/test_pipeline.py tests/mcp_server/test_skill_pack_tools_more_coverage.py`
  passed.
- `uv run pytest tests/skill_pack tests/mcp_server/test_skill_pack_tools_more_coverage.py -q`
  passed with 318 tests.
- `uv run pytest tests/test_architecture.py -q` passed with 5 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10052 passed, 38 skipped`, branch coverage `85.06%`.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Draft Skill Format Tightening

Read and realigned against the local project guidance for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
and `docs/design/agentic-balance.md`. Also re-read the local skill-creator
guidance to keep the generated artifacts inside the Agent Skills format rather
than turning them into report-like context dumps.

Implemented:

- Tightened generated draft skills around a fixed three-section `SKILL.md`
  body: `What This Skill Does`, `Workflow`, and `Output Format`, with no extra
  H2 report/background sections.
- Added required `Required inputs:` and `Produces:` markers so every draft
  skill names the source material it needs and the artifact it returns.
- Updated authoring and refinement prompts to use company context as workflow
  specificity, input/output shape, and validation detail instead of reproducing
  public facts or evidence summaries in the skill body.
- Lowered the validator target ceiling from 3000 to 1500 words to match the
  documented draft-skill sweet spot while keeping the existing hard token cap.
- Updated `docs/SKILL_PACK.md` and regression tests for the stricter draft
  skill contract.

Validation:

- `uv run pytest tests/skill_pack/test_validator.py tests/skill_pack/test_refiner.py tests/skill_pack/test_pipeline.py -q`
  passed with 87 tests.
- `uv run pytest tests/skill_pack -q` passed with 267 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run pytest tests/test_architecture.py tests/skill_pack -q` passed with
  272 tests after splitting the new H2 section-shape helper out of
  `validator.py` to stay below the architecture line ceiling.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10039 passed, 38 skipped`, branch coverage `85.04%`.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Skill Pack Quality

Read and aligned against the project docs governing this work: `README.md`,
`ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/CONTRIBUTING.md`, `docs/IMPROVE.md`,
`docs/ARTIFACTS.md`, `docs/EVAL.md`, `docs/SECURITY.md`,
`docs/STATE_MACHINES.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `docs/design/1x-completion.md`, and
`docs/design/23-orchestrator-refactor-map.md`.

Implemented:

- Removed visible tool-branded generator attribution from current skill-pack
  outputs.
- Made skill frontmatter clean by default, with metadata opt-in through CLI,
  MCP, and config.
- Raised the generated skill body floor to 300 words and made missing intake,
  scope guardrail, human checkpoint, and worked-example markers hard findings.
- Added deterministic `references/role-family.md` generation from sanitized
  role evidence and archetype grounding, attached consistently to every skill in
  the same role family.

Validation so far:

- `uv run pytest tests/skill_pack/test_authoring.py tests/skill_pack/test_archetypes.py tests/skill_pack/test_pipeline.py -q`
  passed with 24 tests.
- `uv run pytest tests/skill_pack -q` passed with 265 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10037 passed, 38 skipped`, branch coverage `85.04%`.

Cost:

- `$0.00`. No cloud or paid validation was used.
