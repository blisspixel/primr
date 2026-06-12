# 1.x Completion: Finishing the Excellent Single-Shot Brief

Status: ACTIVE — this is the current line of work.
ROADMAP anchors: Active Queue #3 (remainder), #4, #9, #23; panel-review
high tier (label calibration, evidence-fetching verify).

## Motivation

1.x is "URL in, consultant-grade artifact out, done well." As of v1.30.0 the
engineering backlog behind that promise is largely closed: the artifact
shipping contract, failover, budget controls, observability, the QA iteration
loop, and runtime robustness all shipped. What remains is concentrated in two
places — *measured quality* (is the analysis actually good, are the labels
actually true) and *core testability* (the pipeline heart is a ~1,900-line
function the suite can only test around).

## Workstreams, in dependency order

### 1. Measure the epistemics — SHIPPED (post-1.30.0: PRs #27, #28, refine acceptance guard)

All three pieces landed: evidence-based `--verify` (fetched snippets +
first-party/third-party provenance + deterministic self-corroboration
downgrade, PR #27); the label-calibration harness
(`qa/label_calibration.py` — deterministic claim sampler, traceability
audit with injectable fetch/judge seams, per-label precision, PR #28); and
the refine-loop anti-Goodhart guard (each iteration audited by the
calibration harness; traceability degradation reverts the iteration).

**Remaining within this workstream:**
- ~~Wire the metric into the model_eval scorecard~~ — DONE: `primr calibrate
  "Company"` / `--calibrate-recent N` (with `--dry-run` judge-call/cost
  preview) audits shipped reports and persists `<report>.calibration.json`
  sidecars; the offline eval reads sidecars into per-report
  confirmed/reported traceability, a pooled `## Label Calibration`
  scorecard section, CSV columns, and a `FAIL_CALIBRATION` decision row.
  The hard gate is armed via `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY`
  (fraction); it stays unset (report-only) until the baseline below exists.
  The harness was also fixed for two artifact-format drifts a free corpus
  dry-run caught before any paid pass: the `[cite: N] url` Sources-appendix
  entry form, and standalone block-trailing labels ([paragraphs]
  [What to validate] [(Label)]) now associate with their block's prose and
  citations instead of sampling bare label lines.
- Run one calibration pass over recent current-format reports (measured by
  dry-run: ~164 judge calls ≈ $0.07–0.15) to establish the per-label
  baseline; then set `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` to the
  measured floor and flip it to an armed-by-default HARD eval gate
- Surface contradicted claims from `verification.json` in the report's
  trust summary (today: JSON + console only)
- v2 calibration check: Estimated/Hypothesis claims must NOT be
  verbatim-from-source (the mislabel in the other direction)

Original build spec (kept for reference):

- A claim sampler: extract N labeled claims per eval report with their
  citations (deterministic, reuses the citation parser)
- A traceability check per label class: `(Confirmed)` must trace to a cited
  source containing the claim's substance; `(Reported)` to a third-party
  source; `(Estimated)`/`(Hypothesis)` are exempt from traceability but
  must not be verbatim-from-source (else they're mislabeled Confirmed)
- An LLM-judged comparison step where string matching is insufficient, run
  against the *fetched source text*, never titles
- Surface per-label precision in the eval scorecard; add
  "Confirmed-claim traceability >= X%" as a HARD gate once a baseline exists

Validation: the harness is free to build (mocked); one calibration pass over
the standing eval corpus costs roughly one judge run (~$0.25–0.50).

**Evidence-fetching `--verify`.** Today `_classify_results` judges claim
support from search-result *titles*, and the claimed company's own domain can
"verify" a claim sourced from itself. Change:

- Fetch top-hit page content (reuse `scrape_external_sources_validated`,
  capped pages, existing SSRF guard) and classify against snippets
- Exclude same-registrable-domain sources from "supporting"
- Record contradicted claims in `verification.json` AND surface them in the
  report's trust summary

Validation: free with mocked search/scrape; one live `--verify` run ≈ $0.01.

**De-Goodhart the refine loop.** `primr refine` optimizes the artifact-
discipline score, which counts the tokens the regenerator can insert. Gate
acceptance on a check the scorer can't see: a claim spot-check (from the
calibration harness) on regenerated sections, or an LLM-judge delta. Reject
the iteration when discipline rose but independent quality didn't.

### 2. Refactor the orchestrators (#23) — EXTRACTION COMPLETE

Status: all ten stages of `perform_fast_research` extracted (Batches A–G,
~1,600 lines into eleven stage modules with ~110 hermetic tests); the
orchestrator is a ~295-line coordinator. Remaining: `FastRunContext`, the
per-module coverage target, the C901 budget, and the
`_execute_consulting_research` split. Working map:
[`23-orchestrator-refactor-map.md`](23-orchestrator-refactor-map.md).

`perform_fast_research` (~1,900 lines) interleaves I/O, LLM calls, and state
transitions; `_execute_consulting_research` (~270 lines) similar. Rules:

- **No behavior change** — seam introduction only; eval scores must be
  unchanged after the refactor
- Extract, in this order (each is independently shippable): scrape+corpus
  assembly; external search + gap analysis; workbook stage; the per-section
  writing loop; cross-validation + repair; strategy generation. Each becomes
  a function taking explicit inputs and returning structured results, with
  the LLM boundary injectable
- After the split: raise per-module coverage targets (research_agent ≥ 80%),
  then enable the `C901` complexity budget repo-wide

This unblocks every later pipeline change (batch API, overlap, routing) from
being reviewable diffs instead of edits inside a monster.

### 3. Consultant-grade strategic writing (#4)

One focused prompt-and-eval cycle, judged by the step-1 instruments:

- Section prompts tuned around management choices, operating constraints,
  likely economics, scenario paths, validation questions
- Fewer brittle section suppressions; constrained-evidence reasoning when
  direct data is thin
- Dense references concentrated in appendices; body reads as analysis
- Target: sparse-company runs feel substantive; rich-company runs sharp

Validation: this is inherently eval-judged. Budget one corpus pass per prompt
iteration (~$4–5 for n=5 at the standard recipe); cap at 2–3 iterations per
cycle; pre-register acceptance criteria before the first run (the
EVAL_V1_24_0 discipline).

### 4. Cost levers (#9 batch API, #19 pipeline overlap)

Mechanical after step 2. Batch API: `--batch-api` flag, xAI batch first,
graceful fallback to the executor path, batch pricing in `ModelConfig` so
estimates stay honest. Overlap: start external search once the homepage is
in; `asyncio.gather` with completion barriers; progress display shows
concurrent phases. Validation: deterministic tests free; one live batch run
to confirm the discount (~$0.50–0.80).

### Also in this band

- **#3 remainder** (live-site dependent, opportunistic): host-level positive
  markers, blocked-site CLI summary, hiring signals in `--premium`,
  BambooHR/iCIMS
- **Panel medium tier**: meeting-brief one-pager output mode, `--json`
  output for the main run, `primr replay` (record/replay run transcripts for
  demos), install extras (`primr[browser]`, `primr[ocr]`), sample gallery

## Exit criteria (1.x done)

1. Confidence labels have measured calibration with a hard eval gate
2. `--verify` verifies against fetched evidence, never titles
3. The three monster functions are split; pipeline-core coverage ≥ 80%;
   complexity budget enforced
4. A #4 prompt cycle has shipped with pre-registered acceptance met
5. Sparse-company and rich-company runs both judged at target by the eval
   harness; artifacts ship clean (gates at zero) on the standing corpus

## Explicitly not in 1.x

Anything from the 2.0 pillars (routing layer, memory, control-plane authz);
new output formats beyond the one-pager/JSON noted above; new scrape tiers.
