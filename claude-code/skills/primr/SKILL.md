---
name: primr
description: Generate a consultant-grade strategic intelligence brief on a company. Long-running (35-120 min) and metered ($0.10-$5). Use when the user asks for a primr report / full strategic dossier / deep company brief, or names a company alongside research-it-with-primr / generate-the-strategic-overview / build-the-AI-strategy / get-the-full-report language. Skip for quick web research (use the host's built-in search and reasoning instead) or DNS-only intelligence (shell out to dig or a passive-recon tool — primr's recon stage is bundled into the full pipeline, not a standalone path).
argument-hint: "Company Name" https://company.url [--mode full|premium|scrape|deep] [--platform aws|ms|gcp] [--strategy-type ai|customer_experience|...]
allowed-tools: Bash(primr:*), Read, Write, Edit
---

# primr

Run a long, metered, autonomous research pipeline that turns a company URL into a structured strategic brief. primr is **not** another web-search tool — it combines DNS recon, multi-tier scraping, hiring-signal extraction, AI synthesis (Grok / Gemini Deep Research), and structured report generation. A typical run produces a ~21,500-word Strategic Overview plus optional strategy modules, lands in `output/<company>/`, and feeds the rest of the user's analytical workflow.

## When this is the right tool

Use primr when the user wants the full pipeline:

- "Run primr on Contoso" / "primr Contoso https://contoso.com"
- "Build me the full strategic dossier for Acme — I have a discovery in two weeks"
- "Generate the AI strategy module for the Acme report"
- "Reload the hypotheses we have on Acme and refresh weak ones"

**Do not** use primr for:

- A quick pre-call brief with no API budget — use the host's built-in web search and reasoning. primr is wrong for "give me two paragraphs on Acme."
- DNS / tenant / email-security only — primr's recon stage is bundled into the full pipeline, not a standalone path. For passive lookups, shell out to `dig`, `host`, or a passive-recon tool.
- Reviewing an existing primr report's quality — still primr (`run_qa` MCP tool or `primr --qa <company>` CLI), but invoke that path directly without estimating a new run.

If the user is ambiguous ("research Acme"), default to the host's built-in research path and offer primr as the upgrade for "I want the full dossier." primr's cost and runtime mean it should never auto-fire on a vague trigger.

## Before first invocation

Confirm primr is installed and configured before the first call in a session:

```bash
primr --version
primr doctor
```

If `primr` is not on `PATH`:

> "primr isn't installed. It's a Python CLI from github.com/blisspixel/primr — `pip install primr` (Python 3.11+). After install, run `primr init` to set the API keys (Grok and/or Gemini). Want me to walk through it?"

Wait for explicit approval before running `pip install`. If `primr doctor` reports missing keys, do not attempt to set them yourself — surface the gap and let the user run `primr init` or `primr keys set <provider>`.

## Detecting MCP vs CLI

Look at your own available-tools list before choosing transport:

- If you see `mcp__primr__*` tools (`mcp__primr__estimate_run`, `mcp__primr__research_company`, etc.) → **prefer MCP**. It returns structured objects, exposes job state via resources, and the cost gate is enforced server-side.
- Otherwise → fall back to the `primr` CLI. Same workflow, file-based artifacts.

Do not call an MCP tool speculatively to test connectivity. To get from CLI-only to MCP, the user adds primr to their host's MCP config (the snippet is `{ "command": "primr", "args": ["mcp"] }`; see the `clients/` directory in the primr repo for per-host paths).

## The cost gate (non-negotiable)

primr runs cost real money and real time. **Never** launch a run without:

1. **Estimating first.** MCP: `estimate_run(company_url=..., mode=..., platforms=[...], strategy_type=...)`. CLI: append `--dry-run` to the exact command you intend to run.
2. **Reporting the estimate** verbatim — quoted dollars and minutes, plus what mode and what strategy.
3. **Getting explicit user approval** in the conversation. "Want me to launch it?" → wait for "yes" / "go" / equivalent. A user asking *"how much would it cost"* is **not** approval.

If the user pushes back on cost, suggest a cheaper mode (`scrape` ~$0.10, default ~$0.75) before walking away. If they want premium depth, surface the `--grok-tier max` (~$4.29) and `--premium` (~$5) tiers and re-estimate.

The MCP server enforces this gate via `primr://agent/governance`; the CLI does not, so on CLI you are the gate.

## Default workflow

1. **Estimate.** `estimate_run` (MCP) or `primr "Name" url --dry-run [flags]` (CLI). Capture the cost, time, page count, planned strategy.
2. **Approve.** Quote the estimate, ask for go-ahead. Stop. Do not proceed without an explicit "yes."
3. **Launch.** MCP: `research_company(company_name=..., company_url=..., mode=..., platform=..., destination=...)` → returns `job_id`. CLI: drop `--dry-run` and run the same command. Note the `job_id` or output directory.
4. **Don't block.** Runs take 35-120 minutes. Tell the user the job is running and what file path will hold the report. Do not poll synchronously in a loop.
5. **Resume on next turn.** When the user comes back ("is the Acme report done?"), check `primr://research/status` or `check_jobs` (MCP), or look for the markdown file at `output/<company>/<Company>_Strategic_Overview_<MM-DD-YYYY>.md` (CLI). If still running, report the stage and `stage_progress_percent`.
6. **Confirm completion, then hand off.** Read the report path. Do NOT dump the full report into the conversation — it's ~21k words. Summarize the executive summary, list the section count, and offer downstream actions (see [references/downstream-handoff.md](references/downstream-handoff.md)).

