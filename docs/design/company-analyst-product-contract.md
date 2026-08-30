# Company Analyst Product Contract

Status: canonical product direction; implementation remains governed by
[`NEXT_STEPS.md`](../NEXT_STEPS.md) and measured promotion gates.

## Product in one sentence

Give Primr a company name and website. Primr researches the company and
produces an exceptional, evidence-grounded, long-form Strategic Overview plus
any selected YAML-defined strategy documents, delivered as polished Markdown
and Word artifacts.

```bash
primr "Company Name" https://company.example
```

That invocation is the product. Framing, hypotheses, source receipts,
capability routing, ledgers, provider recovery, and memory are supporting
machinery. They are valuable only when they improve the research, the strategic
insight, the report, or the reliability and economics of producing it.

## Non-negotiable core

The company name and website must be sufficient for a strong default run. The
operator must not need to design a research plan, select an ontology, understand
provider internals, or write a sophisticated prompt.

A successful default engagement:

1. researches the company broadly enough to support a complete strategic view;
2. uses first-party evidence plus independent external signals;
3. explains what the company does, how it creates value, who buys, and why;
4. assesses market position, differentiation, economics, leadership, risks,
   constraints, and strategic tensions;
5. identifies what appears to be changing and which evidence supports that
   interpretation;
6. distinguishes captured evidence, attributed claims, inference, and
   hypothesis;
7. preserves meaningful contradictions and important unknowns;
8. turns evidence into interpretation, implication, and useful discovery
   questions; and
9. ships readable, internally consistent, citation-valid long-form artifacts.

Primr is not complete when it has collected enough pages. It is complete when
the available public evidence has been converted into the best defensible
strategic company report the selected budget and route can support.

## Primary artifact contract

The long-form Strategic Overview is the primary product. The Word document is
the primary human deliverable. Markdown is the canonical local and agent-ready
source artifact.

```text
<Company>_Strategic_Overview_<date>.md
<Company>_Strategic_Overview_<date>.docx
```

A normal run may also produce one or more strategy artifacts:

```text
<Company>_<Strategy_Name>_<date>.md
<Company>_<Strategy_Name>_<date>.docx
```

The report remains substantial. A concise governing thesis and executive
decision brief should make the analysis easier to consume, not replace the
complete company research.

Diagnostics, source indexes, ledgers, working models, and manifests are
supporting artifacts. They must never become a substitute for the polished
report or make the public invocation harder to understand.

## YAML strategy contract

YAML is Primr's controlled strategy-extension seam. A strategy definition owns
its purpose, intended audience, analytical requirements, curated section
contract, and writing guidance.

Every promoted strategy must:

- consume the researched company context rather than produce a generic
  template essay;
- remain specific to the company's evidence, economics, constraints, and
  strategic position;
- preserve citation and uncertainty discipline for material company claims;
- produce aligned Markdown and Word artifacts;
- pass the same structural shipping and rendering gates as the Strategic
  Overview; and
- remain version-controlled, reviewable, and testable.

Built-in strategy YAML files are immutable product assets for a released
version. Recurring custom strategies belong in the user's override path and
must not modify a built-in definition in place.

## Research model: breadth first, diagnostic depth second

The default report must not trade broad company understanding for a narrow but
interesting hypothesis. Primr therefore uses two conceptual research lanes.

### Coverage lane

Establish the evidence floor needed for the complete report: products,
customers, business model, distribution, market, competition, leadership,
hiring, financial signals, risks, and other material company context.

### Insight lane

Use the remaining research appetite to test the questions most likely to change
the strategic interpretation. A candidate action should identify:

- the hypothesis it tests;
- why the answer matters;
- what would strengthen the hypothesis;
- what would weaken it;
- how diagnostic and independent the expected evidence is; and
- whether the expected information is worth the cost and time.

The coverage lane protects completeness. The insight lane creates
differentiation. Model judgment may rank content and research value at fixed
decision points; code continues to enforce tools, budget, egress, retries,
maximum passes, and terminal conditions.

## Internal company working model

Before final prose, Primr should be able to express a compact, run-scoped view
of the company:

```text
what the company is
economic engine
customer and buying logic
market and competitive position
change vector
governing thesis
competing explanation
strategic tensions
load-bearing evidence and counterevidence
decision-relevant unknowns
what would change the view
implications
```

This is internal analytical state, not a new public product, generic knowledge
graph, or permanent ontology. The planned run-scoped epistemic ledger can make
its evidence and inference chain inspectable, but the report remains the human
deliverable. Cross-run memory earns promotion only when it measurably improves
a later company engagement.

## Report quality hierarchy

The stable report contract may use adaptive depth and emphasis. Fixed section
IDs do not require every section to receive equal space or analytical weight.

The reader should encounter this hierarchy:

1. governing company view and major implications;
2. company model and evidence-backed operating context;
3. strategic tensions, counterevidence, risks, and unknowns;
4. detailed frameworks and source support.

SWOT, Five Forces, value-chain analysis, and similar frameworks are analytical
tools. They should support the company view rather than compete with it or
repeat it. Each material passage should contribute at least one of evidence,
interpretation, implication, qualification, or a decision-relevant question.

The signature analytical chain is:

```text
evidence
-> operating interpretation
-> strategic dynamic
-> business implication
-> useful next question or decision implication
```

## Economic contract

Primr is free-first and dollar-disciplined.

The target routing order is:

