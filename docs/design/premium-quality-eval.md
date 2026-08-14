# Premium quality evaluation

Status: optional design, deferred and not run. No budget is approved. All
model-backed execution remains estimate-gated. If the operator later approves
this product experiment, its aggregate campaign ceiling is **$25.00**,
including research runs, cloud judges, provider tools, and approved retries.
This is an absolute safety ceiling, not a target or planned expense.

## Decision this evaluation supports

Determine whether the current Premium product path produces a meaningfully
better strategic brief than the current Standard path, especially on document
coherence and epistemic quality.

This is a paired product evaluation, not a speed contest and not a universal
test of serial versus concurrent writing. Standard and Premium differ in
collection, models, context flow, and assembly as well as writing topology.
The result may support product positioning and identify a weak stage. It cannot
attribute every difference to section scheduling alone.

## Fixed evaluation set

The operator selects five companies outside the repository. No company name,
URL, report body, or source corpus is committed. Freeze the selection before
the first billable run using these placeholders and criteria:

| Placeholder | Required selection characteristic |
|-------------|-----------------------------------|
| Company A | Sparse private-company public footprint, with enough first-party material to identify the business |
| Company B | Rich public-company footprint, including investor or regulatory material |
| Company C | Partially blocked or script-heavy first-party site that exercises recovery behavior |
| Company D | Hiring-rich company with multiple credible technology or operating signals |
| Company E | Company with a recent strategic change and a meaningful risk of stale or contradictory sources |

Reject a candidate if it cannot be researched legally from public sources, if
it duplicates another selection characteristic, or if the operator has a
conflict that would bias human review. Record only the placeholder, selection
reason, and a local hash of the private selection record in the decision
artifact.

Each company produces one Standard and one Premium Strategic Overview from the
same release commit, for ten scored artifacts total. Run each pair as close
together as practical with the same operator context and output contract. Do
not change prompts, models, configuration, or code between arms.

## Entry conditions

Before estimating the run set:

- Complete a zero-spend provider currency check against official model,
  pricing, retirement, rate-limit, storage, and API-migration documentation.
  Record the audit date and source URLs in the private run ledger.
- Register current models with exact pricing before quoting them, but do not
  change production routing merely because a newer model exists. Any model or
  endpoint promotion remains comparison-gated.
- Resolve known API-contract gaps before spending. As of the 2026-08-13 audit,
  xAI recommends Responses over deprecated Chat Completions, publishes exact
  `cost_in_usd_ticks`, and recommends a stable `prompt_cache_key`. Google
  recommends the GA Interactions API; the Deep Research path already uses its
  required background interaction pattern.
- The Standard and Premium execution paths and their active model ownership are
  documented accurately.
- Each quoted option is actually consumed by its execution branch. In
  particular, the Premium verification contract must be wired or explicitly
  excluded from both its estimate and this evaluation.
- Any page-length control used in the commands has executable semantics; an
  accepted but ignored `target_pages` value is not an evaluation treatment.
- Both arms emit the report, run manifest, source appendix, usage summary, and
  available verification or calibration sidecars needed by the rubric.
- The exact commit, configuration fingerprint, prompt/config fingerprints, and
  model registry entries are frozen in the private run ledger.

If an entry condition fails, stop and fix the contract. Do not reinterpret a
misconfigured run as evidence about report quality.

## Estimate and approval gate

All ten research runs are billable. Before execution:

1. Dry-run the exact Standard and Premium command for every selected company.
2. Record each quoted cost, runtime band, mode, strategy behavior, and any
   non-interruptible provider task.
3. Sum the quotes and add only an explicit, documented contingency for approved
   retries. Set a hard aggregate budget no higher than **$25.00**. A lower
   operator-approved amount becomes the effective ceiling.
4. Present the ten-run estimate and request explicit approval for that exact
   run set. A request for an estimate is not approval.
5. Estimate any cloud-judge calls separately and include them in the same
   aggregate ceiling. Prefer free local judges for the
   first scoring pass. Never treat a host subscription as proven zero-cost
   unless its billing provenance is known.

