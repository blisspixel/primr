# Research Tradecraft: From Collection-First to Hypothesis-First

Status: IN PROGRESS — methodology shift for the 1.x→2.0 quality line.
**Steps 1-3 (framing, Day-1 hypothesis tree, `--plan` checkpoint) are SHIPPED**
(see the per-step status notes below); Steps 4-7 remain. Steps 4-7 are where the
methodology starts changing *output quality* and so need the eval/live
validation noted per step (a real run with `GEMINI_API_KEY` + `XAI_API_KEY`),
not just deterministic seam tests.
ROADMAP anchors: subsumes and deepens Active Queue #4 (consultant-grade
writing); reuses the calibration/verify instruments from
[`1x-completion.md`](1x-completion.md) workstream 1; depends on the #23
orchestrator refactor (DONE) that made the pipeline a sequence of injectable
`fast_run_*.py` stages.

## Why this doc exists

The product's *philosophy* already says the right thing — "hypothesis
generation over premature conclusions," "the pipeline is the product." The
*flow* does not yet live up to it. This doc names how the best research
organizations actually work, measures Primr's real pipeline against that bar
(grounded in the code, not the README), and lays out the dependency-ordered
work to close the gap. The thesis in one line:

> **Elite teams plan the argument before they gather the evidence, and treat
> falsification and calibrated uncertainty as the core craft. Primr today
> gathers the evidence, then assembles a fixed template. We should invert it.**

## How the best teams work (the spine)

Seven practices recur across strategy consulting, investment diligence,
intelligence analysis, and elite product teams. They rhyme.

1. **Issue-driven / answer-first (McKinsey, Bain).** Start from the *question*,
   form a Day-1 hypothesis, build a MECE issue tree, and gather *only* the data
   that confirms or refutes a branch. 80/20: a complete provisional answer on
   day one, refined — not "collect everything, then see."

