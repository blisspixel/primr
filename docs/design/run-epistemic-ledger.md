# Run-Scoped Epistemic Ledger

Status: ADOPTED AS DIRECTION, NOT YET IMPLEMENTED. This document owns the
within-run evidence, finding, inference, relation, and usage contract. It does
not add a current execution card, change the report, or move memory ahead of
the v1.40 calibration decision.

ROADMAP anchors: backlog item #2 (structured research artifacts), backlog item
#4 (evidence-grounded strategic analysis), v1.43 research-memory layer 1,
v1.44+ claim-aware writing, 2.0 research memory, and 2.x Strategy Delta.

Related contracts:

- [Agentic balance](agentic-balance.md) owns the rule-versus-judgment line.
- [Research tradecraft](research-tradecraft.md) owns hypothesis-first analysis.
- [Open Knowledge Format](open-knowledge-format.md) owns the future
  interchange projection.
- [Research memory](2.0-research-memory.md) owns cross-run reconciliation and
  persistence.

## Decision in one page

Primr will introduce a small, run-scoped epistemic intermediate
representation between captured evidence and report prose:

```text
captured public evidence
        |
        v
source_index.json
  SourceReceipt + digest-bound EvidenceAnchor
        |
        v
findings.jsonl
  ResearchFinding: observation or attributed source claim
        |
        v
strategic_inferences.jsonl
  StrategicInference: premises, assumptions, counterevidence,
  disconfirming signals, and bounded external rationale
        |
        v
fixed report scaffold + strategy writers
        |
        v
Markdown / DOCX decision artifact
```

The first implementation is shadow-only. It writes the structured records and
measures them against the existing report without changing report bytes or
making the writer depend on them. A later, measured promotion may give each
section a bounded evidence view and collect the IDs it used. Persistent
cross-run proposition identity, priming, OKF export, and Delta remain memory
work.

The report stays the human deliverable. The ledger becomes the run's canonical
structured analysis state only after shadow evaluation proves that it is
complete and useful enough to replace duplicated workbook structures. Until
then it is a diagnostic research artifact with an explicit migration exit.

## Why this belongs in Primr

Primr already has most of the pieces, but they are separated by prose:

- `source_index.json` exists on the Primr Zero path, but does not yet bind
  sources to immutable same-run captures and exact evidence spans.
- The analysis workbook contains facts, hypotheses, gaps, and contradictions,
  but its prose is not an addressable claim contract.
- report verification re-extracts `VerifiableClaim` objects after the report is
  written.
- calibration separately re-extracts labeled claims and reviews support,
  contradiction, source independence, authority, reasoning strength, and
  uncertainty honesty.
- the Day-1 hypothesis tree is typed planning state, but its nodes do not yet
  link to the evidence that supported, weakened, or refuted them.

This creates a preventable failure path:

```text
evidence -> writer interpretation -> polished prose -> appears factual
```

The ledger inserts an inspectable boundary:

```text
evidence -> finding -> strategic inference -> prose
```

It also gives later memory and Delta work a better input than re-extracting
claims from old reports.

## The epistemic levels

Primr needs separate fields for concepts that the current four labels partly
overload:

| Concept | Question it answers | Initial representation |
|---------|---------------------|------------------------|
| Evidence anchor | What exact captured bytes support this record? | `EvidenceAnchor` |
| Epistemic kind | Is this observed, attributed, inferred, or still being tested? | record type plus `finding_kind` / `inference_kind` |
| Confidence label | How should the current report express its status? | Confirmed, Reported, Estimated, Hypothesis |
| Verification event | Who or what reviewed it, when, and with what result? | append-only review reference |
| Evidence grade | How strong, independent, authoritative, and contradictory is the support? | calibration review dimensions |
| Editorial use | Where did the report use it? | later section-usage edges |

These are orthogonal. `Confirmed` does not mean independently verified. A
verification event does not automatically promote confidence. An operator's
decision to use or ignore a finding does not change its truth class.

Primr keeps its existing public four-label vocabulary in this workstream. The
typed boundary makes the vocabulary more honest without introducing a second
set of user-facing labels before the two-axis evidence-grading work is
measured.

## Native records

The examples below define the semantic contract, not final Python class names.
Schema names and filenames become public only when implementation and fixtures
ship.

### SourceReceipt and EvidenceAnchor

Evolve the existing evidence source index rather than adding another source
catalog. A source receipt identifies the resource and the bytes Primr actually
saw in this run:

```yaml
schema: primr.evidence-source-index
version: "2.0"
run_id: RUN-123
sources:
  - source_id: S001
    source_key: sha256:resource-identity
    source_type: first_party
    collection_method: direct_site_scrape
    url: https://acme.example/about
    title: About Acme
    publisher: Acme Corp
    published_at: null
    retrieved_at: 2026-08-30T18:22:00Z
    capture:
      artifact_path: _raw_scrapes/about.txt
      artifact_sha256: sha256:capture-bytes
      content_sha256: sha256:normalized-content
      capture_state: fetched
      truncated: false
```

