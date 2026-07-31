# Next Steps

Last research refresh: 2026-07-19.

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
- For MCP resources, keep context surfaces compact and application-driven.
  Parameterized job reads should move toward resource templates as client
  support matures; the current implementation extends the repo's existing
  URI-pattern resource listing for compatibility while preserving the same
  body-free and ownership-gated contract for artifacts, QA, usage, source
  appendix, and scrape trace metadata. Eval-id reads should avoid arbitrary
  file paths and expose only compact application summaries.
- For HTTP MCP auth, keep Primr as the protected resource server and enforce
  internal scopes per operation. The latest MCP revision adds incremental
  scope-consent semantics through `WWW-Authenticate`, which fits the existing
  small `read`/`research`/`delegate`/`admin` vocabulary and should shape the
  next HTTP parity slice.
- Track the MCP `2026-07-28` release candidate as a post-final compatibility
  review item, not an immediate implementation target before July 28, 2026.
  The stateless HTTP core, server discovery, `Mcp-Method` and `Mcp-Name`
  routing headers, resource and list cache hints, Tasks extension, Apps
  extension, JSON Schema 2020-12 tool schemas, W3C trace context propagation,
  and authorization hardening map directly onto Primr's HTTP MCP transport,
  long-running job handles, metadata-first resources, audit spans, and
  protected-resource model.
- For A2A, keep the Agent Card as a discovery contract and enforce actual
  authorization at the server-side skill boundary. The protocol advertises
  security schemes, but Primr-owned scope decisions must still happen before
  handler dispatch so read-only agents cannot start paid work.
- Treat GenAI observability as structured telemetry: model calls, tool calls,
  token/cost metadata, outcome, and trace ids. Full prompt/output capture
  should stay opt-in and privacy-aware.
- Treat provider background execution as a durable lifecycle, not a long HTTP
  request. Persist the provider interaction id immediately, reconnect by id,
  and acknowledge completion only after Primr's owning output boundary proves
  the required artifacts are durable. Apply that contract consistently to
  normal completion and recovery paths.
- Keep package publication on PyPI Trusted Publishing. Build once from an
  immutable tag on green `main`, publish that exact artifact set through OIDC,
  and verify registry filenames and hashes before creating the GitHub release.
- Treat validation as layered evidence and reasoning evaluation. Citation
  parsing, source fetches, and sidecar schemas are deterministic input
  assembly. They are not quality validation. Validation has to judge support,
  contradiction, source independence, source authority, uncertainty honesty,
  reasoning strength, and business relevance through pre-registered evals,
  agreement checks, and human spot review where needed.
- Keep AI Strategy business-first. Begin with company economics, strategic
  tensions, industry change, value pools, and the art of the possible. Rank
  revenue, margin, service, product, productivity, and risk outcomes before
  selecting models, vendors, or infrastructure. Stanford's 2026 AI Index shows
  rapid adoption and investment alongside mixed macro-level productivity
  evidence, which supports explicit value hypotheses rather than technology-led
  certainty.
- Make each AI initiative carry business and technical unit economics. Connect
  total cost and marginal cost to a measurable unit such as revenue, cost to
  serve, transaction, case resolved, cycle time, or risk reduction. FinOps
  guidance explicitly uses those links to inform workload placement, packaging,
  pricing, and roadmap tradeoffs.
- Treat the observed technology estate as evidence, not destiny. AI Strategy
  should account for every credible recon signal across productivity, identity,
  data, cloud, AI providers, and existing data-center capability, then assign a
  disposition such as reuse, integrate, contain, migrate, retire, or evaluate.
- Default to workload-specific placement analysis across public cloud, private
  cloud, on-premises accelerated infrastructure, edge, and hybrid patterns.
  Recommend owned accelerated capacity only when sustained utilization, data
  gravity, latency, sovereignty, resilience, or unit economics justify the
  operational burden. Current vendor architecture guidance supports both
  consumption-based AI and purpose-built AI factories, but neither is a
  universal default.
