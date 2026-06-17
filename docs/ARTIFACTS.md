# Artifact Pipeline

Primr treats **research artifacts** and **shipping artifacts** as different
classes of output. Intermediate research steps (scrape summaries, gap-analysis
notes, source inventories, contradiction findings, section briefs) optimize for
consistency, provenance, and parseability - their formatting matters far less
than whether they are complete and structured enough to feed later stages
reliably. Final reports and strategy documents are a stricter output contract:
they must ship cleanly as Markdown, TXT, DOCX, and best-effort PDF when a local
converter is available, with deterministic cleanup, citation normalization,
validation gates, and renderer hardening.

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
  plus a sidecar diagnostic still ship) for structural or referential defects:
  dangling citations (inline `[cite: N]` with no matching Sources entry,
  `PRIMR_MAX_DANGLING_CITATIONS`), duplicate top-level headings, empty sections
  (`PRIMR_MAX_STRUCTURE_DEFECTS`), and unambiguous internal-token leaks. The
  scaffolding-leak scan is now a non-blocking warning and eval metric, not a
  content-quality gate.
- **An artifact regression corpus** (`tests/fixtures/artifacts/`) of long-form
  report/strategy fixtures that exercises the gates and renders the clean ones
  end-to-end to DOCX, so validator/renderer changes are tested against
  real-shaped output.

The writing and regeneration prompts carry an explicit prohibition against the
internal-scaffolding markers the cleanup strips, sourced from a single shared
constant co-located with the scanner so the upstream instruction and downstream
visibility stay in lockstep. The deterministic cleanup is meant to be a safety
net, not load-bearing, and the `writer_output_clean` signal tracks whether it
stays that way. Near-term work continues to move final rendering toward
structured document data rather than free-form markdown recovery.
