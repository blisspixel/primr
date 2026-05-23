---
name: scrape-strategy
version: "1.1.0"
description: "Guide mode selection when site scraping is weak, blocked, or low quality. Use when the user asks why scraping failed or how Primr should proceed on a protected site."
mcp_server: "primr"
tools:
  - estimate_run
  - check_jobs
resources:
  - primr://research/modes
  - primr://research/status
---

# Scrape Strategy

## Purpose

Use this skill when the bottleneck is site access rather than report writing. Focus on deciding whether to stay in scrape-capable modes or pivot to external research.

## Workflow

1. Read `primr://research/modes` to compare scrape, deep, full, and premium behavior.
2. Review current run state through `primr://research/status` or `check_jobs`.
3. Use `references/tiers.md` only when you need tier-level scraping context.
4. Recommend the smallest viable change: retry, change mode, or accept partial coverage.

## Decision Rules

- Prefer `deep` when the target site is heavily protected or first-party signal is sparse.
- Stay with `scrape` or `full` when first-party pages are the core evidence source.
- Do not promise exact success percentages unless the run data already shows them.
- Escalate from site troubleshooting to mode selection quickly; avoid over-explaining scrape internals unless the user asks.

## Example

```text
User: The site seems blocked

1. Read primr://research/status
2. Read primr://research/modes
3. Explain whether deep mode is the better fit
4. If needed, estimate_run(company_url="https://example.com", mode="deep")
```
