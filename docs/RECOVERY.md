# Crash Recovery and Resume

Primr writes per-run state to the working folder as `_run_state.json` and keeps recoverable cloud interaction IDs in `logs/pending_research_jobs.json`. Status inspection and recovery are separate actions so checking a job never consumes it or writes output artifacts.

## Recovery Commands

```bash
# 1) Inspect pending cloud jobs and the latest local run without changing them
primr --check-jobs

# Machine-readable inspection, exactly one versioned JSON object
primr --check-jobs --json

# 2) Finalize completed cloud jobs and acknowledge provider-terminal jobs
primr --resume-latest

# 3) Continue a local run for one company from its latest incomplete folder
primr "Company Name" https://company.com --resume-local
```

When a cloud job is complete, `--check-jobs` prints the next command but leaves the pending record intact. Normal runs and `--resume-latest` acknowledge the provider job only after their outer output boundary verifies every required artifact is a nonempty regular file. Recovery writes canonical `.md`, `.txt`, and `.docx` outputs. If finalization fails, Primr writes a fallback text artifact and retains the job so canonical conversion can be retried.

Background interaction creation is persisted immediately. Polling and status
inspection never acknowledge it. Preflight validation does not launch a
billable Deep Research interaction merely to test connectivity.

Provider-terminal jobs remain visible during inspection. Explicit resume reports their exact terminal status and removes them from the pending list. Connectivity or status-check errors remain pending and return a nonzero exit code.

## Local Run State

`--check-jobs` also prints the latest readable local run state when one exists, including only fields that are present. It always prints the exact `_run_state.json` path for deeper diagnosis.

Inspect that file only when the summary is insufficient:

```powershell
Get-Content -Raw "working\Company_Name\YYYY-MM-DD_HHMM\_run_state.json"
```

```bash
cat "working/Company_Name/YYYY-MM-DD_HHMM/_run_state.json"
```

Local resume reuses the latest incomplete working folder for the requested company and skips pages already saved in `_raw_scrapes`. Scrape progress remains available in `_raw_scrapes/_scrape_trace.log` and `_run_state.json`.
