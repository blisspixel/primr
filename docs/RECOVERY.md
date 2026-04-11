# Crash Recovery & Resume

Primr writes per-run state to the working folder as `_run_state.json` (phase, status, timeline events). If your computer reboots mid-run, you can recover without losing progress.

## Recovery Commands

```bash
# 1) Recover completed cloud jobs (Deep Research / AI Strategy)
primr --resume-latest

# 2) Continue local run from latest incomplete working folder for this company
primr "Company Name" https://company.com --resume-local

# 3) Inspect local run state (scrape + phase checkpoints)
type working\\Company_Name\\YYYY-MM-DD_HHMM\\_run_state.json
```

## Recovery Behavior

- Deep Research / AI Strategy jobs run in the cloud and can be recovered after reboot.
- `--resume-latest` finalizes recovered outputs to canonical filenames (`.md/.txt/.docx`).
- `--resume-local` reuses the latest incomplete working folder for the same company and skips pages already saved in `_raw_scrapes` (same run folder is reused for standard/Grok mode).
- Local scrape progress is logged in `_raw_scrapes/_scrape_trace.log` and summarized in `_run_state.json`.