`source_key` identifies the source resource. The capture digests identify the
specific bytes seen in this run. Neither is a semantic proposition ID.

An evidence anchor points into that immutable capture:

```yaml
source_id: S001
relation: supports
anchor:
  locator_type: text_span
  artifact_path: _raw_scrapes/about.txt
  artifact_sha256: sha256:capture-bytes
  start_char: 1432
  end_char: 1719
  text_sha256: sha256:selected-text
  status: exact
```

Offsets are meaningful only with an artifact digest. A live URL plus offsets is
not an anchor because the page may change.

Exactness is capability-dependent and must be honest:

| Source | Initial anchor capability |
|--------|---------------------------|
| Captured HTML, feeds, Wayback, EDGAR text | Text span in the saved normalized capture |
| Recon and retained structured artifacts | JSON Pointer or text span, bound to the artifact digest |
| Retained hiring-posting bodies | Text span; indexed metadata may use JSON Pointer |
| Extracted PDFs | Text span only until page boundaries or a page map are retained |
| Provider Deep Research | Dossier span or source-only citation; never invent a source-page span |
| Title-only verification fallback | `unavailable` with reason `title_only` |
| Unsupported transcript or repository locators | `unavailable` until Primr owns a source-native collector |

Every missing exact anchor carries a bounded reason such as `source_only`,
`provider_citation`, `title_only`, `not_retained`, or `unsupported_locator`.
Absence is a capability fact, not evidence failure.

### ResearchFinding

A finding is one evidence-bound assertion about the company. It is either a
direct observation or an attributed source claim. Use `ResearchFinding`, not
the existing executive-summary `KeyFinding`, which has a different purpose.

```yaml
schema: primr.research-finding
version: "1.0"
run_id: RUN-123
finding_id: F001
statement: Acme lists an enterprise plan.
finding_kind: observation
topic: pricing
confidence: Confirmed
qualifiers:
  geography: null
  population: null
  conditions: []
observed_at: 2026-08-30T18:22:00Z
valid_from: null
valid_until: null
evidence:
  - source_id: S001
    relation: supports
    anchor: {}
relations: []
reviews: []
producer:
  stage: analysis_workbook
  name: primr
  version: 1.39.10
  generated_at: 2026-08-30T18:25:00Z
```

Initial findings use Confirmed or Reported because they represent captured or
attributed assertions. A later evidence-grade model may express likelihood and
analytic confidence separately, but it must not collapse finding kind,
confidence, and verification into one value.

### StrategicInference

A strategic inference is Primr's conclusion from findings. It is deliberately
not another fact:

```yaml
schema: primr.strategic-inference
version: "1.0"
run_id: RUN-123
inference_id: I001
statement: Acme appears to be shifting upmarket.
inference_kind: hypothesis
topic: go_to_market
confidence: Hypothesis
premise_finding_ids: [F002, F019, F044]
supporting_inference_ids: []
counterevidence_finding_ids: [F051]
assumptions:
  - Hiring reflects expansion rather than replacement.
rationale: >-
  Enterprise hiring and compliance investments are consistent with an
  upmarket motion, but public customer-mix evidence remains incomplete.
calculation: null
disconfirming_signals:
  - Enterprise hiring reverses.
  - New launches concentrate on self-service buyers.
validation_questions:
  - What share of new pipeline is enterprise?
observed_at: 2026-08-30T18:25:00Z
valid_from: null
valid_until: null
supersedes: null
```

`rationale` is a concise external justification. It is not private model
chain-of-thought. Estimated records retain the current rule that an actual
calculation must be shown; interpretations default to Hypothesis until the
evidence-grading design is promoted.

Primr does not add a generic durable `Argument` or `Belief` object in this
slice. `StrategicInference` carries the argument-like fields needed for one
company case. A general expert-state argument graph belongs outside Primr's
immediate product boundary unless a later evaluation shows that it improves
Primr artifacts materially.

### DiagnosticHypothesis

The existing Day-1 hypothesis tree remains planning state. Ledger work links
each hypothesis to supporting, contradicting, and qualifying finding or
inference IDs and records whether it remains open, weakened, refuted, or
carried forward. It does not silently convert an untested hypothesis into a
finding.

### SectionEvidenceUsage

After shadow evaluation, a fixed report section may receive an allowed set of
finding and inference IDs and return the IDs it used. The usage graph is
structural metadata, not proof that the prose faithfully represents the
record.

```yaml
section: Competitive Positioning
allowed_finding_ids: [F002, F019, F044, F051]
allowed_inference_ids: [I001]
used_finding_ids: [F019, F044, F051]
used_inference_ids: [I001]
```

