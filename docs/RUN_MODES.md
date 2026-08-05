# Run Modes and Costs

This guide explains how to choose a Primr run mode, estimate cost, and understand which artifacts each command produces.

Always run `--dry-run` before billable work:

```bash
primr "Company" https://company.com --dry-run
```

Dry-run output is the source of truth for the next run. The numbers below are current guideposts for the common xAI plus Gemini setup, not guarantees.

Except for the Primr Zero row, this matrix describes direct terminal execution
through Primr's provider-backed pipeline. A bare request in a capable agent
chat defaults to Primr Zero; the same text entered in a terminal retains the
provider-backed behavior.

## Mode Matrix

| Mode | Command shape | Output | Typical time | Typical cost |
|------|---------------|--------|--------------|--------------|
| Primr Zero in an agent host | Ask the host: `primr "Company" url` | Keyless evidence bundle plus host-written dossier | 5-15 min collection, then host-dependent | $0.00 incremental model API spend when the host is plan-backed |
| Provider-backed default | `primr "Company" url` in a terminal | Strategic Overview plus one integrated AI Strategy | 34-53 min | ~$0.89 |
| Base report only | `primr "Company" url --no-ai-strategy` | Strategic Overview | 31-47 min | ~$0.76-$0.79 |
| XAI-only default | `primr "Company" url` with no Gemini key | Strategic Overview plus one integrated AI Strategy | 34-53 min | ~$5.06 |
| XAI-only base | `primr "Company" url --no-ai-strategy` with no Gemini key | Strategic Overview | 31-47 min | ~$4.36 |
| Scrape | `primr "Company" url --mode scrape` | Site corpus plus insights | 5-10 min | ~$0.10 |
| Deep | `primr "Company" url --mode deep` | Deep Research plus hiring signals | 11-17 min | ~$2.50 |
| Premium | `primr "Company" url --premium` | Deep Research plus hiring signals plus strategy | 50-75 min | ~$5 |
| Premium lite | `primr "Company" url --premium --lite` | Premium strategy with lighter model path | 50-80 min | ~$4 |
| Recon | `primr recon company.com` | DNS intelligence | 2-3 sec | $0.00 |
| Render | `primr render <file>.md` | DOCX + TXT from existing Markdown | <5 sec | $0.00 |
| Skill pack | `primr skills "Company" url` | Agent Skills tree plus Cowork zip | ~3 min | ~$0.30 |

## First useful output (while a long run is still going)

Long provider-backed runs can take half an hour or more. Primr already has
earlier, honest signals you can use without waiting for the full Strategic
Overview:

| When | What to run or watch | Notes |
|------|----------------------|--------|
| Seconds | `primr recon company.example` | DNS / tenant / email-security signals, $0 model |
| Minutes | `primr prep "Company" url` | Keyless evidence bundle for host-assisted synthesis |
| Mid-run | Working folder + **working brief** | After scrape (+ hiring refresh): free, incomplete brief |
| End of run | Strategic Overview + optional AI Strategy | Primary deliverables |

**Layer 1 working brief (shipped):** after collection on the **fast path** and
on **structured/deep Phase 1** (premium/complete data collection), Primr writes
a deterministic incomplete brief (no extra model calls) to
`working/<run>/working_brief.md` and a dated public
`<Company>_Working_Brief_<date>.md` under the run’s `output_dir` (or default
`output/`). Pure `--mode deep` without a structured scrape may have no brief.
Loud banner: not the Strategic Overview. Inventory role: `working_brief`
(never `primary_report`). MCP job status includes body-free
`early_artifact_paths`. Design:
[`design/progressive-artifacts.md`](design/progressive-artifacts.md).

## Default Provider Recipe

When both `XAI_API_KEY` and `GEMINI_API_KEY` are configured, Primr uses:

- Grok for reasoning-heavy stages.
- Gemini for bulk writing and utility stages.
- DuckDuckGo search by default, which does not require a search API key.

This measured recipe is much cheaper than the older xAI-only path while preserving the trust gate used in evaluation. XAI-only runs still work and keep the legacy writing and utility path.

OpenAI, Anthropic, and local OpenAI-compatible endpoints are wired into the provider layer for fallback, utility, evaluation, and planned backend-freedom routing. Full-report execution still uses the supported direct provider path described in [API Key Setup](API_KEYS.md).

