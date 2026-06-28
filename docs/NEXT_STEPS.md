# Next Steps

Last research refresh: 2026-06-27.

This page answers the working question: what should Primr do next, and why?
`ROADMAP.md` remains the ordered backlog. This page is the shorter execution
brief for the next planning cycles.

## Research-backed decision rules

The current docs and roadmap already match the external guidance that matters
for Primr's shape:

- Keep the root README as a project front door: purpose, use fit, quick start,
  and pointers to deeper material. Detailed workflows belong in focused docs,
  matching the Diataxis split and GitHub README guidance.
- Keep the changelog grouped under `Unreleased` and human-readable change
  categories, following Keep a Changelog.
- Keep docs builds strict. Broken navigation or links should fail the build
  before they reach users.
- Treat agent integrations as a control plane for a paid local-first research
  product, not as generic shell execution. MCP and current agent-security
  guidance converge on least privilege, explicit consent for high-impact
  actions, tool safety, scoped resources, and auditability.
- Treat GenAI observability as structured telemetry: model calls, tool calls,
  token/cost metadata, outcome, and trace ids. Full prompt/output capture
  should stay opt-in and privacy-aware.
- Treat validation as layered evidence and reasoning evaluation. Citation
  parsing, source fetches, and sidecar schemas are deterministic input
  assembly. They are not quality validation. Validation has to judge support,
  contradiction, source independence, source authority, uncertainty honesty,
  reasoning strength, and business relevance through pre-registered evals,
  agreement checks, and human spot review where needed.

Reference anchors:

- Diataxis: <https://diataxis.fr/>
- GitHub README guidance: <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes>
- Keep a Changelog: <https://keepachangelog.com/en/1.1.0/>
- MkDocs strict mode: <https://www.mkdocs.org/user-guide/configuration/#strict>
- MCP security best practices: <https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices>
- OWASP Agentic AI Threats and Mitigations: <https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/>
- Microsoft Zero Trust AI threat modeling: <https://learn.microsoft.com/en-us/security/zero-trust/sfi/threat-modeling-ai>
- OpenTelemetry GenAI semantic conventions: <https://opentelemetry.io/docs/specs/semconv/gen-ai/>
- OpenTelemetry GenAI semantic conventions repository:
  <https://github.com/open-telemetry/semantic-conventions-genai>
- NIST AI Risk Management Framework Generative AI Profile:
  <https://www.nist.gov/itl/ai-risk-management-framework/generative-artificial-intelligence>
- NIST Practices for Automated Benchmark Evaluations for AI System Security:
  <https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.800-2.ipd.pdf>
- OWASP Top 10 for LLM Applications 2025:
  <https://genai.owasp.org/owasp-top-10-for-llm-applications-2025/>
- OpenAI evaluation best practices:
  <https://developers.openai.com/api/docs/guides/evaluation-best-practices>
- OpenAI evals guide:
  <https://developers.openai.com/api/docs/guides/evals>
- Anthropic building effective agents:
  <https://www.anthropic.com/engineering/building-effective-agents>
- Anthropic long-running agent harnesses:
  <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- NSA MCP security design considerations:
  <https://media.defense.gov/2026/Jun/02/2003943289/-1/-1/0/CSI_MCP_SECURITY.PDF>

## 2026-06-27 guidance refresh

The refresh confirmed the roadmap direction and tightened the execution bar.
Newer guidance has six practical implications for Primr:

- The eval future is local, dataset-driven, and calibrated. OpenAI now treats
  the Evals platform as legacy, but its current evaluation guidance still
  reinforces the durable pattern Primr should follow: define the objective,
  collect representative data, define metrics, run comparisons, and keep
  continuous evaluation growing from production misses. Primr should keep its
  own eval harness and use provider tools only as optional runners.
- Evaluation has to combine deterministic checks, human or expert spot review,
  and model judging calibrated against trusted labels. Single score evals and
  single model judges are not enough for gates. Pairwise, pass/fail, and
  criterion-specific grading fit Primr better than open-ended "quality"
  judgments.
- Evidence validation has to separate retrieval, support, contradiction,
  source independence, source authority, reasoning quality, uncertainty
  honesty, and decision usefulness. A live source URL or matching phrase proves
  access, not truth.
- Agent surfaces need least privilege, explicit approval for high-impact or
  paid actions, narrowly scoped tools, session-safe identity, and resource
  access that can be audited. The 2026 MCP security guidance raises the bar
  beyond "tools work" to "tool and resource access are bounded, consented, and
  reviewable."
- GenAI observability should use structured spans, metrics, and events for
  model calls, tool calls, token and cost use, route choices, request ids, job
  ids, outcomes, and errors. Full prompt and report body capture should remain
  opt-in because Primr is local-first and research artifacts can be sensitive.
