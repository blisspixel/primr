# Next Steps

Last research refresh: 2026-06-26.

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

Reference anchors:

- Diataxis: <https://diataxis.fr/>
- GitHub README guidance: <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes>
- Keep a Changelog: <https://keepachangelog.com/en/1.1.0/>
- MkDocs strict mode: <https://www.mkdocs.org/user-guide/configuration/#strict>
- MCP security best practices: <https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices>
- OWASP Agentic AI Threats and Mitigations: <https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/>
- Microsoft Zero Trust AI threat modeling: <https://learn.microsoft.com/en-us/security/zero-trust/sfi/threat-modeling-ai>
- OpenTelemetry GenAI semantic conventions: <https://opentelemetry.io/docs/specs/semconv/gen-ai/>

## Ordered execution plan

### 1. Evidence calibration and label honesty

Why next: the roadmap's measured quality gap is not prose polish. It is
epistemic grounding: whether `(Confirmed)` and `(Reported)` claims actually
trace to cited evidence. This work improves the core report, is cheap to
validate on existing artifacts, and creates the measurement foundation needed
before routing or memory can safely depend on prior claims.

Do next:

- Run a multi-report calibration baseline over current-format reports.
- Compare local and cloud judges on the same sampled claims before trusting a
  local judge path.
- Set `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` only from the measured floor of
  that agreement-validated baseline.
- Surface contradicted `--verify` claims in the report trust summary, not only
  in JSON and console output.

Done when:

- The eval scorecard carries stable label-calibration results.
- The hard gate is either armed from a defensible baseline or deliberately left
  report-only with documented evidence.
- No new deterministic prose-quality gate was added.

### 2. Backend freedom production wiring

Why next: provider abstraction, capability routing, and availability snapshots
exist, but the full-report runtime still has xAI/Gemini-era assumptions. This
is the highest-leverage architectural gap because it unlocks honest
OpenAI-only, Anthropic-only, host-agent, hybrid, and local profiles without
forking the pipeline.

Do next:

- Move `grok_browse_and_summarize` and Gemini quota UI into provider-owned
  seams.
- Add long-context surcharge fields to estimates for models with tiered
  long-input pricing.
- Wire one cheap utility stage through capability routing behind an explicit
  inference/profile flag while preserving today's fallback chain.
- Keep every promotion eval-backed. A provider path is supported only when the
  report quality and cost records prove it.

Done when:

- The stage declares requirements; the router chooses candidates; execution
  consumes the resulting chain.
- Estimates and usage records name the backend and billing mode honestly.
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
  usage/cost summary, and selected artifact metadata.
- Extend the same scope, approval, and audit decisions to A2A.
- Carry request/job ids into OpenTelemetry-compatible spans and structured logs
  without storing raw report bodies by default.

Done when:

- A read-only agent credential can monitor and consume a completed job without
  starting paid work.
- A research credential still cannot delegate unless it also has the delegate
  scope.
- Tool invocations and artifact-resource reads are auditable without raw
  argument or report-body persistence.

### 4. Research memory layer 1

Why later: memory compounds Primr's value, but it should not precede claim
calibration and job-scoped artifact resources. Without those, memory risks
repeating stale or weak claims with too much confidence.

Do next after the first three items are stable:

- Implement filesystem-backed company tracking in the per-user data directory.
- Store run pointers, hypothesis history, freshness metadata, and exportable
  OKF bundles.
- Ship deletion, retention, and no-secret write rules with layer 1, not after
  it.

Done when:

- `primr company track`, `company list`, and `company export` work without new
  services.
- Clearing a company removes its local profile and claim history.
- Prior-run material can inform a run only as clearly marked context, never as a
  fresh claim without attribution.

### 5. Coverage and maintenance ratchet

Why continuous: the recent refactors made the core easier to test. The right
coverage goal is not a blanket 95 percent global target; it is a rising branch
coverage gate plus per-module coverage on the newly extracted seams.

Do next alongside every feature slice:

- Add focused tests for each touched seam.
- Raise per-module coverage where a refactor makes that honest.
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
- Do not promote a new backend because it works once. Promote only after
  measured quality, cost, and failure behavior are recorded.
- Do not build memory before deletion, retention, source attribution, and
  confidence-label rules are explicit.
- Do not create a generic agent orchestration platform. Primr remains URL in,
  serious artifact out, with a disciplined control plane around that job.

## Validation policy

Use free and local validation first: unit tests, strict docs build, static
analysis, mocked evals, local judge comparison, and existing report sidecars.
Any paid eval must have a pre-registered question, a cost cap, and explicit
approval before it runs.
