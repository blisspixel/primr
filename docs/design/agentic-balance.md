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

- "Blind broad scrape (≈50 pages)" — `fast_run_collection.py`, no hypothesis
  filter. The set of pages is fixed by the harness, not chosen by judgment.
- "Reactive gap-fill (search for missing *data*, not to test a *claim*)" —
  `fast_run_gaps.py`. Fills holes in a template, does not pursue a question.

That is exactly the "open-ended problem hardcoded as a fixed path" the criterion
warns against: *what to read about a company* cannot be enumerated in advance.
Tradecraft Steps 4–7 are the Level-2 upgrades, each at a decision point the
harness still owns:

| Tradecraft step | Decision handed to the model | Loop still owned by harness |
|-----------------|------------------------------|-----------------------------|
| 4 — hypothesis-steered collection | *Which pages/queries test the open hypotheses* | Stage order, page cap, retries |
| 5 — argument-derived structure | *What the report's sections should be, from the argument* | Render pipeline, validation |
| 6 — adversarial refine (ACH / pre-mortem) | *Whether the governing thesis survives refutation* | Bounded number of refine rounds |
| 7 — two-axis evidence grading | *Likelihood vs analytic confidence per claim* | Where grades attach in the artifact |

## The four principles to apply when refining

### 1. Regularize toward the rule. Add judgment only when a fixed path falls short.

Both sources say start simple. Anthropic: "find the simplest solution possible,
and only increasing complexity when needed... only when it demonstrably improves
outcomes." smolagents is blunter:

> "If that deterministic workflow fits all queries, by all means just code
> everything! ... it's advised to regularize towards not using any agentic
> behaviour."

Application: the spine stays rule-based. Orchestration, scrape-tier escalation,
HTTP client selection, atomic writes, retries, the cost estimate, rendering —
these are well-defined tasks; workflows win on predictability. Do not agentify
the plumbing. The bar for promoting a component to "judgment" is that the fixed
path *demonstrably falls short too often*, not that judgment feels more modern.

### 2. Go agentic only where the path genuinely can't be hardcoded.

The legitimate Level-2 decision points in primr are about *content*, never
*control flow*: what to collect (4), how to structure the argument (5), whether
the thesis holds (6), how strong each claim is (7). If you can write the
decision as an `if/else` that stays correct across companies, it is a rule —
keep it one.

### 3. Gate the irreversible actions, not the reasoning (the keep-list).

NVIDIA locates the risk precisely:

> "the risk associated with these systems lies mostly in the tools or plugins
> available to those systems."

So guardrails belong on *actions with external consequence*, and reasoning stays
unconstrained. primr already does this and it is the pattern to preserve as
collection gets more agentic:

- **Spend** — the cost gate (estimate + explicit approval before any billable
  run). Non-negotiable.
- **Egress** — every outbound URL through `utils.security.is_safe_url`
  (validated post-redirect).
- **Disk** — state writes through `utils.atomic_io`.

A more judgment-driven Step 4 does not loosen any of these. It makes the model
*choose better targets*; the SSRF guard still vets every fetch and the cost gate
still bounds the spend. Never put a guardrail on the thinking; only on the act.

### 4. Completion is decided by ground truth, not a self-reported flag.

The most-cited long-running-agent failure is self-declared done. Anthropic,
[Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents):

> "Claude's tendency to mark a feature as complete without proper testing."

The fix is external verification: "Only mark features as 'passing' after careful
testing," validated against real behaviour. The primr analogue is the
`core/refine.py` "artifact-discipline score" — a *proxy* for quality, and a
proxy is a self-report dressed as a metric. Tradecraft Step 7 is the
ground-truth gate: a run is done when the governing thesis has survived an
adversarial pass (Step 6) and each claim carries a likelihood/confidence grade,
not when the pipeline reaches its last stage. Build completion checks that read
the artifact's *substance*, not its *form*.

## The coupling the sources don't name: agentic collection needs a budget

This is the one design consequence specific to primr. A blind 50-page scrape is
expensive but *boundable* — you can estimate it before the run, which is what
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
   sequences — or is it about control flow?** Only the former is a legitimate
   Level-2 upgrade (Principle 2). Control-flow autonomy is out of scope by the
   "not a DAG engine" non-goal.
3. **What does it touch — reasoning, or an irreversible act (spend, egress,
   disk)?** Guard the act, never the reasoning (Principle 3). If it touches
   spend, it needs a budget the model paces against (the coupling above).

Then make sure "done" is judged by the artifact's substance, not a flag
(Principle 4).

## Sources

- Anthropic, [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — the workflow-vs-agent definitions and decision criterion; "start simple."
- Anthropic, [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — hardcoded logic creates fragility; "less structure, more model."
- Anthropic, [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — self-declared completion is unreliable; verify against ground truth.
- NVIDIA, [Agentic Autonomy Levels and Security](https://developer.nvidia.com/blog/agentic-autonomy-levels-and-security/) — risk lives in the tools/actions; Levels 0–3 taxonomy.
- HuggingFace, [smolagents: Introduction to Agents](https://huggingface.co/docs/smolagents/en/conceptual_guides/intro_agents) — agency as a spectrum; regularize toward not-agentic when a fixed path fits.

> Have a deeper local research artifact (e.g. an `AGENTIC_BALANCE.md` deep-research
> output) you want folded in as the canonical source set? Point to it and this
> doc absorbs it rather than duplicating it.
