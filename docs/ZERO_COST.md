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
| Cited draft using an installed model | `primr draft --local BUNDLE` | `$0.00` model API spend when the configured runtime is unmetered | Unvalidated draft Markdown and DOCX, matching source excerpts, and coverage/provenance receipts |
| A sourced dossier with no key or GPU | `primr prep` plus `primr-zero` | `$0.00` for collection; `$0.00` total incremental only with verified plan-backed host execution and no overages | Host-assisted Strategic Overview, depth dependent on evidence and host allowance |
| No working Primr launcher, but the host can search and reason | `primr-zero` host-native fallback | Uses the existing host plan only after billing verification; otherwise cost is unknown or potentially metered | A lighter dossier without Primr DNS, adaptive collection, ATS adapters, traces, or local QA |
| Reproducible full Primr pipeline | Estimated provider-backed run | Billable | Primr workbook, external research, writing, cross-validation, trust stages, strategy modules, and rendered artifacts |

The host-assisted result is deliberately labeled as such. A subscription can
provide capable reasoning, but it does not turn thin evidence into confirmed
facts or make the result identical to a measured provider-backed Primr run.

## Agent-host quick start

When an agent can see this repository or the installed Primr skill, the user
does not need to know the collection subcommand. The public request stays:

```text
primr "ExampleCo" https://example.co
```

Without explicit paid intent, the agent defaults to `primr-zero`, runs
`primr prep` internally when it has shell access, then uses its current host
tools for external research, synthesis, evidence review, and artifact handoff.
It must not ask the user to choose `prep`, `scrape`, or `full`. It must not
infer permission to spend from provider keys that happen to be configured.

If host billing cannot be verified, the agent can still state that Primr model
API spend is `$0.00`, but it must describe host cost as unknown or potentially
metered rather than calling the complete workflow free. Explicitly paid or
premium requests route to a fresh provider-backed estimate and approval gate.
The direct terminal command remains provider-backed; this default applies to
requests interpreted by an agent host.

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
`primr prep` is already noninteractive: run it directly, never pipe `y` into
it, and do not add `--skip-confirm`. If the command asks for provider-spend
approval, stop because the provider-backed research path was selected instead.
Only an explicitly requested provider-backed automation run may replace an
approved dry-run command's `--dry-run` with `--skip-confirm`.

Primr assembles each real bundle in a private same-root staging directory and
publishes it only after the manifest is complete. An in-process error or
interruption removes the staging directory, so artifact discovery sees either
a validated bundle or nothing from that attempt.

The prep command uses the lightweight public entry path for both console and
`python -m primr` execution. If collection is interrupted, it returns exit code
130, removes any incomplete staging, and asks you to inspect the output root
before retrying. If skill installation is interrupted, inspect that destination
before using or retrying it because installation updates files individually.

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

Wikipedia references require a current Wikidata official website claim linked
to the supplied company website. Hiring collection prefers operator-supplied
career URLs and the company's own careers pages, including ATS links and
redirects. Guessed ATS tenants need an explicit company-homepage link on the
board; otherwise only individual roles whose employer website matches through
`JobPosting.hiringOrganization.url` or `sameAs` can enter the posting index,
source index, or synthesis. Search results use the individual employer check.
Customer, tool, and other links in descriptions establish no employer identity.
The prep summary reports identity-linked hiring rows; their `identity_evidence` records
the association basis. The `identity: verified` record means an identity link
was found, including operator assertions and provider-reported metadata. It is
not an independent guarantee of posting authenticity or claim accuracy.

Identity matching normalizes HTTP(S) hostnames and accepts the supplied host,
its `www` form, and child hosts. It keeps the complete host instead of guessing
public suffixes or accepting similarly named organizations. A separate brand
domain, missing official website claim, or inaccessible employer metadata can
therefore reduce coverage. Unverified candidates are omitted; no model call is
used to guess identity.

## Draft with an installed local model

After prep, pass the exact published bundle directory to the explicit draft
command. No provider API key is required. It checks live `/v1/models`, selects
an installed chat model using the existing local judge family preference, and
never pulls a model or falls back to a provider:

```bash
primr draft --local "output/ExampleCo_Primr_Prep_20261011" --dry-run
primr draft --local "output/ExampleCo_Primr_Prep_20261011"
# Pin a model that the configured runtime already serves:
primr draft --local --model "your-installed-model" "output/ExampleCo_Primr_Prep_20261011"
```

