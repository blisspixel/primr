# Roadmap and compatibility review

Primr should close the demonstrated agent-integration defects, finish its
bounded orchestration ownership repair, then prove the quality of its reports
and evaluators before promoting additional backends. This ordering protects
the existing product while turning its strongest promise into measurable
evidence: a company name and website produce a useful, defensible long-form
Strategic Overview and strategy documents as Word and Markdown artifacts.

This is an evidence snapshot checked on September 13, 2026 against released
baseline v1.39.14, commit `6dc8c92b3eee8d1fc29fc66c229c2c49dfd794f3`.
The executable queue remains exclusively in [Next Steps](NEXT_STEPS.md).
Recommendations below explain that queue; they do not define another release
schedule, authorize provider spending, or claim universal client support.

## Assessment of the README and roadmap

The README has the right product focus and is already short enough to be a
useful front door. It distinguishes agent-host Primr Zero from the paid
terminal path, explains why configured credentials are not permission to
spend, and leads with durable artifacts. Retain this structure. Add a direct
route to the executable queue, rather than expanding the README into a second
architecture or protocol manual.

The roadmap's dependency order is also sound: quality measurement precedes
backend promotion; governed job consumption precedes memory; evidence-aware
writing must earn promotion through measured improvement. Its weakness is
navigation and historical accumulation. The lengthy implementation ledger
contains older experiments and plans alongside newer measurements. Readers
can mistake historical instructions for current authority, particularly when
an old evaluation says to arm a gate that the current baseline deliberately
keeps report-only. Correct these contradictions at their source; retain the
single current queue instead of adding another summary of every feature.

The [product contract](design/company-analyst-product-contract.md) provides a
strong filter for new work. Protocols, provider choice, ledgers, and adapters
matter when they improve report usefulness, reliability, safety, or economics.
Their mere availability is not a reason to expand the product. A polished
report with unsupported material claims is a failure even when every stage
ran successfully; a correct claim inventory without strategic interpretation
also falls short of the promised product.

## What takes priority and why

| Priority | Decision | Evidence and completion standard |
|---|---|---|
| Immediate | Repair existing agent entry points | The HTTP transport accepted an invalid browser Origin; portable plugin state defaults to its installation tree; the VS Code example has the wrong top-level key. Prove the fixes through real transport and installed-layout tests. |
| Next bounded cleanup | Remove one orchestration back edge | `fast_run_sections` imports its coordinator's writer and coherence functions. The architecture test records an 11-module core cycle. Reduce that component without artifact, estimate, approval, or budget drift. |
| Next product milestone | Validate the corpus and the evaluators | Five reports and judge agreement are useful instruments, but two reports lack a decidable Confirmed floor and agreement does not establish correctness. Complete evidence review and independently audit shared errors. |
| Conditional expansion | Promote a backend only after comparison | Compare identical evidence packets and artifact contracts. Record quality, failures, latency, and actual cost. Retain preview status when the outcome is inconclusive. |
| Later | Tasks, governed memory, claim-aware writing | Integrate through existing job and artifact ownership; require SDK support and measured report lift. Do not duplicate lifecycle storage or make an always-running service part of Primr. |

The architecture repair remains worthwhile, but its value is enabling reliable
changes rather than directly improving report quality. The compatibility
findings justify moving ahead of it because they affect current advertised
entry points and have small, deterministic fixes. That is a bounded correction
to the queue, not an invitation to postpone quality behind an endless sequence
of refactors.

## MCP revision and implementation status