- Keep governance tied to business context throughout the lifecycle. NIST AI
  RMF calls for mission goals and business value to be defined before system
  decisions, with ongoing governance, measurement, and management rather than a
  one-time risk checklist.

Reference anchors:

- Diataxis: <https://diataxis.fr/>
- GitHub README guidance: <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes>
- Keep a Changelog: <https://keepachangelog.com/en/1.1.0/>
- MkDocs strict mode: <https://www.mkdocs.org/user-guide/configuration/#strict>
- MCP security best practices: <https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices>
- MCP specification, latest 2025-11-25 overview:
  <https://modelcontextprotocol.io/specification/2025-11-25>
- MCP resources, latest 2025-11-25 draft:
  <https://modelcontextprotocol.io/specification/draft/server/resources>
- MCP authorization, latest 2025-11-25:
  <https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization>
- MCP 2025-11-25 changelog:
  <https://modelcontextprotocol.io/specification/2025-11-25/changelog>
- Gemini Interactions API overview, accessed 2026-07-10:
  <https://ai.google.dev/gemini-api/docs/interactions-overview>
- Gemini background execution, accessed 2026-07-10:
  <https://ai.google.dev/gemini-api/docs/background-execution>
- PyPA Trusted Publishing release workflow guide, updated 2026-06-22:
  <https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/>
- MCP 2026-07-28 release candidate blog, published 2026-05-21, final spec
  scheduled for 2026-07-28:
  <https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/>
- A2A protocol specification, latest snapshot accessed 2026-06-29:
  <https://a2a-protocol.org/latest/specification/>
- OWASP Agentic AI Threats and Mitigations: <https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/>
- Microsoft Zero Trust AI threat modeling: <https://learn.microsoft.com/en-us/security/zero-trust/sfi/threat-modeling-ai>
- OpenTelemetry GenAI semantic conventions: <https://opentelemetry.io/docs/specs/semconv/gen-ai/>
- OpenTelemetry GenAI semantic conventions repository:
  <https://github.com/open-telemetry/semantic-conventions-genai>
- NIST AI Risk Management Framework Generative AI Profile:
  <https://www.nist.gov/itl/ai-risk-management-framework/generative-artificial-intelligence>
- NIST Practices for Automated Benchmark Evaluations for AI System Security:
  <https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.800-2.ipd.pdf>
- Stanford AI Index 2026: <https://hai.stanford.edu/ai-index>
- NIST AI RMF Core: <https://airc.nist.gov/airmf-resources/airmf/5-sec-core/>
- FinOps Unit Economics:
  <https://www.finops.org/framework/capabilities/unit-economics/>
- Azure Well-Architected AI design principles:
  <https://learn.microsoft.com/en-us/azure/well-architected/ai/design-principles>
- NVIDIA AI Factories: <https://www.nvidia.com/en-us/solutions/ai-factories/>
- OWASP Top 10 for LLM Applications 2025:
  <https://genai.owasp.org/owasp-top-10-for-llm-applications-2025/>
- OpenAI evaluation best practices:
  <https://developers.openai.com/api/docs/guides/evaluation-best-practices>
- OpenAI evals guide:
  <https://developers.openai.com/api/docs/guides/evals>
- OpenAI API pricing:
  <https://openai.com/api/pricing/>
- OpenAI prompt caching:
  <https://developers.openai.com/api/docs/guides/prompt-caching>
- Anthropic building effective agents:
  <https://www.anthropic.com/engineering/building-effective-agents>
- Anthropic long-running agent harnesses:
  <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- Anthropic prompt caching:
  <https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching>
- Gemini API pricing:
  <https://ai.google.dev/gemini-api/docs/pricing>
- Gemini context caching:
  <https://ai.google.dev/gemini-api/docs/caching>
