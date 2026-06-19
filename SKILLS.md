# Engineering Learnings

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