The current official core revision is **2026-07-28**. It changes the connection
model substantially from 2025-11-25: modern requests carry version and client
capabilities themselves; `server/discover` replaces initialization as the
discovery mechanism; core HTTP sessions are removed. Results carry
`resultType`, and cacheable results include freshness and scope metadata.
Primr's SDK v2 adoption addresses this generation of the protocol; the correct
next check is transport behavior, not another version-string replacement.
[MCP specification](https://modelcontextprotocol.io/specification/2026-07-28),
[revision changes](https://modelcontextprotocol.io/specification/2026-07-28/changelog).

The current official Python SDK release at review time is **v2.2.0**, published
September 7, 2026; Primr's lockfile uses **2.0.0** and its declared dependency
range permits 2.x. The newer release includes HTTP session limits and
authorization fixes. The SDK roadmap still lists redesigned Tasks support as
unimplemented. Schedule a separately validated lock refresh, including exported
container dependencies. Do not infer that upgrading the SDK implements
Primr's Tasks lifecycle or repairs configuration that explicitly omits transport
security. [Python SDK v2.2.0 release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0),
[SDK roadmap](https://github.com/modelcontextprotocol/python-sdk/blob/main/ROADMAP.md).

| Boundary | Baseline evidence | Required assurance |
|---|---|---|
| Current core | SDK v2 handlers, discovery, cache hints, resource templates, and aligned unknown-name errors are present | Test actual HTTP requests with per-request metadata and required headers, not only direct handler calls |
| Older clients | Legacy initialization remains supported by the SDK | Exercise legacy negotiation and subsequent operations separately from modern requests |
| Browser and host validation | `StreamableHTTPSessionManager` was constructed without `security_settings`; an invalid Origin reached `tools/list` | Enable the SDK guard; test rejected Origin and Host values, local defaults, and explicit trusted ingress |
| Authorization | Primr has bearer credentials, scopes, ownership checks, and estimate-bound approval tokens | Preserve those boundaries; distinguish this configured-token contract from full OAuth discovery and registration |
| Long-running work | Primr has its own job handles, cancellation, persisted journals, and compact resources | Continue using these until a supported Tasks adapter preserves the same approval, ownership, and recovery semantics |
| Optional extensions | Tasks, trace propagation, and other extensions have separate implementation requirements | Advertise only what is implemented and validated; core conformance does not imply extension support |

The Origin issue was reproduced against the actual installed SDK using an
ASGI request: an untrusted browser Origin received HTTP 200 and a complete
tool listing. Existing focused tests passed because they primarily exercised
handlers or replaced the transport. The protocol requires rejection of an
invalid present Origin with HTTP 403. This makes a wire-level regression more
valuable than adding another mocked constructor test.
[Streamable HTTP security requirements](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http).

MCP Tasks is now an optional extension with a redesigned contract. Its polling
and input-update model differs from the earlier experimental API. Plan against
the current extension, not an old `tasks/result` or `tasks/list` design. Preserve
Primr's existing durable handles as the operational fallback and map a future
adapter onto the same supervisor and journal. The transport's request ID is
not a substitute for durable job identity or an idempotent paid-operation
policy. [MCP Tasks extension](https://modelcontextprotocol.io/extensions/tasks/overview).

Remote authorization needs an equally precise claim. A configured bearer token
can support Primr's current scoped operations. It does not establish that an
arbitrary OAuth-only host will discover, register with, and authenticate to the
server. That integration requires its own issuer, metadata, audience, and
client acceptance work. Keep these requirements visible without building a new
identity service into a local-first company-research tool.

## Agent Plugins and host configuration

Agent Plugins **v1.0.0 is published**, rather than merely a working draft.
Its fixed package layout covers `plugin.json`, skills, and optional MCP server
configuration, while installation, permissions, and client-specific behavior
remain the host's responsibility. The live plugin and MCP JSON schemas match
the repository's parsed offline snapshots at review time, and the existing
manifests validate. The schema is not the gap.
[Agent Plugins specification](https://agent-plugins.org/specification),
[canonical schemas](https://agent-plugins.org/schemas).

The runtime gap is the working directory. Without an explicit `cwd`, a
conformant client uses the plugin root. Installed Primr can then create its
output, working, and log directories there. Immutable installations can fail,
and replacing a plugin can put research state at risk. The specification
permits `cwd: "${PLUGIN_DATA}"` and requires clients to create that writable,
persistent location before launch. Use that contract and return actual artifact
paths to consumers. Shell CLI behavior remains a separate execution context.
[Plugin subprocess environment](https://agent-plugins.org/specification#91-subprocess-environment).

A meaningful test places the installed package outside the repository, launches
from the resolved persistent directory, and verifies state creation without
writes inside the plugin package. Source-checkout tests alone are insufficient:
repository-root discovery can hide the installed-mode failure. A real host
acceptance check is still needed before claiming that a named application's
plugin installer, permission UI, executable lookup, and restart behavior have
all been tested.

The portable MCP command is the bare `primr` executable. A conformant plugin
manifest cannot guarantee that it is installed or visible on the host's PATH.
When the MCP component cannot launch, supported skills can still guide Primr
Zero through a working CLI or host-native fallback. Never substitute a paid
research call simply because a transport component is unavailable.

Native configuration examples must also stay client-specific. In particular,
VS Code's `.vscode/mcp.json` uses a top-level `servers` object. Reusing the
Windsurf-style `mcpServers` example does not configure that file correctly.
Provide a dedicated VS Code snippet and retain a structural regression for its
shape. This is separate from the portable Agent Plugins `mcp.json` schema.
[VS Code MCP configuration](https://code.visualstudio.com/docs/agent-customization/mcp-servers#configure-the-mcpjson-file).

## Quality evidence that changes the plan

Primr's recorded baseline contains five distinct reports, 50 evidence reviews,
and agreement on 33 of 37 comparable cloud/local judgments. Its measured
Confirmed floor is 30 percent across three contributing reports; two lack a
decidable floor. The recorded `keep_report_only` decision is appropriate.
These are historical repository measurements, not a new independent assessment
of today's generated reports. A minimum observed score is a diagnostic
regression baseline, not a sufficient standard for analyst excellence.

Recent evidence supports testing the evaluators themselves. *Time to REFLECT*
introduces controlled research-agent errors and reports below 55 percent
overall accuracy for the best tested judges across its evaluation. The task
match makes this a useful warning for research reports, but it is a May 2026
preprint and does not measure Primr. The practical recommendation is to include
known wrong numbers, entity swaps, unsupported conclusions, and citation
misattribution before trusting a judge to gate release.
[REFLECT](https://arxiv.org/abs/2605.19196).

*Nine Judges, Two Effective Votes* reports correlated mistakes across nine
models from seven families on its natural-language-inference datasets. More
judges did not yield the independence their count suggested. This May 2026
preprint does not invalidate Primr's existing cloud/local comparison; it shows
why agreement needs an independent correctness check. Audit a pre-registered
random sample of unanimous approvals as well as every consequential
disagreement. Report shared-error counts alongside agreement.
[Correlated judge errors](https://arxiv.org/abs/2605.29800).

The August 2026 *Trust-Truth Separability* preprint finds that changing source
attribution on identical question-answer content can shift both trust and
truth judgments. Blind provider and model identity in comparative evaluations.
Assess source authority and whether a claim follows from its evidence as
distinct dimensions; do not count correlated scores as independent support.
[Trust and truth study](https://arxiv.org/abs/2608.21097).

Precision also needs a coverage counterpart. The peer-reviewed EMNLP 2025
*VeriFact* work examines missing context and relational facts in long-form
factuality evaluation. Its precision-and-recall framing supports measuring
omitted material facts and contradictions, rather than rewarding a report
solely for making fewer checkable assertions. Primr should preserve both broad
company understanding and explicit uncertainty.
[VeriFact](https://aclanthology.org/2025.emnlp-main.905/).

These studies motivate measurements, not universal numerical thresholds. The
corpus should include sparse and rich public evidence, blocked collection,
hiring signals, changing company context, and contradictory or stale sources.
Each report must have an explicit evidence state. A sparse report with no
justifiable Confirmed claims should remain honest; it must not manufacture
high-confidence labels to qualify for a calibration statistic.

Before any quality promotion, freeze the reports, source receipts, model and
prompt fingerprints, sampling plan, error taxonomy, human labels, and decision
criteria. Then report error-detection precision and recall by category,
abstentions, retrieval failures, omitted material facts, shared errors, and
sampling uncertainty. Keep structural checks such as citation resolution and
DOCX rendering deterministic. Evidence support and strategic usefulness still
need source-grounded judgment and review.

## Backend freedom, memory, and economics

Backend freedom should mean a validated alternative that preserves the artifact
and uncertainty contract. It should not mean that every provider slug appears
in a menu. The repository already has capability routing, stage metadata, an
unpromoted host adapter, and a standing offline source-relevance corpus. The
valuable next result is a defensible comparison on frozen evidence, followed
by an explicit retain-or-promote decision. Recheck exact model IDs, pricing,
retirements, and SDK behavior immediately before a paid comparison.

Current provider documentation reinforces cost provenance rather than a new
default-model recommendation. xAI returns per-request `cost_in_usd_ticks`
including applicable discounts and server-side tools; preserve those receipts
instead of replacing them with token-price estimates. OpenRouter distinguishes
the charged amount from upstream inference cost, while `max_price` limits token
pricing rather than total campaign spending. Claude Code's local dollar display
is not an authoritative bill for included subscription usage. These are
different accounting contracts and should remain explicit in route metadata.
[xAI cost tracking](https://docs.x.ai/developers/cost-tracking),
[OpenRouter accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting),
[OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection),
[Claude Code costs](https://code.claude.com/docs/en/costs).

Similarly, memory should first prove that a subsequent company engagement
improves without importing stale claims or exposing unrelated research. Keep
the proposed ledger in shadow mode until a held-out comparison supports its
use in writing. Retention, deletion, export, evidence provenance, and freshness
are entry requirements. More persistent state is not itself product progress.

Cost controls need a clear scope. A Primr per-run ceiling does not enforce a
whole campaign's total across research runs, judges, host agents, and retries.
The review's requested ceiling is **$10 total**. No paid Primr research or
provider-judge execution is part of this change. Host-agent dollar usage is
not exposed in this environment, so an all-inclusive measured total cannot be
asserted. An unrelated deferred Premium evaluation's $25 ceiling is not
authorization to spend that amount here.

If later paid evaluation is justified, prepare the exact pilot and fresh
estimate first. Reserve already-authorized noninterruptible work, include
judges and provider tools, reconcile actual charges, and stop on an
instrumentation or protocol defect. A small budget should produce a decision
or a clearly documented limit, not a claim that a small sample proves
production-wide quality.

## Persistent development guidance

The development contract remains in
[`CLAUDE.md`](https://github.com/blisspixel/primr/blob/main/CLAUDE.md).
`AGENTS.md` retains its deliberate role as the operating guide. The refinement
adds evidence-specific verification, source and history checks, use of the
existing AST dependency graph, precise status claims, and resumable state in
the existing gitignored `.agent/` directory. It preserves the Python stack,
canonical seams, spending gate, local-first boundary, and release policy.

Commands were checked against the manifests, current tool behavior, and CI.
The primary CI environment includes all extras; its five sequential test
shards contribute to one 81 percent branch-coverage gate. Local verification
uses `uv run --no-sync` to reuse the prepared environment, while dependency
exports continue to use CI's pinned uv version. Mypy has a mixed existing
baseline with module-specific stronger checks, rather than universal strict
coverage; the new MCP configuration boundary joins that stronger set.
[uv environment synchronization](https://docs.astral.sh/uv/concepts/projects/sync/),
[mypy guidance for existing code](https://mypy.readthedocs.io/en/stable/existing_code.html).

## Validation and limits

Local checks passed for the real HTTP transport and Azure configuration
(68 tests), portable plugin packaging and installed state (10 tests), and the
existing architecture ratchets. The generated Bicep template compiles. Ruff,
mypy, strict documentation, static security checks, dependency auditing,
source-distribution inspection, and the separate recovery floor passed during
this review. Dry-run tests exposed local gateway configuration leakage; the
fixture now isolates that setting and all 35 handler cases pass.

The local full-suite run completed the protocol, agentic/property, and provider
groups. Windows event-loop setup stalled during the core retry, so it is not
reported as a complete suite or combined coverage result. The release remains
gated on the existing CI matrix, its 81 percent combined branch-coverage floor,
and an independent successful run on the exact main commit. The pull request
and release workflow carry the final run evidence; baseline CI does not prove
this patch.

This review validates primary-source contracts and local implementation
behavior. It does not claim a live acceptance run in every named host,
production cloud deployment, full OAuth interoperability, Tasks support, or
new paid report-quality evidence. Those limits define subsequent acceptance
work rather than weakening the requirements for the behavior implemented now.

## Source register

All external sources were accessed September 13, 2026. Undated living documents
are identified as such; an access date is not a publication date.

| Publisher | Source | Publication or revision | Use |
|---|---|---|---|
| Model Context Protocol | [Core specification](https://modelcontextprotocol.io/specification/2026-07-28) and [changes](https://modelcontextprotocol.io/specification/2026-07-28/changelog) | 2026-07-28 | Current protocol generation and extension separation |
| Model Context Protocol | [Transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) | 2026-07-28 | HTTP security and transport behavior |
| Model Context Protocol | [Tasks](https://modelcontextprotocol.io/extensions/tasks/overview) | Living extension documentation | Future durable-job adapter boundary |
| MCP Python SDK maintainers | [v2.2.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0) | 2026-09-07 | SDK currency and implementation limitations |
| Agent Plugins | [Specification](https://agent-plugins.org/specification), [schemas](https://agent-plugins.org/schemas) | Published v1.0.0; living pages | Package/runtime contract and schema comparison |
| Microsoft | [VS Code MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers#configure-the-mcpjson-file) | Living documentation | Native client configuration shape |
| Wang et al. | [Time to REFLECT](https://arxiv.org/abs/2605.19196) | 2026-05-18; preprint | Controlled research-agent error evaluation |
| Kohli | [Nine Judges, Two Effective Votes](https://arxiv.org/abs/2605.29800) | 2026-05-28; preprint | Correlated judge mistakes |
| Sun et al. | [Trust-Truth Separability](https://arxiv.org/abs/2608.21097) | 2026-08-21; preprint | Source-attribution sensitivity |
| Association for Computational Linguistics | [VeriFact](https://aclanthology.org/2025.emnlp-main.905/) | EMNLP, November 2025 | Long-form factual precision and recall |
| xAI | [Cost tracking](https://docs.x.ai/developers/cost-tracking) | Living documentation | Exact request-level charges |
| OpenRouter | [Accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting), [routing](https://openrouter.ai/docs/guides/routing/provider-selection) | Living documentation | Charge provenance and price-ceiling scope |
| Anthropic | [Claude Code costs](https://code.claude.com/docs/en/costs) | Living documentation | Host usage estimates versus subscription billing |
| Astral | [Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/) | Living documentation | Verification environment behavior |
| Mypy maintainers | [Existing codebases](https://mypy.readthedocs.io/en/stable/existing_code.html) | Living documentation | Incremental type-checking boundaries |

Repository evidence: [Next Steps](NEXT_STEPS.md),
[product contract](design/company-analyst-product-contract.md),
[evaluation plan](design/eval-plan.md),
[Premium evaluation design](design/premium-quality-eval.md),
[architecture cohesion plan](design/24-architecture-cohesion-plan.md), and
[agent control-plane design](design/2.0-agent-control-plane.md).