- xAI API pricing:
  <https://docs.x.ai/developers/pricing>
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
  reviewable." Primr's shipped control-plane resources now cover artifact
  inventory, QA summary, usage/cost metadata, source appendix metadata, and
  scrape trace metadata, and claim verification metadata without report body
  content, raw trace logs, raw claims, source URLs, search queries, or
  explanations. Stage eval scorecard readback also stays compact and eval-id
  scoped rather than accepting raw filesystem paths.
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
- Runtime economics: profile production-shaped work before optimizing. Improve
  phase topology and Python algorithms first. A different runtime must beat the
  optimized reference on an explicit end-to-end or operational SLO and carry
  its correctness, packaging, observability, fallback, and rollback costs.

## Ordered execution plan

### 1. Evidence-grounded validation and label honesty

Status: current measured-baseline milestone complete on 2026-07-13. A curated
five-report baseline is ready with 33 of 37 comparable cloud and local verdicts
in agreement. Operator review deliberately kept the hard gate report-only
because two reports lack a decidable Confirmed floor. The current body-free
decision record and reviewable disagreement pointers preserve the evidence for
that choice. Recalibration on a fully decidable production corpus remains a
continuous follow-up, not a blocker to item 2.

Why next: the roadmap's measured quality gap is not prose polish, and it is
not a request for simplistic fact matching. It is epistemic grounding: whether
the report's conclusions, labels, caveats, and strategic inferences are
supported by the evidence they cite and honest about what remains uncertain.
Label traceability is the first measurable slice because it is cheap to run on
existing artifacts, but it is only one input to validation. The broader bar is
whether the artifact's reasoning survives evidence review, contradiction
review, and uncertainty review.

Completed in this milestone:

- Froze a curated five-report pack with explicit representative tags, report
  and sidecar fingerprints, source appendices, and current-format artifacts.
- Ran a measured multi-report baseline without reducing validation to string
  overlap or isolated fact matching.
- Captured 50 source reviews. Support produced 18 affirmative results; the
  secondary contradiction, independence, authority, reasoning, uncertainty,
  and relevance dimensions remained unknown and therefore did not justify a
  gate.
- Compared local and cloud judges on the same sampled claims, persisted exact
  body-free disagreement pointers, and manually adjudicated all four
  disagreements before deciding whether to trust the local path.
- The report-only scorecard publishes per-dimension rates, judge agreement,
  contradicted-claim counts, and abstention or uncertainty rates without
  blocking runs. Shipped slices cover evidence-review rates,
  standard verification contradiction counts, and sidecar-backed judge
  agreement rates, plus a local-only calibration-pack manifest, a curated
  pack-selection template for manual representative tagging, a curated
  pack-selection contract for explicit representative coverage tags, a
  zero-spend selection inspection that shows missing representative tags before
  manifest generation, report/sidecar content fingerprints in pack manifests,
  and a zero-spend baseline readiness artifact that names exactly why a pack is
  not ready. The readiness check now requires every
  baseline candidate to come from an explicit curated pack-selection manifest
  with non-empty representative tag requirements; latest-N aggregate manifests
  report `missing_representative_selection` and remain report-only. It also
  requires every selected report to carry
  evidence-review dimensions and cloud-vs-local judge-agreement metadata, so
  partial coverage cannot satisfy the baseline by aggregate counts alone.
  Calibration sidecars and eval/baseline summaries now also flag source-copied
  `(Estimated)` / `(Hypothesis)` claims as a report-only signal.
  `primr calibrate --inspect-baseline <baseline.json>` exposes those blockers
  as machine-readable JSON for operators and checks current report/sidecar
  fingerprints against the frozen pack without returning report bodies. MCP
  clients can read the same path-allowlisted payload through
  `primr://calibration/baseline/inspection?path=<baseline.json>`. Ready
  baseline artifacts now publish a report-only gate recommendation from the
  per-report Confirmed traceability floor, including the exact
  `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` assignment to review before arming a
  hard gate. Baseline artifacts and inspections now also include a body-free
  operator-review block that keeps automatic gate arming disabled, names the
  required checks for representative coverage, evidence dimensions, judge
  disagreement, false-positive and false-negative risk, and threshold
  selection, and distinguishes gate candidates from report-only
  recommendations without exposing report bodies or raw claims. Ready curated
  multi-report baselines now also publish a `measurement` block with
  `measured_operator_curated_multi_report_baseline` status when representative
  coverage, evidence review, and judge agreement are complete. Baseline
  `next_actions` now mirrors the body-free hard-gate state exposed by inspection
  JSON, including the absent, incomplete, or zero Confirmed-floor reason and the
  selected-report counts that keep the environment variable unset. Baseline
  artifacts and inspections now also carry a body-free
  `operator_decision_template` with allowed decisions, required review items,
  selected-report counts, and operator-supplied fields for documenting a later
  report-only or manual gate decision without recording one automatically.
  `primr calibrate --baseline-decision-from ... --baseline-decision-out ...`
  now writes a body-free operator decision record only when the inspected
  template allows the requested decision, and never sets the hard-gate
  environment variable itself. `primr calibrate --inspect-baseline-decision ...`
  revalidates a saved decision against the current baseline fingerprint and
  allowed-decision evidence before downstream loops trust it. Raw
  report-bound sidecars now preserve each cloud-vs-local disagreement as a
  body-free claim-index and verdict pointer for operator adjudication. Compact
  MCP and A2A summaries continue to omit the pointer list and all raw claim or
  source content.
