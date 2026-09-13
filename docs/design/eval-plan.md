# Evaluation protocols and historical results

> **Purpose.** primr's quality changes are validated by eval, not unit tests, and
> model-backed evals can cost real money. This doc records protocols and results.
> Freeze the hypothesis, exact commands, instruments, and acceptance criteria
> before new spend so a paid run gives a decision instead of a post-hoc argument.
> Start with low-cost checks and stop if they fail to justify further spend.
>
> No corpus is committed (the no-real-company-data rule): the operator supplies
> real companies locally. Freeze representative selection before evaluation.
> A sparse/rich pair can expose pilot defects; it does not establish readiness
> for a production quality gate or a backend promotion.

The executable queue lives only in [Next Steps](../NEXT_STEPS.md). The numbered
experiments below preserve their original hypotheses and historical outcomes;
their order does not supersede that queue. Quoted costs are historical planning
figures, not current estimates or approved spend. Every new billable run or
judge call requires a fresh exact estimate, explicit approval, and a cost cap.
Local artifact inspection needs no provider key. Configured local judges can
avoid model API charges; host-plan billing must be verified separately.

---

## Experiment index

| # | Eval | What it answers | Historical planning cost | Interpretation |
|---|------|-----------------|-------------|--------------|
| 1 | Label-calibration baseline | Are `(Confirmed)/(Reported)` labels traceable to sources? | ~$0.10 | Report-only measurement followed by readiness inspection and an operator decision |
| 2 | Framed vs unframed (tradecraft Step 4) | Does framing + hypothesis-steered collection produce a better brief? | ~$1.58 / company | Historical pilot did not justify default promotion |
| 3 | Content-depth prompt work (#4) | Do sharper section prompts (management choices, economics, scenarios, constrained-evidence) beat the current prompts? | ~$4-5 / company | Re-register a bounded experiment before execution |
| 4 | Context curation | Does a different evidence subset improve the brief? | ~$1.58 / company | Historical pilot did not justify default promotion |

Calibration does not arm a gate. Start with existing artifacts and zero-spend
readiness inspection; later experiments depend on trustworthy instruments and
the current executable card, not a historical pilot's place in this table.

---

## Eval 1 - label-calibration baseline (~$0.10)

> **Historical result (3 reports, approximately $0.02): grounding defects worth
> investigating.** The recorded counts were 1/10 Confirmed claims traced and
> 0/25 Reported claims traced, with `unfetchable=0`. These sampled judge verdicts
> exposed a problem in that sample. They do not establish a
> population error rate or prove that other quality dimensions are satisfactory.
> The n=1 pilots in Evals 2 and 4 did not justify their respective promotions;
> they did not rule out improvements to collection or context assembly.

The subsequent July 13, 2026 milestone and operator decision are recorded in the
[roadmap](https://github.com/blisspixel/primr/blob/main/ROADMAP.md): five reports,
50 evidence reviews, 33/37 comparable
cloud/local verdicts agreeing, and a deliberate `keep_report_only` decision
because two reports lacked a decidable Confirmed floor. These are historical
measurements, not a current-file inspection or proof that agreement is accuracy.

**Hypothesis:** confidence-label traceability can be measured against fetched
source text, with evaluator errors and missing evidence made explicit, to inform
a reviewed regression-gate decision.

**Commands**
```bash
primr calibrate --calibrate-recent 10 --dry-run    # preview judge-call count + cost
```

Choose the judge explicitly and obtain approval for any billable execution
before running calibration. An aggregate latest-N sample is not a curated
representative baseline.

**Instrument:** the `qa/label_calibration.py` harness (per-label precision of
`(Confirmed)`/`(Reported)` against fetched source text; `no_source` counts
against; unfetchable excluded). Use `--judge local` for $0 if Ollama is up.

**Acceptance / output:** record per-label precision, decidable counts,
unfetchable/no-source counts, and evaluator-validation results. Freeze report
and sidecar fingerprints in an explicitly curated `--pack-selection` manifest
with representative tags. Use `--pack-manifest`, then `--baseline-from` and
`--inspect-baseline` to inspect readiness without model calls. Resolve the
reported blockers and review the evidence before recording a decision through
`--baseline-decision-from` and `--baseline-decision keep_report_only|arm_gate`.
The command writes a decision record; it does not set an environment variable.
Use `--inspect-baseline-decision` to verify the record against current artifacts.
`arm_gate` is available only when the inspected template permits it and the
operator has completed the required review. No example in this document
authorizes arming `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` automatically.

The implementation's minimum observed report rate is a candidate **regression
floor**, not the desired **quality bar**. Define the latter from material error
risk and analyst usefulness before evaluating a change. A low observed floor
does not become acceptable quality because every report becomes decidable.
Distinguish missing evidence or failed assessment from a sparse report with no
warranted Confirmed claims. Do not add artificial Confirmed labels to make a
baseline pass; preserve honest labels and the report-only decision when required.

### Validate the evaluators

Freeze human-adjudicated clean cases and controlled variants before judging.
Cover wrong numbers/entities/dates, negation, stale evidence, unsupported causal
claims, insufficient independent support, omitted contradictions, and incorrect
citation attribution. Keep these cases separate from the production report
scores. Report detection precision and recall by error category, sample counts,
abstention and retrieval-failure rates, and uncertainty intervals. Pre-register
error tolerances and the minimum usable sample for each decision. Missing
evidence is not a correct verdict, and high precision cannot excuse low coverage.

Blind model/provider identity, test order sensitivity, and obtain source-grounded
human review of consequential disagreements **and a pre-registered random sample
of unanimous approvals**. Record shared errors as well as agreement. Assess
claim support separately from source authority and stylistic trust cues; do not
count correlated scores as independent confirmation.

This protocol addresses findings from [REFLECT](https://arxiv.org/abs/2605.19196)
(May 18, 2026), whose tested research-agent judges remained below 55% overall
failure-detection accuracy, and
[Nine Judges, Two Effective Votes](https://arxiv.org/abs/2605.29800) (May 28,
2026), which found strongly correlated panel errors. Both are preprints on their
own benchmarks, not Primr measurements. The August 21, 2026 preprint
[Trust-Truth Separability](https://arxiv.org/abs/2608.21097) also finds source
labels can shift truth judgments on identical QA. The peer-reviewed
[VeriFact](https://aclanthology.org/2025.emnlp-main.905/) (EMNLP, November 2025)
supports measuring factual recall and relational context alongside precision.
These sources motivate evaluator stress tests; they do not supply universal
promotion thresholds.

---

## Eval 2 - framed vs unframed (tradecraft Step 4, ~$1.58/company)

> **Historical result (n=1, ~$0.69 spent): no default promotion.** First A/B (one
> mid-market financial-services company, standard recipe ~$0.35/arm) - steering
> fired correctly but the blind pairwise grade was a **wash, slightly favoring
> unframed**; neutral cost; both gates PASS. Did **not** clear the acceptance
> criterion below. A possible explanation was a breadth/depth tradeoff against
> the fixed report structure; this pilot did not isolate that cause.
> **Decision:** keep Step 4 opt-in without default promotion. Directional (n=1).
> Full write-up in [research-tradecraft.md](research-tradecraft.md) Step 4.

**Hypothesis:** when a run is framed (`--purpose/--question`), the Day-1
hypothesis tree steers collection toward testing branches, producing a brief that
a blind panel prefers - without a trust-gate or cost regression.

**Commands** (per company; `<co>`/`<url>` are the operator's real targets)
```bash
# unframed arm (today's default path)
py -3.12 scripts/eval/run_recipe_brief.py --company "<co>" --url <url> \
    --recipe standard --tag standard-unframed
# framed arm (operator intent steers framing + tree + gap queries)
py -3.12 scripts/eval/run_recipe_brief.py --company "<co>" --url <url> \
    --recipe standard --tag standard-framed \
    --purpose <purpose> --question "<the decision question>"
# blind pairwise grade (free local judges)
py -3.12 scripts/eval/grade_pairwise.py --label framing \
    --baseline output/eval/briefs/standard-unframed/<brief>.md \
    --candidate output/eval/briefs/standard-framed/<brief>.md \
    --judges "ollama:<model>"
```

**Instruments:** `grade_pairwise.py` (position-swapped, length-penalized, panel;
free local judges), plus each run's own trust gate and the `~$cost` line.

**Pre-registered acceptance (ALL must hold across the fixed company set):**
1. **Quality:** framed wins the **section-majority** on the strategic sections
   (Executive Summary, SWOT, Strategic Positioning, Competitive Landscape,
   Strategic Tensions) - i.e. more candidate-wins than baseline-wins by section
   majority - on **both** the sparse and the rich company.
2. **No trust regression:** the framed arm's trust gate is PASS, at or above the
   unframed arm.
3. **No cost regression:** framed run cost ≤ ~110% of unframed (framing adds the
   cheap tree pass; if it balloons cost, that's a fail).

**Decision interpretation:** clears all three → consider framing promotion
after evaluator validation and review. Fails #1 → the tested steering did not
demonstrate its benefit; reconsider Step 4 before building on it.
Fails #2/#3 → fix the regression
before re-judging quality.

---

## Eval 3 - content-depth prompt work (#4, ~$4-5/company)

When the executable queue selects this experiment, re-register the candidate
and decision criteria using validated evaluators. Same A/B shape: current
section prompts (baseline) vs a candidate prompt revision (management choices,
operating constraints, likely
economics, scenario paths, constrained-evidence reasoning, explicit "so what"
per section - content *within* the fixed structure, never new sections). Judge
with `grade_pairwise.py` + the calibration instrument from Eval 1.

**Pre-register before running** (fill in when the candidate prompt is ready):
the exact prompt diff, the same fixed company set, and the same three acceptance
criteria as Eval 2 (quality by section majority, no trust regression, no cost
regression). Structure stays the curated `company_overview.yaml` scaffold - see
[research-tradecraft.md](research-tradecraft.md) Step 5 and the structure
carve-out in [agentic-balance.md](agentic-balance.md).

---

## Eval 4 - context curation at analysis/writing (candidate; ~$1.58/company)

> **Historical result (n=1, ~$1.4 spent): wash, no default promotion.** A/B on a
> large content-dense company whose corpus was **~360k chars** (curation dropped
> ~72%, choosing the most-relevant 100k vs the first 100k). Blind pairwise grade:
> **every section tied** (section-majority 0/5/0; the strongest cross-family judge
> tied on all five), both gates PASS. This company, configuration and grading
> protocol did not demonstrate a quality improvement. The feature remains
> default-off. Together with Eval 2, this supports withholding those promotions;
> it does not prove evidence collection or context assembly cannot improve
> reports, nor establish workbook or prompt changes as the causal alternative.

**Original motivation:** a historical dry-run estimated approximately 1.9M
aggregate input tokens across analysis and section-writing calls. This motivated
testing which evidence reaches each model call. Aggregate tokens do not measure
one context window, prove context degradation, or imply quadratic API charges.

**Hypothesis:** curating the context that reaches the analysis + writing stages
(relevance-rank the corpus, drop low-signal pages, route per-section evidence
instead of dumping everything) produces an equal-or-better brief at materially
lower token cost - and possibly *better* quality by reducing context rot.

**Magnitude (measured, honest):** the ~1.9M is **~23 section calls of ~60k
*cached* tokens each** (the cached-prefix split, roadmap #8), not one bloated
window. Cost is already softened by caching; the lever is mainly *quality* (less
irrelevant context in each call) with cost upside if the prefix shrinks. Any
benefit remains a hypothesis to measure, not a consequence of the token count.

**Status: BUILT (flag-gated, default off).** `core/context_curation.py`
`rank_corpus_by_relevance()` replaces the section writer's blind first-100k-chars
corpus truncation with the most-relevant 100k (ranked by term-overlap with the
analysis workbook), shared across sections so the cached prefix is preserved.
Activate with `PRIMR_SECTION_EVIDENCE_CURATION=1`; default off is byte-identical.

**Method (A/B, same harness):** baseline = current pipeline (env unset);
candidate = `PRIMR_SECTION_EVIDENCE_CURATION=1`, same recipe + company set (use
companies large enough that the corpus exceeds the 100k budget - otherwise it's a
no-op). Grade with `grade_pairwise.py` (free local judges) + the Eval 1
calibration instrument.

**Pre-registered acceptance (for the BUILT shared-rank version - quality test).**
The shipped curation keeps the *same* 100k budget (most-relevant 100k vs first
100k), so it does **not** reduce tokens; its value is purely *which* evidence the
writer sees. Judge it on quality at no regression:
1. **Quality:** candidate **wins or ties** by section majority (a clear win →
   promote toward default; a wash → keep opt-in, no harm; a loss → the rank hurts,
   revert/rethink).
2. **No trust regression.**
3. **No cost regression** (same budget → cost should be ~flat; a jump means the
   rank changed cacheable content unexpectedly).

> The **≥20% token-reduction** goal belongs to the *separate, not-yet-built*
> per-section routing version (each section gets a smaller, section-specific
> subset), which breaks the shared cached prefix and carries the breadth/depth
> risk Eval 2 surfaced. Scope + pre-register that as its own eval if/when the
> shared-rank version proves worthwhile here.

**Doctrine note:** curation is *context assembly*, not a content gate. It can be a
deterministic relevance rank (cheap, stable - a legitimate rule) or model-judged
selection; either way it's measured by this eval, never a regex that judges
quality. Build the curator behind a flag so the raw path stays the default until
this clears (no speculative default change).

---

## Why pre-registration

Stating the acceptance criteria *before* the run is the anti-Goodhart, anti-vibes
discipline the doctrine requires (Model Adaptability: "data-driven adoption, no
gut decisions"). It also bounds spend: each eval has a clear go/no-go, so a cheap
failing step stops the expensive one from running at all.