## Inference Profiles

`--inference cloud` is the default and preserves the validated direct-provider
path. `--inference hybrid` enables the backend-freedom utility-stage pilots:
`fast.scrape_summary`, `fast.source_relevance`, and `fast.hiring_signals`
resolve their legacy utility models through the capability router, log safe
route metadata, append body-free `stage_routes` entries to `_run_state.json`,
and then execute through existing provider seams. The public CLI exposes only
`cloud` and `hybrid`.

`fast.source_relevance` also has an unpromoted, experimental Codex CLI route.
It remains disabled unless a single-company command includes both
`--inference hybrid` and `--acknowledge-host-agent-may-bill`. Codex CLI
authentication does not tell Primr whether a session uses plan allowance or
metered billing, so the route is recorded as `potentially_metered`; its unknown
host charge is excluded from `--dry-run` totals and `--budget`. The route uses
a read-only sandbox with web search and shell tools disabled. If no runner
qualifies, hybrid keeps the already-estimated cloud baseline. If a selected
host execution fails, source filtering keeps all sources without making a
second cloud call. This explicit pilot has not cleared its hybrid-vs-cloud
promotion eval and is not a validated default. Batch use is rejected. Use
`primr-zero` inside a verified plan-backed host for the supported plan-native
path. Local profiles remain unexposed until stage adapters and evals clear the
promotion bar.

## Strategy Generation

The default command includes AI Strategy. Disable it when you only need the Strategic Overview:

```bash
primr "Company" https://company.com --no-ai-strategy
```

Platform targeting:

```bash
primr "Company" https://company.com --platform ms
primr "Company" https://company.com --platform aws azure
```

`--platform ms` explicitly expands to `azure private`, creates two strategy
artifacts, and must be estimated as a two-platform run. Use `--platform azure`
when only a Microsoft ecosystem emphasis is intended.

When `--platform` is omitted, Primr runs DNS recon first. No strong
infrastructure signal produces one vendor-neutral AI Strategy. One strong
ecosystem signal emphasizes that ecosystem in one strategy. Multiple strong
ecosystem signals produce one integrated vendor-neutral strategy so the user
does not receive an accidental artifact fan-out. Explicit multi-platform input
still creates separate strategy artifacts and must be included in the estimate.

The default AI Strategy starts with business economics, an enterprise
performance agenda, strategic tensions, industry direction, and value pools. It
tests how AI could defend the core, improve operations, extend products and
services, or create new business models before selecting technology. It then
builds a prioritized portfolio and connects each initiative to measurable
business outcomes, the complete observed technology and service stack, fully
loaded unit economics, operating ownership, governance, and workload placement.
Every initiative includes a non-AI alternative and opportunity cost. Every
material observed ecosystem receives an explicit disposition rather than being
silently omitted. Public cloud, multicloud, private or on-premises accelerated
infrastructure, edge, and hybrid options are evaluated when the workload makes
them material. A platform flag is an evaluation emphasis, not permission to
ignore other detected ecosystems or skip credible alternatives.

Strategy types are YAML-defined and discovered at runtime:

```bash
primr --list-strategies
primr "Company" https://company.com --strategy-type customer_experience
```

Current selectable strategy documents include AI, customer experience, modern
security and compliance, data fabric, and skills. Use `primr skills` for the
skills pack workflow. `primr --list-strategies` is the installed source of
truth; historical or placeholder YAML files are not selectable strategies.

MCP `generate_strategy` is a standalone post-report path backed by one Gemini
Deep Research task per document. Its current planning estimate is about $2.50,
including when `strategy_type="skills"`; call `estimate_strategy` for the live
value. This differs from the fast in-pipeline YAML writer and from the
QA-refined `primr skills` pack workflow shown in the mode matrix.

## Cost Controls

Use the built-in control path:

```bash
primr "Company" https://company.com --dry-run
primr "Company" https://company.com --budget 1.25
primr show-usage
```

### Authorization floor (CLI and MCP)

CLI dry-run, `--budget`, and launch quotes use the same shaping kwargs as
execution. The dollar ceiling is **`max(planning defaults, historical averages)`**
when enough samples exist — the same rule MCP/A2A already applied — so a few
cheap past runs cannot under-approve a full recipe. Unknown estimator modes
fail closed (they raise); product aliases such as `full` / `deep` / `scrape`
map to internal mode names.

