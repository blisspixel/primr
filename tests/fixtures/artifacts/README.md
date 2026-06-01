# Artifact regression corpus

Realistic long-form report/strategy artifacts used to regression-test the final
**shipping pipeline** — the ship-time markdown gate
(`primr.output.artifact_validation._validate_output_markdown`) and the
markdown -> DOCX renderer (`primr.output.markdown_converter.markdown_to_docx` +
`_validate_output_docx`).

The harness is `tests/test_output/test_artifact_corpus.py`. It reads
`manifest.json`, and for each fixture asserts the gate's pass/fail outcome and
the expected issue categories; clean fixtures (`render_docx: true`) are also
rendered end-to-end to DOCX and re-validated, so renderer changes are tested
against real-shaped output, not toy strings.

## Why this exists

Unit tests use small hand-crafted strings. This corpus tests the gates and
renderer against artifacts shaped like actual deliverables (multi-section,
confidence labels, `[cite: N]` + `## Sources` appendix, tables). It is the
backstop the roadmap's "Artifact Pipeline Hardening" item calls for, and the
prerequisite for a future section-structure gate.

## Adding a fixture

1. Drop a `.md` file here. **No real company data** — use placeholders
   (`Acme Corp`, `Northwind Haulage`, `ExampleCo`, `acme.example`). If you are
   seeding from a real shipped/failed run, sanitize every company name, URL,
   and identifying detail first (see `docs/CONTRIBUTING.md`).
2. Add a `manifest.json` entry:
   - `expect_pass`: whether `_validate_output_markdown` should pass it.
   - `issue_prefixes`: issue-string prefixes that must appear when it fails
     (e.g. `citation_integrity:`, `scaffolding_leak:`, `raw_source_tag:`).
   - `render_docx`: `true` only for clean fixtures that should render to a
     clean DOCX.
   - `notes`: what failure mode (or clean shape) the fixture exercises.

The harness picks it up automatically — no test code changes needed.
