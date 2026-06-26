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

# Focused RTX 4090 sweep before paying for another sub-dollar API comparison
primr --eval --eval-id eval-2026-06-4090-vs-subdollar --eval-local-stage website-summary --eval-judge-provider local --eval-judge-model-list 4090-report-race --eval-judge-base-url http://localhost:11434/v1
```

Local judge runs now evaluate every staged non-baseline profile against the chosen baseline, not just the first available profile. They write one JSON artifact per model plus `local_judge_summary.json` / `local_judge_summary.md` with candidate-profile coverage, winner consensus, and per-profile breakdowns for side-by-side comparison.

This is useful for evaluating local models against existing cloud-generated reports before routing any production pipeline stages to local inference. It is still a judge-based acceptance layer, not proof that a local model is ready to replace report-writing or deep-research stages directly.

For a 24 GB RTX 4090 or comparable local box, start with `4090-report-race` before the broader `4090-top10` sweep. It keeps the first local run cheap in wall-clock time and answers the product question directly: is the local box already good enough for this stage, or is the ~$1 API route still buying meaningful quality? Promote local stages only when the eval artifacts show quality within the accepted band and the run sidecars make provenance unambiguous.

## 2) Track the same metrics for every profile

- Trust gate (must-pass): citation coverage + section completeness + confidence-label quality
- Decision utility: actionable recommendations, risks/tradeoffs, key validation questions, and depth of strategic interpretation
- Reuse quality (human + AI): structured headings, tables, machine-friendly signal density, and readable appendix-style sourcing
- Efficiency: utility-per-dollar and total estimated cost
- Runtime: end-to-end duration per company
- Artifact drift: per-report `scaffolding_leaks` count and a per-profile `total_scaffolding_leaks` aggregate (leaked internal scaffolding that should never reach a deliverable). Surfaced in the scorecard's `## Artifact Drift` section (clean/DRIFT per profile) and a `scaffolding_leaks` CSV column. Target: 0 - non-zero is a regression, tracked every eval run rather than via ad-hoc offline scans.
- Label calibration: traceability of `(Confirmed)`/`(Reported)` claims against the *fetched text* of their cited sources, measured by `primr calibrate` (a separate, bounded paid step - pennies per report) and persisted as `<report>.calibration.json` sidecars next to the staged reports. The offline eval reads the sidecars into per-report traceability, a pooled `## Label Calibration` scorecard section, and `confirmed_traceability` / `reported_traceability` CSV columns. Set `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` (a fraction, e.g. `0.8`) to arm the hard gate: profiles below it get `FAIL_CALIBRATION` in the decision table. Preview the judge-call count and cost first with `primr calibrate --calibrate-recent 10 --dry-run` (free).

### Local judge for calibration ($0 judge calls)

If you run a local OpenAI-compatible inference server (Ollama, LM Studio, llama.cpp server, vLLM - anything serving `GET /v1/models` and the chat API), calibration can judge locally instead of via the cloud fast tier:

```
primr calibrate "Company" --judge auto          # local when reachable, else cloud
primr calibrate "Company" --judge local         # explicit; errors if no server
primr calibrate "Company" --judge local --judge-model qwen2.5:14b   # pin a model
primr calibrate "Company" --judge-compare       # judge with BOTH, report agreement
```

Design rules (these hold for any setup, not a particular machine):

- **Cloud is the default judge.** Local is opt-in (`--judge local`) or preference-with-fallback (`--judge auto`). No local server means zero behavior change.
- **Detection enumerates what you actually have** via the generic `/v1/models` endpoint and picks a judge-suitable model by family preference, falling back to whatever chat model is installed. Nothing is hardcoded; a single small model still works. Endpoint resolves via `LOCAL_LLM_BASE_URL` > `OLLAMA_BASE_URL` > `localhost:11434` - remote boxes, WSL, and containers are configuration, not code.
- **Size is not auto-detected; pin a model that fits.** The picker chooses by family preference, not by memory footprint, so on a RAM-limited machine it can select a model too large to load. That call fails and falls back to the cloud judge (visible as a non-zero `cloud_fallbacks` in the sidecar plus a "fell back to cloud" warning), which quietly incurs cloud cost instead of staying $0. To keep local judging truly free, pin a model that fits with `--judge-model` (for example a 14B-class model on a 32 GB machine). Confirm it stuck by checking that `cloud_fallbacks` is 0 in the sidecar.
- **Provenance is never ambiguous.** Every sidecar records `judge: {kind, model}` (plus a `cloud_fallbacks` count when a flaky local server forced per-call fallbacks), so a calibration number always says what judged it.
- **Trust is measured, not assumed.** `--judge-compare` runs cloud and local over the same claims (cloud verdicts are the result of record and are billed exactly once) and reports the agreement rate. If your local model agrees ~90%+, future calibration runs can go local-first and recurring judge cost drops to zero.

These dimensions are aligned to the README goal: producing deep strategic analysis that gets humans and AI up to speed quickly and safely, not just producing long reports.

## 3) Use a clear decision rule

Adopt a candidate profile when all are true:

- Trust gate passes for compared reports
- Mean decision-utility score >= 80% of baseline profile
- Mean cost <= 20% of baseline (or your own budget target)
- Utility-per-dollar improves enough to matter operationally

This lets you make explicit tradeoffs such as "80% of quality for 1/10th of cost" with evidence, not intuition.