1. Primr Zero in a capable current agent host;
2. a validated local model;
3. a validated local agentic harness;
4. the approximately $1 Standard provider-backed recipe; and
5. Premium only by explicit request and fresh approval.

Candidate local harnesses include Claude Code, Codex CLI, Grok CLI, agy CLI,
and other bounded adapters that later satisfy the same quality, billing,
security, and artifact contracts. Listing a candidate is not a claim that the
adapter is implemented or promoted.

Authenticated harnesses are not automatically free. Execution may be local,
plan-backed, metered, organization-funded, or unknown. Primr must describe the
route with the existing billing vocabulary, including `zero_api_runtime`,
`host_plan_usage`, `api_dollars`, `api_credits`, `potentially_metered`, or
`unknown`, only when the available evidence supports that label. It must never
copy host OAuth tokens, cookies, or credentials into Primr.

When paid provider APIs are required, Standard targets the best complete
Strategic Overview and default strategy artifacts Primr can produce for about
$1. This is a target budget envelope, not a static price promise. Every paid
run still requires:

1. a fresh estimate for the exact recipe;
2. an explicit statement of route, expected cost, duration, and artifacts;
3. operator approval;
4. a hard budget cap; and
5. run-scoped actual-cost reporting when measurement is possible.

Primr may optimize a recipe to meet the target. It must not silently remove the
Strategic Overview, promised strategy artifact, evidence integrity, or output
validation to make the estimate look cheaper. Scrape-only execution remains a
specialized mode, not the flagship free product.

## Core evaluation contract

The flagship end-to-end benchmark starts from the bare invocation, without
special framing flags:

```bash
primr "Company" https://company.example
```

Representative cases should include a sparse private company, a source-rich
public company, a company in visible strategic transition, a company with
conflicting or derivative sources, and a stable company where diminishing
returns matter.

Blinded, agreement-validated evaluation plus human adjudication should measure:

- company understanding and research completeness;
- governing-thesis quality and falsifiability;
- prioritization of the important dynamics;
- evidence support, source authority, and source independence;
- contradiction diagnosis and counterevidence use;
- strategic synthesis and the evidence-to-implication chain;
- uncertainty and label honesty;
- report coherence, non-repetition, and readability;
- decision usefulness;
- quality of proposed next research actions;
- stopping discipline; and
- quality lift relative to cost and time.

Structural code may validate files, references, schemas, citations, and budget
boundaries. Content quality remains an eval and human-review decision, never a
regex ship gate or a lone-judge verdict.

Any promoted route, including local and agentic harnesses, must satisfy the
same artifact contract. Routes may differ in measured quality, assurance,
provider ownership, and cost accounting, but they must not silently redefine
the product.

## Feature admission test

A proposed feature belongs in Primr only when it materially improves at least
one of these outcomes for the core company-and-website run:

1. research accuracy or completeness;
2. strategic insight or company understanding;
3. evidence quality, triangulation, or uncertainty honesty;
4. report specificity, coherence, or decision usefulness;
5. reliable Markdown and Word delivery;
6. cost or time without quality regression; or
7. safe, understandable operation for humans and agents.

If the main result is a generic corpus, graph, note system, agent framework,
collaboration surface, or model-serving platform, it does not belong in Primr.
Internal architecture work remains justified when it measurably reduces risk or
unlocks one of the product outcomes above.

## Release and publication contract

Primr maintains one long-lived `main` branch. Feature branches are short-lived
and merge through focused pull requests. A release is cut for a coherent
user-facing improvement or an important correctness or security fix, not merely
because commits accumulated.

Before a release:

1. Ruff check and format, mypy, strict documentation, security scans, packaging
   checks, and the full applicable test suite pass.
2. Branch coverage stays above the repository ratchet.
3. `pyproject.toml`, package `__version__`, ROADMAP Current State, and
   `CITATION.cff` agree.
4. The changelog accurately describes the shipped behavior.
5. Wheel and source distribution contents are inspected and release-integrity
   tests pass.
6. Required CI is green on the exact `main` commit to be tagged.

The GitHub release and PyPI publication must refer to that same verified commit
and version. After publication, verify the public PyPI version, perform a clean
installation, and run zero-spend smoke checks for version, help, prep dry-run,
and rendering. GitHub, PyPI, documentation, and package metadata must never
describe different product states.

Commits, pull requests, documentation, changelogs, release notes, code comments,
and generated artifacts must not contain non-human authorship attribution,
coauthor trailers, or generated-by notices.

## Dependency-ordered development

The current executable architecture-cohesion slice remains first because it is
behavior-preserving, zero-spend work that makes analytical stages easier to
test. Product development then proceeds through measured slices:

```text
architecture ownership
-> fully decidable epistemic baseline
-> company working model in shadow mode
-> adversarial thesis and next-action evaluation
-> breadth-preserving diagnostic deepening
-> working-model-informed report writing
-> measured local and agentic route promotion
-> bounded stopping and cost improvements
-> repeat-engagement memory only after demonstrated report lift
```

No product-quality promotion or paid evaluation bypasses the estimate,
approval, representative-corpus, agreement, and human-adjudication requirements.

## Change control

The root README owns the short public promise. This document owns the durable
product and delivery contract. `NEXT_STEPS.md` owns the current executable
slice, the roadmap owns dependency order, research-tradecraft documents own
analytical methods, and the changelog owns completed behavior.

When a proposed roadmap item conflicts with this contract, either narrow the
item until it strengthens the company research and strategic-report product or
record an explicit product decision to amend this contract first.
