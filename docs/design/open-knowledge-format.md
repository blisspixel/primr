# Open Knowledge Format as the Findings Interchange Shape

Status: ADOPTED AS DIRECTION. This is a cross-cutting format decision, not a
standalone workstream. It rides on work already planned: backlog item #2
(intermediate artifacts structured for downstream consumption), 2.0 research
memory (export bundle plus claim store), and 3.0 Workstream C (post-artifact
handoff manifest). No new queue item. This doc fixes which shape those efforts
emit so they do not each invent a different one.

ROADMAP anchors: backlog item #2; "2.0 Memory"; "3.0 post-artifact
skill-processing handoff"; the skill pack subsystem (the first handoff
instance).

References:

- Google Cloud's [Open Knowledge Format
  introduction](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/),
  which introduced OKF v0.1.
- The current [OKF v0.2
  specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md),
  which supersedes v0.1.

OKF is a vendor-neutral format for sharing structured knowledge as markdown
files with YAML frontmatter in a hierarchical directory tree, where markdown
links form a graph. It has one always-required concept field (`type`), the
"just files, just markdown, just YAML" principle, producer/consumer
independence, and "format, not platform." Primr targets OKF v0.2 for future
findings interchange. The target is pinned here so memory, claim-store, and
handoff implementations do not accidentally emit the older v0.1 shape.

## Motivation

