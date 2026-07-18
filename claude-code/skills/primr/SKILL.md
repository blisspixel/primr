---
name: primr
description: Route and run Primr company research from an agent host. Use for a bare Primr company-and-URL request, named Primr report, full strategic dossier, Strategic Overview, or strategy module. Default to Primr Zero unless the user explicitly requests paid, metered, provider-backed, or premium execution; use an inline primr prep fallback when primr-zero is unavailable. Route quick briefs to host web research and DNS-only requests to primr recon.
argument-hint: '"Company Name" https://company.url [explicit paid pipeline modifiers]'
allowed-tools: Bash(primr:*), Bash(uv run --no-sync primr:*), Read, Write, Edit, Glob, Grep, WebSearch, WebFetch
---

# primr

Route Primr research without making the user learn its internal commands.
Primr Zero combines deterministic Primr collection with the current agent
host's research and reasoning. The provider-backed pipeline adds Primr-managed
model synthesis, cross-validation, strategy generation, and rendering after an
estimate and explicit spend approval. Both aim for useful strategic artifacts;
the host-powered path is not a renamed scrape mode or a deliberately worse
application.

The declared tool surface covers both routes: narrowly scoped Primr shell
commands for collection and provider-backed operation, plus host-native web
research and artifact editing for the no-launcher Zero fallback. Normal host
permissions and workspace boundaries still apply.

## Agent-host default

When a request is addressed to an agent host, keep the public invocation
simple:

```bash
primr "Company" https://company.example
```

Treat that bare company-and-URL request, "run Primr," and "build a full
dossier" as **Primr Zero by default**. Use the `primr-zero` skill and run
`primr prep` internally when a shell is available. Do not make the user choose
between `prep`, `scrape`, and `full`, and do not ask for spend approval for the
zero-model-call collection. Disclose its public network activity, then
continue.

Route to the provider-backed pipeline only when the user explicitly asks for
paid, metered, provider-backed, or premium Primr; supplies a dollar budget;
asks to use provider API keys; or provides provider-only CLI modifiers such as
`--premium`, `--mode`, `--platform`, `--strategy-type`, or
`--no-ai-strategy`. Configured API keys are capability, not consent to spend.

This is an agent-routing rule, not a CLI compatibility change. When a human
runs `primr "Company" https://company.example` directly in a terminal, the
existing provider-backed CLI behavior remains unchanged and requires the
normal estimate and approval discipline.

## When this is the right tool

Use Primr Zero when the user wants substantial Primr research without explicit
provider-spend intent:

- "Run Primr on ExampleCo" / "primr ExampleCo https://example.co"
- "Build me the full strategic dossier for ExampleCo"
- "Use this repository to research ExampleCo"
- "Build the fullest dossier you can for $0 using my existing agent plan"

Use the provider-backed pipeline when paid intent is explicit:

- "Run the paid Primr pipeline on ExampleCo"
- "Use my provider API keys after showing me the estimate"
- "Run premium Primr with a budget of $5"
- "Generate the paid AI strategy module for the ExampleCo report"
- "Refresh ExampleCo with the provider-backed pipeline"

**Do not** use primr for:

- A quick pre-call brief with no API budget - use the host's built-in web search and reasoning. primr is wrong for "give me two paragraphs on Acme."
- DNS / tenant / email-security only - use `primr recon company.com`, which is
  keyless and standalone. A host-native passive lookup is also fine when Primr
  is not installed.
- Reviewing an existing primr report's quality - still primr (`run_qa` MCP tool or `primr --qa <company>` CLI), but invoke that path directly without estimating a new run.

If the user is ambiguous ("research ExampleCo"), use the host's normal quick
research path. If the user names Primr or points the agent at this repository,
use the Agent-host default above. A vague research request must never trigger
billable Primr.

## Before first invocation

Resolve a working Primr launcher before the first call in a session. For Primr
Zero, provider configuration is irrelevant:

```bash
primr --version
```

