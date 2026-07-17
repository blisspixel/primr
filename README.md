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
- No model API key or GPU is required for `primr recon` or `primr prep`.
- API keys are required only for provider-backed research. The measured low-cost default uses xAI plus Gemini.
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

## Keyless Quick Start

If you already have a research-capable agent plan but no model API key or GPU,
prepare a bounded evidence bundle locally and let that host do the synthesis:

```bash
primr prep "ExampleCo" https://example.co --dry-run
primr prep "ExampleCo" https://example.co
```

`primr prep` performs public network requests but makes no model calls. Its
hard-zero guard remains active even when provider keys are configured. The
bundle contains first-party pages, typed fallback provenance, a source index,
hashes, a fenced host packet, a host workflow, and an installable copy of the
`primr-zero` Agent Skill. DNS, public hiring signals, and scrape traces are
included when their collectors return evidence. Use the skill to research
external gaps and write the dossier with the host allowance you already have,
but verify that the host is plan-backed and will not bill API usage or overages
before calling the whole workflow zero incremental spend.

Install the packaged skill globally when you do not want a repository copy:

```bash
primr prep --install-skill ~/.agents/skills/primr-zero
```

Claude Code uses `~/.claude/skills/primr-zero` instead.

Prep collection is `$0.00` in model API spend. Host synthesis is also zero
incremental only when the host is verified to use included plan allowance with
no API billing or overages. Subscription terms, plan limits, electricity, and
network access still apply. See
[Zero-Cost and Host-Assisted Research](docs/ZERO_COST.md) for install paths,
capability fallbacks, and the difference between this host-native path and the
explicitly gated, unpromoted in-pipeline Codex pilot.

## Provider-Backed First Run

Always estimate before a billable run:

```bash
primr "ExampleCo" https://example.co --dry-run
primr "ExampleCo" https://example.co
```

Current dry-run shape for the common setup:

| Run | What it does | Typical time | Typical cost |
|-----|--------------|--------------|--------------|
| `primr recon` | DNS intelligence only | 2-3 sec | $0.00 |
| `primr prep` + `primr-zero` | Keyless Primr collection plus synthesis in an existing agent plan | 5-15 min collection, then host-dependent | $0.00 incremental model API spend |
| Default with xAI plus Gemini | Strategic Overview plus AI Strategy | 34-59 min | ~$0.89-$1.01 |
| Base report only | Strategic Overview, no AI Strategy | 31-47 min | ~$0.76-$0.79 |
| `primr skills` | Agent Skills pack from company evidence | ~3 min | ~$0.30 |
| `--mode scrape` | Site corpus and extracted insights only | 5-10 min | ~$0.10 |
| `--premium` | Gemini plus Deep Research for maximum depth | 50-75 min | ~$5 |

Costs change with provider configuration, strategy count, cache hits, model pricing, and run mode. Treat `--dry-run` as the source of truth for the next run.
Human dry-runs end with concise launch, monitoring, recovery, and artifact-retrieval steps. Add `--verbose` to inspect the serialized recovery policy, or `--json` to receive one machine-readable estimate object.
`primr skills` generates Cowork icons locally by default; remote image APIs are used only with `--remote-icons`.
Cached vendor research is reused when present. Fresh vendor-research generation or refresh requires `--refresh-vendor-research`, `primr --generate-vendor-research`, or `PRIMR_ALLOW_VENDOR_REFRESH=1`.
PDF text extraction uses local PyMuPDF by default; Gemini PDF extraction is opt-in with `PRIMR_PDF_LLM_MAX_CALLS=N`.

`primr init --help` and `primr doctor --help` show focused one-screen guidance for onboarding and diagnostics. Use `primr --help` for the complete command reference.

See [Run Modes and Costs](docs/RUN_MODES.md) for the full mode matrix, platform selection, strategy types, premium modes, and output examples.

## Choose a Command

