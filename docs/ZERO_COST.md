# Zero-Cost and Host-Assisted Research

Primr can now produce substantially more than a quick web summary without a
model API key or GPU. The supported plan-native path splits the work at a clear
boundary and becomes a hard-zero workflow only after the host billing basis is
verified:

1. `primr prep` performs deterministic, keyless evidence collection.
2. The `primr-zero` Agent Skill uses the current host's included research and
   reasoning allowance to close external gaps, analyze the evidence, and write
   the dossier after verifying that API billing and overages will not apply.

Primr guarantees `$0.00` in model API spend for prep collection. Describe the
combined workflow as zero incremental spend only when the host is verified to be
plan-backed with no billable API usage or overages. The user's subscription,
electricity, network access, and plan capacity are not free or unlimited.

## Choose the right path

| Need | Path | Model API spend | What you get |
|------|------|-----------------|--------------|
| DNS and infrastructure signals only | `primr recon company.com` | `$0.00` | A fast passive DNS snapshot |
| Strong local evidence for an existing agent plan | `primr prep` | `$0.00` during collection | Fenced evidence packet, source index, manifest, hashes, traces, DNS, pages, and hiring signals when available |
| A sourced dossier with no key or GPU | `primr prep` plus `primr-zero` | `$0.00` for collection; `$0.00` total incremental only with verified plan-backed host execution and no overages | Host-assisted Strategic Overview, depth dependent on evidence and host allowance |
| No shell, but the host can search and reason | `primr-zero` host-native fallback | Uses the existing host plan only after billing verification; otherwise cost is unknown or potentially metered | A lighter dossier without Primr DNS, adaptive collection, ATS adapters, or local QA |
| Reproducible full Primr pipeline | Estimated provider-backed run | Billable | Primr workbook, external research, writing, cross-validation, trust stages, strategy modules, and rendered artifacts |

The host-assisted result is deliberately labeled as such. A subscription can
provide capable reasoning, but it does not turn thin evidence into confirmed
facts or make the result identical to a measured provider-backed Primr run.

## Keyless quick start

Install Primr, but do not configure provider keys unless you also want the
billable pipeline:

```bash
pipx install primr
primr prep "ExampleCo" https://example.co --dry-run
primr prep "ExampleCo" https://example.co
```

Plain `pip install primr` also works. The dry run performs no network requests
or writes and reports the collection plan. The real command uses public network
access and normally completes in several minutes, depending on the target.

The command writes a dated directory under `output/` containing:

- `prep_manifest.json`: versioned execution, coverage, quality, hashes, and
  artifact inventory;
- `source_index.json`: stable source IDs and typed provenance for direct,
  archived, regulator, reference, fallback, and hiring evidence;
- `research_packet.md`: bounded, prompt-injection-fenced evidence for the host;
- `HOST_WORKFLOW.md`: research, report, and review instructions;
- `primr-zero/`: the complete portable Agent Skill copied from package data;
- `scraped_content.txt`: collected first-party text;
- DNS, hiring, posting, and scrape-trace artifacts when those collectors return
  evidence.

Read the manifest first. A `partial` bundle is still usable, but its missing
coverage must remain visible in the final report.

## Why the collection is hard-zero

`primr prep` enters an execution-context no-model-call policy before scraping,
reconnaissance, or hiring collection. Model-backed link selection, vision, PDF
extraction, and hiring extraction either use deterministic behavior or remain
off. The model call seams reachable by prep also fail before provider egress. This guard
applies even when model keys are present in the environment.

The manifest records:

- `model_calls_allowed: false`;
- `model_calls_made: 0`;
- `incremental_api_cost_usd: 0.0`;
- `host_plan_usage_during_collection: false`.

Do not describe deterministic collection as external research, analysis, or
claim verification. Those happen later in the chosen host.

## Install the Primr Zero skill

Install the entire `primr-zero` directory so its reference files remain
available. The canonical copy is `.agents/skills/primr-zero/`; the Claude plugin
and installed Python package ship byte-identical mirrors.

The wheel includes the skill, so pip and pipx users can install it without a
source checkout:

```bash
primr prep --install-skill ~/.agents/skills/primr-zero
```