- Kept `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` unset because two of five reports
  lack a decidable Confirmed floor, even though the three-report measured floor
  is 30 percent.
- Surfaced contradicted `--verify` claims in the report trust summary. Standard
  runs now add verification trust rows with WARN and contradiction counts when
  verification finds contradicted claims.
- Kept `PRIMR_LABEL_HONESTY` unchanged because adjudication found judge errors
  in both directions and does not justify a default-on move.

Continuous production-corpus follow-up:

- Freeze at least five current provider-backed production reports in which
  every report contributes decidable Confirmed claims and secondary evidence
  dimensions are complete rather than unknown.
- Repeat cloud-vs-local comparison and human disagreement adjudication on that
  corpus. Reconsider the hard threshold and label-honesty default only when the
  resulting false-positive and false-negative evidence supports the change.

Done when:

- The eval scorecard separates structural extraction, evidence support,
  reasoning quality, contradiction handling, uncertainty honesty, and judge
  agreement. The sidecar and scorecard slices are shipped, including the
  report-only inference source-copy check; the multi-report pack-manifest,
  selection-template, selection-inspection, curated selection, and
  baseline-readiness artifact slices are shipped; baseline artifacts now carry
  explicit body-free operator-review requirements; readiness now refuses
  non-curated latest-N packs; and ready curated multi-report baselines now carry
  explicit measurement status in JSON and Markdown; ready-but-report-only
  baselines now publish explicit hard-gate next actions; baseline artifacts now
  include a decision template, and the CLI can write a separate operator-created
  decision record for gate evidence. The current five-report measured baseline
  completed operator review and records `keep_report_only`; future production
  corpus recalibration remains continuous evaluation work.
- The hard gate is either armed from a defensible baseline or deliberately left
  report-only with documented evidence.
- Contradicted claims are visible in the human-facing report trust surface for
  the standard `--verify` path.
- No new deterministic prose-quality or claim-quality gate was added.

### 2. Backend freedom production wiring

Why next: provider abstraction, capability routing, and availability snapshots
exist, but the full-report runtime still has xAI/Gemini-era assumptions. This
is the highest-leverage architectural gap because it unlocks honest
OpenAI-only, Anthropic-only, billing-proven host-agent, hybrid, and local
profiles without forking the pipeline.

Do next:

- Inventory every production stage by capability requirements: browsing,
  long-context reasoning, structured extraction, writing, vision, tool use,
  citation handling, cache support, streaming, and max output. First slice
  shipped: `src/primr/core/stage_inventory.py` now records router-ready
  requirements, accepted backend families, current backend ownership,
  promotion gates, budget checkpoints, and artifacts for the fast-mode and
  premium deep-research stages. The inventory is descriptive only; production
  execution still uses the legacy routing seams.
