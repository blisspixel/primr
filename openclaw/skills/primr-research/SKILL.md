---

name: primr-research

version: "1.1.0"

description: "Run and monitor company research through Primr MCP. Use when the user wants a new research run, asks for status, or needs mode selection help before starting."

metadata:

  openclaw:

    requires:

      bins:

        - primr-mcp

      env:

        - XAI_API_KEY

        - GEMINI_API_KEY

      os:

        - linux

        - darwin

        - win32

mcp_server: primr

tools:

  - estimate_run

  - research_company

  - check_jobs

  - cancel_job

  - wait_for_status_change

resources:

  - primr://research/modes

  - primr://research/status

  - primr://output/latest

  - primr://output/artifacts

  - primr://output/artifacts/by_job/{job_id}

  - primr://output/qa_summary/by_job/{job_id}

  - primr://output/usage_summary/by_job/{job_id}

  - primr://output/source_summary/by_job/{job_id}

---



# Primr Research Skill



## Conceptual Framework



This skill is a thin orchestrator over Primr MCP.



Use MCP resources to discover current behavior instead of assuming fixed costs, providers, or defaults from the skill text. `full` is the standard end-to-end workflow, `premium` is the higher-depth option, and `scrape` and `deep` are narrower research modes.



Research runs are async jobs. Start the run, then monitor status until terminal. Standard runs often take 35-50 minutes; premium multi-vendor runs can take 75-120 minutes.



## Operational Capabilities



### 1. Select a mode



- Read `primr://research/modes` before advising on mode selection.

- Use `scrape` for first-party reconnaissance.

- Use `deep` when the site is blocked or low-signal.

- Use `full` for the default strategic analysis workflow.

- Use `premium` when the user explicitly wants maximum depth.



### 2. Estimate before execution



Always call `estimate_run` before `research_company`, then state that the run incurs real API cost and wait for explicit user approval.



```text

estimate_run(company_url="https://example.com", mode="full")

```



### 3. Start and monitor the job



After user approval, call `research_company` and pass the approved `max_estimated_cost_usd` when available, then monitor with `wait_for_status_change`, `check_jobs`, or `primr://research/status`. Do not assume the client session will stay attached for the entire run.



```text

research_company(company_name="ExampleCo", company_url="https://example.com", mode="full")

```



### 4. Retrieve results



When the run completes, read `primr://output/artifacts/by_job/{job_id}` first
to inventory artifacts without report body content. Read
`primr://output/qa_summary/by_job/{job_id}` when QA artifacts are attached.
Read `primr://output/usage_summary/by_job/{job_id}` when cost, timing,
approval, or artifact-count metadata is needed.
Read `primr://output/source_summary/by_job/{job_id}` when citation/source
appendix metadata is needed.
Read `primr://output/latest` only when the next step needs a report preview.



## Error Handling



- `job_in_progress`: report the existing run and monitor it instead of starting another.

- `invalid_url` or `ssrf_blocked`: require a valid public URL, or consider `deep` mode.

- `rate_limit_exceeded`: wait for the retry window.

- `api_error`: surface the provider error clearly and recommend retry or diagnostics.