- Long-running agent work needs durable state and external ground truth.
  Compaction or summaries are not enough. Primr should continue to privilege
  manifests, sidecars, artifacts, status resources, and test results over
  self-reported completion.

Exceptional execution standard for every workstream:

- Product behavior: a visible CLI, MCP, A2A, artifact, or report behavior
  changes for the better.
- Measurement: a scorecard, sidecar, trace, usage record, or calibration run
  proves what changed.
- Safety boundary: approval, scope, spend, egress, deletion, retention, or
  privacy behavior is explicit.
- Regression guard: focused deterministic tests ship with the change, and any
  content-quality claim has a documented eval or calibration record.

## Ordered execution plan

### 1. Evidence-grounded validation and label honesty

Why next: the roadmap's measured quality gap is not prose polish, and it is
not a request for simplistic fact matching. It is epistemic grounding: whether
the report's conclusions, labels, caveats, and strategic inferences are
supported by the evidence they cite and honest about what remains uncertain.
Label traceability is the first measurable slice because it is cheap to run on
existing artifacts, but it is only one input to validation. The broader bar is
whether the artifact's reasoning survives evidence review, contradiction
review, and uncertainty review.

Do next:

- Freeze a representative calibration pack of current-format reports, sidecars,
  source appendices, and `--verify` outputs with
  `primr calibrate --pack-manifest`. Include clean, blocked-origin,
  weak-citation, strategy-module, and high-hiring-signal examples.
- Run a multi-report calibration baseline over that pack, but keep the rubric
  broader than string overlap or isolated fact matching.
- Use the new calibration sidecar evidence-review dimensions to score sampled
  report units across support, contradiction, source independence, source
  authority, reasoning strength, uncertainty honesty, and business relevance.
- Compare local and cloud judges on the same sampled claims, then sample human
  review where judges disagree before trusting a local judge path.
- Add a report-only scorecard first. It should publish per-dimension rates,
  judge agreement, contradicted-claim counts, and abstention or uncertainty
  rates without blocking runs. Shipped slices now cover evidence-review rates,
  standard verification contradiction counts, and sidecar-backed judge
  agreement rates, plus a local-only calibration-pack manifest, a curated
  pack-selection template for manual representative tagging, a curated
  pack-selection contract for explicit representative coverage tags, a
  zero-spend selection inspection that shows missing representative tags before
  manifest generation, and a zero-spend baseline readiness artifact that names
  exactly why a pack is not ready. The readiness check now requires every
  selected report to carry
  evidence-review dimensions and cloud-vs-local judge-agreement metadata, so
  partial coverage cannot satisfy the baseline by aggregate counts alone.
  `primr calibrate --inspect-baseline <baseline.json>` exposes those blockers
  as machine-readable JSON for operators, and MCP clients can read the same
  path-allowlisted payload through
  `primr://calibration/baseline/inspection?path=<baseline.json>`.
- Set `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` only from the measured floor of
  that agreement-validated baseline.
- Surface contradicted `--verify` claims in the report trust summary. First
  slice shipped: standard runs now add verification trust rows with WARN and
  contradiction counts when verification finds contradicted claims.
- Decide whether `PRIMR_LABEL_HONESTY` can move toward default-on only after
  the baseline proves acceptable false positive and false negative behavior.

Done when:

- The eval scorecard separates structural extraction, evidence support,
  reasoning quality, contradiction handling, uncertainty honesty, and judge
  agreement. The sidecar and scorecard slices are shipped; the multi-report
  pack-manifest, selection-template, selection-inspection, curated selection,
  and baseline-readiness artifact slices are shipped; the representative
  multi-report baseline itself is still pending.
- The hard gate is either armed from a defensible baseline or deliberately left
  report-only with documented evidence.
- Contradicted claims are visible in the human-facing report trust surface for
  the standard `--verify` path.
- No new deterministic prose-quality or claim-quality gate was added.

### 2. Backend freedom production wiring

Why next: provider abstraction, capability routing, and availability snapshots
exist, but the full-report runtime still has xAI/Gemini-era assumptions. This
is the highest-leverage architectural gap because it unlocks honest
OpenAI-only, Anthropic-only, host-agent, hybrid, and local profiles without
forking the pipeline.

Do next:

- Inventory every production stage by capability requirements: browsing,
  long-context reasoning, structured extraction, writing, vision, tool use,
  citation handling, cache support, streaming, and max output.
- Move `grok_browse_and_summarize`, Gemini quota UI, and provider-specific
  fallback messages into provider-owned seams.
- Add long-context surcharge fields and cache-token fields to estimates for
  models with tiered long-input or cache pricing.
