# Open Claw Integration Guide



This guide covers the maintained OpenClaw integration for Primr.



Primr is exposed to OpenClaw through `primr-mcp`. Skills and workflows should treat MCP as the source of truth for current modes, defaults, status, and outputs.



## Prerequisites



- Python 3.12+

- Primr installed

- OpenClaw installed

- `XAI_API_KEY` for the standard default workflow, `GEMINI_API_KEY` for premium mode, or both

- Optional: `SEARCH_API_KEY` and `SEARCH_ENGINE_ID` if you want Google Custom Search instead of DuckDuckGo



## Installation



### 1. Install Primr



```bash

pip install primr

primr-mcp --help

```



### 2. Copy the OpenClaw assets



```bash

# Linux/macOS

cp -r openclaw/* ~/.openclaw/



# Windows

xcopy /E openclaw %USERPROFILE%\.openclaw```



### 3. Configure environment variables



```bash

export XAI_API_KEY="your-xai-api-key"

export GEMINI_API_KEY="your-gemini-api-key"

# Optional fallback search config

export SEARCH_API_KEY="your-google-search-api-key"

export SEARCH_ENGINE_ID="your-search-engine-id"

```



### 4. Verify the installation



```bash

primr doctor

```



## What the integration provides



### Skills



- `primr-research`: estimate, start, and monitor research jobs

- `primr-strategy`: estimate and generate strategy deliverables from existing reports

- `primr-qa`: run QA and diagnostics



### Workflow



- `research-pipeline`: estimate, approval, execution, and monitoring for a full research run
- `strategy-pipeline`: estimate, approval, and governed strategy generation from an existing report



## Operating model



- Read `primr://research/modes` before advising on mode selection.

- Call `estimate_run` before starting new research work and show the user the expected cost/time.
- If `PRIMR_ENFORCE_MCP_COST_CAPS` is enabled, the packaged research workflow now propagates the approved estimate as `max_estimated_cost_usd` into `research_company`, and the packaged strategy workflow does the same for `generate_strategy`.

- Treat `full` as the standard end-to-end mode.
- Expect long runtimes: standard runs are often 35-50 minutes, and premium multi-vendor runs can take 75-120 minutes.
- Build around async monitoring and reconnection, not one long blocking session.

- Use `premium` only when the user explicitly wants maximum-depth research.

- Use `primr://research/status`, `wait_for_status_change`, or `check_jobs` for monitoring.



## Troubleshooting



### `primr-mcp` is not found



```bash

which primr-mcp

where primr-mcp

pip install --upgrade primr

```



### API keys are missing or incorrect



```bash

primr doctor

```



Confirm the relevant provider key is available in the environment passed to OpenClaw.



### A run looks stuck



- Read `primr://research/status`

- Check whether `possibly_stuck` is true

- Use `cancel_job` only if the run is no longer making progress



## Docker sandbox



```bash

docker build -f openclaw/Dockerfile.primr -t primr-sandbox .

docker run -e XAI_API_KEY -e GEMINI_API_KEY -e SEARCH_API_KEY -e SEARCH_ENGINE_ID -v ./output:/workspace/output primr-sandbox

```



## Related docs



- [API.md](API.md)

- [README.md](https://github.com/blisspixel/primr/blob/main/README.md)

- [openclaw.json](https://github.com/blisspixel/primr/blob/main/openclaw/openclaw.json)

