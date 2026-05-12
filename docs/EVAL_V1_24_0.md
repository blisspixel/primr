# v1.24.0 Cross-Provider Eval — Decision Plan

> **Status:** matrix registered, eval not yet executed.
> **Author:** Primr maintainer
> **Date drafted:** 2026-05-08
> **Decision deadline:** before v1.24.0 ships

This document records the decision criteria for the v1.24.0 cross-provider eval **before the run**. The discipline is the same one that produced the v1.22.0 dispatch decisions: write down what you'd accept and what you'd reject in advance, so the actual scorecard becomes a mechanical lookup against pre-committed gates rather than a post-hoc rationalization.

The hard goal is one sentence: **the default `primr` command produces an excellent strategic-analysis report for under $1.**

If no candidate clears the bar, v1.24.0 doesn't ship a new default — we keep the current ~$4.27 Grok 4.3 hybrid and document why. "Failed eval" is a valid outcome.

---

## 1. The matrix

11 candidate profile slots are registered in `src/primr/config/eval_profiles.py`. They split into four groups:

### 1A. Cloud sub-$1 candidates (the headline group)

| Slot | Reasoning | Writing | Utility | Est. cost | Stage 1 |
|---|---|---|---|---|---|
| `grok43-flashlite` | Grok 4.3 (cached) | Gemini 3.1 Flash-Lite | Gemini 3 Flash | ~$0.65 | yes |
| `grok43-nano` | Grok 4.3 (cached) | GPT-5.4-nano | GPT-5.4-nano | ~$0.55 | yes |
| `grok43-mini` | Grok 4.3 (cached) | GPT-5.4-mini | GPT-5.4-mini | ~$0.85 | yes |
| `grok43-haiku-batch` | Grok 4.3 (cached) | Haiku 4.5 (batch) | Haiku 4.5 (batch) | ~$0.80 | yes |
| `all-gemini` | Gemini 3.1 Pro | Gemini 3.1 Flash-Lite | Gemini 3 Flash | ~$0.95 | yes |
| `o4mini-flashlite` | o4-mini | Gemini 3.1 Flash-Lite | Gemini 3 Flash | ~$0.55 | **deferred** |

The expected winner is `grok43-flashlite` — Grok 4.3's $0.20 cached input is the cheapest reasoning rate in the lineup, and Gemini 3.1 Flash-Lite at $0.25/$1.50 is the cheapest Gemini-3-era writer. But the eval is what decides, not the prediction.

> **Stage 1 deferral note (2026-05-08):** `o4mini-flashlite` is the only candidate that needs cross-provider *reasoning* (not just writing). primr's reasoning stages currently call `grok_client.grok_llm` directly — an xAI-specific path that doesn't honor the recipe override. Wiring cross-provider reasoning is a larger refactor than v1.24.0 stage 1 should absorb. The slot stays registered; it runs in stage 2 alongside the local cells once the wiring lands. The other 5 candidates use Grok 4.3 for reasoning and only differ in their writing/utility models, which the writing-tier recipe override does cover.

### 1B. Quality-ceiling reference (over budget, scoring baseline)

| Slot | Reasoning | Writing | Utility | Est. cost |
|---|---|---|---|---|
| `grok43max-flashlite` | Grok 4.3 (max effort) | Gemini 3 Flash | Gemini 3 Flash | ~$1.50 |

Expected to fail the <$1 hard gate. Used as the upper bound for utility-per-dollar comparison among slots that pass.

### 1C. Local / hybrid candidates (zero or low cost)

| Slot | Reasoning | Writing | Utility | Est. cost |
|---|---|---|---|---|
| `local-llama4scout` | Llama 4 Scout (10M ctx) | Llama 4 Scout | Llama 4 Scout | $0.00 |
| `local-qwen32b` | Qwen3 32B | Qwen3 32B | Qwen3 7B | $0.00 |
| `hybrid-grok-local` | Grok 4.3 (cached) | Qwen3.6 35B-A3B | Qwen3 7B | ~$0.30 |

Local cells trivially win utility-per-dollar (cost = 0 means infinity). The binding question is absolute quality — can free match cloud?

