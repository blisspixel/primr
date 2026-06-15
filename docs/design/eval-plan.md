# Eval plan: what to spend on, in what order, and what counts as a pass

> **Purpose.** primr's quality changes are validated by eval, not unit tests, and
> evals cost real money. This doc **pre-registers** the pending evals — the
> hypothesis, the exact commands, the instruments, and the acceptance criteria —
> *before* any spend, so a paid run gives a decision instead of a post-hoc
> argument. Cheapest-first; stop early if a cheap step fails to justify the next.
>
> No corpus is committed (the no-real-company-data rule): the operator supplies
> real companies locally. Pick a **fixed** set and reuse it across runs so
> results are comparable. A good minimal set is two companies — one *sparse*
> (thin public signal) and one *rich* (filings, postings, press) — so both ends
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
opt-in and default-safe today). Run #1 any time — it's nearly free and arms a gate.

---

## Eval 1 — label-calibration baseline (~$0.10)

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

## Eval 2 — framed vs unframed (tradecraft Step 4, ~$1.58/company)

> **RESULT (n=1, ~$0.69 spent): NO-GO for default-promotion.** First A/B (one
> mid-market financial-services company, standard recipe ~$0.35/arm) — steering
> fired correctly but the blind pairwise grade was a **wash, slightly favoring
> unframed**; neutral cost; both gates PASS. Did **not** clear the acceptance
> criterion below. Root cause: steered collection trades *breadth for depth* and
> fights the broad fixed report structure. **Decision:** keep Step 4 opt-in, do
> not promote, do not build more collection-steering on it. Directional (n=1).
> Full write-up in [research-tradecraft.md](research-tradecraft.md) Step 4.

**Hypothesis:** when a run is framed (`--purpose/--question`), the Day-1
hypothesis tree steers collection toward testing branches, producing a brief that
a blind panel prefers — without a trust-gate or cost regression.

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
   Strategic Tensions) — i.e. more candidate-wins than baseline-wins by section
   majority — on **both** the sparse and the rich company.
2. **No trust regression:** the framed arm's trust gate is PASS, at or above the
   unframed arm.
3. **No cost regression:** framed run cost ≤ ~110% of unframed (framing adds the
   cheap tree pass; if it balloons cost, that's a fail).

**Decision:** clears all three → keep/recommend framing as the steer for real
runs and proceed to Eval 3. Fails #1 → the steering isn't earning its keep;
reconsider Step 4 rather than building on it. Fails #2/#3 → fix the regression
before re-judging quality.

---

## Eval 3 — content-depth prompt work (#4, ~$4–5/company)

Only after Eval 2 clears. Same A/B shape: current section prompts (baseline) vs a
candidate prompt revision (management choices, operating constraints, likely
economics, scenario paths, constrained-evidence reasoning, explicit "so what"
per section — content *within* the fixed structure, never new sections). Judge
with `grade_pairwise.py` + the calibration instrument from Eval 1.

**Pre-register before running** (fill in when the candidate prompt is ready):
the exact prompt diff, the same fixed company set, and the same three acceptance
criteria as Eval 2 (quality by section majority, no trust regression, no cost
regression). Structure stays the curated `company_overview.yaml` scaffold — see
[research-tradecraft.md](research-tradecraft.md) Step 5 and the structure
carve-out in [agentic-balance.md](agentic-balance.md).

---

## Eval 4 — context curation at analysis/writing (candidate; ~$1.58/company)

**Why this is the more promising lever than more collection-steering.** A dry-run
shows the standard pipeline pushes **~1.9M input tokens** into the analysis +
section-writing stages (raw corpus + external sources, dumped whole). That is
squarely in "lost-in-the-middle" / context-rot territory: past a point, more
tokens *hurt* reasoning and cost quadratically. Eval 2 showed steering *what we
collect* is a wash; this tests a different axis — *what reaches the model at the
analysis/writing step*.

**Hypothesis:** curating the context that reaches the analysis + writing stages
(relevance-rank the corpus, drop low-signal pages, route per-section evidence
instead of dumping everything) produces an equal-or-better brief at materially
lower token cost — and possibly *better* quality by reducing context rot.

**Magnitude (measured, honest):** the ~1.9M is **~23 section calls of ~60k
*cached* tokens each** (the cached-prefix split, roadmap #8), not one bloated
window. Cost is already softened by caching; the lever is mainly *quality* (less
rot in each 60k call) with cost upside if the prefix shrinks. So this is a **real
but modest** lever — flag- and eval-gated for exactly that reason.

**Status: BUILT (flag-gated, default off).** `core/context_curation.py`
`rank_corpus_by_relevance()` replaces the section writer's blind first-100k-chars
corpus truncation with the most-relevant 100k (ranked by term-overlap with the
analysis workbook), shared across sections so the cached prefix is preserved.
Activate with `PRIMR_SECTION_EVIDENCE_CURATION=1`; default off is byte-identical.

**Method (A/B, same harness):** baseline = current pipeline (env unset);
candidate = `PRIMR_SECTION_EVIDENCE_CURATION=1`, same recipe + company set (use
companies large enough that the corpus exceeds the 100k budget — otherwise it's a
no-op). Grade with `grade_pairwise.py` (free local judges) + the Eval 1
calibration instrument.

**Pre-registered acceptance:**
1. **Quality:** candidate is **at least a wash** (section-majority not worse than
   baseline) — for context curation, "no worse + cheaper" is already a win; a
   quality *gain* is upside.
2. **Cost:** candidate input tokens materially lower (target ≥20% reduction) at
   no trust-gate regression.
3. **No trust regression.**

**Doctrine note:** curation is *context assembly*, not a content gate. It can be a
deterministic relevance rank (cheap, stable — a legitimate rule) or model-judged
selection; either way it's measured by this eval, never a regex that judges
quality. Build the curator behind a flag so the raw path stays the default until
this clears (no speculative default change).

---

## Why pre-registration

Stating the acceptance criteria *before* the run is the anti-Goodhart, anti-vibes
discipline the doctrine requires (Model Adaptability: "data-driven adoption, no
gut decisions"). It also bounds spend: each eval has a clear go/no-go, so a cheap
failing step stops the expensive one from running at all.
