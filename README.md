# Primr

[![CI](https://github.com/blisspixel/primr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/primr/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/blisspixel/primr/badge)](https://securityscorecards.dev/viewer/?uri=github.com/blisspixel/primr)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

Primr turns a company website into a sourced strategic intelligence brief.

It reads public website pages, DNS records, hiring signals, and external sources, then produces a consultant-style report with confidence labels, citations, strategic hypotheses, and optional strategy modules. The useful part is not a generic article summary. It is the primary-signal layer: what the company exposes through infrastructure, job postings, product pages, filings, and public evidence.

```bash
primr "ExampleCo" https://example.co
```

Typical output is a 23-section Strategic Overview as Markdown, TXT, DOCX, and best-effort PDF when a local converter is available. The default run also creates an AI Strategy module unless you pass `--no-ai-strategy`.

## What Primr Is For

Use Primr when you need a serious first draft for discovery, account planning, diligence, competitive analysis, or strategy work.

Primr is built for:

- A structured strategic brief instead of scattered notes.
- Research grounded in public evidence, not only web-search summaries.
- Clear uncertainty: confirmed, reported, estimated, inferred, and hypothesis labels.
- Cost-aware local execution with dry-run estimates before billable work.
- Reusable artifacts for humans, agent hosts, and downstream workflows.

Primr is not a generic crawler, a SaaS collaboration app, a model-serving platform, or a tool for bypassing authentication, paywalls, or site restrictions.

Use normal web search for a quick two-paragraph pre-call brief. Use Primr when
you want the full evidence pipeline and durable artifacts.

## Quick Start

Requirements:

- Python 3.12 or newer.
- API keys for the model providers you want to use. The measured low-cost default uses xAI plus Gemini.
- Browser dependencies installed by `primr init` for browser-backed scraping tiers.

Install with the script:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.ps1 | iex"
```

```bash
curl -fsSL https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.sh | bash
```

Or install with pipx:

```bash
pipx install primr
primr init
primr doctor
```

Plain pip also works:

```bash
pip install primr
primr init
primr doctor
```

On Windows, use the installer or pipx if `primr` is not found after `pip install`; a bare pip install can place scripts in a user Scripts directory that is not on `PATH`.

## First Run

Always estimate before a billable run:

```bash
primr "ExampleCo" https://example.co --dry-run
primr "ExampleCo" https://example.co
```

Current dry-run shape for the common setup:

| Run | What it does | Typical time | Typical cost |
|-----|--------------|--------------|--------------|
| Default with xAI plus Gemini | Strategic Overview plus AI Strategy | 34-59 min | ~$0.89-$1.01 |
| Base report only | Strategic Overview, no AI Strategy | 31-47 min | ~$0.76-$0.79 |
| `primr skills` | Agent Skills pack from company evidence | ~3 min | ~$0.30 |
| `--mode scrape` | Site corpus and extracted insights only | 5-10 min | ~$0.10 |
| `--premium` | Gemini plus Deep Research for maximum depth | 50-75 min | ~$5 |
| `primr recon` | DNS intelligence only | 2-3 sec | $0.00 |

Costs change with provider configuration, strategy count, cache hits, model pricing, and run mode. Treat `--dry-run` as the source of truth for the next run.

See [Run Modes and Costs](docs/RUN_MODES.md) for the full mode matrix, platform selection, strategy types, premium modes, and output examples.

## Choose a Command

| Need | Command |
|------|---------|
| Estimate the next run | `primr "Company" https://company.com --dry-run` |
| Standard Strategic Overview plus AI Strategy | `primr "Company" https://company.com` |
| Strategic Overview only | `primr "Company" https://company.com --no-ai-strategy` |
| Strategy aimed at Microsoft Azure plus private cloud | `primr "Company" https://company.com --platform ms` |
| Site corpus and extracted insights only | `primr "Company" https://company.com --mode scrape` |
| DNS intelligence only, no model keys required | `primr recon company.com` |
| Agent Skills pack for downstream hosts | `primr skills "Company" https://company.com` |
| Client-facing deliverables in a chosen folder | `primr "Company" https://company.com --output-dir "C:\Clients\Company"` |

For agent-host operation, the same lifecycle applies: estimate, show the cost
and mode, get explicit approval, launch, monitor asynchronously, then read the
output artifact before summarizing it. See [Agent Integration](docs/AGENT_INTEGRATION.md).

## Cost and Safety Contract

Primr treats spend and egress as explicit control surfaces:

- `--dry-run` is the source of truth for the next run estimate.
- `--budget N` refuses to start when the estimate exceeds the cap.
- Fast full-report runs checkpoint optional spend during the run.
- Premium, deep, complete, and hybrid Deep Research paths checkpoint before
  optional strategy documents after the required Deep Research task completes.
- Required Deep Research tasks cannot be stopped mid-flight once started, and
  scrape mode remains estimate-gated only.
- Outbound URLs and redirects are guarded against internal-network and
  cloud-metadata targets.

## What It Collects

Primr combines several evidence streams:

- DNS reconnaissance for cloud, identity, email security, CDN, and SaaS signals.
- Browser-first adaptive scraping across protected and ordinary websites.
- Hiring-signal discovery across major ATS providers plus careers-page fallback.
- External research and source cross-validation.
- Optional strategy modules for AI, customer experience, security, data, migration, and skills.

The pipeline is defensive: every outbound URL is validated, redirects are guarded, and protected or low-signal sites are surfaced as constraints instead of silently padded.

## Outputs

Default runs write artifacts under `output/` and diagnostics under `working/`.

Common deliverables:

- `<Company>_Strategic_Overview_<date>.md`
- `<Company>_Strategic_Overview_<date>.docx`
- `<Company>_AI_Strategy_<date>.md` when strategy generation is enabled
- `run_manifest.json` with estimate, approval, execution, and audit metadata
- `scraped_content.txt`, `insights.json`, and other intermediates for debugging

Agent hosts can inventory one completed job with
`primr://output/artifacts/by_job/{job_id}` before requesting report content.
That resource returns artifact paths, types, sizes, timestamps, hashes, and
missing-file state without returning report body content.
They can inspect attached QA outcomes with
`primr://output/qa_summary/by_job/{job_id}`, which returns compact
score/status/count metadata without detailed QA or report body text.
They can inspect run cost, timing, approval, and artifact counts with
`primr://output/usage_summary/by_job/{job_id}` without loading full manifests.
They can inspect citation/source appendix health with
`primr://output/source_summary/by_job/{job_id}` without loading report body
content.
They can inspect claim verification outcomes with
`primr://output/verification_summary/by_job/{job_id}` without loading raw
claims, source URLs, search queries, or explanations.
They can inspect scrape trace health with
`primr://output/trace_summary/by_job/{job_id}` without loading URLs, raw trace
entries, or page content.

With `--output-dir`, Primr writes customer-facing Markdown and DOCX deliverables to that folder while keeping TXT mirrors and validation diagnostics in the run diagnostics directory.

See [Artifact Pipeline](docs/ARTIFACTS.md), [Recovery Guide](docs/RECOVERY.md), and [Improve Guide](docs/IMPROVE.md).

## Configuration

Start with:

```bash
primr init
primr keys set xai
primr keys set gemini
primr keys list
primr doctor --fix
```

Important keys:

| Key | Purpose |
|-----|---------|
| `XAI_API_KEY` | Grok reasoning, strategy, and xAI-only fallback |
| `GEMINI_API_KEY` | Low-cost writing, utility, premium mode, and Gemini-backed stages |
| `OPENAI_API_KEY` | Optional OpenAI fallback provider |
| `ANTHROPIC_API_KEY` | Optional Anthropic fallback provider |
| `OLLAMA_BASE_URL` | Optional local OpenAI-compatible endpoint for local eval and utility paths |

See [API Key Setup](docs/API_KEYS.md) and [Configuration Reference](docs/CONFIG.md).

## Agent and Tool Integration

Primr can be operated from MCP-compatible agent hosts, local CLI workflows, OpenClaw, and Microsoft agent surfaces. The same rule applies everywhere: estimate first, get explicit approval, launch, then monitor asynchronously.

Start with [Agent Integration](docs/AGENT_INTEGRATION.md). Programmatic MCP and A2A details live in [MCP and A2A API](docs/API.md). Skill-pack generation is covered in [Skill Pack Guide](docs/SKILL_PACK.md).

## Development

For source checkouts, see [Contributing](docs/CONTRIBUTING.md).
The development contract is [CLAUDE.md](CLAUDE.md); it defines the code-quality
bar, architecture seams, and verification gates for changing Primr itself.

The repository has 10,000+ tests, branch coverage above the 80% CI floor, Ruff
formatting, mypy checks, Bandit, pip-audit, and strict documentation builds.

## Documentation

| Topic | Guide |
|-------|-------|
| Run modes and costs | [Run Modes and Costs](docs/RUN_MODES.md) |
| API keys | [API Key Setup](docs/API_KEYS.md) |
| Configuration | [Configuration Reference](docs/CONFIG.md) |
| Skill packs | [Skill Pack Guide](docs/SKILL_PACK.md) |
| Agent integration | [Agent Integration](docs/AGENT_INTEGRATION.md) |
| MCP and A2A API | [API Reference](docs/API.md) |
| Architecture | [System Design](docs/ARCHITECTURE.md) |
| Security | [Security Policy](docs/SECURITY.md) |
| Batch runs | [Batch Guide](docs/BATCH.md) |
| Evaluation | [Evaluation Guide](docs/EVAL.md) |
| Cloud deployment | [Cloud Deployment](docs/CLOUD_DEPLOYMENT.md) |
| Next steps | [Next Steps](docs/NEXT_STEPS.md) |
| Roadmap | [Roadmap](ROADMAP.md) |

The docs site starts at [docs/README.md](docs/README.md).

## Disclaimer

Primr retrieves and analyzes public web content. You are responsible for checking site terms, provider costs, output accuracy, and legal fit for your use case. AI-generated analysis can be wrong or outdated; verify important findings before acting on them.

## License

Apache 2.0. See [LICENSE](LICENSE).
