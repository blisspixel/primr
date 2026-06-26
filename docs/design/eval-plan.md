# Eval plan: what to spend on, in what order, and what counts as a pass

> **Purpose.** primr's quality changes are validated by eval, not unit tests, and
> evals cost real money. This doc **pre-registers** the pending evals - the
> hypothesis, the exact commands, the instruments, and the acceptance criteria -
> *before* any spend, so a paid run gives a decision instead of a post-hoc
> argument. Cheapest-first; stop early if a cheap step fails to justify the next.
>
> No corpus is committed (the no-real-company-data rule): the operator supplies
> real companies locally. Pick a **fixed** set and reuse it across runs so
> results are comparable. A good minimal set is two companies - one *sparse*
> (thin public signal) and one *rich* (filings, postings, press) - so both ends
> of the depth range are covered.

All commands assume `GEMINI_API_KEY` + `XAI_API_KEY` are set (the sub-$1 default
recipe). Free local judges (`--judges "ollama:<model>"`) keep grading at $0.

---

## Order of operations (cheapest first)

| # | Eval | What it answers | Approx cost | Gate to next |
|---|------|-----------------|-------------|--------------|
| 1 | Label-calibration baseline | Are `(Confirmed)/(Reported)` labels traceable to sources? Sets the gate threshold. | ~$0.10 | always run first |
| 2 | Framed vs unframed (tradecraft Step 4) | Does framing + hypothesis-steered collection produce a better brief? | ~$1.58 / company | only if you want to validate Step 4 |
| 3 | Content-depth prompt work (#4) | Do sharper section prompts (management choices, economics, scenarios, constrained-evidence) beat the current prompts? | ~$4–5 / company | only after #2 clears |

Do **not** run #3 before #2 clears, and don't run #2 before you care to (Step 4 is
opt-in and default-safe today). Run #1 any time - it's nearly free and arms a gate.

---

## Eval 1 - label-calibration baseline (~$0.10)

> **RESULT (3 reports, ~$0.02): SYSTEMIC grounding gap - this is the real quality
> lever.** Across three briefs (one mid-market, two large content-dense, with
> 25+ "Reported" claims between them): **Confirmed 8% traceability** (1/10 traced)
> and **Reported 0%** (0/25 traced). `unfetchable=0`, so sources *were* fetched
> and the claims still didn't trace - the labels over-claim their grounding. Not a
> thin-company fluke; the rich briefs confirmed it.
>
> **The full data-backed map (with Evals 2 & 4):** prose/analytical depth is
> *already strong* (a direct read of a brief confirmed consultant-grade tensions,
> evidence, discovery questions); evidence *plumbing* (collection-steering Eval 2,
> context-curation Eval 4) is a *wash, wash*; the one *measured* deficiency is
> **epistemic grounding** - the brief reads authoritative but its `(Confirmed)/
> (Reported)` labels don't trace to their cited sources. Cheapest to iterate of
> any lever: calibration scores it on *existing* reports for ~$0, so a
> label-honesty change is validated without expensive prose A/Bs. Doctrine-clean
> fix: judge whether each cited source supports the claim (model judgment + ground
> truth, like the shipped `--verify`) and *downgrade* labels that don't trace -
> judgment decides, the downgrade is mechanical; not a regex. **SHIPPED opt-in**
> (`PRIMR_LABEL_HONESTY=1`, `qa/label_honesty.py`): the pre-ship pass re-judges
> each `(Confirmed)`/`(Reported)` claim against its cited source and rewrites the
> untraceable ones to `(Estimated)`. Fail-safe by construction: confidence only
> lowers, `no_source`/`unfetchable`/uncertain verdicts keep the label, and a
> `_label_honesty.json` audit records every change. Default-off, never blocks
> shipping; the open follow-up is the agreement-validated calibration baseline
> that would justify promoting it toward default (a hard gate is never armed from
> a single noisy judge).

**Hypothesis:** the confidence labels primr emits are traceable to fetched source
text often enough to be trustworthy; we can set `FAIL_CALIBRATION`'s threshold
from measured numbers instead of a guess.

