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
- **Zero-cost Markdown rendering** through the `primr render` subcommand, which
  exposes the `markdown_to_docx` renderer so any Markdown report (including
  host-written Primr-Zero dossiers) reaches DOCX/TXT deliverable parity with a
  paid run.
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
- **Mid-run working briefs (Layer 1)** after scrape/collection: incomplete
  markdown with a loud banner, classified as `working_brief` (never
  `primary_report`). Fast path and structured/deep Phase 1 both emit; public
  files land under the run `output_dir`. MCP `check_jobs` exposes
  body-free `early_artifact_paths` for those files while a job is running.
- **Job-scoped artifact metadata for agents** through
  `primr://output/artifacts/by_job/{job_id}`. The resource returns file names,
  paths, sizes, SHA-256 hashes, timestamps, artifact classifications, and
  missing-file state for one owned job without returning report body content.
  This is the safe first read before an agent requests a report preview or
  opens files directly.
- **Job-scoped QA summary metadata for agents** through
  `primr://output/qa_summary/by_job/{job_id}`. The resource reads attached QA
  JSON sidecars and current text QA reports, then returns score/status/count
  metadata, parse state, hashes, timestamps, and top-level keys without
  returning detailed QA or report body content.
- **Job-scoped usage and cost metadata for agents** through
  `primr://output/usage_summary/by_job/{job_id}`. The resource reads attached
  run manifests adjacent to owned job outputs and returns estimate, approval,
  timing, execution, parse, hash, timestamp, and artifact-count metadata
  without returning company URLs, approval tokens, manifest artifact lists, or
  full manifest content. Completed measurable jobs report run-scoped
  `actual_cost_usd`; cancellations and otherwise unmeasurable terminal paths
  retain `null`. Estimates and approved ceilings are never reported as actual
  spend.
- **Job-scoped source appendix metadata for agents** through
  `primr://output/source_summary/by_job/{job_id}`. The resource reads owned
  markdown and text report artifacts, then returns citation counts, source
  definition counts, missing and unused citation numbers, duplicate URL counts,
  domains, and source URLs without returning report body content.
- **Job-scoped scrape trace metadata for agents** through
  `primr://output/trace_summary/by_job/{job_id}`. Same-run trace JSONL files
  are attached to job metadata when present, and the resource returns tier
  attempts, success rates, latency summaries, block counts, HTTP status counts,
  and validation health without returning URLs, final URLs, raw trace entries,
  or page content.
- **Job-scoped claim verification metadata for agents** through
  `primr://output/verification_summary/by_job/{job_id}`. Same-run
  `verification.json` files are attached to job metadata when MCP verification
  runs, including fast-mode MCP runs, and the resource returns trust score,
  claim counts, status counts, first-party downgrade counts, and
  source-reference counts without returning raw claims, source URLs, search
  queries, explanations, or report body content.
- **Job-scoped label-calibration metadata for agents** through
  `primr://output/calibration_summary/by_job/{job_id}`. The resource
  summarizes attached `.calibration.json` artifacts and standard sidecars
  adjacent to owned report artifacts, then returns per-label traceability
  counts, report-only inference source-copy counts, evidence-review count
  buckets, judge provenance, and judge-agreement metadata without returning raw
  claims, source URLs, evidence reviews, rationales, or report body content.
- **One bounded artifact inventory seam** shared by local and agent-facing
  surfaces. Explicit paths preserve missing-file state; exact adjacent
  Markdown, TXT, DOCX, and PDF siblings can be expanded without fuzzy cross-run
  matching; producers attach job-scoped manifests explicitly. Bounded root
  scans do not follow directory symlinks or read artifact bodies.
  `primr --list-recent --json` exposes the local
  `primr.artifact-inventory` v1.1 form. Each row retains its physical
  `artifact_type` and adds a content-free `artifact_role` for downstream
  selection: `primary_report`, `strategy_module`, `skill_pack`, `report`,
  `working_brief`, `diagnostic`, `run_metadata`, or `supporting_artifact`.
  Known product names are inferred from filenames; custom outputs fall back to
  `report` instead of being guessed from document bodies. Mid-run
  `working_brief` files are never classified as `primary_report`. Human
  `primr --list-recent` groups primary report deliverables separately from
  calibration, QA, and verification diagnostics and prints root-relative paths
  with short type tags. Explicit MCP inventories cap metadata inspection at 256
  paths and report `truncated: true` when more owned paths exist, preventing
  unbounded hashing work.

## Downstream document handoff

The artifact inventory is the neutral bridge from Primr into document skills,
agent workflows, and other consumers. Start with the Markdown
`primary_report`, add only relevant `strategy_module` artifacts and explicit
user-provided context, and preserve citations, uncertainty labels,
contradictions, and evidence gaps. The downstream consumer owns its business
schema, audience, rendering formats, destination, approval gates, and final QA.
Primr does not assume a particular sales process, brand, vendor, or HTML, PDF,
slide, or spreadsheet renderer.

The writing and regeneration prompts carry an explicit prohibition against the
internal-scaffolding markers the cleanup strips, sourced from a single shared
constant co-located with the scanner so the upstream instruction and downstream
visibility stay in lockstep. The deterministic cleanup is meant to be a safety
net, not load-bearing, and the `writer_output_clean` signal tracks whether it
stays that way. Near-term work continues to move final rendering toward
structured document data rather than free-form markdown recovery.
