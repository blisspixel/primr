# Primr

[![CI](https://github.com/blisspixel/primr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/primr/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/primr.svg)](https://pypi.org/project/primr/)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/blisspixel/primr/badge)](https://securityscorecards.dev/viewer/?uri=github.com/blisspixel/primr)

**Company URL → sourced strategic brief.** Built for agent hosts and the CLI:
structured collection, confidence labels, and durable artifacts, not a free-form
chat essay.

Primr gathers public site pages, DNS/recon, hiring signals, and other open
sources, then produces a consultant-style Strategic Overview (and optional
strategy modules) with citations and Confirmed / Reported / Estimated /
Hypothesis labels. Point an agent at the repo, or run the CLI. Both paths use
the same evidence and uncertainty contract and can produce the same artifact
formats, but their execution, model ownership, and assurance are different.

<p align="center">
  <img
    src="docs/images/primr-demo.png"
    alt="Illustrative primr CLI session for ExampleCo: estimate, then report artifacts"
    width="920"
    loading="lazy"
  />
</p>

<p align="center"><sub>Placeholder demo data (ExampleCo), not a live company capture.</sub></p>

```bash
primr "ExampleCo" https://example.co
```

In an agent chat, that request **defaults to Primr Zero**: keyless evidence
collection in Primr, research and writing in the host (when the host plan does
not bill API usage). When a human runs the command **directly in a terminal**,
it retains the **provider-backed** CLI path after a dry-run estimate and
approval.

## What it is for

Use Primr when you need a serious first draft for discovery, account planning,
diligence, competitive analysis, or strategy work, not a two-paragraph pre-call
blurb (use normal web search for that).

- Structured brief with uncertainty labels, not scattered notes
- Research grounded in public evidence, not only search summaries
- Cost-aware local execution: dry-run before billable work
- Reusable Markdown/DOCX artifacts for humans, agents, and downstream tools

Primr is not a generic crawler, a SaaS collaboration app, a model-serving
platform, or a tool for bypassing authentication, paywalls, or site restrictions.

## Start here

| Where you run it | Default path | Spend | Result |
|---|---|---|---|
| Agent chat pointed at Primr | Primr Zero | No Primr model API spend; verify host plan allowance | Evidence bundle + host-written sourced dossier |
| Terminal or script | Provider-backed | Billable after a fresh quote and explicit approval | Primr Strategic Overview + strategy artifacts |

Both paths can deliver a Strategic Overview and AI Strategy as Markdown and
DOCX (on the Zero path, `primr render <file>.md` converts host Markdown to DOCX
at `$0`). The provider-backed path additionally owns its measured synthesis,
cross-validation, usage accounting, and recovery stages. A configured API key
is capability, not consent to spend.

### Agent path

Point a capable agent at this repository:

```text
primr "ExampleCo" https://example.co
```

The agent uses Primr Zero unless you explicitly request paid, metered,
provider-backed, or premium execution. Details, MCP setup, and host handoff:
[Agent Integration](docs/AGENT_INTEGRATION.md) ·
[Zero-Cost / Primr Zero](docs/ZERO_COST.md).

The experimental [`agent-plugin/`](agent-plugin/) distribution follows the
Agent Plugins v1.0.0 Working Draft with a portable root `plugin.json`, Agent
Skills, and `mcp.json`. The existing [`claude-code/`](claude-code/) package
remains the Claude-specific adapter.

### Terminal path

```bash
primr "ExampleCo" https://example.co --dry-run        # always first
primr "ExampleCo" https://example.co                  # foreground, then approve
primr "ExampleCo" https://example.co --skip-confirm   # automation, after approval
```

`--skip-confirm` is the approval signal for a noninteractive or background
launch of the standard provider-backed commands. Use it only after a person has
reviewed and approved the fresh quote. The experimental `primr orchestrate`
command is the exception: its noninteractive approval and spend ceiling is
`--max-cost <usd>` after the exact dry run is approved.

Mode matrix, platforms, strategy types, and cost controls:
[Run Modes and Costs](docs/RUN_MODES.md).

## Install

- Python 3.12+
- No API key or GPU for `primr recon` / `primr prep`
- Keys only for provider-backed research (measured default: xAI + Gemini)
- `primr init` installs browser deps for scrape tiers

```bash
pipx install primr
primr --version
```

Plain `pip install primr` also works. On Windows, prefer pipx or the installer
if `primr` is missing from `PATH` after pip.

Upgrade in a foreground terminal with `primr update`. An approved automated
upgrade must pass `primr update --yes`; otherwise Primr exits before inspecting
or running the installation command.

The convenience installers set up pipx and common PATH issues. Download and inspect
the script before executing it:

```powershell
$primrInstaller = Join-Path $env:TEMP "primr-install.ps1"
Invoke-WebRequest https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.ps1 -OutFile $primrInstaller
Get-Content $primrInstaller
powershell -ExecutionPolicy Bypass -File $primrInstaller
```

```bash
primr_installer="$(mktemp)"
trap 'rm -f "$primr_installer"' EXIT
curl -fsSL https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.sh -o "$primr_installer"
cat "$primr_installer"
bash "$primr_installer"
```

Provider-backed setup only when you want billable runs:

```bash
primr init
primr doctor
```

Keys and full config: [API Key Setup](docs/API_KEYS.md) ·
[Configuration](docs/CONFIG.md).

## Common commands

| Need | Command |
|------|---------|
| Agent-host dossier (Zero by default) | `primr "Company" https://company.com` |
| Keyless evidence bundle | `primr prep "Company" https://company.com` |
| Estimate a paid run | `primr "Company" https://company.com --dry-run` |
| Strategic Overview only | `primr "Company" https://company.com --no-ai-strategy` |
| Site corpus only | `primr "Company" https://company.com --mode scrape` |
| DNS only (no keys) | `primr recon company.com` |
| Skills pack | `primr skills "Company" https://company.com` |
| Markdown → DOCX/TXT ($0) | `primr render "output/report.md"` |
| Strategy on existing report | `primr --ai-strategy-only "output/report.md" --dry-run` |
| Check or install an update | `primr update --check` / `primr update` |

Focused help: `primr --help`. Everything: `primr --help-all`.

## Cost gate

Billable runs need a fresh estimate and explicit approval. Use `--dry-run` to
inspect the plan without starting work; normal execution repeats the quote and
asks before provider work begins. `--budget N` refuses to start above the cap.
Without `--skip-confirm`, a noninteractive launch starts no provider work and
tells the caller how to rerun after approval. A closed input stream is reported
as missing approval instead of being recorded as a user cancellation.
Batch, enrichment, vendor research, and standalone strategy each have their own
quote path. See [Run Modes and Costs](docs/RUN_MODES.md#cost-controls).

## Outputs

Default: customer-facing files under `output/`, diagnostics under `working/`.

- `<Company>_Strategic_Overview_<date>.md` / `.docx`
- `<Company>_AI_Strategy_<date>.md` / `.docx` (unless `--no-ai-strategy`)
- `run_manifest.json` (estimate, approval, audit)

Agent inventory (paths/roles only, no report body):
`primr://output/artifacts/by_job/{job_id}`. Full artifact and recovery guides:
[Artifacts](docs/ARTIFACTS.md) · [Recovery](docs/RECOVERY.md).

## Docs

| Topic | Guide |
|-------|-------|
| Run modes and costs | [RUN_MODES](docs/RUN_MODES.md) |
| Primr Zero / host-assisted | [ZERO_COST](docs/ZERO_COST.md) |
| Agent / MCP / A2A | [AGENT_INTEGRATION](docs/AGENT_INTEGRATION.md) · [API](docs/API.md) |
| API keys | [API_KEYS](docs/API_KEYS.md) |
| Configuration | [CONFIG](docs/CONFIG.md) |
| Artifacts | [ARTIFACTS](docs/ARTIFACTS.md) |
| Skill packs | [SKILL_PACK](docs/SKILL_PACK.md) |
| Security | [SECURITY](docs/SECURITY.md) |
| Contributing / architecture | [CONTRIBUTING](docs/CONTRIBUTING.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) |
| Roadmap | [ROADMAP](ROADMAP.md) |

Docs site index: [docs/README.md](docs/README.md).

## Disclaimer

Primr retrieves and analyzes public web content. You are responsible for site
terms, provider costs, output accuracy, and legal fit. AI-generated analysis can
be wrong or outdated. Verify important findings before acting on them.

## License

Apache 2.0. See [LICENSE](LICENSE).