| Need | Command |
|------|---------|
| Keyless evidence bundle for an existing agent plan | `primr prep "Company" https://company.com` |
| Estimate the next run | `primr "Company" https://company.com --dry-run` |
| Standard Strategic Overview plus AI Strategy | `primr "Company" https://company.com` |
| Strategic Overview only | `primr "Company" https://company.com --no-ai-strategy` |
| Strategy aimed at Microsoft Azure plus private cloud | `primr "Company" https://company.com --platform ms` |
| Enable routed utility-stage pilot | `primr "Company" https://company.com --inference hybrid` |
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
- The unpromoted Codex source-relevance pilot requires `--inference hybrid`
  plus `--acknowledge-host-agent-may-bill`, is limited to single-company runs,
  and may incur host charges that are excluded from `--dry-run` totals and
  `--budget`.
- Remote Cowork icon generation, vendor-research refresh, and Gemini PDF
  extraction are opt-in controls rather than key-presence side effects.
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
That resource returns artifact paths, physical types, semantic roles, sizes,
timestamps, hashes, and missing-file state without returning report body
content. Roles identify the primary report, strategy modules, other reports,
diagnostics, and run metadata for tool-neutral downstream handoffs. Exact
adjacent Markdown, TXT, DOCX, and PDF siblings are included even when an older
producer attached only its primary path; current producers attach their
job-scoped run manifest explicitly. `primr --list-recent` uses the same bounded
inventory model locally, groups primary deliverables separately from
calibration, QA, and verification diagnostics, and ranks named product reports
above empty or incidental files; add `--json` for the versioned object.
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
They can inspect label-calibration outcomes with
`primr://output/calibration_summary/by_job/{job_id}` without loading raw
claims, source URLs, evidence reviews, rationales, or report body content.
That summary includes per-label traceability counts and report-only
source-copy counts for cited `(Estimated)` / `(Hypothesis)` claims.
They can inspect scrape trace health with
`primr://output/trace_summary/by_job/{job_id}` without loading URLs, raw trace
entries, or page content.
MCP `resources/read` calls are audited with hashed URI/result values,
normalized resource kind, job id when present, granted scopes, duration, and
outcome; raw URI query values and resource bodies are not persisted in the
audit log. A2A skill calls and task cancellation use the same audit log with
hashed message/result payloads, hashed caller ids, granted scopes, duration,
outcome, and job id when present; raw message text, task ids, URLs, report
paths, raw results, and caller ids are not persisted.

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

Primr can be operated from MCP-compatible agent hosts, local CLI workflows,
OpenClaw, and Microsoft agent surfaces. Billable research follows the same rule
everywhere: estimate first, get explicit approval, launch, then monitor
asynchronously. `primr prep` is a separate hard-zero collection path: disclose
its public network access, but no spend approval is required because model calls
are disabled for the workflow.

Start with [Agent Integration](docs/AGENT_INTEGRATION.md). The no-key, no-GPU
path is covered in [Zero-Cost and Host-Assisted Research](docs/ZERO_COST.md).
Programmatic MCP and A2A details live in [MCP and A2A API](docs/API.md).
Skill-pack generation is covered in [Skill Pack Guide](docs/SKILL_PACK.md).

`primr --check-jobs --json` returns `primr.job-status-list` v1.0. Each row is a
body-free `primr.job-status` v1.0 snapshot with normalized lifecycle, progress,
timestamps, artifact availability, and bounded error metadata. MCP, A2A,
hosted control-plane, and application API status surfaces project the same
contract additively while preserving their legacy fields.

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
| Zero-cost and host-assisted research | [Zero-Cost Research](docs/ZERO_COST.md) |
| API keys | [API Key Setup](docs/API_KEYS.md) |
| Configuration | [Configuration Reference](docs/CONFIG.md) |
| Skill packs | [Skill Pack Guide](docs/SKILL_PACK.md) |
| Agent integration | [Agent Integration](docs/AGENT_INTEGRATION.md) |
| MCP and A2A API | [API Reference](docs/API.md) |
| Job status contract | [Job Status](docs/JOB_STATUS.md) |
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