No run, replacement run, or cloud judge starts without the applicable estimate
and approval. A provider-accepted failed run is reported and preserved. It is
not silently replaced with another paid attempt.

### Staged stop rules

The five-pair design remains the requirement for a positive Premium quality
claim, but spending is staged to fail cheaply:

1. **Stage 0, $0:** complete the provider/API audit, freeze fixtures and
   fingerprints, validate blinding and rubric tooling on existing or synthetic
   artifacts, and collect all ten dry-run quotes.
2. **Stage 1, at most $5 cumulative:** run one paired pilot only after a fresh
   estimate and approval. Stop if artifacts, manifests, blinding, citation
   parsing, or judge inputs are incomplete. The pilot may count toward the five
   pairs only if no protocol, prompt, model, or configuration changes follow.
3. **Stage 2, at most $15 cumulative:** run two more pairs only if Stage 1 is
   valid and the exact estimates fit the remaining ceiling.
4. **Stage 3, at most $25 cumulative:** run the final two pairs only if the
   protocol remains valid, the decision is not already a documented pipeline
   failure, and every estimated call fits below the remaining ceiling.

Track both quoted and actual cost after every provider response. Use exact
provider-billed cost when exposed, including xAI `cost_in_usd_ticks`; otherwise
use the manifest's conservative token and tool estimate. Before each call,
subtract actual spend and already-authorized non-interruptible work from the
effective ceiling. Never rely on a provider-side monthly limit as the campaign
guard.

Early stopping cannot produce `premium_quality_lift_supported`. That decision
requires all five valid pairs and every acceptance criterion below. A stop for
cost, invalid instrumentation, or inconclusive evidence records
`evaluation_inconclusive`; a clear product defect may record
`premium_pipeline_rework_needed`. Do not exceed $25 to rescue sample size or
replace a failed call.

## Artifact blinding

An evaluator who did not run the research creates a private arm map. Reports
are copied to opaque identifiers such as `P01-A` and `P01-B`, with arm order
randomized independently for each pair. Remove mode, model, price, runtime,
file-name, and pipeline-stage disclosures that reveal the arm. Preserve report
content, confidence labels, citations, source appendix, headings, and all
quality-relevant defects.

Judges receive one pair at a time and do not receive the arm map. Half of the
pairs present A first and half present B first. Re-score a randomly selected
two-pair subset with the order reversed to expose position sensitivity. The
arm map is opened only after judge output and human adjudication are frozen.

## Rubric

Score every dimension from 1 to 5 for each artifact and choose a pairwise
preference of A, B, or tie. Each score requires a short rationale and report
location. Evidence dimensions also require source references.

| Dimension | Evaluation question |
|-----------|---------------------|
| Evidence support | Do material factual and strategic claims follow from the cited or supplied evidence? |
| Contradiction handling | Does the report surface, reconcile, or appropriately preserve conflicting evidence instead of choosing silently? |
| Source authority and independence | Are important claims grounded in suitable first-party or authoritative sources, with independent support where the claim warrants it? |
| Uncertainty and label honesty | Do Confirmed, Reported, Estimated, and Hypothesis labels match the strength of the evidence and the wording of the claim? |
| Argument arc | Does the report build a coherent company-level argument in which later conclusions use and refine earlier findings? |
| Repetition | Does each section add decision value without restating the same claim or recommendation unnecessarily? |
| Terminology consistency | Are company names, segments, products, time periods, metrics, and strategic terms used consistently across the document? |
| Citation resolution | Does every citation marker resolve to one unambiguous source entry, without dangling or duplicate references? |

Citation resolution may use deterministic parsing because it is a structural
fact. Deterministic tools may also assemble samples and locate candidate
citations. They must not decide evidence support, contradiction, authority,
label honesty, argument quality, or prose quality. Do not add a regex content
gate as a result of this evaluation.

For long reports, score evidence dimensions on a pre-registered sample that
includes the executive summary, every high-confidence material claim, and a
fixed number of claims sampled across early, middle, and late sections. Score
document dimensions against the complete artifact, not isolated excerpts.