- Move provider-specific behavior into provider-owned seams. Shipped:
  `XAIProvider` owns the xAI Responses API browse/search surrogate behind the
  legacy `grok_browse_and_summarize()` wrapper, and `GeminiProvider` owns
  terminal quota guidance rendered by the legacy Gemini `llm()` path.
- Add long-context surcharge fields and cache-token fields to estimates for
  models with tiered long-input or cache pricing. Shipped: estimates now carry
  live input, cached input, cached-input cost, and long-context surcharge
  fields, with observed historical cache hits included when available.
- Wire cheap utility stages through capability routing behind an explicit
  inference/profile flag while preserving today's fallback chain. Shipped:
  `fast.scrape_summary`, `fast.source_relevance`, and `fast.hiring_signals`
  now consume `route_stage()` behind `--inference cloud|hybrid`, log safe route
  metadata, append capped body-free `stage_routes` records to
  `_run_state.json`, and execute through existing provider seams with today's
  role defaults preserved as fallback. The public CLI remains
  `--inference cloud|hybrid`. `fast.source_relevance` also has an
  Codex CLI adapter. Its first promotion-safety slice is shipped as an
  unpromoted, single-company experimental route: it additionally requires
  `--acknowledge-host-agent-may-bill`, records the route as potentially metered
  with pending-eval status, excludes unknown host charges from Primr estimates
  and budgets, and rejects batch fan-out. This opt-in is not promotion; cloud
  remains the validated baseline until a representative labeled host-vs-cloud
  comparison and human review clear the stage gate. Runtime
  route resolution now consumes sanitized env-only cloud provider availability
  snapshots by default, can accept injected quota snapshots, and records
  body-free availability metadata without adding live quota collection or local
  probes to normal runs. Route records now also include measured
  token/cache/cost deltas when provider usage counters expose them. Body-free
  stage route comparison helpers now aggregate those records into JSON/Markdown
  artifacts by stage/backend/profile. Stage eval scorecards now join those
  route rows with explicit quality evidence and classify candidates for human
  review without auto-promotion. The scorecard artifact flow is available through
  `primr --eval --eval-stage-scorecard --eval-stage-quality <quality.json>`,
  and MCP clients can inspect those artifacts through
  `primr://eval/stage_scorecard/{eval_id}` without receiving prompt, report,
  quality-source, or raw run-state content. The website-summary local-stage
  eval now emits `website_summary_stage_quality_evidence.json` as a structured
  scorecard input, and same-command scorecard generation can consume it when a
  manual `--eval-stage-quality` path is not supplied. Source-relevance labeled
  fixtures now emit body-free precision, recall, F1, exact-match, and quality
  evidence through `--eval-source-relevance-fixture`, giving the Codex
  source-relevance pilot a review-only comparison path before host execution is
  broadened. The two other routed utility stages also fail closed when the
  internal agent profile is exercised by tests or evals and no host adapter
  qualifies: website summaries write
  deterministic source excerpts, hiring signals use deterministic triage plus
  posting metadata, and both record body-free `agent_profile_unavailable` route
  fallbacks instead of invoking cloud LLMs.
- Promote one host/local candidate only after stage-scoped evals prove quality,
  cost, latency, failure behavior, and billing provenance. If billing cannot be
  proven, promotion requires an explicit operator acknowledgment that metered
  API usage may apply.
- Promote one stage at a time. A provider path is supported only when report
  quality, cost, latency, and failure behavior are measured against the same
  calibration pack.

Done when:

- The stage declares requirements; the router chooses candidates; execution
  consumes the resulting chain. The declaration slice and three utility-stage
  runtime slices are shipped; broader production wiring is still pending.
