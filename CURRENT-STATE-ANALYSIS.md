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