**Commands**
```bash
primr calibrate --calibrate-recent 10 --dry-run    # preview judge-call count + cost
primr calibrate --calibrate-recent 10              # run it (uses the local/cloud judge per --judge)
```

**Instrument:** the `qa/label_calibration.py` harness (per-label precision of
`(Confirmed)`/`(Reported)` against fetched source text; `no_source` counts
against; unfetchable excluded). Use `--judge local` for $0 if Ollama is up.

**Pre-registered acceptance / output:** record measured per-label precision across
the sample. Set `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` to a *conservative* value
(e.g. the observed 25th percentile, rounded down) so the gate fails only on real
regressions, not noise. This is a measurement-and-threshold step, not pass/fail.

---

## Eval 2 - framed vs unframed (tradecraft Step 4, ~$1.58/company)

> **RESULT (n=1, ~$0.69 spent): NO-GO for default-promotion.** First A/B (one
> mid-market financial-services company, standard recipe ~$0.35/arm) - steering
> fired correctly but the blind pairwise grade was a **wash, slightly favoring
> unframed**; neutral cost; both gates PASS. Did **not** clear the acceptance
> criterion below. Root cause: steered collection trades *breadth for depth* and
> fights the broad fixed report structure. **Decision:** keep Step 4 opt-in, do
> not promote, do not build more collection-steering on it. Directional (n=1).
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

**Decision:** clears all three → keep/recommend framing as the steer for real
runs and proceed to Eval 3. Fails #1 → the steering isn't earning its keep;
reconsider Step 4 rather than building on it. Fails #2/#3 → fix the regression
before re-judging quality.

---

## Eval 3 - content-depth prompt work (#4, ~$4–5/company)

Only after Eval 2 clears. Same A/B shape: current section prompts (baseline) vs a
candidate prompt revision (management choices, operating constraints, likely
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

> **RESULT (n=1, ~$1.4 spent): WASH - keep off/opt-in, do not promote.** A/B on a
> large content-dense company whose corpus was **~360k chars** (curation dropped
> ~72%, choosing the most-relevant 100k vs the first 100k). Blind pairwise grade:
> **every section tied** (section-majority 0/5/0; the strongest cross-family judge
> tied on all five), both gates PASS. So relevance-ranking the corpus subset does
> not change brief quality even when it fires hard.
>
> **Inference (with Eval 2): the bottleneck is not the evidence plumbing.** Two
> levers tested - steered *collection* (Eval 2) and curated *context* (this one) -
> both wash. Brief quality rides on the analysis **workbook** + external sources +
> the **writer prompts**, not on which raw pages reach the writer. The next real
> quality lever is the analysis/section **prompts** (content depth - Eval 3),
> not collection or context-assembly plumbing. The curation feature stays merged
> but default-off (no harm; available if a future routing version wants the seam).

**Why this is the more promising lever than more collection-steering.** A dry-run
shows the standard pipeline pushes **~1.9M input tokens** into the analysis +
section-writing stages (raw corpus + external sources, dumped whole). That is
squarely in "lost-in-the-middle" / context-rot territory: past a point, more
tokens *hurt* reasoning and cost quadratically. Eval 2 showed steering *what we
collect* is a wash; this tests a different axis - *what reaches the model at the
analysis/writing step*.

**Hypothesis:** curating the context that reaches the analysis + writing stages
(relevance-rank the corpus, drop low-signal pages, route per-section evidence
instead of dumping everything) produces an equal-or-better brief at materially
lower token cost - and possibly *better* quality by reducing context rot.

**Magnitude (measured, honest):** the ~1.9M is **~23 section calls of ~60k
*cached* tokens each** (the cached-prefix split, roadmap #8), not one bloated
window. Cost is already softened by caching; the lever is mainly *quality* (less
rot in each 60k call) with cost upside if the prefix shrinks. So this is a **real
but modest** lever - flag- and eval-gated for exactly that reason.

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