- Estimates and usage records name the backend and declared route category. The
  route ledger records backend/profile/billing metadata for
  `fast.scrape_summary`, `fast.source_relevance`, and `fast.hiring_signals`,
  and appends measured stage-scoped token/cache/cost deltas when counters are
  available. Codex route metadata is not proof of the authenticated session's
  billing mode.
- Provider comparison artifacts exist for every promoted stage.
  The route-metadata comparison artifact exists; quality comparison artifacts
  now have a CLI-accessible scorecard layer, and website-summary local-stage
  evals can produce either structural completeness evidence or local semantic
  judge-panel evidence for same-command scorecards. Source-relevance fixture
  evals can also produce F1 quality evidence for the experimental host-agent
  pilot. These remain report-only scorecard evidence, not promotion gates;
  calibrated samples and human-reviewed acceptance criteria are still required
  before any promotion. The standing source-relevance corpus
  (`source_relevance_standing_v1`) is now packaged with representative tags and
  dual cloud/host candidates, and
  `--eval-source-relevance-standing-corpus` produces review-only scorecard
  evidence offline. The next concrete slice is to run a controlled live
  host-vs-cloud comparison against that standing corpus after explicit approval
  of potentially metered host use and direct cloud spend, then record a
  human-reviewed promotion decision without auto-arming host routing.
- No hidden provider dependency remains in the full-report path for the wired
  stage.

### 3. Agent control-plane consumption resources and A2A parity

Why next: MCP authorization, approval tokens, audit logging, and runtime budget
propagation are shipped. A2A now shares MCP's read/research scope split,
compact resource reads, approval-token enforcement for research execution, and
runtime budget propagation for accepted research jobs. A2A report-read parity
is also shipped: agents request full report content only through an explicit
report-scoped skill, without requiring broad filesystem access or dumping
reports into context by default.

Do next:

- Continue A2A parity now that the seven compact MCP job-scoped resource
  slices shipped:
  `primr://output/artifacts/by_job/{job_id}` returns ownership-gated file names,
  paths, physical classifications, semantic roles, sizes, hashes, timestamps,
  and missing-file state for one job, and
  `primr://output/qa_summary/by_job/{job_id}` returns compact QA score/status
  and count metadata, and
  `primr://output/usage_summary/by_job/{job_id}` returns compact cost, timing,
  approval, execution, and artifact-count metadata, and
  `primr://output/source_summary/by_job/{job_id}` returns compact citation and
  source appendix metadata, and
  `primr://output/trace_summary/by_job/{job_id}` returns compact scrape trace
  health metadata, and
  `primr://output/verification_summary/by_job/{job_id}` returns compact claim
  verification trust score, claim counts, status counts, first-party downgrade
  counts, and source-reference counts, and
  `primr://output/calibration_summary/by_job/{job_id}` returns compact
  label-calibration per-label counts, inference source-copy counts,
  evidence-review count buckets, judge provenance, and judge-agreement
  metadata. None returns report body content;
  trace summaries omit raw trace entries and page content, verification
  summaries omit raw claims, source URLs, search queries, and explanations,
  and calibration summaries omit raw claims, source URLs, evidence reviews,
  and rationales. Resource reads are now audited with normalized resource kind,
  hashed URI, hashed result body, job id when present, granted scopes,
  duration, and outcome, without raw URI query values or resource bodies.
  A2A now advertises equivalent read-scoped `read_artifacts_by_job`,
  `read_qa_summary_by_job`, `read_usage_summary_by_job`,
  `read_source_summary_by_job`, `read_trace_summary_by_job`, and
  `read_verification_summary_by_job`, and `read_calibration_summary_by_job`
  skills for the artifact metadata, QA summary, usage/cost, source appendix,
  scrape trace, claim verification, and label-calibration slices, using the
  same ownership-gated compact summary helpers.