## Mode, tier, platform, strategy

primr exposes four orthogonal levers. Default is `full` mode, no platform bias, default `--grok-tier`, no `--strategy-type` (Strategic Overview only).

For the full decision matrix — when to pick each, cost and time per combination, multi-platform behavior — see [references/modes-and-strategies.md](references/modes-and-strategies.md). One-liner heuristics:

- **Mode**: `full` for almost everything. `scrape` if external research isn't needed. `deep` if the site is blocked. `premium` only when the user asks for board-grade depth.
- **Platform**: omit unless the user is positioning a specific cloud. Then pass exactly what they're selling against (`--platform aws`, `--platform ms`, etc.). It biases the AI strategy module, not the core report.
- **Strategy type**: omit for default Strategic Overview. Add `--strategy-type ai` to also produce the AI Strategy module in the same run. Other built-ins: `customer_experience`, `modern_security_compliance`, `data_fabric_strategy`, `cloud_migration`, `data_strategy`, `ai_first_transformation`. Use `primr --list-strategies` or `primr://strategies/available` to enumerate.

## Custom strategies

primr discovers any YAML file dropped into `<install>/prompts/strategies/` (or the user's override path). Author one when the user wants a recurring deliverable that doesn't fit the built-ins (e.g., "FinOps assessment for retail clients", "M&A integration playbook").

For the schema and a worked example, see [references/custom-strategy-yaml.md](references/custom-strategy-yaml.md). Keep custom strategies in version control; do not edit a built-in YAML in place.

## Async monitoring

Long runs are the common case. Treat each turn statelessly:

- On launch: record `job_id` and expected output path. Tell the user "I'll check back when you ping me, or you can ask me to check now."
- On follow-up turn: read state first (`check_jobs` / `primr://research/status` / filesystem), then summarize. Never claim done until the report file exists *and* `check_jobs` reports `status: completed`.
- On failure: read `primr://output/manifest/latest` if available — it contains the audit trail (estimate, approval, execution, error). Surface the failure cause; do not silently re-launch.

## Output handling

Reports land in `output/<company_slug>/`:

- `<Company>_Strategic_Overview_<date>.md` — primary deliverable
- `<Company>_AI_Strategy_<date>.md` — only if `--strategy-type ai` (or another module) was selected
- `scraped_content.txt`, `insights.json`, `dossier.json` — pipeline intermediates
- `run_manifest.json` — audit trail

When the user asks "what did we get": list the artifacts, quote the executive summary, and note section count. Do not dump the full markdown unless they ask for the full text. Offer to convert to DOCX (`primr` writes both by default in `full` mode) or to feed it to a downstream consumer.

## Downstream handoff

primr's outputs are inputs to the rest of the user's toolchain. Do not let a report sit unused. When a run completes, proactively offer the next step the user is likely to need.

For the mapping (Strategic Overview → which next action, AI Strategy module → which next action, hypotheses → which next action), see [references/downstream-handoff.md](references/downstream-handoff.md).

## Hypothesis memory

primr persists durable research memory per company. Before launching a new run on a company you've researched before:

- MCP: call `get_hypotheses(company=...)` and read `primr://memory/<company>` to see what's already known.
- After the run completes, the pipeline saves new hypotheses automatically. If the user asks you to record a finding from a customer conversation, use `save_hypothesis(company=..., statement=..., confidence=..., evidence=...)`.

Display confidence levels honestly (`untested`, `validated`, `invalidated`, `confirmed`). Do not promote hypotheses without new evidence.

## How to talk about primr's output

primr's voice is **hedged strategic analysis with cited sources**. Mirror that:

- Surface confidence annotations the report already carries — don't strip them.
- Quote sources from the citation appendix when the user pushes on a specific claim.
- Say "primr's analysis suggests…" rather than asserting findings as facts; the report is one input, not ground truth.
- If the user asks a question the report doesn't cover, say so — do not extrapolate beyond what's written.

## Hard rules

- **Cost gate.** Never launch a billable run without a fresh estimate and explicit approval in the same conversation turn.
- **No synchronous waits.** Long runs are async; check state on the next turn.
- **No silent retries.** A failed run gets reported back to the user with the manifest's error context — they decide whether to re-run.
- **No re-estimating against an active job.** If `check_jobs` shows the company already running, surface that and ask if they want to monitor it instead of starting a parallel run.
- **Defer behaviorally, not by skill name.** Vague "research X" with no budget → use the host's web search and reasoning. DNS-only → shell out to `dig` or a passive-recon tool. Quality-checking an existing report → `run_qa` directly, no new estimate.
- **Never edit built-in strategy YAMLs.** Custom strategies live in the user's override path; built-ins ship with the package.