### Dual-provider dry-run honesty

OpenAI- or Anthropic-only keys (or no XAI/Gemini keys) can still produce a
full-mode **planning** quote. That quote is the XAI/Gemini full-recipe floor,
not OpenAI/Anthropic live rates. Dry-run labels say estimate-only / keys
required; `--dry-run --json` sets `execution_ready: false` and next steps
point at configuring `XAI_API_KEY` or `GEMINI_API_KEY` before launch. Full
execution preflight still refuses without XAI or Gemini.

### Experimental `primr orchestrate`

```bash
primr orchestrate "Company" https://company.com --dry-run
primr orchestrate "Company" https://company.com --max-cost 5.0
```

Always prices first. Launch requires estimate ≤ `--max-cost` or interactive
`[y/N]` yes (then a runtime CostGuardHook at estimate + 25%). Invalid or
empty URLs fail closed after scheme normalization.

Cost behavior:

- Dry-run estimates the run before model calls.
- `--budget` refuses to start if the estimate exceeds the cap.
- Fast full-report runs also consult runtime budget checkpoints before optional stages.
- Premium, deep, and non-fast complete or hybrid runs checkpoint before and between optional strategy documents after the required Deep Research task completes.
- Required Deep Research tasks cannot be stopped mid-flight by `--budget`; scrape remains estimate-gated only.
- MCP HTTP tools can enforce server-side cost caps and approval tokens.
- Vendor-research generation (AI news) is freshness-aware and explicit: cached
  research is reused, but missing or stale cache files do not trigger a fresh
  refresh in estimate-bound runs unless you pass `--refresh-vendor-research`.
  The default refresh engine is grounded-lite (~$0.30, one Gemini plus Google
  Search grounded call, live and cited); `--deep-research` restores the thorough
  Deep Research engine (~$2.50/task). Dry-run and budget output then include one
  separate refresh task per selected platform. Use
  `primr --generate-vendor-research <vendor> --dry-run` to quote deliberate
  direct cache generation. The direct command aggregates `all` targets, honors
  `--budget`, requires confirmation unless `--skip-confirm` is supplied, and
  returns nonzero if any requested target fails. `all` covers Azure, AWS, GCP,
  private accelerated infrastructure, and vendor-neutral research.
  Ambient `PRIMR_ALLOW_VENDOR_REFRESH` applies only to direct library callers
  that leave policy environment-controlled; integrated CLI and MCP strategy
  paths override it off.
- A fast run with `--refresh-vendor-research` preflights both XAI and Gemini
  credentials before starting the base pipeline. Multi-platform refresh tasks
  run serially, then the strategy-writing calls fan out in parallel.
- Local dependency and configuration checks run before the cost gate. Network
  connectivity checks run only after the estimate is within `--budget`, so a
  refused run cannot make provider requests.
- A completed base report and requested strategy artifacts have separate
  outcomes. If any explicitly requested strategy or refresh target fails or is
  budget-skipped, the report remains available, the run state and JSON result
  list each target outcome, and the CLI returns nonzero instead of hiding the
  partial result. JSON `status` describes the base artifact while
  `fulfillment_status` describes the whole request. Missing or malformed
  outcome state produces `fulfillment_status: unknown` and a nonzero exit.
  Human completion output and `primr --check-jobs` surface unresolved targets
  and the state path. Local monitoring also requires a canonical completed
  lifecycle and internally consistent outcome partitions before it reports
  completed fulfillment. Standalone multi-platform strategy generation follows
  the same all-target success rule.
- Fast, deep, complete, hybrid, and standard summaries reconcile refresh tasks
  that actually reached provider submission. Standard mode also includes its
  AI Strategy Deep Research task. AI Strategy and refresh counts are run-local,
  so overlapping runs cannot claim one another's submissions. Refresh usage is
  not duplicated in the main run history because each submitted refresh
  records its own usage row.
- The legacy non-fast `structured` runtime supports one AI Strategy platform.
  It rejects custom strategy types and multiple explicit platforms before any
  provider preflight; use complete mode or XAI fast mode for those shapes.
- Gemini PDF extraction is off by default and local PyMuPDF parsing is used
  instead. Set `PRIMR_PDF_LLM_MAX_CALLS=N` only when provider-backed PDF chart
  and table extraction is worth the extra spend.