The default endpoint is `http://localhost:11434/v1`. `LOCAL_LLM_BASE_URL`
overrides it, followed by `OLLAMA_BASE_URL`. For your own remote inference box,
set `LOCAL_LLM_BASE_URL=http://garage-box:11434/v1` before running the same
commands. Only `LOCAL_LLM_API_KEY` supplies optional authentication for metadata
and inference requests; cloud provider keys are not reused or recorded in draft
artifacts. Protect a remote listener and use HTTPS
when evidence or runtime credentials cross an untrusted network.

**The configured runtime is a trust boundary.** A loopback address alone does
not prove local execution: Ollama can route cloud models through its local
server. Primr rejects known public provider endpoints, detectable cloud model
names, and exposed remote/cloud alias metadata. Arbitrary compatible servers
cannot prove their execution location or billing basis through this protocol.
Use a runtime you control that performs unmetered inference. For Ollama, disable
cloud features on that server with `OLLAMA_NO_CLOUD=1` or its documented
`disable_ollama_cloud` setting and restart it. Primr does not change server
configuration. See the [Ollama FAQ](https://docs.ollama.com/faq) and
[OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).
The command bypasses ambient HTTP proxies and refuses redirects for both
metadata and inference requests. All evidence is sent to the configured
runtime, which may be another machine if you selected one.

The dry run reads and verifies the three required prep inputs, makes metadata
requests only to that runtime, and prints installed model details, a request
cap, and a conservative planning range. It performs no inference and publishes
no report. These time estimates are planning guidance, not measured speed or
a wall-clock deadline. Loading, CPU inference, and queues can take longer.
`--max-chunks` accepts 1-24 (default 12); `--timeout` accepts 10-300 seconds per
request (default 180). HTTP timeouts govern network waits, not an entire run.

Drafting verifies the manifest hashes and reads stable, bounded snapshots of
`prep_manifest.json`, `source_index.json`, and `scraped_content.txt`. Linked or
changed files fail closed. New prep source rows also bind each stripped captured
body with its own character count and SHA256 digest. The reader reconciles every
serialized source frame with the captured index, including legacy bundles,
and rejects extra, duplicate, missing, or metadata-only frames with recollection
guidance. Legacy whitespace stripping and metadata-only hiring rows remain
supported. Evaluation reads artifact provenance again before selecting a parser.
Draft markers retain their local, review-only classification after copying,
moving, or renaming the directory. Invalid markers fail closed; prep markers or
a retained prep source index also require strict parsing and remain review-only.
Ordinary provider runs without prepared provenance keep their existing parser
compatibility and are preferred as evaluation baselines.
These integrity checks do not authenticate a publisher or prove source truth.
Metadata is limited to 2 MB per file and captured
text to 8 MB. Source chunks are at most 3,200 UTF-8 bytes and selected across
captured pages in round-robin order. Map and reduce prompts are capped at
6,000 UTF-8 bytes including the system instruction, with at most 900 generated
tokens per request. Reducers select existing claim IDs rather than inventing
new prose, and their inputs and batch counts are bounded too. These byte caps
are conservative input limits, not exact tokenizer counts. Configure sufficient
serving context at the runtime; a model's advertised maximum context does not
establish the context actually served. Ollama context configuration belongs to
the operator, as described in its OpenAI compatibility guide. For recognized
Ollama runtimes the command requests JSON mode and no thinking output so the
small output budget can hold the requested result.

Each retained claim has a known source ID and a matching captured excerpt.
Unknown IDs, absent excerpts, malformed model responses, and empty results
cannot silently become a successful report. An excerpt match proves that text
was captured, not that it entails the claim or is reliable. Review every
reported assertion and its excerpt. Missing sections, truncated inputs,
unprocessed hiring/recon artifacts, and partial prep coverage remain visible.
This path does not browse, collect external evidence, cross-validate claims,
write strategy modules, or establish full Primr quality equivalence.

Each success publishes a unique `Local_Draft_<timestamp>_<suffix>/` directory
inside the prep bundle, with:

- `<Company>_Local_Draft_Strategic_Overview_<date>.md` and `.docx`, visibly
  labeled **Local draft, not the validated Primr report**, including model,
  quantization when reported, runtime, source citations, and recorded $0 spend;
- `draft_manifest.json` with backend provenance, token usage, call count,
  input-manifest hash, zero model API spend, and honest coverage/quality limits;
- `mapped_claims.json`, captured text, source index, and
  `scraped_website_summary.txt` for inspection and local-stage evaluation.

Publication is transactional and never overwrites an earlier draft or provider
baseline. A busy runtime returns exit code 75 without retry or cloud fallback;
mapped work is retained in a `Local_Draft_Checkpoint_*` directory for inspection,
without report files. A later invocation starts a new draft from the original
bundle; checkpoints are not automatic resume files. Other failures or
interruptions remove incomplete staging. Runtime/cloud execution, hardware,
electricity, and network costs remain the operator's responsibility; the
receipt records model API spend as zero for the selected unmetered runtime.

Local-stage evaluation discovers these flat prep bundles and records
`baseline_kind=local_draft` plus the baseline model. Local/self comparisons are
review-only and excluded from quality-evidence exports and model recommendations.
Existing provider-run baselines retain their comparison behavior. A successful
synthetic draft, citation syntax, quote matching, or local judge agreement is
not backend promotion evidence.

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
available. The canonical copy is `.agents/skills/primr-zero/`; the repository
Claude project skill, Claude plugin, and installed Python package ship
byte-identical mirrors.

The wheel includes the skill, so pip and pipx users can install it without a
source checkout:

```bash
primr prep --install-skill ~/.agents/skills/primr-zero --dry-run
primr prep --install-skill ~/.agents/skills/primr-zero
```

The first command previews the requested destination and reports zero model
calls, network requests, and file writes. The second command performs the
installation.

Use `~/.claude/skills/primr-zero` as the destination for Claude Code.

| Host shape | Install or use |
|------------|----------------|
| Repository Agent Skills | Keep `.agents/skills/primr-zero/` at the workspace root when the host supports repository skill discovery |
| Claude Code in this repository | Use the checked `.claude/skills/primr-zero/` and `.claude/skills/primr/` project skills |
| Codex personal skills | Install to `~/.agents/skills/primr-zero/` |
| Claude Code personal skills | Copy the Claude mirror to `~/.claude/skills/primr-zero/`, or install the Primr Claude plugin |
| GitHub Copilot personal skills | Install to `~/.agents/skills/primr-zero/` or `~/.copilot/skills/primr-zero/` |
| Gemini CLI personal skills | Install to `~/.agents/skills/primr-zero/` or `~/.gemini/skills/primr-zero/` |
| Agent Plugins v1 client | Use the experimental `agent-plugin/` package when the client supports its declared skills or MCP components. The MCP component requires an installed `primr` executable, but the skills remain usable if that component is unavailable. Loading the package does not authorize spend. |
| Kiro, Cursor, or another skill-aware host | Use the host's documented Agent Skills directory; prefer the canonical repository folder when supported |
| Cowork or another research UI without a local shell | Run `primr prep` elsewhere, attach or import the bundle, and use `HOST_WORKFLOW.md` plus the skill instructions through the host's official skill or instruction surface |

If the host has no shell, cannot launch Primr, or cannot install it with user
approval, it cannot run `primr prep`. It can still analyze an attached bundle.
If it has web research but no bundle, the skill falls back to host-native
research and explicitly records which Primr collection advantages were
unavailable. Installation is optional for this fallback, not a blocker. If the
host has neither web research nor supplied sources, it must stop rather than
produce a current dossier from model memory.

## Hand the dossier to another workflow

The host writes and checkpoints the Markdown dossier inside its prep bundle.
After review, run
`primr --list-recent --json --output-dir "<bundle-parent>"`, replacing the
placeholder with the directory containing that bundle. Select the Markdown
record whose `file_path` is inside that prep bundle and whose role is
`primary_report`, then pass that exact path to any requested document skill or
agent workflow. Add only relevant `strategy_module` paths plus explicit
user-provided notes. Preserve citations and uncertainty, and let the downstream
consumer own its schema, audience, output destination, rendering formats,
approval gates, and final QA. When the current host cannot run the inventory,
pass the exact written path and disclose that the check was unavailable.

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