> **Scheduling note (May 2026):** the local + hybrid cells are **deferred** from the v1.24.0 deciding eval. The RTX 4090 isn't available during the v1.24.0 window. The cloud cells (groups 1A + 1B) plus the current-default baseline (1D) are sufficient to pick a v1.24.0 default. The local cells remain registered in `eval_profiles.py` and run as `eval-2026-05-r2` when the GPU is free; that incremental run uses the same registered slots and only needs to score the new pairs (this is exactly what the dynamic profile-slot registration was built for). If the local matrix later produces a recipe that beats the v1.24.0 cloud winner, default flips in a v1.24.x patch.

### 1D. Current default (regression baseline)

| Slot | Reasoning | Writing | Utility | Est. cost |
|---|---|---|---|---|
| `grok43-current-default` | Grok 4.3 | Grok 4.20-NR | Grok 4.20-NR | ~$4.27 |

The recipe v1.24.0 is trying to replace. Establishes the quality bar.

---

## 2. Decision criteria

### 2A. Hard gates (must clear all)

A candidate that fails any hard gate is **disqualified** regardless of how it scores on soft gates. No exceptions.

1. **Cost gate.** Mean total run cost across the eval corpus must be **< $1.00 USD**.
2. **Trust gate.** `trust_pass_rate` must be **>= the current `grok43-current-default` baseline** measured on the same corpus.
3. **Drift gate.** No regression in instruction-line leakage or `[cross-ref ...]` / `[workbook]` markers vs the baseline (see ROADMAP "Artifact Drift in the Standard Pipeline"). Quantitative threshold: bare `**What to validate:` lines per report <= baseline mean.
4. **Section completeness gate.** `key_sections_found / key_sections_total` >= 0.75 on every individual report (not just mean).

### 2B. Soft gates (tiebreakers among hard-gate survivors)

Among slots that clear all hard gates, rank by these in order of priority:

1. **Decision-utility score.** Mean `decision_utility_score` across the corpus. Higher is better. Floor: must be within 5% of the baseline. Slots that drop more than 5% below baseline lose even with a cost win.
2. **Utility-per-dollar.** `decision_utility_score / estimated_cost_usd`. Higher is better. This is where local and hybrid candidates can make headlines but only if their absolute decision-utility clears the soft floor above.
3. **LLM-judge subjective quality.** Run `primr eval --eval-llm-judge --eval-judge-provider grok --eval-judge-model grok-4.3` over the candidate-vs-baseline pairs. Optional secondary run with local Ollama (`run_local_judge`) for independent confirmation. Higher win rate is better.
4. **Latency.** Wall-clock time within 10% of baseline. Going slower than 50 minutes per run is a real UX regression even if cheaper.

### 2C. Decision tree

```
For each registered profile slot:
    Run primr against eval corpus, generate reports
    Stage outputs to output/evals/eval-2026-05-r1/<slot-name>/

Run primr eval with all slots specified
    → emits scorecard.md, scorecard.csv

For each slot's summary:
    if trust_pass_rate < baseline.trust_pass_rate:
        DISQUALIFY (hard gate 2)
        continue
    if estimated_cost_usd >= 1.00:
        DISQUALIFY (hard gate 1)
        continue
    if drift_markers > baseline.drift_markers:
        DISQUALIFY (hard gate 3)
        continue
    if any individual report has section_ratio < 0.75:
        DISQUALIFY (hard gate 4)
        continue
    SURVIVOR

If no survivors:
    OUTCOME: v1.24.0 ships without a new default.
              Update ROADMAP entry, document in changelog.
              Keep grok43-current-default at ~$4.27.

If 1 survivor:
    OUTCOME: that slot's recipe becomes the new default.

If multiple survivors:
    Rank by soft gates 1 → 2 → 3 → 4.
    Top-ranked recipe becomes the new default.

Local-only candidates ranking:
    If a local candidate clears hard gates AND beats every cloud
    candidate's decision_utility_score, default flips to a hybrid
    where local handles bulk writing. Otherwise local stays
    informational (eval matrix coverage, not the production default).
```

