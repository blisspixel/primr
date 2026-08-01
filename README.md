# Primr

[![CI](https://github.com/blisspixel/primr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/primr/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/primr.svg)](https://pypi.org/project/primr/)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/blisspixel/primr/badge)](https://securityscorecards.dev/viewer/?uri=github.com/blisspixel/primr)

**Company URL → sourced strategic brief.** Local-first CLI and agent tooling for
discovery, account planning, diligence, and strategy work.

Primr collects public website pages, DNS/recon, hiring signals, and other open
sources, then produces a consultant-style report with confidence labels,
citations, and optional strategy modules. It is meant to complement chat-style
deep research and enterprise CI tools—not replace every research workflow.

<p align="center">
  <img
    src="docs/images/primr-demo.png"
    alt="Illustrative primr CLI session: dry-run cost estimate for ExampleCo, then a completed run writing Strategic Overview Markdown and DOCX artifacts"
    width="920"
    loading="lazy"
  />
</p>

<p align="center"><sub>Illustrative demo with placeholder company data (ExampleCo). Not a live capture of a real target. Regenerated via <code>scripts/render_readme_demo.py</code>.</sub></p>

```bash
primr "ExampleCo" https://example.co
```

In an agent chat, that request defaults to **Primr Zero**: keyless evidence
collection in Primr, research and writing in the host (when the host plan does
not bill API usage). In a terminal, the same command uses the provider-backed
pipeline after a dry-run estimate and your approval.

A full provider-backed run typically yields a multi-section Strategic Overview
(Markdown, TXT, DOCX; best-effort PDF when a converter is present) plus a
business-first AI Strategy unless you pass `--no-ai-strategy`.

## What Primr Is For

Use Primr when you need a serious first draft for discovery, account planning, diligence, competitive analysis, or strategy work.

Primr is built for:

- A structured strategic brief instead of scattered notes.
- Research grounded in public evidence, not only web-search summaries.
- Clear uncertainty: Confirmed, Reported, Estimated, and Hypothesis labels.
- Cost-aware local execution with dry-run estimates before billable work.
- Reusable artifacts for humans, agent hosts, and downstream workflows.

Primr is not a generic crawler, a SaaS collaboration app, a model-serving platform, or a tool for bypassing authentication, paywalls, or site restrictions.

Use normal web search for a quick two-paragraph pre-call brief. Use Primr when
you want the full evidence pipeline and durable artifacts.

## Start Here

The clean request stays the same, but the execution boundary matters:

| Where you make the request | Default path | Spend contract | Primary result |
|---|---|---|---|
| Capable agent chat pointed at Primr | Primr Zero | No Primr model API spend; verify the host uses included plan allowance | Evidence bundle plus a host-written sourced dossier |
| Terminal or script | Provider-backed Primr | Billable; run `--dry-run` and approve the quoted estimate first | Primr-generated Strategic Overview plus strategy artifacts |

Terminal users who want the host-assisted path can run `primr prep` and hand
the published bundle to their agent. Agent users who want the provider-backed
path must ask for it explicitly and approve its fresh estimate.

**Same outputs, however you run it.** Primr meets you where you are — bring API
keys (pricier, can be the highest quality), run on a quota/subscription host
(excellent, `$0` incremental), or stay all-local (improving fast, `$0`
marginal). Every mode produces the same deliverable set: a Strategic Overview
and an AI Strategy, each as Markdown **and** DOCX, plus any optional strategy
modules, scraping corpus, and skill packs. The credential is transport, not a
different product. On the host/Zero path, `primr render <file>.md` converts any
host-written Markdown to DOCX/TXT at `$0` (no model calls), so the artifacts
match a provider-backed run.

### Agent-host path

Point a capable agent at this repository and ask it:

```text
primr "ExampleCo" https://example.co
```

The agent should use Primr Zero unless you explicitly request paid, metered,
provider-backed, or premium execution. It runs `primr prep` internally when a
shell is available, uses its existing research and reasoning surface to build
the dossier, checkpoints the Markdown inside the prep bundle, runs artifact QA
when possible, confirms the report's `primary_report` inventory role, and hands
its exact path to any downstream workflow you request. You do not need to know
or select the internal `prep` command.

If the host has no shell, cannot launch Primr, or cannot install it with your
approval, Primr Zero falls back to host-native web research and discloses which
Primr collection signals were unavailable. It does not block the useful free
path on installation. A configured API key is never treated as permission to
spend. To choose the paid pipeline, say so explicitly, for example: "Run paid
provider-backed Primr, show me the estimate first." The agent must still wait
for approval after showing that estimate.

## Install

Requirements:

- Python 3.12 or newer.
- No model API key or GPU is required for `primr recon` or `primr prep`.
- API keys are required only for provider-backed research. The measured low-cost default uses xAI plus Gemini.
- Browser dependencies installed by `primr init` for browser-backed scraping tiers.

On a sound keyless install, `primr doctor` returns ready with warnings: prep and
recon remain available while provider-backed research is clearly marked
unavailable. Doctor never sends a model-generation request, so its connectivity
section cannot consume model tokens. When a Gemini key is present, the separate
orphaned-resource inventory makes non-generative list requests and labels any
failure as a warning rather than claiming model connectivity.

Install the versioned package with pipx:

```bash
pipx install primr
primr --version
```

Plain pip also works:

```bash
pip install primr
primr --version
```

The convenience installers set up pipx and account for common PATH issues.
Download and inspect the script before executing it.

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

Initialize provider keys and browser dependencies only when you want the
provider-backed pipeline:

```bash
primr init
primr doctor
```

On Windows, use the installer or pipx if `primr` is not found after `pip install`; a bare pip install can place scripts in a user Scripts directory that is not on `PATH`.

## Manual Primr Zero Handoff

If you are operating Primr manually rather than through an agent, prepare a
bounded evidence bundle locally and let a research-capable host do the
synthesis:

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

Prep assembles the bundle privately and publishes the dated directory only
after its manifest is complete. A collection error or interruption leaves no
discoverable partial bundle; a published `partial` status instead means the
bundle is valid but coverage is limited.

Prep also enters through the lightweight CLI path, so previews do not load the
provider-backed command graph. Ctrl-C returns exit code 130 with recovery
guidance. Check the output directory before retrying collection, and inspect an
interrupted skill destination before using it.

Install the packaged skill globally when you do not want a repository copy:

```bash
primr prep --install-skill ~/.agents/skills/primr-zero --dry-run
primr prep --install-skill ~/.agents/skills/primr-zero
```

The install preview performs no network requests and writes no files.

Claude Code uses `~/.claude/skills/primr-zero` instead.

A source checkout already includes synchronized project skills at
`.agents/skills/primr-zero/`, `.claude/skills/primr-zero/`, and
`.claude/skills/primr/`. Supported agent hosts can discover the applicable
guidance directly from the repository.

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
| Default with xAI plus Gemini | Strategic Overview plus one integrated AI Strategy | 34-53 min | ~$0.89 |
| Base report only | Strategic Overview, no AI Strategy | 31-47 min | ~$0.76-$0.79 |
| `primr skills` | Agent Skills pack from company evidence | ~3 min | ~$0.30 |
| `--mode scrape` | Site corpus and extracted insights only | 5-10 min | ~$0.10 |
| `--premium` | Gemini plus Deep Research for maximum depth | 50-75 min | ~$5 |

Costs change with provider configuration, strategy count, cache hits, model pricing, and run mode. Treat `--dry-run` as the source of truth for the next run.
Human dry-runs end with concise launch, monitoring, recovery, and artifact-retrieval steps. Add `--verbose` to inspect the serialized recovery policy, or `--json` to receive one machine-readable estimate object.
`primr skills` generates Cowork icons locally by default; remote image APIs are used only with `--remote-icons`.
Explicit multi-platform strategy fan-out adds time and cost; for example, two
strategy artifacts are typically about $1.01 and 37-59 minutes with xAI plus
Gemini. Cached vendor research is reused when present. Current product claims
and names must be supported by official evidence; when that evidence is not
available to a run, the strategy must leave the claim unasserted and name the
evidence gap and validation action. AI news (vendor research) defaults to a
grounded-lite engine (~$0.30): a single Gemini call with live Google Search
grounding, cited from current sources rather than stale model memory.
`--refresh-vendor-research` is freshness-aware — it reuses cached briefs newer
than the freshness window and regenerates only stale or missing ones, so an
integrated run does not pay to rebuild fresh research. The heavyweight Deep
Research engine (~$2.50/task) is opt-in via `--deep-research`.
`primr --generate-vendor-research` is the deliberate direct
cache-generation command. It quotes the aggregate tasks, cost, and time before
execution, supports zero-call `--dry-run` and `--budget`, and requires an
interactive confirmation unless `--skip-confirm` explicitly approves a
noninteractive run. Targets include Azure, AWS, GCP, private accelerated
infrastructure, vendor-neutral research, or all five together. Estimate-bound
CLI and MCP strategy paths never turn the ambient `PRIMR_ALLOW_VENDOR_REFRESH`
setting into unquoted provider work.
Integrated runs preserve a completed Strategic Overview when a requested
strategy artifact or explicit refresh target fails, but they do not report full
success. The run state and `--json` result separate base-report status from
`strategy_status` and `vendor_refresh_status`, list completed, failed, and
budget-skipped targets, and the CLI returns nonzero for partial fulfillment.
Machine results keep `status` as the base-artifact status and add
`fulfillment_status` as `completed`, `partial`, `failed`, or `unknown`; callers
must use the latter for whole-request success. Missing or malformed outcome
state fails closed as `unknown`. Human handoffs and `primr --check-jobs` name
unresolved targets and the exact state record. Actual-cost summaries include
every provider task that reached submission, including standard-route AI
Strategy and refresh tasks, through run-local accounting that remains correct
when runs overlap. Separate vendor-refresh usage records are not duplicated.
Standalone strategy automation uses a separate machine contract:
`--dry-run --json` emits one `primr.strategy-estimate.v1` object, while approved
execution with `--json --skip-confirm` emits one `primr.strategy-result.v1`
object with expected, successful, and failed targets. JSON execution without
`--skip-confirm` returns one structured approval-required refusal and never
opens an interactive prompt.
PDF text extraction uses local PyMuPDF by default; Gemini PDF extraction is opt-in with `PRIMR_PDF_LLM_MAX_CALLS=N`.

`primr --help`, `primr init --help`, and `primr doctor --help` show focused
one-screen guidance. Use `primr --help-all` for every command and advanced
option. Version and focused help use a lightweight entry path, so they do not
load the research pipeline or initialize logs, output, and working directories.

See [Run Modes and Costs](docs/RUN_MODES.md) for the full mode matrix, platform selection, strategy types, premium modes, and output examples.

## Choose a Command

| Need | Command |
|------|---------|
| Full host-assisted dossier from an agent chat | `primr "Company" https://company.com` |
| Keyless evidence bundle for an existing agent plan | `primr prep "Company" https://company.com` |
| Estimate the next run | `primr "Company" https://company.com --dry-run` |
| Standard Strategic Overview plus AI Strategy | `primr "Company" https://company.com` |
| Strategic Overview only | `primr "Company" https://company.com --no-ai-strategy` |
| Separate Microsoft and private-infrastructure strategy artifacts | `primr "Company" https://company.com --platform ms` |
| Enable routed utility-stage pilot (single-company; may meter host billing) | `primr "Company" https://company.com --inference hybrid --acknowledge-host-agent-may-bill` |
| Site corpus and extracted insights only | `primr "Company" https://company.com --mode scrape` |
| DNS intelligence only, no model keys required | `primr recon company.com` |
| Agent Skills pack for downstream hosts | `primr skills "Company" https://company.com` |
| Convert a Markdown report to DOCX/TXT (zero cost, no model calls) | `primr render "output/report.md"` |
| Quote website enrichment without starting it | `primr --batch "companies.csv" --enrich --dry-run` |
| Quote a whole research batch without starting it | `primr --batch "companies_enriched.csv" --dry-run` |
| Quote a strategy from an existing report (~$1 lite by default; `--deep-research` for thorough) | `primr --ai-strategy-only "output/report.md" --dry-run` |
| Client-facing deliverables in a chosen folder | `primr "Company" https://company.com --output-dir "C:\Clients\Company"` |

For agent-host operation, a bare Primr request defaults to Primr Zero and does
not need a spend-approval pause. An explicitly paid request follows the full
lifecycle: estimate, show the cost and mode, get explicit approval, launch,
monitor asynchronously, then read the output artifact before summarizing it.
See [Agent Integration](docs/AGENT_INTEGRATION.md).

## Cost and Safety Contract

Primr treats spend and egress as explicit control surfaces:

- `--dry-run` is the source of truth for the next run estimate.
- `--budget N` refuses to start when the estimate exceeds the cap.
- Batch research quotes and gates the whole pending batch, never performs a
  hidden website lookup, and does not automatically retry paid company runs.
  `--enrich` is a separate quoted operation that pins its model, disables
  provider failover and retries, and requires approval before lookups.
- Standalone strategy generation emits its own estimate, requires approval,
  and uses a private content-digest-verified snapshot of a report contained in
  `output/` or `working/`. `--dry-run` starts no model calls.
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
- Optional strategy modules for AI, customer experience, security, data fabric, and skills.

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
MCP and A2A doctor responses expose only body-free audit-sink state such as
`not_observed`, `ok`, or `degraded`, recent write/read outcomes, malformed-event
count, and bounded-tail state. They never expose the audit path, event bodies,
URLs, caller ids, or exception messages.
Audit events normalize registered tool, scope, and resource labels, hash
unrecognized identifiers, reject oversized records, and return only events that
match the explicit versioned audit schema. Additive persisted fields are not
returned. Audit reads and writes reject symbolic-link targets, and sink health
reports replacement or truncation after a successful write.

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
| `AZURE_OPENAI_API_KEY` | Optional Azure AI Foundry provider (with `AZURE_OPENAI_BASE_URL`) |
| `AWS_BEARER_TOKEN_BEDROCK` | Optional AWS Bedrock provider (or the AWS credential chain; needs `primr[bedrock]`) |
| `OLLAMA_BASE_URL` | Optional local OpenAI-compatible endpoint for local eval and utility paths |

`primr keys test` validates any configured provider credential with a live check.

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
