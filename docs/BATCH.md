# Batch Research

Primr can enrich a spreadsheet with missing website URLs, then run the same
governed research shape across every eligible row. Enrichment and research are
separate cost and approval boundaries.

## Two-Step Workflow

First, quote the missing-site lookups without sending a search or model call:

```bash
primr --batch "companies.xlsx" --industry Utilities --enrich --dry-run
```

Review the quoted model, lookup count, maximum token shape, estimated cost, and
output path. Then remove `--dry-run` and approve the enrichment when ready:

```bash
primr --batch "companies.xlsx" --industry Utilities --enrich
```

Review the enriched CSV. Quote the entire pending research batch before
starting it:

```bash
primr --batch "companies_utilities_enriched.csv" --mode scrape --dry-run
```

The plan counts parsed, invalid, completed, missing-site, and pending rows. It
multiplies the canonical per-company estimate by pending rows and applies
`--budget` to that whole-batch total. Remove `--dry-run` only after the plan is
acceptable:

```bash
primr --batch "companies_utilities_enriched.csv" --mode scrape --budget 2.00
```

## Input Contract

- Excel (`.xlsx`, `.xls`) and UTF-8 CSV files are supported.
- Common company, website, industry, and context headers are classified
  deterministically. Planning does not call a model or search provider.
- A row with a website but no company name derives a display name from the
  validated normalized hostname.
- Duplicate company names are collapsed case-insensitively.
- Research does not look up missing websites. Enrich and review those rows
  first.
- Invalid rows block paid execution and are listed in the plan.

## Cost and Execution Contract

- `--dry-run` starts no search, model, or research call.
- Enrichment performs its exact quoted lookup shape only after approval. It
  pins the quoted model and disables automatic retries and provider failover.
- Research collects one batch approval. Nested company runs do not ask again.
- `--budget N` is a cap for the full pending batch. Primr allocates the approved
  cap across pending companies and clears budget state after each run.
- Network-bearing diagnostics never run before approval. The post-approval
  batch preflight is local-only.
- Paid company runs are attempted at most once. Primr stops after three
  consecutive failures and leaves remaining rows visibly unattempted.
- Reports already present for the current day are excluded from the pending
  count and quote.
- `--skip-confirm` is the explicit unattended-execution override. It does not
  enable hidden retries or unsupported options.

## Options

Common governed options include `--industry`, `--limit`, `--mode`,
`--platform`, `--strategy-type`, `--no-ai-strategy`, `--lite-strategy`,
`--fast`, `--premium`, `--grok-tier`, `--verify`, `--no-qa`, `--skip-recon`,
`--max-scrape-time`, `--output-dir`, `--budget`, and `--skip-confirm`.

Per-company context files, discovery notes, framing fields, resume-local,
vendor refresh, open-after, and potentially metered host-agent acknowledgment
are rejected for batch research because their per-row or fan-out semantics are
not governed. Enrichment also rejects shared options it cannot honor rather
than silently ignoring them.

Use `--json` with `--dry-run` for one machine-readable JSON object. The legacy
`--csv` option routes through the same governed research path but is deprecated;
new automation should use `--batch`.