If the current workspace is a Primr source checkout and `primr` is not on
`PATH`, try `uv run --no-sync primr --version`. When that succeeds, use
`uv run --no-sync primr` anywhere these instructions show `primr`. If neither
launcher works during Primr Zero, continue with the host-native research
fallback when the host can search the web. You may offer installation, but do
not block useful work on it and do not install or sync an environment without
approval. A provider-backed request does require a working Primr installation.

Before a provider-backed run, also check its configuration:

```bash
primr doctor
```

For an explicitly provider-backed request where Primr is not installed:

> "Primr isn't installed. It's a Python CLI from github.com/blisspixel/primr. For this provider-backed run, use `pipx install primr` on Python 3.12+, then run `primr init`. Want me to walk through it?"

Wait for explicit approval before running `pip install`. For Primr Zero, if
installation is declined or unavailable, proceed with the host-native fallback
and disclose the unavailable Primr collectors. If `primr doctor`
reports missing keys, do not attempt to set them yourself. Missing keys block
provider-backed research, but they do not block `primr prep` or `primr recon`.

## Detecting MCP vs CLI

Choose Primr Zero versus provider-backed execution before choosing transport.
Primr Zero collection uses `primr prep`; never call a billable MCP research
tool as a substitute. For an explicitly provider-backed request, look at your
available-tools list:

- If you see `mcp__primr__*` tools (`mcp__primr__estimate_run`, `mcp__primr__research_company`, etc.) → **prefer MCP**. It returns structured objects, exposes job state via resources, and the cost gate is enforced server-side.
- Otherwise → fall back to the `primr` CLI. Same workflow, file-based artifacts.

Do not call an MCP tool speculatively to test connectivity. To get from CLI-only to MCP, the user adds primr to their host's MCP config (the snippet is `{ "command": "primr", "args": ["mcp"] }`; see the `clients/` directory in the primr repo for per-host paths).

## Zero-cost host handoff (precedes billable modes)

Treat a bare Primr company-and-URL request in an agent host, any request for a
free version, zero cost, no API key or API spend, or use of an existing Claude,
Codex, Copilot, Gemini, Cowork, or other agent plan as a request for **Primr
Zero**. This routing decision takes precedence over the billable cost gate and
applies even after a paid estimate was shown, declined, or cancelled. Stop the
paid workflow before continuing. Never answer "there is no free tier": the
provider-backed Primr pipeline has no free mode, but Primr Zero is a supported
workflow.

Tell the user that Primr Zero uses keyless `primr prep` collection with zero
Primr model calls, followed by research and synthesis in the current agent
host. Only describe the complete workflow as zero incremental spend after
verifying that the host is plan-backed and will not bill API usage or
overages.

If the dedicated `primr-zero` skill is available, use it. If it is unavailable,
stale, or cannot be loaded from the current skill, do not deny the free path or
stall. With shell access, follow this inline fallback:

```bash
primr --version
primr prep "Company" https://company.example --dry-run
primr prep "Company" https://company.example
```

The dry run must report `$0.00` and zero model calls. The real command performs
public network requests, emits a bounded evidence bundle and portable skill,
and fails closed against model egress even when keys are configured. Disclose
the network activity, but do not require spend approval for this zero-dollar
collection. Read the emitted `prep_manifest.json`, `source_index.json`,
`research_packet.md`, and `HOST_WORKFLOW.md` in that order, then follow the
emitted `primr-zero/SKILL.md` for host research, writing, and QA. Never pass
host OAuth tokens or cookies into Primr, and never switch to a paid run
silently.

Without shell access, or when the Primr launcher is unavailable and installation
is declined or cannot proceed, use the host's supported web research and file
tools to follow the same Primr Zero report contract. Do not stall on the missing
launcher. Disclose that Primr DNS, browser-backed collection, ATS adapters,
scrape traces, and local artifact QA were unavailable. If the host cannot
research the web, ask for a prep bundle or source files instead of writing from
model memory.

`--mode scrape` is still a billable provider-backed mode, typically around
`$0.10`. It is not Primr Zero and must not be presented as the free or cheapest
available path when the user asked for `$0`.

