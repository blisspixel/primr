# Progress Log

## 2026-06-19

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