- Wire one cheap utility stage through capability routing behind an explicit
  inference/profile flag while preserving today's fallback chain.
- Record backend id, billing mode, route reason, fallback reason, token mix,
  cache use, cost, latency, and failure class in usage metadata.
- Promote one stage at a time. A provider path is supported only when report
  quality, cost, latency, and failure behavior are measured against the same
  calibration pack.

Done when:

- The stage declares requirements; the router chooses candidates; execution
  consumes the resulting chain.
- Estimates and usage records name the backend and billing mode honestly.
- Provider comparison artifacts exist for every promoted stage.
- No hidden provider dependency remains in the full-report path for the wired
  stage.

### 3. Agent control-plane consumption resources and A2A parity

Why next: MCP authorization, approval tokens, audit logging, and runtime budget
propagation are shipped. The next gap is consumption safety: agents should be
able to read compact, job-scoped artifacts without requiring broad filesystem
access or dumping full reports into context. A2A should enforce the same
least-privilege and approval semantics as MCP.

Do next:

- Add job-scoped resources for `qa_summary`, source appendix, trace summary,
  usage/cost summary, verification summary, calibration summary, and selected
  artifact metadata.
- Define the scope matrix before implementation: monitor can read status and
  compact summaries; artifact read can read compact resources; report read can
  request full report content; research can estimate; execution still requires
  approval for paid work.
- Extend the same scope, approval, budget, and audit decisions to A2A.
- Audit resource reads as well as tool calls, with resource uri, job id,
  subject, scope, and outcome.
- Carry request/job ids into OpenTelemetry-compatible spans and structured logs
  without storing raw report bodies by default.

Done when:

- A read-only agent credential can monitor and consume a completed job without
  starting paid work.
- A research credential still cannot delegate unless it also has the delegate
  scope.
- Tool invocations and artifact-resource reads are auditable without raw
  argument or report-body persistence.
- MCP and A2A enforce the same approval and read-scope semantics for equivalent
  operations.

### 4. Research memory layer 1

Why later: memory compounds Primr's value, but it should not precede claim
calibration and job-scoped artifact resources. Without those, memory risks
repeating stale or weak claims with too much confidence.

Do next after the first three items are stable:

- Implement filesystem-backed company tracking in the per-user data directory.
- Store run pointers, hypothesis history, source attribution, confidence,
  freshness metadata, retention metadata, and exportable OKF bundles.
- Ship deletion, retention, and no-secret write rules with layer 1, not after
  it.
- Require every persisted hypothesis to identify the source artifact and the
  evidence dimension that supports it.

Done when:

- `primr company track`, `company list`, and `company export` work without new
  services.
- Clearing a company removes its local profile and claim history.
- Prior-run material can inform a run only as clearly marked context, never as a
  fresh claim without attribution.
- Stale prior-run material cannot be promoted without fresh source evidence.

### 5. Coverage and maintenance ratchet

Why continuous: the recent refactors made the core easier to test. The right
coverage goal is not a blanket 95 percent global target; it is a rising branch
coverage gate plus per-module coverage on the newly extracted seams.

Do next alongside every feature slice:

- Add focused tests for each touched seam.
- Raise per-module coverage where a refactor makes that honest.
- Add mutation or adversarial fixtures for high-risk slices such as claim
  parsing, scope checks, cost caps, redirects, and citation handling.
- Run the standing bug-hunt and security review lane every six to eight cycles.
- Keep Bandit, pip-audit, Trivy, Ruff, mypy, strict docs, and branch coverage
  green.

Done when:

- New code has local regression coverage.
- No warning-only resource leak, redirect bypass, or cost-control ambiguity is
  accepted as "later" when it is in the touched surface.

## Explicitly not next

- Do not expand the README with roadmap detail. Link to this page and the
  design docs instead.
- Do not add more regex-like prose gates for content quality.
- Do not call validation complete because a cited page contains a matching
  phrase. That is retrieval evidence, not reasoning validation.
- Do not promote a new backend because it works once. Promote only after
  measured quality, cost, and failure behavior are recorded.
- Do not build memory before deletion, retention, source attribution, and
  confidence-label rules are explicit.
- Do not create a generic agent orchestration platform. Primr remains URL in,
  serious artifact out, with a disciplined control plane around that job.

## Validation policy

Use free and local validation first: unit tests, strict docs build, static
analysis, mocked evals, local judge comparison, and existing report sidecars.
Deterministic checks may prepare evidence, prove structure, and guard
irreversible actions. They must not judge free-form content quality. Any paid
eval must have a pre-registered question, a cost cap, explicit approval, and a
rubric that measures substance rather than phrase matches.
