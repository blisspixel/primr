# Agent Integration

Primr can be operated from agent hosts through MCP, A2A, packaged skills, and
documented host configuration snippets. There are two distinct agent workflows:

- `primr prep` plus the `primr-zero` skill performs hard-zero collection and
  uses an existing host plan for research and synthesis.
- MCP, A2A, or CLI launches the provider-backed Primr pipeline after an estimate
  and explicit spend approval.

Do not describe the first path as an API-key substitute inside Primr. The host
owns its research and reasoning; Primr owns deterministic evidence collection
and the handoff artifacts.

## Operating Rules

Any billable agent-driven Primr run must follow this lifecycle:

1. Estimate the exact run.
2. Show the cost, time, mode, platform, and strategy choice.
3. Get explicit approval from the user.
4. Launch the job.
5. Monitor asynchronously.
6. Read the output artifact before summarizing.

Do not start billable work from a vague request like "research Acme." Use the
host-native plan path, after verifying that it will not bill API usage or
overages, or normal web research for quick briefs. Reserve provider-backed Primr
for requests that need the full pipeline.

For hard-zero collection:

1. Run `primr prep "Company" https://company.example --dry-run` when the user
   wants to inspect the plan.
2. Explain that collection costs `$0.00` in model API spend but performs public
   network requests.
3. Run `primr prep` without a spend-approval gate.
4. Read `prep_manifest.json`, `source_index.json`, and `research_packet.md`.
5. Use `primr-zero` in the current host to close external gaps and write the
   dossier without silently switching to API billing.

See [Zero-Cost and Host-Assisted Research](ZERO_COST.md) for the complete
contract and failure behavior.

## MCP Server

The Model Context Protocol server is the main programmatic surface:

```bash
primr mcp
primr mcp --http --port 8000
primr-mcp --stdio
```

Use stdio for local desktop agent hosts. Use HTTP only when you need a networked service with JWT auth and explicit cost-cap enforcement.

Important MCP concepts:

- `estimate_run` produces a structured cost and time estimate.
- `research_company` launches approved research jobs.
- Job resources expose status and output paths.
- `primr://output/artifacts/by_job/{job_id}` exposes compact artifact metadata
  for one owned job without report body content. Use it before requesting full
  report previews or reading files directly.
- `primr://output/qa_summary/by_job/{job_id}` exposes compact QA score/status
  and count metadata for attached QA JSON sidecars and text QA reports without
  detailed QA or report body content.
- `primr://output/usage_summary/by_job/{job_id}` exposes compact cost, timing,
  approval, execution, and artifact-count metadata from owned-job run manifests
  without full manifest content.
- `primr://output/source_summary/by_job/{job_id}` exposes compact
  citation/source appendix counts, domains, missing citations, duplicate URL
  counts, and source URLs without report body content.
- `primr://output/trace_summary/by_job/{job_id}` exposes compact scrape trace
  counts, tier health, latency, block, HTTP status, and validation metadata
  without URLs, raw trace entries, or page content.
- `primr://output/verification_summary/by_job/{job_id}` exposes compact claim
  verification trust score, claim counts, status counts, first-party downgrade
  counts, and source-reference counts without raw claims, source URLs, search
  queries, explanations, or report body content.
- `primr://output/calibration_summary/by_job/{job_id}` exposes compact
  label-calibration per-label counts, inference source-copy counts,
  evidence-review count buckets, judge provenance, and judge-agreement
  metadata without raw claims, source URLs, evidence reviews, rationales, or
  report body content.
- HTTP mode can enforce server-side cost caps and approval tokens.
- Audit resources record MCP tool calls, MCP resource reads, and A2A skill
  calls with hashed payloads and normalized resource kinds for admin review.

Full tool and resource details are in [MCP and A2A API](API.md).

## A2A Server

A2A support is optional:

```bash
pip install primr[a2a]
primr-a2a
primr-a2a --host 127.0.0.1 --no-auth
primr-mcp --http --a2a
```

Use unauthenticated A2A only on loopback for local development. Networked
deployments should use auth and the same cost controls as MCP HTTP mode. A2A
bearer tokens use the same scope vocabulary as MCP: `read` can estimate, check
job status, and run system health; `research` is required to start research,
run QA, or cancel an A2A task. Legacy `write` tokens still satisfy
research-scope A2A calls for compatibility. Authenticated A2A jobs are owned
by the bearer token `client_id`; unauthenticated loopback jobs keep the legacy
local `a2a` owner id.
A2A skill invocations and task cancellation append privacy-preserving audit
events to the shared audit log. Events include hashed message/result payloads,
hashed caller ids, granted scopes, outcome, duration, and job id when present,
but not raw message text, task ids, URLs, report paths, raw results, or caller
ids.

## Host Configuration

