# Versioned Model Evaluation (Quality vs Cost)

When a new model or profile is released (for example, a new Pro/Flash/Grok variant), evaluate it with a repeatable run ID so decisions are data-driven.

## 1) Pick an eval version and fixed corpus

- Example eval ID: `eval-2026-02-r1`
- Use 5-10 representative companies (keep this set stable across model tests)
- Save runs under a dedicated folder per profile:

```bash
primr "ExampleCo A" https://example-a.com --mode full --output-dir output/evals/eval-2026-02-r1/full
primr "ExampleCo A" https://example-a.com --mode full --lite --output-dir output/evals/eval-2026-02-r1/lite
primr "ExampleCo A" https://example-a.com --fast --output-dir output/evals/eval-2026-02-r1/fast
```

Offline comparison (no API spend):

```bash
primr --eval --eval-id eval-2026-02-r1
primr --eval --eval-id eval-2026-02-r1 --eval-company "ExampleCo"
```

By default, `--eval` auto-stages matching existing reports from `output/` into `output/evals/<eval-id>/<profile>/` and writes `staging_manifest.json` for reproducibility.

Optional controlled fill-in for missing profile/company pairs (explicit spend caps required):

```bash
primr --eval --eval-id eval-2026-02-r1 --eval-run-missing --eval-manifest eval_companies.csv --eval-max-new-runs 2 --eval-max-estimated-cost 12
```

## LLM Judge Overlays

Optional LLM-judge overlays on staged reports:

```bash
# Cloud judge (requires spend cap)
primr --eval --eval-id eval-2026-02-r1 --eval-llm-judge --eval-judge-provider grok --eval-judge-model grok-4-1-fast-reasoning --eval-judge-max-cost 0.25

# Local judge against an Ollama/OpenAI-compatible endpoint
primr --eval --eval-id eval-2026-03-local --eval-llm-judge --eval-judge-provider local --eval-judge-model qwen3:30b --eval-judge-base-url http://localhost:11434/v1

# Local multi-model sweep on the same staged company/profile pairs
primr --eval --eval-id eval-2026-03-local-sweep --eval-llm-judge --eval-judge-provider local --eval-judge-models qwen3:30b qwen2.5-coder:32b-instruct-q5_K_M qwen2.5:14b --eval-judge-base-url http://localhost:11434/v1

# Local sweep from a maintained named shortlist
primr --eval --eval-id eval-2026-03-local-sweep --eval-llm-judge --eval-judge-provider local --eval-judge-model-list 4090-top10 --eval-judge-base-url http://localhost:11434/v1
```

Local judge runs now evaluate every staged non-baseline profile against the chosen baseline, not just the first available profile. They write one JSON artifact per model plus `local_judge_summary.json` / `local_judge_summary.md` with candidate-profile coverage, winner consensus, and per-profile breakdowns for side-by-side comparison.

This is useful for evaluating local models against existing cloud-generated reports before routing any production pipeline stages to local inference. It is still a judge-based acceptance layer, not proof that a local model is ready to replace report-writing or deep-research stages directly.

## 2) Track the same metrics for every profile

- Trust gate (must-pass): citation coverage + section completeness + confidence-label quality
- Decision utility: actionable recommendations, risks/tradeoffs, key validation questions, and depth of strategic interpretation
- Reuse quality (human + AI): structured headings, tables, machine-friendly signal density, and readable appendix-style sourcing
- Efficiency: utility-per-dollar and total estimated cost
- Runtime: end-to-end duration per company

These dimensions are aligned to the README goal: producing deep strategic analysis that gets humans and AI up to speed quickly and safely, not just producing long reports.

## 3) Use a clear decision rule

Adopt a candidate profile when all are true:

- Trust gate passes for compared reports
- Mean decision-utility score >= 80% of baseline profile
- Mean cost <= 20% of baseline (or your own budget target)
- Utility-per-dollar improves enough to matter operationally

This lets you make explicit tradeoffs such as "80% of quality for 1/10th of cost" with evidence, not intuition.