This can measure unused evidence, repeated support, and inferences referenced
without their premises. Those are report-only diagnostics. Semantic support,
repetition quality, and argument strength remain eval-owned.

## Small declarative ontology and semantic firewall

The ledger should not scatter relationship rules through prompts and Python
conditionals. Once record types exist, Primr may define a small declarative
ontology and compile it into structural validators.

An initial Primr-native shape is intentionally smaller than a general belief
graph:

```yaml
node_types:
  source_assertion: {}
  observation: {}
  strategic_inference: {}
  diagnostic_hypothesis: {}

relations:
  grounds:
    from: [source_assertion, observation]
    to: strategic_inference

  supports:
    from: [source_assertion, observation, strategic_inference]
    to: [strategic_inference, diagnostic_hypothesis]

  contradicts:
    from: [source_assertion, observation, strategic_inference]
    to: [source_assertion, observation, strategic_inference]
    symmetric: true
    requires_assurance: model_confirmed

  qualifies:
    from: [source_assertion, observation, strategic_inference]
    to: [source_assertion, observation, strategic_inference]
    requires_assurance: model_confirmed

  derived_from:
    from: [strategic_inference, diagnostic_hypothesis]
    to: [source_assertion, observation, strategic_inference]

  supersedes:
    from: [source_assertion, observation, strategic_inference]
    to: [source_assertion, observation, strategic_inference]
    acyclic: true
```

The model emits candidate nodes and candidate relations. The semantic firewall
returns one of:

- `legal`: structurally valid and semantically assured where required;
- `illegal`: forbidden endpoint types, missing targets, invalid fields, or a
  prohibited cycle;
- `needs_semantic_adjudication`: structurally legal, but meaning has not been
  judged to the required assurance level.

Python owns enum membership, endpoint legality, required fields, bounds,
reference resolution, symmetry normalization, declared acyclicity, schema
versions, and digest integrity. A model or human owns whether two statements
mean the same thing, support or contradict each other, differ in scope, share
an independent origin, or supersede one another semantically.

The ontology is experimental until actual inference provides measurable value.
It lands with the ledger, not as an ontology over the current prose pipeline.
No RDF store, reasoner, graph database, or generic ontology service is part of
this design.

## Identity and time

Run-local identity is deliberately narrower than cross-run proposition
identity:

- source and capture IDs are deterministic where possible;
- finding IDs identify assertion instances in one run;
- inference IDs identify one run's explicit conclusion;
- hashes identify bytes or exact normalized records, not semantic meaning;
- embeddings may later nominate possible proposition matches but never merge
  records by themselves;
- stable semantic proposition IDs are assigned only by the 2.0 claim store,
  with model-judged reconciliation and preserved assertion instances.

Every record distinguishes at least:

- `observed_at` or `retrieved_at`: when Primr saw the evidence;
- `valid_from` and `valid_until`, when known: when the assertion applies;
- `generated_at`: when Primr produced the structured record.

This is the minimum bi-temporal discipline needed for pricing, hiring,
regulation, product capability, and later Delta work.

## Determinism, judgment, and gates

| Concern | Owner |
|---------|-------|
| Schema shape, IDs, bounds, digests, paths, reference resolution | Deterministic Python |
| Whether an exact retained span still matches its digest | Deterministic Python |
| Candidate extraction from evidence | Model at a fixed, budgeted stage |
| Same proposition, support, contradiction, qualification, supersession | Model or human adjudication |
| Confidence and evidence grading | Agreement-validated judgment |
| Report quality and whether the ledger improves it | Pre-registered eval plus human review |
| Spend, egress, disk, recovery, partial-result behavior | Existing deterministic gates |

The semantic firewall validates legality, not truth. No relation count, unused
finding count, or writer-used-ID signal becomes a ship-time content gate. The
standing rule from `agentic-balance.md` still applies: deterministic checks may
guard prose-invariant structure, never semantic quality.

## Artifacts and access boundary

The narrow native target is:

```text
source_index.json
findings.jsonl
strategic_inferences.jsonl
```

`source_index.json` evolves the existing evidence index. The two JSONL files
hold bounded records without duplicating raw source bodies. If claim-aware
writing is promoted, a bounded section-usage artifact joins them. Topic cards
and section evidence maps are generated views, not another canonical store.

When implemented, these are supporting research artifacts with one semantic
inventory role such as `research_graph`. They are not `working_brief`,
`primary_report`, or `strategy_module`.

The existing job-scoped artifact inventory remains the first body-free read.
If agent demand justifies a compact findings summary after v1.42, it may return
schema versions, hashes, counts by record type and confidence, anchor coverage,
review status, relation counts, and temporal coverage. It must not return
statements, source URLs, evidence excerpts, locator values, assumptions,
rationales, or validation questions. Raw content requires an explicit content
scope or direct local file access and reuses existing job ownership and audit
seams.

