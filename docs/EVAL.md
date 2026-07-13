# Versioned Model Evaluation (Quality vs Cost)

When a new model or profile is released (for example, a new Pro/Flash/Grok variant), evaluate it with a repeatable run ID so decisions are data-driven.

## Current External Practice Checkpoint

Reviewed 2026-06-29:

- OpenAI's current evaluation guidance says to keep evals task-specific,
  representative of real distributions, logged, automated where possible, and
  calibrated against human feedback. OpenAI's legacy Evals platform is also in
  deprecation, with new work steered toward Datasets and trace/eval workflows.
  See [Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices),
  [Working with evals](https://developers.openai.com/api/docs/guides/evals),
  and [Evaluate agent workflows](https://developers.openai.com/api/docs/guides/agent-evals).
- Anthropic's current test-and-evaluate guidance starts with explicit success
  criteria and evaluations before prompt iteration, and its agent-evals writeup
  warns that LLM-as-judge graders need calibration against human experts. See
  [Define success criteria and build evaluations](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests)
  and [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
- Google's current Gemini Enterprise Agent Platform docs describe Gen AI
  evaluation as test-driven evaluation with adaptive rubrics, candidate and
  baseline responses, autorater configuration, and immutable evaluation items.
  The older Vertex AI Gen AI docs now warn that Vertex documentation is no
  longer the current surface. See
  [Gen AI evaluation service overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/evaluation-overview)
  and the [EvaluationItem API](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/projects.locations.evaluationItems).
- NIST's AI RMF Generative AI Profile frames evaluation as part of governing,
  mapping, measuring, and managing GenAI risk, while NIST AI 700-1 demonstrates
  curated benchmark datasets plus statistical metrics for GenAI text
  evaluation. See [NIST AI 600-1](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
  and [NIST AI 700-1](https://www.nist.gov/publications/2024-nist-genai-pilot-study-text-text-evaluation-overview-and-results).

Primr's eval path therefore treats a calibration baseline as an explicit,
representative, agreement-checked artifact. A latest-N pack can estimate cost
and surface missing sidecars, but it is not baseline-ready unless it came from
a curated `primr.calibration_pack_selection.v1` file with non-empty required
representative tags.

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

# Same focused sweep with local semantic judge-panel evidence for same-command stage scorecards
primr --eval --eval-id eval-2026-06-4090-vs-subdollar --eval-local-stage website-summary --eval-local-stage-semantic-judge --eval-local-stage-semantic-judge-model llama3.1:70b,qwen2.5:14b --eval-stage-scorecard --eval-stage-id fast.scrape_summary --eval-judge-provider local --eval-judge-model-list 4090-report-race --eval-judge-base-url http://localhost:11434/v1

# Source-relevance host/cloud comparison from labeled keep-list fixtures
primr --eval --eval-id eval-2026-06-source-relevance --eval-source-relevance-fixture .agent/source-relevance-fixture.json --eval-stage-scorecard --eval-stage-id fast.source_relevance --eval-stage-route-root working

# Page-access classifier false-positive/false-negative eval from sanitized fixtures
primr --eval --eval-id eval-2026-06-page-access --eval-page-access-fixture .agent/page-access-fixture.json
```

Local judge runs now evaluate every staged non-baseline profile against the chosen baseline, not just the first available profile. They write one JSON artifact per model plus `local_judge_summary.json` / `local_judge_summary.md` with candidate-profile coverage, winner consensus, and per-profile breakdowns for side-by-side comparison.

This is useful for evaluating local models against existing cloud-generated reports before routing any production pipeline stages to local inference. It is still a judge-based acceptance layer, not proof that a local model is ready to replace report-writing or deep-research stages directly.

For a 24 GB RTX 4090 or comparable local box, start with `4090-report-race` before the broader `4090-top10` sweep. It keeps the first local run cheap in wall-clock time and answers the product question directly: is the local box already good enough for this stage, or is the ~$1 API route still buying meaningful quality? Add `--eval-local-stage-semantic-judge` when a local judge backend is available. The judge-model option accepts one model or a comma-separated local judge panel; panel runs record score-spread agreement metadata. The resulting semantic scorecard evidence is still review-only, and promotion requires a broader calibrated sample with provenance and human-reviewed acceptance criteria.

For the `fast.source_relevance` host-agent pilot, use `--eval-source-relevance-fixture` to convert labeled keep-list fixtures into body-free precision, recall, F1, and exact-match artifacts. The fixture should use source numbers only, not source URLs or text bodies:

```json
{
  "schema_version": 1,
  "cases": [
    {
      "case_id": "case-001",
      "company": "ExampleCo",
      "source_count": 4,
      "expected_keep": [1, 3],
      "candidates": [
        {"backend_id": "codex-host", "kept": [1, 3]},
        {"backend_id": "cloud-baseline", "kept": [1, 2, 3]}
      ]
    }
  ]
}
```

The generated `source_relevance_stage_quality_evidence.json` feeds the same review-only stage scorecard as other route evidence. It does not promote host execution by itself; promotion still requires representative samples, route observations, and human-reviewed acceptance criteria.

For protected-site access classification, use `--eval-page-access-fixture` to
score labeled sanitized HTML cases or trace-derived `access_assessment`
predictions. The generated `page_access_stage_eval.json`,
`page_access_stage_eval.md`, and `page_access_stage_quality_evidence.json`
include confusion-matrix counts, false-positive and false-negative rates,
case ids, tags, and classifier states. They do not copy raw HTML, URLs, page
bodies, prompts, or provider responses.

```json
{
  "schema_version": 1,
  "cases": [
    {
      "case_id": "sanitized-real-about",
      "expected_real_content": true,
      "html": "<html>sanitized real page fixture</html>",
      "url": "https://redacted.invalid/about",
      "http_status": 200,
      "expected_markers": ["exampleco"],
      "tags": ["protected-site", "real"]
    },
    {
      "case_id": "trace-soft-block",
      "expected_real_content": false,
      "access_assessment": {
        "state": "soft_block",
        "confidence": 0.96,
        "reason": "Challenge/interstitial shell detected"
      },
      "tags": ["protected-site", "trace"]
    }
  ]
}
```

Use only sanitized, consented fixtures in this file. Keep real page bodies and
raw URLs out of committed corpora; store working corpora under the gitignored
`.agent/` directory until they are scrubbed into canonical test fixtures.

The canonical protected-site corpus is
`tests/fixtures/page_access/protected_site_trace_corpus.json`. It contains
sanitized trace `access_assessment` records only, with raw URLs, raw HTML, page
bodies, company names, and provider payloads removed. Run it with:

```bash
primr --eval --eval-id protected-site-trace-corpus-v1 --eval-page-access-fixture tests/fixtures/page_access/protected_site_trace_corpus.json
```

The corpus is review evidence, not a promotion gate. It deliberately includes
known historical false-positive and false-negative cases so the eval artifacts
continue to measure both failure directions as classifier behavior changes.

## 2) Track the same metrics for every profile

- Trust gate (must-pass): citation coverage + section completeness + confidence-label quality
- Decision utility: actionable recommendations, risks/tradeoffs, key validation questions, and depth of strategic interpretation
- Reuse quality (human + AI): structured headings, tables, machine-friendly signal density, and readable appendix-style sourcing
- Efficiency: utility-per-dollar and total estimated cost
- Runtime: end-to-end duration per company
- Artifact drift: per-report `scaffolding_leaks` count and a per-profile `total_scaffolding_leaks` aggregate (leaked internal scaffolding that should never reach a deliverable). Surfaced in the scorecard's `## Artifact Drift` section (clean/DRIFT per profile) and a `scaffolding_leaks` CSV column. Target: 0 - non-zero is a regression, tracked every eval run rather than via ad-hoc offline scans.
- Label calibration: traceability of `(Confirmed)`/`(Reported)` claims against the *fetched text* of their cited sources, measured by `primr calibrate` (a separate, bounded paid step - pennies per report) and persisted as `<report>.calibration.json` sidecars next to the staged reports. The offline eval reads the sidecars into per-report traceability, a pooled `## Label Calibration` scorecard section, and `confirmed_traceability` / `reported_traceability` CSV columns. Set `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` (a fraction, e.g. `0.8`) to arm the hard gate: profiles below it get `FAIL_CALIBRATION` in the decision table. Preview the judge-call count and cost first with `primr calibrate --calibrate-recent 10 --dry-run` (free).
- Inference label source-copy: `(Estimated)` and `(Hypothesis)` claims remain
  exempt from traceability, but cited inference-class claims are checked for
  deterministic source-copy leakage against fetched source text. Sidecars carry
  per-label `source_copied` counts, offline eval surfaces a report-only
  `## Inference Label Checks` section, and CSV exports include
  `inference_source_copied`. Do not gate on this signal until the representative
  baseline defines acceptable behavior.
- Evidence review: calibration sidecars also carry judge-reported, report-only
  source-review signals for support, contradiction, source independence, source
  authority, reasoning strength, uncertainty honesty, and business relevance.
  Offline eval pools those into the scorecard's `## Evidence Review` section
  and CSV columns such as `evidence_support_rate`,
  `evidence_contradiction_rate`, and `evidence_strong_reasoning_rate`. Treat
  these as calibration signals until a multi-report baseline and
  judge-agreement record justify gates.
- Judge agreement: `primr calibrate --judge-compare` stamps per-report
  cloud-vs-local agreement metadata into each calibration sidecar. Offline eval
  pools those counts into `## Judge Agreement` and CSV columns
  `judge_agreement_compared` / `judge_agreement_rate`. Agreement remains a
  baseline-readiness signal, not a quality gate. The raw report-bound sidecar
  also records each disagreement as a body-free pointer containing only the
  sampled claim index and the cloud and local verdicts. `claim_index` is the
  zero-based index into that sidecar's top-level `claims` array, including
  preceding non-decidable claims. Operators can resolve those pointers against
  the claims already bound into that sidecar for human adjudication. Compact MCP
  and A2A calibration summaries deliberately omit the pointer list and all raw
  claim or source content.
- Calibration pack manifest: add `--pack-manifest path/to/pack.json` to
  `primr calibrate` or its `--dry-run` preview to freeze the selected reports,
  sidecar state, sampled-claim counts, judge-call estimate, per-label totals,
  evidence-review summary, inference source-copy counts, judge-agreement
  metadata, and report/sidecar content fingerprints before running a
  multi-report baseline.
- Report binding: every newly written calibration sidecar records the exact
  report byte size and SHA-256 digest it evaluated. Pack aggregation and the
  compact MCP/A2A calibration summary reject legacy sidecars and any binding
  that no longer matches the current report. A nearby filename is not treated
  as evidence ownership.
- Curated pack selection: add `--pack-selection path/to/selection.json` when
  the baseline needs explicit representative coverage instead of "latest N"
  report selection. The selection file uses
  `primr.calibration_pack_selection.v1`, lists exact report paths, and records
  operator-supplied coverage tags. Primr treats those tags as audit metadata,
  not inferred content truth. Start with
  `primr calibrate --calibrate-recent 10 --pack-selection-template path/to/selection.json`
  to write a zero-spend template, then fill each report's tags manually. Run
  `primr calibrate --inspect-selection path/to/selection.json` to verify the
  required, present, and missing representative tags before writing a pack
  manifest.
- Calibration baseline artifact: add `--baseline-from path/to/pack.json` to
  build a zero-spend readiness artifact from a frozen pack. It writes
  `primr.calibration_baseline.v1` JSON, and optional Markdown via
  `--baseline-md path/to/baseline.md`, with explicit not-ready reasons such as
  `insufficient_reports`, `missing_evidence_reviews`, or
  `missing_judge_agreement`. A ready baseline also requires an explicit curated
  selection manifest with non-empty representative tag requirements; otherwise
  the artifact reports `missing_representative_selection`, even if all sidecar
  and agreement counts are present. Evidence review and judge agreement are
  per-report coverage requirements, not merely aggregate nonzero counts; a pack
  with one reviewed report and four unreviewed reports remains not ready. When
  the pack manifest declares required representative tags, the artifact reports
  `missing_representative_coverage` until every required tag appears in the
  selected pack. Inspection compares current report and sidecar fingerprints
  against the frozen pack and reports missing or mutated artifacts without
  returning report bodies. When the pack is ready, the artifact also publishes a
  report-only `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` recommendation from the
  per-report Confirmed traceability floor; operators still have to review the
  representative pack, disagreement cases, and false-positive risk before
  arming a hard gate. The floor is complete only when every selected report has
  decidable `(Confirmed)` claims. If some reports lack a decidable Confirmed
  floor, the artifact stays report-only with
  `incomplete_confirmed_traceability_floor`, the affected counts, and an
  operator-review item documenting why the hard gate remains unset. The artifact
  includes structured `next_actions` with missing counts, remediation,
  suggested commands, and the policy to keep the hard calibration gate unset
  until the pack is ready. For ready-but-report-only packs, `next_actions` also
  names the hard-gate action, gate-recommendation reason, selected-report counts,
  and absent, incomplete, or zero Confirmed-floor state that keeps the
  environment variable unset. Its per-report summaries include evidence-review
  counts, inference source-copy counts, and judge-agreement compared-claim counts
  so operators can identify the exact selected artifacts still blocking
  readiness. The artifact and inspection JSON also include a body-free
  `operator_decision_template` naming the allowed decisions, required review
  items, selected-report counts, and operator-supplied fields needed to document
  either a report-only decision or a manual hard-gate assignment. It is a
  template, not a recorded decision, and it never arms the gate automatically.
  When an operator has reviewed the template, run
  `primr calibrate --baseline-decision-from path/to/baseline.json --baseline-decision-out path/to/decision.json --baseline-decision keep_report_only --baseline-decision-reviewer "<name-or-role>" --baseline-decision-rationale "<why>"`
  to write a body-free `primr.calibration_gate_decision_record.v1` artifact.
  Use `--baseline-decision arm_gate` only when the inspected template lists that
  decision as allowed; Primr still only writes the record and never sets the
  environment variable itself.
  Later, run
  `primr calibrate --inspect-baseline-decision path/to/decision.json` to
  re-check that the saved record still matches the baseline artifact fingerprint
  and that the current baseline inspection still allows the recorded decision.
  The readback omits report bodies, raw claims, and operator rationale text.
  Run `primr calibrate --inspect-baseline path/to/baseline.json` to print the
  same blockers as machine-readable JSON for agents or automation. MCP clients
  can read `primr://calibration/baseline/inspection?path=<baseline.json>` when
  the baseline path is inside the MCP allowed roots.
  This summarizes baseline readiness; it does not arm a quality gate.

### Local judge for calibration ($0 judge calls)

If you run a local OpenAI-compatible inference server (Ollama, LM Studio, llama.cpp server, vLLM - anything serving `GET /v1/models` and the chat API), calibration can judge locally instead of via the cloud fast tier:

```
primr calibrate "Company" --judge auto          # local when reachable, else cloud
primr calibrate "Company" --judge local         # explicit; errors if no server
primr calibrate "Company" --judge local --judge-model qwen2.5:14b   # pin a model
primr calibrate "Company" --judge-compare       # judge with BOTH, report agreement
primr calibrate --calibrate-recent 10 --pack-selection-template .agent/calibration-selection.json
primr calibrate --inspect-selection .agent/calibration-selection.json
primr calibrate --pack-selection .agent/calibration-selection.json --dry-run --pack-manifest .agent/calibration-pack.json
primr calibrate --pack-selection .agent/calibration-selection.json --judge-compare --pack-manifest .agent/calibration-pack.json
primr calibrate --baseline-from .agent/calibration-pack.json --baseline-md .agent/calibration-baseline.md
primr calibrate --inspect-baseline .agent/calibration-pack.baseline.json
```

Minimal curated selection file:

```json
{
  "selection_format": "primr.calibration_pack_selection.v1",
  "required_tags": [
    "clean",
    "blocked_origin",
    "weak_citation",
    "strategy_module",
    "high_hiring_signal"
  ],
  "reports": [
    {
      "path": "output/ExampleCo_Strategic_Overview_06-28-2026.md",
      "tags": ["clean", "high_hiring_signal"]
    }
  ]
}
```

Design rules (these hold for any setup, not a particular machine):

- **Cloud is the default judge.** Local is opt-in (`--judge local`) or
  preference-with-fallback (`--judge auto`). `--judge auto` can choose the
  cloud judge at selection time when no local server is reachable; once a local
  model is selected, per-call local failures fail closed instead of silently
  spending through the cloud judge.
- **Detection enumerates what you actually have** via the generic `/v1/models` endpoint and picks a judge-suitable model by family preference, falling back to whatever chat model is installed. Nothing is hardcoded; a single small model still works. Endpoint resolves via `LOCAL_LLM_BASE_URL` > `OLLAMA_BASE_URL` > `localhost:11434` - remote boxes, WSL, and containers are configuration, not code.
- **Size is not auto-detected; pin a model that fits.** The picker chooses by
  family preference, not by memory footprint, so on a RAM-limited machine it can
  select a model too large to load. That call now records the affected report as
  a calibration failure instead of falling back to paid cloud judging. To keep
  local judging reliable, pin a model that fits with `--judge-model` (for
  example a 14B-class model on a 32 GB machine).
- **Provenance is never ambiguous.** Every sidecar records
  `judge: {kind, model}` so a calibration number always says what judged it.
  Local call failures produce no sidecar for that report and are reported as
  calibration failures.
- **Trust is measured, not assumed.** `--judge-compare` runs cloud and local over
  the same claims (cloud verdicts are the result of record and are billed
  exactly once) and reports the agreement rate. It also preserves body-free
  disagreement pointers in each raw sidecar so operator review can identify
  false positives and false negatives before trusting the local path. If your
  local model agrees ~90%+, future calibration runs can go local-first and
  recurring judge cost drops to zero.
- **Dry-run spend follows the requested judge policy.** Explicit local-only
  previews report `$0.00` estimated cloud spend and write
  `estimated_cloud_cost_usd: 0.0` in pack manifests. `--judge auto` always
  quotes the bounded cloud fallback ceiling, even when the preview resolves to
  a local model, because availability can change before execution. Cloud and
  comparison previews likewise price their bounded cloud calls before
  approval. Nonzero sub-cent estimates retain four decimal places instead of
  rendering as `$0.00`.
- The agreement rate is persisted in sidecars, so later `primr eval` scorecards
  can show whether a profile's calibration data came from an agreement-checked
  judge setup.

These dimensions are aligned to the README goal: producing deep strategic analysis that gets humans and AI up to speed quickly and safely, not just producing long reports.

## 3) Use a clear decision rule

Adopt a candidate profile when all are true:

- Trust gate passes for compared reports
- Mean decision-utility score >= 80% of baseline profile
- Mean cost <= 20% of baseline (or your own budget target)
- Utility-per-dollar improves enough to matter operationally

This lets you make explicit tradeoffs such as "80% of quality for 1/10th of cost" with evidence, not intuition.