2. **Work backwards from the output (Amazon PR/FAQ; the consulting "ghost
   deck").** Write the headline claims of the deliverable *before* doing the
   analysis, then go prove or kill each headline. The empty storyboard is the
   plan.

3. **Pyramid Principle (Minto).** Communicate top-down: governing thesis →
   MECE supporting arguments → evidence. SCQA framing. Every fact ladders up to
   a "so what"; no data without an implication.

4. **Analysis of Competing Hypotheses + Structured Analytic Techniques
   (CIA tradecraft, Heuer).** Enumerate rival explanations, score evidence by
   its *diagnosticity* (which evidence discriminates between hypotheses), and
   try to *refute*, not confirm. Key-assumptions check, pre-mortem, devil's
   advocate before committing.

5. **Graded sources + calibrated estimative language (Admiralty/NATO code;
   ICD 203 / Sherman Kent).** Rate evidence on two axes — source *reliability* ×
   information *credibility* — and state *likelihood* separately from *analytic
   confidence*. "Probably (70-85%), high confidence" is a different claim than
   "probably, low confidence."

6. **Triangulation and primary signal.** Any load-bearing claim needs multiple
   independent sources; the sharpest signal is primary (filings, postings,
   channel checks) not the article *about* the company. (Primr's DNS-recon +
   hiring-signal layer is exactly this instinct — it just doesn't yet *drive*
   the analysis.)

7. **Shape before you build; align at a checkpoint (Shape Up; Google/Stripe
   RFCs).** Fixed appetite, variable scope. A written plan reviewed at a
   betting table / Day-1 answer review *before* the expensive work starts.

The two unifying moves: **plan the argument before gathering evidence**, and
**make falsification + calibrated uncertainty the discipline**, not an
afterthought.

## What Primr actually does today (code-grounded)

Verified against the `perform_fast_research` coordinator and its stage modules.
The pipeline is **DATA-FIRST-THEN-ANALYZE**, the opposite of the spine above.

| Elite practice | Primr today | Evidence |
|---|---|---|
| Frame the engagement question | No first-class framing. `--discovery-notes`/`--context`/`--strategy-type` reach **only Phase 6 strategy**, never collection/analysis/writing | `fast_run_strategy.py` is the sole consumer; not threaded to Phases 1–4 |
| Day-1 hypothesis tree from cheap signals | Hypotheses generated **after** full collection, inside the Phase-3 workbook, as a passive "3–5 hypotheses" list. The `agentic` `Hypothesis` model exists but is **unused** in fast mode | `fast_run_workbook.py`, `section_prompts.py` (workbook prompt); `agentic/models.py` Hypothesis unused by `perform_fast_research` |
| Ghost deck / argument outline before evidence | Fixed **23-section template, always written**. "Adaptive" = word-count tuning + constrained-evidence mode, not section selection | `config` `company_overview.yaml` (23 hardcoded sections); `section_planning.py` groups, never drops |
| Targeted, hypothesis-steered collection | **Blind broad scrape** (≈50 pages) + **reactive gap-fill** (search for missing *data*, not to test a *claim*) | `fast_run_collection.py` (no hypothesis filter); `fast_run_gaps.py` (data-gap queries) |
| ACH / pre-mortem / refute | Cross-validation resolves *contradictions* and re-writes weak sections; `primr refine` optimizes the artifact-*discipline* score | `fast_run_validation.py`; `core/refine.py` |
| Two-axis source grading; confidence≠likelihood | Single-axis 4-label scheme `(Confirmed)/(Reported)/(Estimated)/(Hypothesis)`; calibration now *measured* | `qa/report_analyzer.py`, `qa/label_calibration.py` |
| Align at a plan checkpoint before spend | Only a **cost Y/n** prompt; everything after is autonomous to DOCX | `research_agent.py` cost confirmation |

The engine (9-tier scraping, recon, hiring signals, failover, eval harness) is
genuinely strong and ahead of the field on the *evals-as-progress* axis. The
gap is not the engine — it is that **the engine serves a template, not an
argument.**

## The work, in dependency order

Each step is independently shippable and makes the next reviewable. Mapped to
the user's frame: *approach · prep · plan · align · refine · design.*

### 1. Framing as a first-class input  (prep)  — SHIPPED

> **Status: SHIPPED** (`core/research_framing.py`). `ResearchFraming`
> (purpose/audience/decision/core-question + discovery notes) resolves once via
> `resolve_run_framing` and threads into the analysis workbook and section
> prompts; operator flags `--purpose/--audience/--decision/--question`. Unframed
> runs are byte-identical (empty prompt block). Step 1a = the seam + threading;
> Step 1b = the CLI surface.

Promote "what is this research *for*" to a typed object threaded through every
phase — purpose (sales pursuit / diligence / competitive intel / partnership),
audience, the decision it informs, and the core question. `--discovery-notes`
and `--context` fold into it; `--strategy-type` becomes one facet.

- New `ResearchFraming` dataclass; resolved once, passed to collection,
  deepening, workbook, and section writing — not just strategy.
- Pure plumbing + one resolver prompt. **Validation: free** (deterministic
  seam tests; a framing object changes which prompts fire, assertable without
  LLM calls).

### 2. Day-1 hypothesis tree from cheap signals  (prep → plan)  — SHIPPED

> **Status: SHIPPED** (`core/hypothesis_tree.py`). MECE issue tree of
> build-to-refute `DiagnosticHypothesis` nodes (supporting/counter slots +
> diagnostic test question, confidence reusing the `agentic` `ConfidenceLevel`),
> with `hypothesis_tree.{md,json}` artifacts. Wired into the workbook stage
> (Step 2b): when a run is framed, the tree is formed from the cheap signals,
> saved, and prepended so the workbook is hypothesis-driven. Fail-soft;
> gated on `framing.is_specified` so unframed runs are unchanged.

Generate a MECE issue tree *before* expensive collection, from recon + homepage
+ hiring signals (the cheap layer Primr already gathers in Phase 0/early
Phase 1). Reuse the dormant `agentic` `Hypothesis` model. Each node carries
supporting/counter evidence slots, a diagnostic test question, and a
confidence — i.e., it is *built to be refuted*.

- Output artifact `hypothesis_tree.{md,json}` in the working dir, like the
  skill-pack `role_plan`. **Validation: free** to build (mocked recon/homepage
  inputs); quality judged later by the eval harness.

### 3. Plan-preview + alignment checkpoint  (align)  — SHIPPED

> **Status: SHIPPED** (`core/cli_plan.py`). `primr <co> <url> --plan` previews
> the framing + Day-1 hypothesis tree (from free recon + the cheap signal layer)
> + the proposed report outline, writes `plan.md` + `hypothesis_tree.{md,json}`,
> and exits before any expensive collection or writing. Fail-soft; no spend
> beyond the cheap tree pass. The agent-facing approval-token variant folds into
> the 2.0 control-plane work and is not yet built.

`primr <co> <url> --plan` (and a plan-preview gate on full runs, opt-in)
surfaces the framing + hypothesis tree + proposed argument outline, lets the
operator edit/approve/prune branches, *then* spends. This is the betting table
/ Day-1 review. It doubles as the **agent-facing** approval seam (an MCP caller
approves a plan token before the run commits budget) — folds cleanly into the
2.0 control-plane authz work.

- Mirrors the existing skill-pack `--plan-only` / `--from-plan` pattern.
  **Validation: free** (the plan renders and round-trips through edit without
  any paid call).

### 4. Hypothesis-steered collection  (approach)

Derive the Phase-1 scrape targets and Phase-2 search queries from the tree:
each retrieval *tests a branch*; branches that come up empty or refuted are
pruned (logged, never silently). Gap analysis shifts from "we lack data X" to
"hypothesis Y is under-evidenced — test it."

- Refactor inside `fast_run_collection.py` / `fast_run_gaps.py` behind the
  existing injectable seams. **Validation: free** for the routing logic; one
  live run to confirm the scrape budget lands on higher-signal pages
  (≈ standard run cost, pre-registered).

### 5. Argument-derived report structure  (design)

Replace the always-23 skeleton with an outline *derived from* the framing +
tree, rendered Pyramid-Principle style: governing thesis → MECE supporting
lines → evidence, each section ending in an explicit "so what." Sparse
companies get a tighter, honest tree; rich companies get a deeper one. This
**is** ROADMAP #4, deepened from "tune the prompts" to "let the argument decide
the sections."

- The riskiest, highest-value step. **Validation: eval-judged** — pre-register
  acceptance criteria, 2–3 corpus passes (~$4–5 each at the standard recipe),
  judged by the step-1 calibration/verify instruments so "better" is measured,
  not vibes.

### 6. Adversarial refine: ACH + pre-mortem  (refine)

Add a red-team pass that *tries to refute* the governing thesis and runs a
key-assumptions / pre-mortem check on the argument — distinct from today's
contradiction-resolution (which fixes local inconsistencies, not the thesis).
Gate acceptance on a signal the discipline score can't see (reuses the
anti-Goodhart guard from `1x-completion.md` workstream 1).

