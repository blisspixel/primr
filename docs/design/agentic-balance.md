# Agentic balance: where primr uses judgment, where it uses rules

> A decision aid, not a manifesto. Read it when you are about to make part of
> primr "smarter" and are unsure whether to hardcode the path or let the model
> drive. It exists because that choice recurs across the tradecraft work
> ([research-tradecraft.md](research-tradecraft.md)), and getting it wrong in
> either direction is expensive: too rigid and the brief is shallow, too loose
> and the run is unpredictable and unbounded.

## The axis

The industry has converged on one distinction, and it is the whole axis.
Anthropic, [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents):

- **Workflow** = "systems where LLMs and tools are orchestrated through
  predefined code paths." (Deterministic. The *rule*.)
- **Agent** = "systems where LLMs dynamically direct their own processes and
  tool usage, maintaining control over how they accomplish tasks." (The
  *judgment*.)

The decision criterion, verbatim:

> "Workflows offer predictability and consistency for well-defined tasks,
> whereas agents are the better option when flexibility and model-driven
> decision-making are needed at scale."

And the trigger for going agentic at all:

> Agents suit "open-ended problems where it's difficult or impossible to
> predict the required number of steps, and where you can't hardcode a fixed
> path."

"Agentic" is not binary. [smolagents](https://huggingface.co/docs/smolagents/en/conceptual_guides/intro_agents)
frames agency as a continuous spectrum (simple processor → router → tool-call →
multi-step loop → multi-agent). [NVIDIA](https://developer.nvidia.com/blog/agentic-autonomy-levels-and-security/)
quantizes the same spectrum into levels that matter for *risk*:

| Level | Name | Who controls flow |
|------:|------|-------------------|
| 0 | Inference API | One model call per request |
| 1 | Deterministic system | Multiple calls in a fixed order |
| 2 | Weakly autonomous | Model decides *whether* to act **at predetermined decision points** |
| 3 | Fully autonomous | Model decides *if/when/how*, revises its own plan continuously |

## primr's position: Level 2, on purpose

primr is **not** trying to become a Level-3 agent, and the tradecraft work is
not a step toward one. The standing non-goal is explicit
([research-tradecraft.md](research-tradecraft.md) "Explicitly not"):

> "Not a DAG/agent framework. The tree is a *plan artifact*, not a runtime
> graph engine; the pipeline stays a linear sequence of injectable stages."

So the target is **Level 2**: the control flow (the orchestrator's stage
sequence) stays deterministic and enumerable, and the model exercises judgment
*inside* fixed decision points. That reconciles the two forces that otherwise
look contradictory:

- The "less structure, more model" direction. Anthropic,
  [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents):
  hardcoding logic to force exact behaviour "creates fragility and increases
  maintenance complexity over time," and "as model capabilities improve,
  agentic design will trend towards letting intelligent models act
  intelligently, with progressively less human curation."
- primr's hard constraints: a non-negotiable cost gate, the single-job design,
  and "not a DAG engine."

Level 2 is how both hold at once: **give the model the decision, keep the
harness in control of the loop.**

## What today's primr gets wrong (and the tradecraft work fixes)

primr today is Level 1 where it should be Level 2. Its collection is a
*predefined path* dressed up as research
([research-tradecraft.md](research-tradecraft.md), code-grounded table):

- "Blind broad scrape (≈50 pages)" - `fast_run_collection.py`, no hypothesis
  filter. The set of pages is fixed by the harness, not chosen by judgment.
- "Reactive gap-fill (search for missing *data*, not to test a *claim*)" -
  `fast_run_gaps.py`. Fills holes in a template, does not pursue a question.

That is exactly the "open-ended problem hardcoded as a fixed path" the criterion
warns against: *what to read about a company* cannot be enumerated in advance.
Tradecraft Steps 4-7 are the Level-2 upgrades, each at a decision point the
harness still owns:

| Tradecraft step | Decision handed to the model | Loop still owned by harness |
|-----------------|------------------------------|-----------------------------|
| 4 - hypothesis-steered collection | *Which pages/queries test the open hypotheses* | Stage order, page cap, retries |
| 5 - argument-derived structure | *What the report's sections should be, from the argument* | Render pipeline, validation |
| 6 - adversarial refine (ACH / pre-mortem) | *Whether the governing thesis survives refutation* | Bounded number of refine rounds |
| 7 - two-axis evidence grading | *Likelihood vs analytic confidence per claim* | Where grades attach in the artifact |

## The four principles to apply when refining

### 1. Regularize toward the rule. Add judgment only when a fixed path falls short.

Both sources say start simple. Anthropic: "find the simplest solution possible,
and only increasing complexity when needed... only when it demonstrably improves
outcomes." smolagents is blunter:

> "If that deterministic workflow fits all queries, by all means just code
> everything! ... it's advised to regularize towards not using any agentic
> behaviour."

Application: the spine stays rule-based. Orchestration, scrape-tier escalation,
HTTP client selection, atomic writes, retries, the cost estimate, rendering -
these are well-defined tasks; workflows win on predictability. Do not agentify
the plumbing. The bar for promoting a component to "judgment" is that the fixed
path *demonstrably falls short too often*, not that judgment feels more modern.

### 2. Go agentic only where the path genuinely can't be hardcoded.

The legitimate Level-2 decision points in primr are about *content*, never
*control flow*: what to collect (4), how the analysis reasons within the
report (the argument/insight per section), whether the thesis holds (6), how
strong each claim is (7). If you can write the decision as an `if/else` that
stays correct across companies, it is a rule - keep it one.

**Carve-out - the report's section *structure* is a rule, on purpose.** Which
sections a strategic brief contains (the 23-section scaffold in
`config/company_overview.yaml`) is **not** a per-run agentic decision, even
though "structure the argument" sounds like judgment. A great deliverable's
shape is a *known, stable thing*: you research and iterate it **offline** in the
curated YAML, version-controlled, improved deliberately - you do not re-derive it
each run. Consistency is a feature here, not a limitation; rolling per-run
structural dice trades reliability for variability nobody wants in a strategic
report. By Principle 1's own test the fixed scaffold does not demonstrably fall
short, so it stays a rule. The model's judgment goes into the *content within*
each section (depth, insight, strategy, industry understanding), not into picking
the sections. (This overrides the earlier "argument-derived structure" framing of
tradecraft Step 5 - see [research-tradecraft.md](research-tradecraft.md).)

### 3. Gate the irreversible actions, not the reasoning (the keep-list).

NVIDIA locates the risk precisely:

> "the risk associated with these systems lies mostly in the tools or plugins
> available to those systems."

So guardrails belong on *actions with external consequence*, and reasoning stays
unconstrained. primr already does this and it is the pattern to preserve as
collection gets more agentic:

- **Spend** - the cost gate (estimate + explicit approval before any billable
  run). Non-negotiable.
- **Egress** - every outbound URL through `utils.security.is_safe_url`
  (validated post-redirect).
- **Disk** - state writes through `utils.atomic_io`.

A more judgment-driven Step 4 does not loosen any of these. It makes the model
*choose better targets*; the SSRF guard still vets every fetch and the cost gate
still bounds the spend. Never put a guardrail on the thinking; only on the act.

### 4. Completion is decided by ground truth, not a self-reported flag.

The most-cited long-running-agent failure is self-declared done. Anthropic,
[Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents):

> "Claude's tendency to mark a feature as complete without proper testing."

The fix is external verification: "Only mark features as 'passing' after careful
testing," validated against real behaviour. The primr analogue is the
`core/refine.py` "artifact-discipline score" - a *proxy* for quality, and a
proxy is a self-report dressed as a metric. Tradecraft Step 7 is the
ground-truth gate: a run is done when the governing thesis has survived an
adversarial pass (Step 6) and each claim carries a likelihood/confidence grade,
not when the pipeline reaches its last stage. Build completion checks that read
the artifact's *substance*, not its *form*.

## The failure mode in both directions - and which one to fear here

The 2026 production consensus is blunt: **most agents fail not because the model
is weak but because the harness is brittle** - hardcoded branching that tries to
anticipate every path, and regex/format rules that "break the moment someone
adjusts the formatting." But the symmetric trap is just as real: handing
*validation* to a model is also brittle - LLM-judge verdicts swing on seed,
option order, and instruction placement by margins comparable to the gains they
claim to measure. Neither extreme is safe. The resolution the field landed on,
and the one this doc encodes:

> **Determinism on *structure and irreversible acts*; judgment on *content*;
> layered eval (not a regex) for *quality*.** Microsoft's June-2026 red-team
> taxonomy puts it the same way: deterministic *structure* (provenance, tiered
> approval) should govern processes, "not replaced by brittle output rules";
> the eval guides recommend layering deterministic format checks, heuristic
> scoring, LLM-as-judge, and human calibration rather than leaning on any one.

The concrete anti-pattern to refuse in primr: reaching for a regex or a hand-rule
the moment LLM-generated *content* is involved. A regex can only check shape, so
the instant you actually care about quality, argument strength, or relevance, a
rule is the wrong tool - it false-blocks good output and silently rots as prompts
evolve. **The default for anything touching model output is judgment, measured by
eval. A deterministic check is the exception**, and it earns its place only by
being genuinely stable. Do not present a rule and judgment as equal options and
"draw the line" between them - the burden is on the rule.

Two failure smells worth naming, because primr has shipped both:

- **The regex treadmill.** Scanning free-form prose for an open-ended marker
  vocabulary is brittle *by construction*. The scaffolding-leak scanner is the
  case study, not a model to copy: it kept missing new variants (colon-only, then
  space-separated, then bare `[workbook]`), each patched in after the fact - which
  is the failure, not the fix. The durable answer is *upstream* (prompt the writer
  not to emit the markers) plus an *eval metric* that measures leakage
  (`writer_output_clean`); any ship-time scan is a shrinking backstop that should
  trend toward zero work, never the mechanism. If a check needs a new case every
  time the model rephrases, it has already failed.
- **Quality-as-regex.** A deterministic gate on "is this analysis good / strong /
  complete / on-topic" cannot exist - that is the Level-2 judgment work (Steps
  4-7), enforced by the calibration/verify instruments against ground truth, never
  a hand-written rule.
- **Fact-match masquerading as validation.** A cited page existing, a citation
  resolving, or a phrase appearing in fetched text is not validation. Those are
  input-preparation and structural facts. Validation has to judge whether the
  evidence actually supports the claim, whether stronger contradictory evidence
  exists, whether the source is independent and authoritative enough for the
  label, whether the inference is warranted, and whether the artifact is honest
  about uncertainty. That is substance, so it belongs to layered eval and
  agreement-validated judgment, not a regex or string-overlap threshold.

What legitimately stays a rule is narrow: the irreversible-act guards (spend,
egress, disk - Principle 3) and **referential/structural validity that does not
change when prose is reworded** - does the DOCX render, is a `[cite: N]` token
(a marker the pipeline itself defines) resolvable to a `## Sources` entry, are
there duplicate top-level headings. primr's own instinct here was right:
required-section *presence* was deliberately left a QA *signal*, not a ship
blocker, "too false-positive-prone to block on."

Litmus test before adding any check: **would it need a new case every time the
model rephrases?** If yes, it is content-policing in a structure costume - push
the fix upstream and measure it with eval; do not grow the regex. Direct
corollary of Principle 4: substance is *measured*, not matched.

### The standing rule (cite this when reviewing roadmap/PR scope)

> **No new ship-time rule that judges content.** Quality, strength, completeness,
> relevance, label-correctness, "reads like a deliverable" - these are
> model-judgment, enforced *upstream* (the writer/author prompt) and *measured* by
> eval/calibration. A new deterministic gate is allowed ONLY for an irreversible
> act (spend, egress, disk) or prose-invariant structural validity (the DOCX
> renders, `[cite: N]` resolves, no duplicate `##`). Every existing content
> scanner (scaffolding-leak, the QA penalty score, the skill-pack heuristics) is a
> *shrinking backstop* that trends toward a signal, never a block, and never
> grows. If a check would need a new case when the model rephrases, it has already
> failed - delete it, fix the prompt, trust the eval.

This is the trap primr keeps walking back into: shipping a quality moat made of
regex. Refuse it at review time. A PR that adds a content gate must instead add
(or point to) the eval metric that supersedes it.

## Credential and billing boundary

The same rule-vs-judgment line applies to provider choice. primr's product is the
research harness, not a particular model account. API keys, local models,
enterprise gateways, and official host surfaces can all participate in the same
bounded pipeline, but authentication type alone does not establish billing mode.

The allowed pattern:

- **Direct provider APIs** for reproducible, programmatic runs where primr owns
  the model calls and can estimate token spend before launch.
- **Host-account runners** only when an official local/automation surface can
  accept a bounded content task and billing provenance can be proven or the
  operator explicitly acknowledges potentially metered API use. Primr keeps the
  pipeline sequence, egress, disk writes, and eval checks under its harness.
- **Local and gateway profiles** where the operator supplies an
  OpenAI-compatible server or enterprise endpoint, with the same capability
  routing and eval validation.

The disallowed pattern is treating a consumer subscription as an ordinary hidden
API key. Do not scrape browser sessions, reverse-engineer private endpoints, or
proxy through unofficial tools just to avoid API pricing. If Codex or Claude Code
exposes an official authenticated local or automation surface, that is necessary
but not sufficient for a public runner. Primr must also establish the billing
basis or require an explicit acknowledgment. Until then, the Codex transport is
internal/eval-only and the path stays API key, gateway, local, or host-native
`primr-zero`. Host OAuth tokens and session state never enter Primr.

For agentic balance, a host-account runner is just another Level-2 decision
point. The model may decide the content inside a stage; primr still decides which
stage runs, what evidence packet it receives, what budget or plan-limit policy
applies, what URLs may be fetched, where files may be written, and whether the
result clears semantic eval. Route metadata describes the declared policy but is
not proof of an external host session's billing. This is how a future
billing-verifiable host route can fit without turning primr into a Level-3 agent
or weakening the cost gate. Today, `primr-zero` is the supported plan-native
path after the host is verified not to bill API usage or overages.

## The coupling the sources don't name: agentic collection needs a budget

This is the one design consequence specific to primr. A blind 50-page scrape is
expensive but *boundable* - you can estimate it before the run, which is what
the cost gate depends on. Hypothesis-steered collection (Step 4) is cheaper on
average but *variable*: the model decides how deep to go, so a static pre-run
estimate stops being honest, and an honest pre-run estimate is the thing the
cost gate is built on.

Therefore Step 4 cannot ship as "let the model roam." It must ship as a
**budget-aware loop**: the collection decision point receives a token/dollar
budget it can see and self-moderates against, with the keep-list still
hard-stopping at the ceiling. This is the `task_budget` pattern (the model is
told its budget for the whole loop and paces itself), distinct from a hard
per-call cap. The same bounding applies to Step 6: a fixed maximum number of
refine rounds, not open-ended refutation.

Concretely: **going agentic on collection requires turning the cost gate from a
static pre-run estimate into a budget the decision point runs against.** Decide
that before building Step 4, not after.

## How to use this doc

When a change makes part of primr "smarter," answer three questions in order:

1. **Does a fixed path fall short here, often, across companies?** If no, keep
   it a rule (Principle 1). Most plumbing answers no.
2. **If yes, is the decision about content, at a point the harness still
   sequences - or is it about control flow?** Only the former is a legitimate
   Level-2 upgrade (Principle 2). Control-flow autonomy is out of scope by the
   "not a DAG engine" non-goal.
3. **What does it touch - reasoning, or an irreversible act (spend, egress,
   disk)?** Guard the act, never the reasoning (Principle 3). If it touches
   spend, it needs a budget the model paces against (the coupling above).

Then make sure "done" is judged by the artifact's substance, not a flag
(Principle 4).

## Sources

- Anthropic, [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) - the workflow-vs-agent definitions and decision criterion; "start simple."
- Anthropic, [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) - hardcoded logic creates fragility; "less structure, more model."
- Anthropic, [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) - self-declared completion is unreliable; verify against ground truth.
- NVIDIA, [Agentic Autonomy Levels and Security](https://developer.nvidia.com/blog/agentic-autonomy-levels-and-security/) - risk lives in the tools/actions; Levels 0-3 taxonomy.
- HuggingFace, [smolagents: Introduction to Agents](https://huggingface.co/docs/smolagents/en/conceptual_guides/intro_agents) - agency as a spectrum; regularize toward not-agentic when a fixed path fits.
- Microsoft Security, [Updating the Taxonomy of Failure Modes in Agentic AI Systems](https://www.microsoft.com/en-us/security/blog/2026/06/04/updating-taxonomy-failure-modes-agentic-ai-systems-year-red-teaming-taught-us/) (Jun 2026) - a year of red-teaming: brittle harnesses fail; deterministic *structure* governs processes, not brittle *output* rules.
- Adaline, [The Complete Guide to LLM & AI Agent Evaluation in 2026](https://www.adaline.ai/blog/complete-guide-llm-ai-agent-evaluation-2026) - layer deterministic format checks, heuristic scoring, LLM-as-judge, and human calibration; don't rely on regex gates for quality.
- [JudgeSense: A Benchmark for Prompt Sensitivity in LLM-as-a-Judge Systems](https://arxiv.org/html/2604.23478) (2026): a judge can be highly human-agreeing yet self-inconsistent under semantically equivalent prompts, so measure self-consistency, not just accuracy. The symmetric trap, evidence that swapping a brittle rule for a lone judge only moves the brittleness.
- [Diagnosing the Reliability of LLM-as-a-Judge via Item Response Theory](https://arxiv.org/pdf/2602.00521) (2026): single-judge verdicts are psychometrically unstable, so prefer multi-judge panels and agreement checks over a lone judge, and do not arm a hard gate from a small single-judge sample.
- OpenAI, [Codex authentication](https://developers.openai.com/codex/auth) and [Codex access tokens](https://developers.openai.com/codex/enterprise/access-tokens) - ChatGPT sign-in, API-key sign-in, and workspace access tokens are distinct credential modes.
- Anthropic, [Claude Code authentication](https://code.claude.com/docs/en/iam), [Claude Code costs](https://code.claude.com/docs/en/costs), and [using Claude Code with Pro or Max](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan) - subscription OAuth and API-key billing are distinct modes, with explicit user control before API credit usage.

> Have a deeper local research artifact (e.g. an `AGENTIC_BALANCE.md` deep-research
> output) you want folded in as the canonical source set? Point to it and this
> doc absorbs it rather than duplicating it.
