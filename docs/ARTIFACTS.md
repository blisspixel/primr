# Artifact Pipeline

Primr treats **research artifacts** and **shipping artifacts** as different
classes of output. Intermediate research steps (scrape summaries, gap-analysis
notes, source inventories, contradiction findings, section briefs) optimize for
consistency, provenance, and parseability - their formatting matters far less
than whether they are complete and structured enough to feed later stages
reliably. Final reports and strategy documents are a stricter output contract:
they must ship cleanly as Markdown, TXT, DOCX (and eventually PDF), with
deterministic cleanup, citation normalization, validation gates, and renderer
hardening.

Decision principle: permissive about formatting in the research pipeline,
strict about formatting and structure in the final document pipeline.

## What is in place

- **Final-document canonicalization** before shipping, so report/strategy
  artifacts are normalized into a stable shape before MD/TXT/DOCX rendering.
- **Typed generated-section normalization** at the section-writing seam,
  including validation-line cleanup, embedded reference stripping, and citation
  extraction.
- **Mixed-format parsing resilience** so section batches recover cleanly even if
  the model blends XML-style section envelopes with legacy `##` headings.
- **Cleaner DOCX validation**, including reduced false positives from literal
  `#` content inside tables.
- **Configurable ship-time gates** that withhold the polished DOCX (Markdown/TXT
  plus a sidecar diagnostic still ship) when a deliverable carries leaked
  internal scaffolding (`PRIMR_MAX_SCAFFOLDING_LEAKS`), dangling citations
  (inline `[cite: N]` with no matching Sources entry,
  `PRIMR_MAX_DANGLING_CITATIONS`), or structural defects (duplicate `##`
  headings and empty sections, `PRIMR_MAX_STRUCTURE_DEFECTS`). All default to
  zero tolerance and act as regression backstops behind the upstream
  cleanup/repair steps.
- **An artifact regression corpus** (`tests/fixtures/artifacts/`) of long-form
  report/strategy fixtures that exercises the gates and renders the clean ones
  end-to-end to DOCX, so validator/renderer changes are tested against
  real-shaped output.

The writing and regeneration prompts carry an explicit prohibition against the
internal-scaffolding markers the ship-time gate strips, sourced from a single
shared constant co-located with the scanner so the upstream instruction and the
downstream gate stay in lockstep. The deterministic cleanup is meant to be a
safety net, not load-bearing, and the `writer_output_clean` signal tracks
whether it stays that way. Near-term work continues to move final rendering
toward structured document data rather than free-form markdown recovery.