### 2D. What does NOT factor into the decision

- "Vendor relationships." Primr is provider-agnostic. The default is whatever wins the scorecard, not whichever vendor is most strategically convenient.
- "Number of providers required." A multi-provider winner that needs 3 keys is fine; UX cost of extra setup is separate from the recipe pick.
- Aesthetic preferences for any specific model family.
- Pre-eval cost estimates (the numbers in `eval_profiles.py` are directional only — the *measured* cost from the eval run is what counts).

---

## 3. Eval corpus

The corpus must cover diverse signal profiles so a recipe that's good at one shape but bad at another doesn't ship as the default.

| Slot | Profile | Why this profile |
|---|---|---|
| 1 | Rich-signal large public | Tests the dense-evidence ceiling — does the recipe make use of abundant data, or compress it? |
| 2 | Mid-signal mid-market private | The default's most common workload. SaaS company with patchy public signal. |
| 3 | Sparse-signal early-stage | Tests constrained-evidence reasoning. Recipes that hallucinate fail this. |
| 4 | International / non-US | Different domain, different scrape patterns, different language signals in evidence. |
| 5 | Government / nonprofit / education | Org-aware link selection should differ from commercial; recipes that assume SaaS structure fail. |

Specific company picks are determined when the eval is set up — they should be:
- Not previously researched in primr (no cache contamination)
- Publicly accessible (no paywalled or auth-gated content)
- Stable (no major M&A or restructuring during the eval window)

Corpus picks are recorded in `output/evals/eval-2026-05-r1/manifest.json` as part of the eval run.

---

## 4. Process

### 4A. Pre-flight (cloud eval, eval-2026-05-r1)

1. Verify all four cloud provider keys are set: `XAI_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
2. Run `primr doctor` — confirm "Providers" section lists all four cloud providers.
3. Confirm `primr eval --eval-id eval-2026-05-r1 --eval-profiles grok43-flashlite ...` accepts the new slot names without error.
4. **Estimate the budget.** Each cloud slot costs ~$0.55-1.50 per company × 5 companies × 7 cloud slots = ~$25-50 cloud spend.

### 4A.bis. Pre-flight for the deferred local eval (eval-2026-05-r2)

When the RTX 4090 is free:

1. Verify Ollama is running and the target local models are pulled:
   - `ollama pull qwen3:32b qwen3.6:35b-a3b llama4:scout`
2. Run `primr doctor --local` — confirms VRAM, Ollama health.
3. Stage outputs to `output/evals/eval-2026-05-r2/<slot-name>/` and run the scorecard against the v1.24.0 winner only. Incremental scoring; no need to re-run cloud cells.

### 4B. Generation

1. Run primr against each (slot, company) cell. The pipeline must use the slot's recipe — that wiring is in `pick_model_for_role` (task #5) which is the next step after this eval-design task.
2. Output goes to `output/evals/eval-2026-05-r1/<slot-name>/<Company>_Strategic_Overview_<date>.{md,docx}`.
3. Track wall-clock latency per cell.
4. On any failure, retry once. If it fails again, mark the (slot, company) cell as missing and continue. The decision tree handles missing cells as DISQUALIFY for that slot (corpus coverage gate).

### 4C. Scoring

```bash
# v1.24.0 cloud-only eval (local matrix deferred to eval-2026-05-r2)
primr eval \
  --eval-id eval-2026-05-r1 \
  --eval-root output/evals \
  --eval-profiles grok43-current-default grok43-flashlite grok43-nano grok43-mini grok43-haiku-batch all-gemini o4mini-flashlite grok43max-flashlite \
  --eval-baseline grok43-current-default \
  --eval-no-auto-stage  # we generated reports manually above
```

This produces:
- `output/evals/eval-2026-05-r1/scorecard.md` — primary deliverable
- `output/evals/eval-2026-05-r1/scorecard.csv` — for spreadsheet analysis

Then run the LLM judge:

```bash
primr eval --eval-id eval-2026-05-r1 \
  --eval-llm-judge \
  --eval-judge-provider grok \
  --eval-judge-model grok-4.3 \
  --eval-judge-max-pairs 5