## Relationship to verification and calibration

The first ledger does not mechanically absorb existing sidecars:

1. report verification and label calibration remain separate diagnostics;
2. the shadow ledger is correlated to report claims only when an exact finding
   or inference ID survives through the writer;
3. later verification and calibration may consume IDs directly, eliminating
   lossy report re-extraction;
4. prior sidecars remain report-byte-bound historical measurements.

The v1.40 representative calibration corpus remains first and unchanged. It
provides the vocabulary and baseline against which the ledger is judged. The
ledger does not reset or postpone that work.

## Promotion sequence

### Phase 0: contract only

- Freeze these concepts in docs and fixtures.
- Map existing source index, workbook, hypothesis, verification, and
  calibration structures to the contract.
- Make no CLI, API, artifact-name, or report-behavior promise.

### Phase 1: source receipts and exact anchors

- Extend the existing source index, do not create a second catalog.
- Bind locally retained evidence to captures and exact spans where possible.
- Preserve explicit capability gaps for provider-only and non-retained bytes.
- Keep Standard, Premium, and Primr Zero report outputs unchanged.

### Phase 2: v1.43 shadow ledger

- Emit findings and strategic inferences before prose, but do not feed them to
  writers yet.
- Attach a body-free pointer and digest to tracked-company run history.
- Measure material-claim coverage, support, contradiction handling, source
  independence, label honesty, and argument arc on the representative corpus.
- Include every added model stage in dry-run cost and time, approval, budget,
  usage, recovery, and partial-result contracts.

### Phase 3: v1.44+ claim-aware writing

- Generate bounded section views inside the existing fixed scaffold.
- Have writers return used finding and inference IDs.
- Promote only if blinded, agreement-validated review meets or beats the v1.40
  epistemic baseline and does not regress argument quality.
- Add local and agent explainability only after IDs, anchors, ownership, scope,
  limits, and audit are complete.

### Phase 4: indexed memory candidate for v2.0

- Ingest immutable run finding and inference instances directly into the
  governed SQLite claim/proposition store.
- Reconcile propositions semantically without destructively collapsing source
  assertion instances.
- Fence prior research as `validate` context; never reassert it as fresh.
- Export a lossless OKF projection only when a consumer needs it.
- Promote this phase into the 2.0 release only if representative evaluation
  proves that it improves a later company report without freshness,
  uncertainty, privacy, or cost regression.

### Phase 5: v2.x Delta

- First emit a delta while still producing the full report.
- Classify records as new, strengthened, weakened, contradicted, qualified,
  superseded, stale, or unchanged.
- Only after reconciliation is validated may section-usage dependencies drive
  selective regeneration.

## Validation and acceptance

The contract and shadow phases are mostly free to validate:

- schema and unknown-field round trips;
- deterministic IDs and idempotent same-input output;
- every reference resolves;
- required acyclic relations remain acyclic;
- symmetric relations normalize consistently;
- digest mismatch marks an anchor stale;
- unavailable anchors remain explicit;
- files are bounded, atomic, path-contained, and secret-scanned;
- shadow mode leaves current reports, estimates, and dry runs unchanged;
- existing verification and calibration sidecars remain readable.

Semantic promotion needs a representative paid evaluation and explicit spend
approval. Pre-register material-finding coverage, support, contradiction,
independence, label honesty, argument arc, repetition, and citation integrity.
Use agreement-validated judges plus human adjudication. A lone judge, arbitrary
threshold, or small single-company result cannot promote the ledger into the
writer path.

## Explicitly not

- Not a generic knowledge graph, RDF stack, ontology platform, or graph UI.
- Not a new report format or dynamic section-outline system.
- Not a second source index or artifact pipeline.
- Not persistent cross-run memory in 1.x.
- Not canonical prose memory or report-to-claim re-extraction as the target.
- Not a generic durable `Belief`, `Argument`, or `Decision` store in Primr.
- Not hidden chain-of-thought storage.
- Not deterministic semantic deduplication, contradiction, independence, or
  truth judgment.
- Not a new ship-time content gate.
- Not an OKF wrapper around the narrative report.
- Not a Python dependency on sibling projects. Interchange remains files,
  MCP/A2A resources, or a future versioned OKF bundle.
- Not a Primr Zero parity claim before the host and provider-owned paths can
  emit and validate equivalent records honestly.

## Exit criteria

The design is complete when the ownership, types, ontology boundary,
identity/time semantics, access boundary, promotion sequence, and non-goals are
unambiguous across the roadmap and related design docs.

Implementation is complete only when the promoted writer consumes the ledger
without quality regression, every important conclusion can be traversed to its
premises and retained evidence, the cost and recovery surfaces account for the
new stages, and the same records can enter governed cross-run memory without
being re-extracted from report prose.