Per-host snippets live under [`clients/`](https://github.com/blisspixel/primr/tree/main/clients):

- Codex and other repository Agent Skills hosts
- Cursor
- Windsurf
- VS Code and Copilot
- Kiro
- Claude Desktop

The common launch shape is:

```json
{
  "command": "primr",
  "args": ["mcp"]
}
```

Agent hosts differ in where they store MCP configuration and how they load local guidance. Use the host-specific snippet when available instead of hand-writing paths.

## Packaged Skills and Agent Guidance

Primr ships four related guidance surfaces:

- `AGENTS.md` at the repository root for tools that auto-load the open agents.md format.
- `.agents/skills/primr-zero/` as the canonical portable hard-zero skill.
- `claude-code/` plugin files, including a checked `primr-zero` mirror, for the Claude Code plugin workflow.
- Generated skill packs from `primr skills`, which are company-specific Agent Skills artifacts for downstream work.

The full `primr` operating guidance remains thin over the CLI and MCP server.
`primr-zero` is intentionally different: it defines a host-native synthesis
workflow over a versioned Primr evidence packet. Generated skill packs are
company-specific downstream artifacts and are not Primr operating skills.

## Skill-Only Install

When a host supports local skill files but not the plugin flow, install the
entire desired skill directory, including its references.

For hard-zero research, use the canonical package:

```text
Source: .agents/skills/primr-zero/
Codex personal install: ~/.agents/skills/primr-zero/
Claude Code personal install: ~/.claude/skills/primr-zero/
Repository skill install: <workspace>/.agents/skills/primr-zero/
```

From an installed wheel, use `primr prep --install-skill <directory>` to copy
the complete skill and references into any of those explicit destinations.

Claude Code users may copy the checked mirror from
`claude-code/skills/primr-zero/` or install the Primr plugin. Hosts without
shell access can consume a prep bundle through their official file-import or
research UI and use `HOST_WORKFLOW.md` as the task contract.

For provider-backed Primr guidance, install the existing full-pipeline skill:

```text
Fetch https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/primr/SKILL.md
Save it to the host's local skills directory as primr/SKILL.md
Fetch the files under claude-code/skills/primr/references/
Save them under primr/references/
Run primr init before launching billable work
```

Use the host's documented local skill directory. Do not let an installer overwrite unrelated user configuration.

## Credential Boundaries

Primr separates credential types:

- Provider API keys, such as `XAI_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY`, pay for direct model calls inside Primr.
- Agent-host credentials operate the surrounding host and do not automatically replace provider API keys.
- `primr-zero` keeps synthesis inside that surrounding host and never passes its credentials into Primr.
- Primr has an internal/eval-only Codex runner for `fast.source_relevance`, but it is not exposed as an inference profile. Codex authentication can be plan-backed or API-key billed, and Primr cannot prove which billing mode applies.
- Local and gateway endpoints are first-class paths when configured and measured, but full local report profiles remain roadmap work.

Do not paste browser-session cookies, personal web app tokens, or unofficial subscription proxy credentials into Primr.

See [API Key Setup](API_KEYS.md) for the full credential model.

## Async Monitoring

Primr runs can take 35-120 minutes. Good agent integrations avoid tight polling.

Preferred patterns:

1. Launch in the background and report completion.
2. Stream sparse phase markers from logs.
3. Do one early sanity check after the first few minutes.
4. On the next user turn, read job state before saying anything about completion.

A job is complete only when the job state reports completion and the expected report artifact exists.
For agent handoff, read `primr://output/artifacts/by_job/{job_id}` first to
confirm which artifacts exist, their classifications, sizes, timestamps, and
hashes. Request `primr://output/by_job/{job_id}` only when the agent needs a
report preview for summarization. If QA artifacts are attached, read
`primr://output/qa_summary/by_job/{job_id}` before loading any QA body text.
Read `primr://output/usage_summary/by_job/{job_id}` when the handoff needs
run cost, timing, approval, execution, or artifact-count metadata.
Read `primr://output/source_summary/by_job/{job_id}` when the handoff needs
citation/source appendix health without report body content.
Read `primr://output/trace_summary/by_job/{job_id}` when the handoff needs
scrape trace health without URLs, raw trace entries, or page content.
Read `primr://output/verification_summary/by_job/{job_id}` when the handoff
needs claim verification trust and count metadata without raw claims, source
URLs, search queries, explanations, or report body content.
Read `primr://output/calibration_summary/by_job/{job_id}` when the handoff
needs label-calibration counts, inference source-copy counts, or
judge-agreement metadata without raw claims, source URLs, evidence reviews,
rationales, or report body content.
Resource reads and A2A skill calls are audit-logged without raw URI query
values, raw message text, raw result bodies, or caller ids, so prefer compact
resources before requesting report previews or files.

## Related Docs

- [Zero-Cost and Host-Assisted Research](ZERO_COST.md)
- [Run Modes and Costs](RUN_MODES.md)
- [API Key Setup](API_KEYS.md)
- [MCP and A2A API](API.md)
- [Skill Pack Guide](SKILL_PACK.md)
- [OpenClaw Guide](OPENCLAW.md)
