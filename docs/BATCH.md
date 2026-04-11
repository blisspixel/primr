# Batch Research

Have a spreadsheet of companies? Primr can enrich it with website URLs and run research across the list.

## Two-Step Workflow (Recommended)

```bash
# Step 1: Enrich - auto-detect columns, look up websites, filter by industry, save CSV
primr --batch companies.xlsx --industry Utilities --enrich

# Step 2: Review the enriched CSV, then run research
primr --batch companies_utilities_enriched.csv --mode scrape
```

## Options

```bash
--enrich          # Enrich only - look up websites, save CSV, don't research
--industry NAME   # Filter rows by industry column value
--limit N         # Process only the first N companies (useful for testing)
--skip-confirm    # Skip the confirmation prompt (for unattended runs)
--mode MODE       # scrape ($0.10/co), deep ($2.50/co), full (~$0.75/co or ~$5/co with --premium)
--grok-tier TIER  # fast (~$0.53), hybrid (~$0.75, 4.20 reasoning), max (~$4, 4.20 everywhere)
```

## Defensive Behavior

- Shows cost estimate and asks for confirmation before starting (use `--skip-confirm` to bypass)
- **Resume:** re-run the same command to skip companies that already have reports from today
- Cooldown between companies (10s for scrape, 60s for deep/full) to avoid API quota issues
- Exponential retry with jitter on transient API failures (429, 5xx, service unavailable, timeouts)
- Pauses and asks after 3 consecutive failures - option to wait 10 minutes or stop
- Deduplicates companies by name (case-insensitive)

Accepts Excel (`.xlsx`) or CSV files. Smart column detection uses an LLM to find company name, website, and industry columns automatically.