Use `~/.claude/skills/primr-zero` as the destination for Claude Code.

| Host shape | Install or use |
|------------|----------------|
| Repository Agent Skills | Keep `.agents/skills/primr-zero/` at the workspace root when the host supports repository skill discovery |
| Codex personal skills | Install to `~/.agents/skills/primr-zero/` |
| Claude Code personal skills | Copy the Claude mirror to `~/.claude/skills/primr-zero/`, or install the Primr Claude plugin |
| GitHub Copilot personal skills | Install to `~/.agents/skills/primr-zero/` or `~/.copilot/skills/primr-zero/` |
| Gemini CLI personal skills | Install to `~/.agents/skills/primr-zero/` or `~/.gemini/skills/primr-zero/` |
| Kiro, Cursor, or another skill-aware host | Use the host's documented Agent Skills directory; prefer the canonical repository folder when supported |
| Cowork or another research UI without a local shell | Run `primr prep` elsewhere, attach or import the bundle, and use `HOST_WORKFLOW.md` plus the skill instructions through the host's official skill or instruction surface |

If the host has no shell, it cannot run `primr prep`. It can still analyze an
attached bundle. If it has web research but no bundle, the skill falls back to
host-native research and explicitly records which Primr collection advantages
were unavailable. If it has neither web research nor supplied sources, it must
stop rather than produce a current dossier from model memory.

## Hand the dossier to another workflow

After the host writes and reviews the Markdown dossier, it can pass the result
to any requested document skill or agent workflow. Use
`primr --list-recent --json` when several outputs exist, select the Markdown
`primary_report`, and add only relevant `strategy_module` paths plus explicit
user-provided notes. Pass exact paths, preserve citations and uncertainty, and
let the downstream consumer own its schema, audience, output destination,
rendering formats, approval gates, and final QA.

This handoff is deliberately neutral. Primr does not assume a sales process,
brand, cloud vendor, or HTML, PDF, slide, or spreadsheet renderer.