- Non-job eval readback is also available for routed-stage scorecards:
  `primr://eval/stage_scorecard/{eval_id}` reads
  `output/evals/{eval_id}/stage_eval_scorecard.json` through a simple eval-id
  segment, returning status, blocker, route, cost, quality-score, and compact
  row fields without arbitrary path access or raw evidence bodies. A2A now
  advertises the equivalent read-scoped `read_stage_scorecard` skill, backed by
  the same compact eval-id summary contract.
- Scope matrix shipped so far: monitor can read status and compact summaries;
  artifact read can read compact resources; report can read bounded report
  bodies; research can estimate; and A2A paid research execution now requires
  the same approved cap plus approval token as MCP when cost-cap enforcement
  is active. MCP report reads now use
  the separate `report` scope and `primr://output/report/by_job/{job_id}` path
  before exposing report bodies.
- Shipped first A2A parity slice: authenticated A2A HTTP requests now bind the
  bearer token into the shared MCP auth context, and A2A skill dispatch
  enforces `read` for `estimate_research`, `check_jobs`, `system_health`, and
  compact read skills such as `read_artifacts_by_job` and
  `read_qa_summary_by_job`, `read_usage_summary_by_job`, and
  `read_source_summary_by_job`, `read_trace_summary_by_job`,
  `read_verification_summary_by_job`, `read_calibration_summary_by_job`, and
  `read_stage_scorecard`, and `research` for `research_company`, `run_qa`, and
  task cancellation.
  Authenticated A2A jobs are owned by the token `client_id`. Local
  unauthenticated loopback behavior remains permissive, and legacy `write`
  still satisfies research-scope operations for compatibility.
- Shipped second A2A parity slice: skill invocations and task cancellation now
  append privacy-preserving audit events with transport, skill name, hashed
  message/result payloads, hashed caller id, granted scopes, duration,
  outcome, and job id when present, without raw message text, task ids, URLs,
  report paths, raw results, or caller ids.
- Shipped A2A approval and budget parity: `estimate_research` returns
  `approval_token`, `approval_token_id`, and `approval_expires_at`, and
  `research_company` enforces `max_estimated_cost_usd` plus a matching token
  when cost-cap enforcement is active before job creation. Accepted caps are
  propagated into `PipelineRunner` as runtime budgets, and audit events record
  sanitized estimate/cap metadata without raw URLs, message text, or approval
  tokens.
- Shipped A2A report-read parity: `read_report_by_job` requires `report` scope
  for authenticated callers, reuses the MCP ownership-gated
  `primr://output/report/by_job/{job_id}` reader, and supports
  `content_mode`, `artifact_type`, and `max_chars` output negotiation while
  preserving hashed A2A audit events.
- Shipped remaining compact status output negotiation: authenticated MCP
  `check_jobs`, `primr://output/latest`, and `primr://output/by_job/{job_id}`
  now stay metadata-first even for `report`-scoped callers and point agents to
  the explicit report resource; A2A `check_jobs` returns compact artifact and
  report resource URIs instead of raw output paths.
- Shipped OpenTelemetry-compatible audit projections: every MCP tool call,
  MCP resource read, and A2A skill audit event now carries a `request_id` plus
  a body-free `otel_span` name/attribute payload with job id when present,
  without storing raw arguments, results, resource bodies, report bodies, URLs,
  or raw caller ids.
- Shipped non-fast runtime budget visibility: run manifests now persist the
  estimate-time budget-enforcement payload plus the approved ceiling and active
  runtime-budget flag, and compact usage-summary readback exposes that metadata
  including non-interruptible required Deep Research tasks without returning
  company URLs, approval tokens, manifest bodies, or artifact lists.
- Shipped truthful local cancellation: MCP and A2A share one parent-owned
  worker supervisor, strict JSONL lifecycle protocol, ready handshake,
  cleanup-confirmed process-tree escalation, immutable terminal state,
  lease-time journal reload before restart reconciliation, raw non-interpolated
  worker environment loading, exact A2A task ownership, and worker-exit
  manifests for supervised failure or cancellation. Spawn and restart failures
  remain journal-only. A `cancelled` response now means the local worker exited;
  remote provider state remains explicit and may be `unknown`.