primr already produces two classes of output (see [ARTIFACTS](../ARTIFACTS.md)):
the polished report or strategy deliverable (MD, TXT, DOCX, PDF under a strict
shipping contract) and the structured findings underneath it (the analysis
workbook, source inventory, contradiction records, hypotheses with confidence
labels, recon and hiring signals). The deliverable is for a human. The findings
graph is what a downstream agent actually wants, something it can traverse and
query ("every hypothesis still labeled inference", "what changed since the last
run"), not a wall of narrative it must re-read end to end.

We have repeatedly needed an on-disk shape for that findings layer: the 2.0
memory export, the 2.0 claim store, and the 3.0 handoff manifest. The risk is
inventing three slightly different ones. OKF is a good fit and matches primr's
own philosophy ("credentials are transport, not product identity"; "product
over middleware"): a portable format, not a platform. Adopting it as the single
shape lets those efforts converge instead of diverging.

## The decision

1. The polished report does not change. MD plus DOCX (plus best-effort PDF) stay
   exactly as they are, the human deliverable under its existing strict gates.
   OKF touches none of that pipeline. This is binding (see Explicitly not).
2. The structured-findings layer is emitted as an OKF bundle wherever it is
   handed to a consumer: the conformant memory `company export`, the claim
   store's export form, and the 3.0 handoff package. One shape, reused. The
   currently shipped layer-1 profile export is only an OKF-shaped precursor;
   it does not claim v0.2 conformance until it emits the required root bundle
   and full linked contract.
3. OKF is a projection of Primr's native structured state, not its canonical
   store and not a reformat of prose. Within one run, `source_index.json`,
   `findings.jsonl`, and `strategic_inferences.jsonl` are the planned native
   snapshot. Across runs, the governed SQLite claim/proposition store is
   canonical. A findings bundle projects those records into linked,
   addressable units:

   ```
   acme/
   |- index.md              # navigation; root frontmatter: okf_version: "0.2"
   |- company.md            # type: Company, the entity
   |- hypotheses/
   |  |- index.md
   |  |- unannounced-ai-product.md   # frontmatter: confidence, supporting links
   |- claims/               # one file per claim: confidence label plus source links
   |- inferences/           # one file per strategic inference, linked to premises
   |- sources/              # the citation appendix, made addressable
   |- competitors/
   |- signals/              # recon plus hiring signals
   ```

   Concept frontmatter carries `type` (required by OKF), plus:

   - Primr's `confidence` extension (`Confirmed`, `Reported`, `Estimated`, or
     `Hypothesis`), which describes the epistemic status of a claim.
   - OKF `sources`, with the required `resource` for each source entry. OKF
     makes `id` optional, but Primr requires a stable `id` whenever the body
     attributes a claim to that source. Claim-level attribution uses markdown
     footnotes keyed to those source IDs.
   - OKF `generated`, with required `by` and an `at` timestamp for the producer
     and last meaningful content change. OKF requires `by` when `generated` is
     present; Primr's producer contract also requires `at`.
   - OKF `verified` only when an actor actually reviewed the concept against
     its source or resource. Actors may be agents or tools, humans, or
     automated processes under OKF's actor convention.
   - OKF `status` and `stale_after` for lifecycle and freshness when known.

   Primr confidence and OKF verification are orthogonal. A `(Confirmed)` claim
   MUST NOT automatically produce a `verified` event. `verified` records who or
   what performed a review and when; it is not a synonym for claim confidence.
   Markdown links between files form the graph: a claim links its sources and a
   hypothesis links its supporting claims.

   `index.md` is a reserved OKF navigation file, not a concept document. Only
   the bundle-root index may carry frontmatter. OKF makes its
   `okf_version: "0.2"` declaration optional, while Primr requires it for
   emitted bundles. The company entity therefore lives in `company.md`.
   `log.md` is also reserved and has no frontmatter. When present, it is a
   newest-first update history with ISO 8601 `YYYY-MM-DD` date headings.

## Where it applies, and where it explicitly does not

| Surface | OKF? | Why |
|---------|------|-----|
| Final report or strategy (MD, DOCX, PDF) | No | Human deliverable, narrative, strict shipping contract. OKF is for reference structure, not prose. |
| Current layer-1 `company export` | Not yet | The shipped profile/hypothesis Markdown/JSON is an OKF-shaped precursor, but lacks the conformant root bundle and full linked finding graph. |
| 2.0 memory `company export` bundle | Yes | OKF v0.2 is the portable shape, with provenance, generation, review, lifecycle, sources, findings, and strategic inferences represented as linked files. |
| 2.0 claim store export or interchange | Yes | A claim with confidence plus citations plus links is one OKF file. The store's portable form is an OKF bundle. |
| 3.0 post-artifact handoff manifest | Yes | Workstream C's "versioned artifact manifest", with the OKF bundle as the consumer-consumable package. Generalizes the skill-pack pattern. |
| Native run ledger (#2) | No | The versioned source index plus finding/inference JSONL are the machine-facing, run-local source of truth. OKF is emitted only for an explicit consumer boundary. |

Litmus for "should this be OKF": is the artifact a set of addressable, linkable
knowledge units a consumer will traverse? Then yes. Is it a single narrative
document a human reads top to bottom? Then no.

## Convergence already present

primr independently arrived at the OKF pattern in two places, which is part of
why it is a low-friction fit:

- Skill packs emit a `roles/<slug>/SKILL.md` tree with YAML frontmatter, a
  shared `references/role-family.md`, `role_plan.json` provenance, and markdown
  links, which is structurally an OKF bundle. At field level it is not yet
  OKF-conformant: SKILL.md uses `name` and `description`, not OKF's required
  `type`. The convergence is on structure (files plus frontmatter plus links
  plus tree), not on the field set. Declaring conformance, if ever wanted, is a
  small frontmatter alignment, not a pipeline change.
- The repo's own agent-memory convention (an index file plus one-fact files with
  frontmatter and `[[links]]`) is the same idea.

This is the existing dual-emission pattern. Skill packs already emit
byte-identical `SKILL.md` to both a Claude tree and a Cowork `.zip`: one source
of truth, two consumers. The findings bundle is the same move. The run produces
the polished report for the human and the OKF bundle for the agent from the same
underlying findings.

## Anti-temptation: do the valuable version, skip the shallow one

The shallow version, dumping the report markdown into a folder with frontmatter,
is near worthless: it is still narrative an agent must re-read, just relocated.
Do not ship that. The value is the decomposed graph (sources, findings,
strategic inferences, hypotheses, and entities as separate linked units), and
that is substantially the same object as the 2.0 claim store. The run-scoped
native ledger may land earlier in shadow mode, but OKF serialization still
rides on memory or handoff consumer demand. Building a throwaway exporter in
1.x means rebuilding it when the claim store lands.

## Validation cost

The serialization itself is deterministic and free to validate. Contract tests
must cover:

- Primr's required root `okf_version: "0.2"` declaration and reserved
  `index.md`/`log.md` behavior;
- `type` on every concept document;
- `generated.by` and Primr's required `generated.at` when generation metadata
  is emitted;
- `sources[].resource` and unique, stable IDs for claim-attributed sources;
- source-footnote IDs that resolve to matching `sources` entries;
- valid Primr confidence values without conflating them with `verified`;
- lifecycle dates and actor forms when those optional fields are present;
- preservation of unknown frontmatter fields during round trips; and
- lossless supported-field conversion from native run ledger or claim store ->
  OKF -> claim store, including evidence-anchor references, premise and
  counterevidence links, typed relations, and observed/valid time.

OKF itself permits broken links and unknown fields. Primr's producer contract is
deliberately stronger: emitted internal links must resolve because Primr owns
both ends. Consumers remain permissive as required by OKF. No paid run is
needed for the format work. It inherits the live-run budgets already stated for
memory layer 1 and the 3.0 handoff, since it ships as part of those.

## Explicitly not

- Not a change to the polished report contract. The human deliverable stays MD,
  TXT, DOCX, PDF under its existing gates. OKF never gates or reshapes it.
- Not an OKF platform. primr emits and (optionally) ingests the format. It does
  not ship an OKF catalog, server, or visualizer, which would be the
  middleware/SaaS non-goal. "Format, not platform" cuts both ways.
- Not a third artifact pipeline. OKF reuses the existing markdown plus
  frontmatter seam (skill packs, memory entries). It is not a parallel format
  stack, per the "one way to do each thing" contract.
- Not a 1.x exporter feature. No standalone queue item. The v0.2 design pin is
  a 1.x documentation correction; serialization remains the agreed shape for
  memory and handoff work when those land. The only 1.x-visible note is the
  pointer on backlog item #2.

## Exit criteria

There is no separate "OKF is done" milestone, because it is a shape, not a
feature. It is satisfied when the surfaces that adopt it ship: the 2.0 memory
export and claim store emit OKF bundles whose links resolve and whose
frontmatter carries Primr confidence plus OKF v0.2 provenance, generation,
review, and lifecycle fields as applicable, and the 3.0 handoff manifest
declares its bundle as OKF v0.2. The contract and round-trip tests above pass,
and the polished report remains demonstrably unchanged.