```

Optional second judge pass with local Ollama for independent confirmation.

### 4D. Decision

1. Apply the decision tree from section 2C against the scorecard.
2. Document the decision in `output/evals/eval-2026-05-r1/decision.md`:
   - Which slots survived the hard gates
   - Soft-gate ranking among survivors
   - The chosen new default recipe
   - Rationale tied to specific scorecard rows
3. Update `pick_model_for_role` in `src/primr/ai/routing.py` to use the chosen recipe (task #5).
4. Update README, CLAUDE.md, and ROADMAP to reflect the new default cost and recipe (task #6).
5. Tag and ship v1.24.0.

### 4E. Post-I/O re-eval (May 19-20, 2026)

Google I/O may drop a Gemini 3.2 Flash. If so:

1. Audit registry for changes (per the discipline in ROADMAP "Model Adaptability").
2. Register the new model as an additional ProfileSlot in `eval_profiles.py`.
3. Run primr against the eval corpus with the new slot only.
4. Stage outputs to `output/evals/eval-2026-05-r2/<new-slot-name>/`.
5. Run the scorecard against the v1.24.0 winner + the new slot only — incremental scoring, not a full re-do (this is what dynamic profile-slot registration unlocks).
6. If the new slot beats the v1.24.0 winner on hard + soft gates, swap defaults in a v1.24.1 patch.

---

## 5. Failure modes and how we'd respond

| If this happens | Then |
|---|---|
| No candidate clears hard gates | v1.24.0 ships without a new default. Document why. Keep ~$4.27 default. |
| Multiple cloud candidates are statistically tied | Pick the one with fewer required API keys (UX win). Document the tie. |
| Local candidate beats all cloud on quality | Investigate cause. If real, ship a hybrid default (cloud reasoning, local writing) as v1.24.0; document the cost-savings argument explicitly. |
| Specific company (e.g., sparse-signal) fails uniformly across recipes | The recipe isn't the problem — the pipeline is. Open a separate ROADMAP entry for sparse-signal handling. Pick the default recipe based on the other 4 corpus members. |
| Cache hit rate doesn't materialize as expected | Grok 4.3 cost climbs above $1; `grok43-flashlite` may flip to disqualified. The all-Gemini and o4-mini recipes become more important as fallbacks. Document the cache assumption was wrong; revisit prompt-cache prep work in ROADMAP. |
| Drift markers regress | Investigate which slot's writing model leaks template instructions. If it's a recipe-specific issue, eliminate that slot. If it's pipeline-wide, separate ROADMAP entry. |

---

## 6. Open questions to resolve before running the eval

These need answers before generation kicks off:

- [ ] **Recipe → execution wiring.** `pick_model_for_role` doesn't yet read profile recipes. Currently it routes by env keys + role. The eval generation step needs primr to actually use the slot's recipe when running. This is task #5 in the project queue. Until it lands, the eval can't run; we can only register the matrix.
- [ ] **Batch-API plumbing for `grok43-haiku-batch`.** The $0.50/$2.50 batch rate requires Anthropic batch API integration. If this slot can't actually use batch mode at eval time, its real cost is $1.00/$5.00 standard rate, which puts it over budget. Decide whether to drop the slot or wire batch-API support.
- [ ] **Specific corpus picks.** 5 companies with the profile mix in section 3. Should be picked and recorded before generation starts so the eval is reproducible.
- [ ] **Eval budget approval.** Cloud spend ~$25-50 total. Confirm before running.

---

## 7. Why this discipline

Eval-driven default decisions are easy to compromise after the fact. "We were close on the trust gate, let's call it a pass." "The vendor we like came in second; the difference isn't statistically meaningful anyway." The pattern is to shift the goalposts to fit the winner you wanted.

Writing the gates down before the run forecloses that. If `grok43-flashlite` doesn't clear the trust gate in actual measurement, it loses — even though I expect it to win. If `local-llama4scout` clears all gates with room to spare, it wins, even though a fully-local default would be a bigger architectural change than I'm planning for v1.24.0.

The point of writing this doc is to be bound by it. Read this back when the scorecard lands.