## The billable cost gate (non-negotiable)

primr runs cost real money and real time. **Never** launch a run without:

1. **Estimating first.** MCP integrated research: `estimate_run(company_url=..., mode=..., platforms=[one_platform], strategy_type="ai")`. Additional platforms and non-AI modules use `estimate_strategy` plus `generate_strategy` after the base report. CLI: append `--dry-run` to the exact command you intend to run. For an existing report, use `primr --ai-strategy-only REPORT --dry-run`; execution repeats the quote and still requires explicit approval.
2. **Reporting the estimate** verbatim - quoted dollars and minutes, plus what mode and what strategy.
3. **Getting explicit user approval** in the conversation. "Want me to launch it?" → wait for "yes" / "go" / equivalent. A user asking *"how much would it cost"* is **not** approval.

If the user pushes back on cost or asks whether a free version exists, offer
the Primr Zero route above first. Only if they explicitly prefer a cheaper
provider-backed run should you suggest `scrape` (~$0.10) or
`--no-ai-strategy` (around ~$0.76-$0.79 on the measured xAI plus Gemini
recipe), then re-estimate. If they want premium depth, surface `--premium`
(~$5) and re-estimate.

The MCP server enforces this gate via `primr://agent/governance`; the CLI does not, so on CLI you are the gate.

The presence of a configured provider API key never satisfies approval. Paid
intent chooses this path; the estimate and explicit approval authorize the
specific run.

## Provider-backed workflow

1. **Estimate.** `estimate_run` (MCP) or `primr "Name" url --dry-run [flags]` (CLI). Capture the cost, time, page count, planned strategy.
2. **Approve.** Quote the estimate, ask for go-ahead. Stop. Do not proceed without an explicit "yes."
3. **Launch.** MCP: `research_company(company_name=..., company_url=..., mode=..., platform=..., destination=...)` → returns `job_id`. CLI: drop `--dry-run` and run the same command. Note the `job_id` or output directory.
4. **Don't block.** Runs take 35-120 minutes. Tell the user the job is running and what file path will hold the report. Do not poll synchronously in a loop.
5. **Resume on next turn.** When the user comes back ("is the Acme report done?"), check `primr://research/status` or `check_jobs` (MCP), or look for the markdown file at `output/<company>/<Company>_Strategic_Overview_<MM-DD-YYYY>.md` (CLI). If still running, report the stage and `stage_progress_percent`.
6. **Confirm completion, then hand off.** If using MCP, read `primr://output/artifacts/by_job/{job_id}` first to list the owned job's artifacts without loading report body content. If QA ran, read `primr://output/qa_summary/by_job/{job_id}` for compact score/status/count metadata. Read `primr://output/usage_summary/by_job/{job_id}` when you need cost, timing, approval, or artifact-count metadata without loading the full manifest. Read `primr://output/source_summary/by_job/{job_id}` when you need citation/source appendix counts, domains, missing citations, or duplicate URL metadata without loading report body content. Read `primr://output/trace_summary/by_job/{job_id}` when you need scrape trace health, tier attempts, latency, block, HTTP status, or validation metadata without loading URLs, raw trace entries, or page content. Read `primr://output/verification_summary/by_job/{job_id}` when you need claim verification trust score, claim counts, status counts, first-party downgrade counts, or source-reference counts without loading raw claims, source URLs, search queries, explanations, or report body content. Read `primr://output/calibration_summary/by_job/{job_id}` when you need label-calibration counts, evidence-review count buckets, judge provenance, or judge-agreement metadata without loading raw claims, source URLs, evidence reviews, rationales, or report body content. MCP resource reads and A2A skill calls are audit-logged without raw URI query values, raw resource bodies, raw message text, raw results, or caller ids. Then read the report path or preview needed for the handoff. Do NOT dump the full report into the conversation - it's ~21k words. Summarize the executive summary, list the section count, and offer downstream actions (see [references/downstream-handoff.md](references/downstream-handoff.md)).

