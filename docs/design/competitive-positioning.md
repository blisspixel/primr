# Competitive positioning (working notes)

Last research refresh: 2026-08-01.

This note is for contributors and agents choosing what to build next. It is not
marketing copy. The goal is to do Primr's job carefully and well — not to claim
a category or put other tools down.

`ROADMAP.md` still owns priority order. `docs/NEXT_STEPS.md` owns the short
execution brief. This doc owns a plain answer to: what is Primr for, what else
people use, and where we should stay humble.

## What Primr is for

Primr turns a company website into a sourced strategic intelligence brief.

It is built for people who want:

- A structured first draft for discovery, account planning, diligence, or
  strategy work
- Research that includes public primary signals (site content, DNS/recon,
  hiring signals, and other public evidence when collectors work)
- Explicit uncertainty (Confirmed / Reported / Estimated / Hypothesis)
- Local ownership of artifacts (Markdown, DOCX, and related sidecars)
- Cost-aware runs (dry-run estimates and approval before billable work)
- Agent-host use with the same product shape (including Primr Zero when the
  host does the reasoning)

It is not a generic web crawler, a continuous competitive-intelligence SaaS, a
chat product, a model-serving platform, or a tool for bypassing authentication
or paywalls.

## How people already get company research done

Other tools are good at parts of this job. Treat them as real alternatives.

### Chat deep research

Examples include ChatGPT Deep Research, Claude and Gemini research-style
workflows, and Perplexity / Sonar-style research. Provider deep-research APIs
are also building blocks for custom agents.

**Often strong at:** speed, conversation UX, broad synthesis, using an existing
plan allowance.

**Usually weaker at (relative to Primr's aims):** local pipeline ownership,
hard cost gates for automation, recon and hiring-style primary signals, and a
stable consultant-style artifact contract with confidence labels.

**Implication:** for a quick pre-call sketch, chat research is often enough.
Primr is for when someone wants the pipeline, artifacts, and spend discipline.

### Enterprise competitive intelligence and market data

Examples include Crayon, Klue, AlphaSense, SimilarWeb, SEMrush, and similar
platforms.

**Often strong at:** continuous monitoring, team workflows, battlecards,
traffic/SEO/market datasets.

**Usually weaker at (relative to Primr's aims):** local-first single-job
execution, operator-owned files, and agent cost-gated research as a CLI/MCP
role.

**Implication:** Primr should not try to become always-on monitoring SaaS.
That work is deliberately out of scope. If someone needs continuous CI, they
should use tools built for it — or schedule Primr externally and, later, a
delta-style re-run.

### Research and scrape APIs for agents

Examples include Firecrawl, Tavily, Exa, and related search/extract APIs.

**Often strong at:** structured extraction, agent data layers, batch fetch,
developer-friendly credits.

**Usually weaker at (relative to Primr's aims):** end-to-end strategic briefs,
recon/hiring integration, strategy modules, and Primr's estimate/approval
story.

**Implication:** these can be complementary collectors. Primr can stay the
synthesis, labeling, strategy, and governance layer if we ever plug them in
behind the evidence packet. That would be integration, not surrender of the
product boundary.

## Primr's bet (without overclaiming)

We are trying to do one combination well:

1. Primary public signals, not only search summaries
2. Consultant-shaped outputs with uncertainty labels
3. Local artifacts and optional host-plan synthesis (Primr Zero)
4. Explicit spend approval for billable paths
5. Agent surfaces (MCP/A2A/skills) that stay bounded and auditable

That combination is useful. It is not “the only” serious way to research a
company. Chat tools, CI platforms, and custom agent stacks will remain good
choices for many users. Success means Primr is **reliable and clear on the jobs
it claims**, not that it replaces everything else.

## Strengths to protect

- Primary-signal collection when collectors succeed (site access recovery,
  recon, hiring adapters)
- Cost gate and dry-run discipline
- Confidence labels plus verify/calibrate tooling (still unfinished as product
  proof)
- Same deliverable shape across provider-backed, host-assisted, and local
  routes when quality holds
- Body-free control-plane resources for agents

## Gaps to treat honestly

- Epistemic quality is better instrumented than it is finished; hard gates stay
  report-only until evidence supports arming them
- Host and local quality vs cloud is not fully measured or promoted
- Full runs can be slow compared with chat deep research
- Cross-run memory and strategy-delta are not yet the default experience
- Full-report execution still carries some dual-provider-era assumptions
- Public examples and “when to use Primr” guidance are thinner than the code

## Non-goals (still binding)

From the roadmap and product docs, do not pivot into:

- A browser-first app or collaboration suite
- Always-on company watching as a core service
- A generic scraping framework product
- A plugin marketplace

If scope pressure appears, prefer thinner exports and scheduled external runs
over turning Primr into a daemon or SaaS CI clone.

## How to talk about Primr

Prefer plain comparisons:

- “Primr is one way to produce a sourced company brief with primary signals and
  local artifacts.”
- “Compared with chat deep research, we trade some speed and UX for pipeline
  control, cost gates, and signal types chat often skips.”
- “We still have work on label calibration, backend freedom, and cross-run
  memory.”

Avoid:

- “The only…”
- “The standard…”
- “No one else…”
- Victory language about markets we have not earned

Tone for docs and commits: ambitious about craft, modest about claims. We want
the work to be exceptional; we do not need the prose to sound like it already
is.

## Near-term product implications

These follow from the landscape above; they do not reorder the roadmap by
themselves:

1. Keep epistemic validation and measured host/cloud comparison high priority.
2. Improve time-to-first-useful artifact without dropping the full brief
   contract.
3. Advance memory / delta when quality foundations allow, so re-runs can get
   sharper instead of colder.
4. Document when Primr is a good fit vs chat research vs CI SaaS — comparatively,
   not competitively bombastic.
5. Consider external research APIs only as optional collection backends behind
   existing safety and evidence seams.

## Validation cost

- Free: doc updates, offline fixtures, standing corpora, dry-run estimates.
- Paid: live host-vs-cloud comparisons, multi-report calibration on production
  artifacts, any claim that host or local quality matches a cloud baseline.

Do not promote a backend or arm a hard quality gate from marketing preference
or a single small run.

## Explicitly not

- A sales battlecard against named vendors with ranking scores
- A promise that Primr Zero is free of all host billing (hosts vary; disclose)
- A redesign of Primr into continuous monitoring

When the external landscape shifts, refresh the date at the top and keep the
tone the same: curious, specific, and humble.
