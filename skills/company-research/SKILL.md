---

name: company-research

version: "1.1.0"

description: "Run end-to-end company research through Primr. Use when the user asks to research a company, provides a company URL, or wants a new strategic analysis run."

mcp_server: "primr"

tools:

  - estimate_run

  - research_company

  - check_jobs

  - wait_for_status_change

resources:

  - primr://research/modes

  - primr://research/status

  - primr://output/latest

  - primr://output/artifacts/by_job/{job_id}

---



# Company Research



## Purpose



Use this skill to start and monitor Primr research runs through MCP. Treat MCP as the source of truth for current modes, defaults, and outputs.



## Workflow



1. Read `primr://research/modes` to confirm the current mode guidance.

2. Read `primr://research/status` to see whether a run is already active.

3. Call `estimate_run` before starting a new run. Supports `platforms` (array), `strategy_type`, and `no_ai_strategy` parameters. Returns `estimated_time_range` alongside `estimated_time_minutes`.

4. Present the estimate, state that the run incurs real API cost, and get explicit approval before calling `research_company`.

5. After starting a run, monitor with `wait_for_status_change` or `check_jobs` until terminal.

6. Read `primr://output/artifacts/by_job/{job_id}` to inventory completed-job
artifacts without report body content, then read `primr://output/latest` only
when a report preview is needed to present the result and next actions.



## Operating Rules



- Prefer the lightest mode that answers the request.

- Do not restate fixed pricing or provider defaults from memory. Use MCP resources and `estimate_run`.

- If a job is already in progress, surface that state instead of starting a second run.

- Treat `full` as the standard end-to-end workflow and `premium` as the higher-cost, higher-depth option.

- Expect standard runs to take roughly 35-50 minutes and premium multi-vendor runs to reach 75-120 minutes.

- Do not hold the client in a synchronous wait for the entire run; launch once, then monitor and resume from job state.



## Example



```text

User: Research ExampleCo at https://example.com



1. Read primr://research/modes

2. Read primr://research/status

3. estimate_run(company_url="https://example.com", mode="full")

4. After approval: research_company(company_name="ExampleCo", company_url="https://example.com", mode="full", max_estimated_cost_usd=0.67)

5. wait_for_status_change(job_id="...", timeout_seconds=60)

```



## Error Handling



- `job_in_progress`: report the active run and offer to monitor it.

- `invalid_url` or `ssrf_blocked`: ask for a valid public URL or switch to `deep` if appropriate.

- `rate_limit_exceeded`: wait for the retry window and retry.