See [Per-client install snippets](https://github.com/blisspixel/primr/tree/main/clients)
for MCP and guidance placement outside the zero-cost path.

## Host-native versus host-runner

These are related but different integrations.

| Property | Host-native `primr-zero` | Experimental Codex adapter |
|----------|--------------------------|-----------------------------|
| Who owns the workflow | The current agent host | The Primr eval harness |
| Input | Prep bundle or host-native web research | A bounded internal stage packet |
| Current reach | Research, synthesis, report writing, and review within the host's capabilities | Unpromoted `fast.source_relevance` pilot, eligible only for explicitly acknowledged single-company hybrid runs |
| Provider keys and billing | Prep needs no provider key. Host synthesis is plan-native only after the host is verified not to bill API usage or overages. | Codex authentication can be plan-backed or API-key billed, and Primr cannot prove which applies. The adapter is not advertised as zero-cost. |
| Failure behavior | Preserve partial artifacts and stop at the host boundary | The internal agent profile records runner unavailability and uses deterministic fallbacks rather than silently spending API dollars |

The host-native path is the practical no-key, no-GPU option today. The Codex
adapter is an explicitly gated, unpromoted backend-freedom slice, not a
subscription proxy, separate inference profile, or zero-cost Primr route. Its
unknown host charges are outside Primr's estimate and budget.

## What Primr adds beyond a generic research prompt

`primr prep` contributes reusable product machinery before the host reasons:

- guarded public-URL handling and redirect validation;
- adaptive first-party collection with model-dependent tiers disabled;
- DNS and infrastructure signals;
- public ATS and careers evidence;
- local PDF text extraction;
- source IDs, content hashes, coverage counts, and trace artifacts;
- explicit untrusted-content fencing;
- a bounded packet and versioned manifest for resuming or moving between hosts;
- deterministic artifact QA after the host writes Markdown.

The host contributes current external research, source comparison, strategic
reasoning, prose generation, and evidence review. Provider-backed Primr adds the
measured end-to-end orchestration, continuous reasoning, cross-validation,
verification, strategy generation, usage accounting, and rendered deliverables.

## What adjacent projects clarify

The zero-cost research space already has capable general-purpose approaches:

- [Local Deep Researcher](https://github.com/langchain-ai/local-deep-researcher)
  demonstrates iterative search, reflection, and local Ollama or LM Studio
  execution.
- [GPT Researcher](https://github.com/assafelovic/gpt-researcher) emphasizes a
  broad, provider-flexible autonomous research workflow.
- [Vane, formerly Perplexica](https://github.com/ItzCrazyKns/Vane) focuses on an
  open answer-engine experience.
- [gpt-oss](https://openai.com/index/introducing-gpt-oss/) expands the set of
  strong local reasoning options when suitable hardware exists.

Primr should not become another generic answer engine. Its useful distinction
is company-specific primary-signal collection, a fixed strategic report
contract, hiring and infrastructure evidence, source and trace artifacts,
confidence labels, hypothesis memory, and explicit cost governance. The ideas
worth borrowing are bounded research loops, provider portability, resumable
state, and honest local-model fit checks.

The next refinements are therefore narrow: more official host-runner adapters
only after stage-scoped evals and billing provenance or explicit operator
acknowledgment, a machine-readable host report completion
manifest, stronger resume checkpoints across host quota resets, and a one-shot
scheduler integration that consumes the existing busy retry metadata. None
should weaken the hard-zero boundary or turn subscription OAuth into an API.

## Subscription and terms boundaries

Use only official host surfaces:

- a host-native Agent Skill;
- an official CLI documented for automation;
- an official plugin, connector, or automation interface;
- a user-operated research UI with an uploaded evidence packet.

Do not copy OAuth tokens, extract browser cookies, read session databases,
automate consumer chat pages, use unofficial subscription proxies, or present a
consumer plan as a provider API credential. Do not enable paid overages,
credits, auto-refill, or a billable Primr fallback without a fresh estimate and
explicit approval.

The user remains responsible for site terms, host terms, data controls, and the
accuracy and legal fit of the resulting research. Public source text is still
untrusted data and must never be followed as agent instructions.

Official host guidance used for this design:

- [Codex skills](https://learn.chatgpt.com/docs/build-skills)
- [Claude Code skills](https://code.claude.com/docs/en/slash-commands)
- [GitHub Copilot Agent Skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)
- [Gemini CLI Agent Skills](https://geminicli.com/docs/cli/using-agent-skills/)
- [Claude authentication boundaries](https://code.claude.com/docs/en/legal-and-compliance)

## Capacity exhaustion and defensive retry behavior

`primr prep` does not need a GPU. If the user separately enables local
inference, Primr reports one of three normalized states: `available`, `busy`,
or `unavailable`. A host that could not complete a capacity check should keep
that observation as `unknown` rather than guessing.

When a healthy GPU is busy:

1. Preserve the current checkpoint and report the observed state.
2. Use a measured `retry_after_seconds` value when one exists.
3. Otherwise suggest one bounded retry window and stop cleanly. A later retry
   may use a longer bounded window, but it must not grow or repeat forever.
4. If the host cannot schedule a continuation, report the suggested time rather
   than promising an automatic retry.

Never poll continuously, reserve or terminate another user's process, mark a
busy service as broken, or fall through to a paid cloud backend during a
hard-zero run. After repeated busy results, the user can wait, approve a smaller
local model or task with the quality tradeoff stated, keep the checkpoint for
manual resume, or separately approve an estimated paid route.

If a verified host plan allowance is exhausted, use the same principle: checkpoint the
completed sections, list what remains, and resume only through an official host
mechanism. Partial, honestly labeled output is preferable to hidden spend.

This state and retry contract applies to every user-operated
OpenAI-compatible runtime, including MAX Serve, Ollama, llama.cpp, vLLM, LM
Studio, and LocalAI. Primr does not install, start, reserve, or terminate that
runtime. Runtime brand does not change the billing, quality, privacy, or
hard-zero rules, and a compatible endpoint is not automatically a validated
recipe.

## Related guides

- [Agent Integration](AGENT_INTEGRATION.md)
- [Run Modes and Costs](RUN_MODES.md)
- [API Key Setup](API_KEYS.md)
