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