## Mode, tier, platform, strategy

primr exposes four orthogonal levers. Default is `full` mode, recon-driven platform selection, default `--grok-tier`, and the built-in AI Strategy module unless `--no-ai-strategy` is passed.

For the full decision matrix - when to pick each, cost and time per combination, multi-platform behavior - see [references/modes-and-strategies.md](references/modes-and-strategies.md). One-liner heuristics:

- **Mode**: `full` for almost everything. `scrape` if external research isn't needed. `deep` if the site is blocked. `premium` only when the user asks for board-grade depth.
- **Platform**: omit unless the user requests an ecosystem emphasis. Use `--platform azure`, `--platform aws`, `--platform gcp`, or `--platform private` for one strategy. `--platform ms` is the explicit `azure private` shorthand and produces two artifacts, so re-estimate it accordingly. The flag affects the AI strategy module, not the core report.
- **Strategy type**: omit for the default Strategic Overview plus AI Strategy. Pass `--no-ai-strategy` for the base report only. Use an active type reported by `primr --list-strategies` or `primr://strategies/available`, such as `customer_experience`, `modern_security_compliance`, or `data_fabric_strategy`. Use `primr skills`, not `--ai-strategy-only`, for the Skills pack workflow.

## Custom strategies

primr discovers any YAML file dropped into `<install>/prompts/strategies/` (or the user's override path). Author one when the user wants a recurring deliverable that doesn't fit the built-ins (e.g., "FinOps assessment for retail clients", "M&A integration playbook").

For the schema and a worked example, see [references/custom-strategy-yaml.md](references/custom-strategy-yaml.md). Keep custom strategies in version control; do not edit a built-in YAML in place.

## Async monitoring

Long runs are the common case. Pick the lightest async pattern your host supports - never poll synchronously in a tight loop.

**Preferred, in rough order:**

1. **Background launch with completion notification.** If your host can run a command in the background and notify you when it exits, use that to launch primr. You get one event ~45 min later when the run finishes. This is the cleanest pattern.
2. **Stream phase markers from the log.** If your host can tail a file and emit one event per matching line, watch the run log for the phase boundaries (`PHASE`, `Complete`, `Error`) - about 6-8 events across a full run. Right density for "is it making progress?" without polling noise.
3. **Schedule a single early sanity check at ~5 minutes.** Most failures (rejected key, scrape pilot fails, no external sources) surface in the first phase. A one-shot check at +5min catches those before the user wastes 45 minutes.
4. **Fallback (no async primitives at all).** Tell the user "I'll check back in about an hour" and stop. When the next turn arrives, read state first (`check_jobs` / `primr://research/status` / the report file at `output/<company>/<Company>_Strategic_Overview_<MM-DD-YYYY>.md`), then summarize.

**On every follow-up turn, regardless of how you got there:** read state first. Never claim done until the report file exists *and* `check_jobs` reports `status: completed`. On failure, read `primr://output/manifest/latest` if available - it contains the audit trail (estimate, approval, execution, error). Surface the failure cause; do not silently re-launch.

**What not to do:**

- Don't poll in a tight loop or with sub-minute sleeps. primr stages take minutes; sub-minute polling burns context for no information.
- Don't promise a heartbeat cadence the host can't actually deliver. If you can't schedule wake-ups, "check back in an hour" is honest; "I'll update you every 10 minutes" is not.
- Don't treat the absence of completion as failure. A run that's been going 60 minutes is probably fine; check the log for the most recent phase marker before assuming the worst.

## Output handling

Reports land in `output/<company_slug>/`:

- `<Company>_Strategic_Overview_<date>.md` - primary deliverable
- `<Company>_AI_Strategy_<date>.md` - only if `--strategy-type ai` (or another module) was selected
- `scraped_content.txt`, `insights.json`, `dossier.json` - pipeline intermediates
- `run_manifest.json` - audit trail

When the user asks "what did we get": for MCP, prefer `primr://output/artifacts/by_job/{job_id}` as the first inventory read; it returns file names, paths, sizes, hashes, timestamps, classifications, and missing-file state without report body content. If QA artifacts are attached, use `primr://output/qa_summary/by_job/{job_id}` for compact QA score/status/count metadata without detailed QA body text. Use `primr://output/usage_summary/by_job/{job_id}` for compact cost, timing, approval, and artifact-count metadata without full manifest content. Use `primr://output/source_summary/by_job/{job_id}` for compact citation/source appendix counts, domains, missing citations, duplicate URLs, and source URLs without report body content. Use `primr://output/trace_summary/by_job/{job_id}` for compact scrape trace counts, tier health, latency, block, HTTP status, and validation metadata without URLs, raw trace entries, or page content. Use `primr://output/verification_summary/by_job/{job_id}` for compact claim verification trust score, claim counts, status counts, first-party downgrade counts, and source-reference counts without raw claims, source URLs, search queries, explanations, or report body content. Use `primr://output/calibration_summary/by_job/{job_id}` for compact label-calibration counts, evidence-review count buckets, judge provenance, and judge-agreement metadata without raw claims, source URLs, evidence reviews, rationales, or report body content. MCP resource reads and A2A skill calls are audit-logged with hashed payload values, without raw URI query values, resource bodies, message text, raw results, or caller ids. Then list the artifacts, quote the executive summary, and note section count. Do not dump the full markdown unless they ask for the full text. Offer to convert to DOCX (`primr` writes both by default in `full` mode) or to feed it to a downstream consumer.

## Downstream handoff

primr's outputs are inputs to the rest of the user's toolchain. Do not let a report sit unused. When a run completes, proactively offer the next step the user is likely to need.

For the mapping (Strategic Overview → which next action, AI Strategy module → which next action, hypotheses → which next action), see [references/downstream-handoff.md](references/downstream-handoff.md).

## Hypothesis memory

primr persists durable research memory per company. Before launching a new run on a company you've researched before:

- MCP: call `get_hypotheses(company=...)` and read `primr://memory/<company>` to see what's already known.
- After the run completes, the pipeline saves new hypotheses automatically. If the user asks you to record a finding from a customer conversation, use `save_hypothesis(company=..., hypothesis_id=..., claim=..., confidence=..., evidence=...)`.

Display confidence levels honestly (`untested`, `validated`, `invalidated`, `confirmed`). Do not promote hypotheses without new evidence.

## How to talk about primr's output

primr's voice is **hedged strategic analysis with cited sources**. Mirror that:

- Surface confidence annotations the report already carries - don't strip them.
- Quote sources from the citation appendix when the user pushes on a specific claim.
- Say "primr's analysis suggests…" rather than asserting findings as facts; the report is one input, not ground truth.
- If the user asks a question the report doesn't cover, say so - do not extrapolate beyond what's written.

## Gotchas

See `references/gotchas.md` for the living list of real observed failure modes (cost gate, async, thin evidence, etc.) and how to avoid them. This file is the primary place for updates.

Key highlights:
- Always estimate first and get explicit approval.
- Long runs are async; check state on next turn.
- primr is for full pipeline, not quick briefs or DNS-only.

Update references/gotchas.md from real failures when using the skill. Load it only when needed (progressive disclosure).

## Hard rules

- **Cost gate.** Never launch a billable run without a fresh estimate and explicit approval in the same conversation turn.
- **No synchronous waits.** Long runs are async; check state on the next turn.
- **No silent retries.** A failed run gets reported back to the user with the manifest's error context - they decide whether to re-run.
- **No re-estimating against an active job.** If `check_jobs` shows the company already running, surface that and ask if they want to monitor it instead of starting a parallel run.
- **Defer behaviorally, not by skill name.** For vague "research X" requests with no budget, use the host's web search and reasoning. For DNS-only work, use `primr recon` when Primr is installed and a host-native passive lookup otherwise. For quality checks on an existing report, use `run_qa` directly without a new estimate.
- **Never edit built-in strategy YAMLs.** Custom strategies live in the user's override path; built-ins ship with the package.