- MCP `2026-07-28` release candidate watch: after the final spec ships on
  July 28, 2026, audit Primr's HTTP MCP server against the stateless transport
  model, server discovery, operation routing headers, cache hints, explicit
  task-handle lifecycle, Apps extension security model, JSON Schema 2020-12
  schema handling, trace-context `_meta`, and authorization hardening. Keep
  this as compatibility planning until the final spec and SDK support settle.

Done when:

- A read-only agent credential can monitor and consume a completed job without
  starting paid work.
- A research credential still cannot delegate unless it also has the delegate
  scope.
- Tool invocations and artifact-resource reads are auditable without raw
  argument, URI query, resource-body, or report-body persistence.
- MCP and A2A enforce the same approval, audit, and compact read-resource
  semantics for equivalent operations. The shared `read`/`research` skill
  scope split, MCP report-read scope separation, A2A skill-call audit parity,
  artifact-metadata compact read
  parity, QA-summary compact read parity, usage-summary compact read parity,
  source-summary compact read parity, stage-scorecard compact eval-read
  parity, all seven job-scoped compact read parity slices, and A2A research
  approval/budget parity, A2A report-read parity, and compact non-fast runtime
  budget visibility, plus truthful local worker cancellation, are shipped.

### 4. Research memory layer 1

Why later: memory compounds Primr's value, but it should not precede claim
calibration and job-scoped artifact resources. Without those, memory risks
repeating stale or weak claims with too much confidence.

Do next after the first three items are stable:

- Implement filesystem-backed company tracking in the per-user data directory.
  Foundation shipped: default `ResearchMemory()` now writes to
  `<per-user data dir>/research_memory`, `PRIMR_DATA_DIR` relocates it,
  `doctor` reports the path, and memory writes reject secret-like values before
  YAML persistence. Company profile tracking is also started:
  `primr company track`, `company list`, `company show`, and `company export`
  create/read/export local profile bundles under
  `<per-user data dir>/company_profiles` with no network or paid calls. Export
  now includes profile metadata, stored run pointers when present, persisted
  hypotheses, and explicit flagged gaps for missing run-history or claim-store
  data.
- Store run pointers, hypothesis history, source attribution, confidence,
  freshness metadata, retention metadata, and exportable OKF bundles.
- Ship deletion, retention, and no-secret write rules with layer 1, not after
  it.
- Require every persisted hypothesis to identify the source artifact and the
  evidence dimension that supports it.

Done when:

- Run-history pointers, confidence evolution, and source-attributed claim
  history feed the existing company export instead of remaining flagged gaps.
- Completed research runs attach body-free pointers to tracked profiles without
  loading report bodies into profile storage.
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

### Cross-cutting: runtime efficiency and execution isolation

This work supports the ordered product priorities rather than displacing them.
Instrument first, ship pipeline overlap, make cancellation own the actual
worker, and consolidate repeated HTML work into a parse-once Python boundary.
Only then run the optional Rust and Python 3.14t comparisons.

Go and Mojo remain trigger-based evaluations, not queued rewrites. A Go control
plane requires measured Python admission or p99 pressure after durable queueing
exists. Mojo requires a real Primr-owned accelerator kernel; MAX or another
model server may be compared externally through the existing
OpenAI-compatible endpoint. The binding gates and stop conditions are in
[`design/runtime-language-boundaries.md`](design/runtime-language-boundaries.md).

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
- Do not add a language because it is fashionable or because one isolated
  microbenchmark is faster. The complete product and operational contract must
  improve.

## Validation policy

Use free and local validation first: unit tests, strict docs build, static
analysis, mocked evals, local judge comparison, and existing report sidecars.
Deterministic checks may prepare evidence, prove structure, and guard
irreversible actions. They must not judge free-form content quality. Any paid
eval must have a pre-registered question, a cost cap, explicit approval, and a
rubric that measures substance rather than phrase matches.