- **Validation:** free to wire (mocked judges); quality measured on the same
  corpus passes as step 5.

### 7. Two-axis evidence grading + likelihood/confidence split  (design)

Upgrade the label system toward intelligence tradecraft: source *reliability* ×
claim *credibility*, and state *likelihood* separately from *analytic
confidence* (ICD 203). The calibration harness already audits label
traceability; extend it to the second axis.

- **Validation:** harness extension is free; one calibration pass to baseline
  the new axes (~$0.10, per workstream 1's costing).

## Exit criteria (tradecraft done)

1. A run is *framed*: purpose/audience/decision/question shape every phase, not
   just the strategy appendix.
2. A Day-1 hypothesis tree exists *before* expensive collection and **steers**
   it; refuted branches are pruned and logged.
3. `--plan` surfaces framing + tree + outline for human or agent approval
   before budget is committed.
4. The report's section structure is *derived from the argument*, not a fixed
   template; every section ladders to a "so what."
5. An adversarial pass refutes the governing thesis before shipping.
6. Confidence is two-axis and separates likelihood from analytic confidence,
   with measured calibration on both.
7. On the standing eval corpus, sparse- and rich-company runs both clear
   pre-registered acceptance, judged by the calibration/verify instruments.

## Explicitly not

- **Not a DAG/agent framework.** The tree is a *plan artifact*, not a runtime
  graph engine; the pipeline stays a linear sequence of injectable stages.
  (Reaffirms the standing "Why Not a Research DAG" non-goal.)
- **Not a chat agent or always-on watcher.** Framing and `--plan` are a single
  pre-run checkpoint, not a conversation. Loops/scheduling stay consumer-side.
- **Not a new output surface.** This sharpens the *existing* report/strategy
  artifacts; the one-pager/JSON modes from `1x-completion.md` are separate.
- **No primary-research automation.** Expert calls / channel checks are how
  humans extend this; Primr surfaces *where* a human should make them (open
  hypothesis branches), it does not place them.