- `primr skills` emits local Cowork icons by default. Remote image generation
  requires `--remote-icons` or MCP `remote_icons=true`, and the estimate
  includes a conservative image allowance only when that opt-in is set.
- `primr show-usage` ends with a per-mode "Cost Variability" section: it
  compares each mode's recent runs against its prior history (average cost,
  spread, and cache hit rate) and prints a report-only SIGNAL line when
  recent runs cost more or cache less than history. It never blocks a run;
  it surfaces continuous-reasoning or prompt-cache regressions that would
  otherwise erode the sub-$1 default silently.

### Batch and Standalone Cost Gates

Batch research and website enrichment are separate governed operations:

```bash
primr --batch "companies.csv" --enrich --dry-run
primr --batch "companies_enriched.csv" --dry-run
```

Enrichment quotes only rows missing a website. It performs no search or model
call before approval, pins the quoted utility model, disables retries and
provider failover, and writes a reviewable CSV. Batch research requires a
website for every pending company, quotes the entire pending batch, applies
`--budget` to that total, runs local-only preflight after approval, and never
silently retries a paid company run. Machine-readable `--json` is supported for
these dry-run plans and emits exactly one JSON object.

Standalone strategy recovery has its own gate:

```bash
primr --ai-strategy-only "output/report.md" --dry-run
```

`--ai-strategy-only` defaults to the ~$1 Pro-model lite engine (2-3 min); add
`--deep-research` to restore the thorough Deep Research engine (~$2.50/task).
The estimate reflects the selected engine.

Without `--dry-run`, Primr emits the same estimate and asks for approval before
it creates a private content-digest-verified report snapshot. A report changed
during approval is rejected before strategy generation. Normal full Strategic
Overviews are retained in strategy context up to a 200,000-character bound.
For automation, `--dry-run --json` emits one `primr.strategy-estimate.v1`
object. Approved `--json --skip-confirm` execution emits one
`primr.strategy-result.v1` object with expected targets, successful artifacts,
and failures. JSON execution without `--skip-confirm` returns a structured
approval-required refusal and never prompts.

## Output Locations

Default output:

```text
output/
working/<company>/<timestamp>/
```

Deliverables write flat into `output/` with the company name in each filename;
there is no `output/<company>/` subfolder.

Common files:

```text
<Company>_Strategic_Overview_<date>.md
<Company>_Strategic_Overview_<date>.docx
<Company>_AI_Strategy_<date>.md
run_manifest.json
scraped_content.txt
insights.json
dossier.json
```

Use `--output-dir` when you want client-facing deliverables in a specific folder:

```bash
primr "Company" https://company.com --output-dir "C:\Clients\Company"
```

With a custom output directory, Markdown and DOCX deliverables go there. TXT mirrors and validation diagnostics stay in the run diagnostics folder.

### Rendering existing Markdown

`primr render <file>.md` exposes the internal renderer for host-written or
Primr-Zero Markdown. It writes a `.docx` (plus a `.txt` unless `--no-txt`)
beside the source file, or into `--output-dir` when given, with no model calls
or network access. Use `--title` and `--subtitle` to set document metadata.

## Example Run

```text
Grok 4.3 hybrid, recon auto-detected Azure

PHASE 0/6: Recon
Done: 14 services, 8 insights, platform azure

PHASE 1/6: Data collection
Done: 251 links, 50 selected
Done: 48 of 50 pages scraped
Done: 31 external sources

PHASE 2/6: Research deepening
Done: 8 gaps identified, 12 additional sources

PHASE 3/6: Analysis
Done: structured workbook built

PHASE 4/6: Report writing
Done: 23 sections, 21,500 words

PHASE 5/6: Cross-validation
Done: 3 contradictions resolved
Trust: PASS, citations clean
Label Citations: 34/36 Confirmed/Reported cite a source

PHASE 6/6: AI Strategy
Done: strategy generated

Complete in 38m
output/ExampleCo_Strategic_Overview_04-10-2026.docx
PASS, 23 chapters, 48 citations, about $0.89
```

## Related Docs

- [API Key Setup](API_KEYS.md)
- [Configuration Reference](CONFIG.md)
- [Artifact Pipeline](ARTIFACTS.md)
- [Evaluation Guide](EVAL.md)
- [Skill Pack Guide](SKILL_PACK.md)