## Judge agreement and human adjudication

Use at least three independent judge configurations, preferably spanning two
model families. Keep prompts and temperature settings fixed. A local panel may
be used at zero API cost, but local agreement is evidence, not automatic proof
of correctness.

Report:

- per-dimension scores and pairwise preferences;
- unanimous, majority, and no-agreement counts;
- order-reversal consistency on the repeated subset;
- judge-family agreement;
- abstentions and missing-evidence rates.

A human reviewer adjudicates every no-agreement result, every order-sensitive
result, every material contradiction finding, and every difference of two or
more rubric points between judges. The reviewer examines the cited source or
receipt, records the reason, and may choose Standard, Premium, tie, or
insufficient evidence. Human adjudication is frozen before the arm map opens.

## Pre-registered acceptance criteria

The evaluation supports the claim that Premium provides a meaningful quality
lift only when all of the following hold:

1. Premium is the human-adjudicated overall preference for at least four of the
   five company pairs.
2. Premium improves argument arc in at least three pairs and is not materially
   worse in any pair.
3. Premium is not materially worse on evidence support, contradiction handling,
   source authority and independence, or uncertainty and label honesty in any
   pair.
4. Premium is not worse on repetition or terminology consistency in more than
   one pair, and any regression has a documented stage-level cause.
5. Both profiles have complete citation resolution, or every unresolved
   citation is classified as a product defect rather than excluded from the
   score.
6. A majority result is supported by at least two judge configurations and is
   not reversed by human source review.

For this five-company sample, "materially worse" means a human-adjudicated
difference of at least one rubric point with a concrete report example. These
criteria support a bounded product decision, not a permanent quality gate or a
population-wide statistical claim.

## Writing-topology interpretation

Premium's serial section writing is an intentional quality design: later
sections receive prior-section context and wall-clock speed is secondary.
Standard uses structured concurrent section writing plus cross-validation,
deduplication, and coherence work. It is not equivalent to independent chapter
fan-out.

Interpret the result accordingly:

- If Premium wins, retain serial writing and identify which continuity or
  evidence behaviors account for the lift. Do not infer that Standard must
  become serial.
- If Standard wins or ties, do not immediately parallelize Premium. First
  inspect dossier quality, context truncation, section prompts, assembly,
  contradiction handling, and repetition.
- If both profiles fail the same dimension, fix the shared evidence, prompt,
  assembly, or QA seam rather than their scheduling topology.
- Runtime and cost are recorded for estimate honesty and product positioning,
  but they are not tie-breakers for report excellence.

A causal claim about serial versus concurrent writing requires a separate
evidence-normalized experiment that holds corpus, model, prompt, section plan,
and assembly constant. This product evaluation does not make that claim.

## Decision record

Write one private, body-free decision record containing:

- selection-criteria coverage and private selection-record hash;
- commit, configuration, prompt/config, and model-registry fingerprints;
- quoted and actual cost/runtime by arm;
- artifact and sidecar hashes;
- blinded judge results, agreement statistics, order-sensitivity results, and
  human adjudications;
- acceptance-criterion result for each numbered criterion;
- one decision: `premium_quality_lift_supported`,
  `premium_differentiation_not_demonstrated`, `premium_pipeline_rework_needed`,
  or `evaluation_inconclusive`;
- named stage-level follow-ups, owner, and rollback or no-change decision.

Do not store report bodies, raw source corpora, company names, URLs, secrets,
or judge credentials in the record. The result is report-only evidence until a
larger repeated corpus and acceptable judge agreement justify any product or
quality gate.

## Explicitly not part of this evaluation

- Optimizing Premium for minimum wall-clock time.
- Replacing serial Premium writing with independent parallel chapters.
- Treating Standard's structured concurrency as naive fan-out.
- Changing prompts, providers, or models between paired arms.
- Using one judge, one aggregate quality score, or regex prose checks as truth.
- Publishing real-company fixtures, reports, or source material.
- Starting billable research or judging without estimate and explicit approval.
