# Security Policy & Threat Model

## What primr is (and isn't), security-wise

primr is an **LLM-API client + adaptive web scraper + MCP/A2A agent**. It does
**not** train, fine-tune, host, or serve models - the models are third-party
hosted APIs (Gemini, Grok, OpenAI, Anthropic, Ollama). Per primr's design
philosophy, *the model is a commodity; the orchestration pipeline is the asset.*

That framing scopes the threat model. Whole categories of adversarial-ML
security are **out of scope by construction** because primr owns no model
weights or training pipeline: training-time poisoning/backdoors, model
extraction/stealing, membership/attribute inference, model inversion,
watermarking/weight protection, and confidential-compute/certified-robustness
serving. If primr ever ships a hosted/served model, this section must be
revisited.

The real attack surface is four things: (1) untrusted retrieved content flowing
into prompts, (2) LLM output driving downstream actions, (3) the agentic
MCP/A2A tool surfaces, and (4) provider secrets + the dependency supply chain.

## Threat model (MITRE ATLAS-style, scoped to client/scraper/agent)

| # | Threat | Vector | Control(s) | Status |
|---|--------|--------|-----------|--------|
| T1 | Indirect prompt injection | Instructions embedded in scraped pages / postings / sitemaps | `sanitize_for_llm` (injection-pattern + control-char stripping) + `fence_untrusted` data-fencing at the external-content→prompt boundaries. Fenced: insights extraction, deep research, the fast-run analysis-workbook and section-writer corpus/external-source blocks, hypothesis-tree inputs, gap-analysis summaries, report and strategy regeneration evidence, hiring-signal triage and JD extraction, the hiring-signal block entering the Deep Research stage-1 context (load-bearing for the verbatim File Search Store upload), the scraped-external and hiring-signal blocks inside `insights.txt` (which the AI-strategy prompt and the workbook-fallback section prompts read unfenced), and the scraped-adjacent strategy context artifacts (hiring signals, recon context). Sanitize-only (deliberately unfenced): website summarization and composer notes, where the surrounding framing is the instruction boundary. LLM-generated working artifacts (gap analysis, workbook) enter downstream prompts unfenced - the accepted "laundered injection" residual below | Shipped |
| T2 | SSRF / internal pivot | Attacker page or redirect points primr at loopback / RFC1918 / link-local / cloud-metadata | `is_safe_url` on every egress helper; IP-pinned per-hop redirect validation through `data/safe_http.py` for `fallback_sources._http_get`, `hiring_signals._http_get`, Wayback CDX/replay fetches, async citation-resolution HEAD requests, the tiered httpx scraper, pooled `HTTPClient` GET/HEAD calls, the tiered requests scraper, and the curl_cffi scraper; browser egress planning for Chromium-backed tiers with initial-host resolver pins, local loopback egress proxying for dynamic browser hosts, QUIC disabled, and Playwright/Patchright request route guards; manual per-hop validation in `data/scraping/net.py`; `SSRFGuardHook` on tool calls | Shipped |
| T3 | Secret leakage | API key in a log line, prompt, or persisted artifact | `SecretMaskingFilter` on all log handlers; `mask_sensitive_data` (incl. xAI) applied in `chat_logger` before persist; research memory rejects secret-like payloads before durable YAML writes; company profiles reject URL userinfo and secret-like values before durable JSON writes; hardcoded-secret CI gate | Shipped |
| T4 | Cost / resource exhaustion | Runaway tool invocation | `CostGuardHook` budget; `estimate_run`/A2A `estimate_research` first; `PRIMR_ENFORCE_MCP_COST_CAPS`; server-issued approval tokens for MCP cost-cap-governed tools and A2A research execution; explicit budget-enforcement payloads; MCP and A2A runtime budget propagation for fast optional stages and non-fast optional strategy documents; run manifests and compact usage summaries expose approved ceiling, active checkpoint status, and non-interruptible required provider tasks without manifest bodies; remote skill-pack icons require `--remote-icons` / `remote_icons`; vendor-research generation/refresh requires `--refresh-vendor-research`, `primr --generate-vendor-research`, or `PRIMR_ALLOW_VENDOR_REFRESH=1`; Gemini PDF extraction defaults to local PyMuPDF unless `PRIMR_PDF_LLM_MAX_CALLS` is set; single-job model; rate limiting | Shipped, with required Deep Research tasks still estimate-gated mid-flight |
| T5 | Unauthorized tool access | Calling MCP/A2A tools without/with stale creds | JWT (HMAC-SHA256, constant-time, finite expiry/nbf/aud validation, fail-closed explicit scope claims), admin-token hashing with uncached max-age enforcement, loopback-only unauthenticated MCP HTTP and A2A, and shared MCP/A2A bearer-token context for authenticated A2A requests | Shipped |
| T6 | Output egress / scope expansion | Injected instruction tries to widen URL/tool scope or exfiltrate | All fetches gated by T2; the LLM cannot register tools or bypass `is_safe_url` (tested invariant) | Shipped |
| T7 | Supply-chain compromise | Vulnerable/malicious dep or tampered release | PR/push and weekly scheduled `pip-audit` + Trivy gates; `bandit`; `uv.lock`; hash-verified lock exports for production containers; OIDC publishing; SLSA build-provenance; manually reviewed dependency updates | Shipped |
| T8 | Per-tool privilege separation | Low-trust client invokes a high-cost/admin tool | Per-tool MCP scope policy (`read`, `report`, `research`, `delegate`, `admin`) enforced at dispatch and report-resource readback; A2A skill dispatch enforces the shared `read`/`report`/`research` split for estimate, status, health, compact resources, report reads, research, QA, and cancellation; OAuth `scope` / Entra `scp` claims honored; legacy `write` tokens retained for compatibility for research/delegate only and does not satisfy `report`; approval tokens required for MCP cost-cap-governed execution and A2A research execution when enforcement is active; privacy-preserving agent audit log with admin-readable MCP tool-call events, MCP resource-read events, and A2A skill-call events, each carrying a stable `request_id` and body-free `otel_span` projection; ownership-gated job artifact metadata via `primr://output/artifacts/by_job/{job_id}`, QA summary metadata via `primr://output/qa_summary/by_job/{job_id}`, usage/cost summary metadata via `primr://output/usage_summary/by_job/{job_id}`, source appendix metadata via `primr://output/source_summary/by_job/{job_id}`, scrape trace metadata via `primr://output/trace_summary/by_job/{job_id}`, verification metadata via `primr://output/verification_summary/by_job/{job_id}`, and calibration metadata via `primr://output/calibration_summary/by_job/{job_id}` without report body content; explicit report-body reads go through `primr://output/report/by_job/{job_id}` and A2A `read_report_by_job` with ownership checks, `report` scope for HTTP callers, and `content_mode` / `artifact_type` / `max_chars` negotiation; `check_jobs`, `primr://output/latest`, and `primr://output/by_job/{job_id}` no longer return report bodies or previews to authenticated HTTP callers even when they hold `report`; A2A `check_jobs` returns compact artifact/report resource URIs instead of raw output paths; resource-read audit events store normalized resource kind, hashed URI, hashed result body, job id when present, granted scopes, duration, outcome, request id, and span-safe attributes without raw URI query values or resource bodies; A2A skill-call events store transport, skill name, hashed message/result payloads, hashed caller id, granted scopes, duration, outcome, job id when present, request id, span-safe attributes, and sanitized estimate/cap metadata without raw message text, task ids, URLs, report paths, approval tokens, raw results, or caller ids; trace summaries omit raw trace entries, URLs, and page content, verification summaries omit raw claims, source URLs, search queries, and explanations, and calibration summaries expose counts including inference source-copy counts while omitting raw claims, source URLs, evidence reviews, and rationales | Shipped (MCP Stages 1-3 plus all seven artifact-resource slices, MCP report-read scope separation, resource-read audit, A2A skill scopes, A2A skill-call audit, A2A compact-resource parity, A2A report-read parity, and A2A research approval/budget parity) |

### Residual risks (accepted)
- **T1** is mitigated, not eliminated - a novel phrasing could evade the pattern
  set; the data-fence is the backstop, and an injection red-team eval is tracked.
- **T1 laundered injection**: LLM-generated working artifacts (gap analysis,
  the analysis workbook) are built FROM fenced scraped inputs but enter later
  prompts unfenced; an injection that survives into the model's own output
  re-enters downstream prompts as trusted text. Accepted because re-fencing
  model output would fence the pipeline's own analysis, and the upstream
  fences plus sanitization make survival unlikely; the red-team eval covers
  this path.
- **T2** has complete pre-request SSRF validation and per-hop redirect
  validation on the shared safe HTTP seam, async citation HEAD requests,
  preflight website HEAD checks, provider-hosted skill-pack image fetches,
  discovery HTTP helpers, pooled HTTPClient GET/HEAD calls, and the tiered
  requests/httpx/curl_cffi scrapers. Workday hiring-signal JSON POST probes
  now drop redirects rather than following an unvalidated hop. The shared safe
  HTTP seam, tiered httpx scraper, pooled HTTPClient, tiered requests scraper,
  and curl_cffi scraper now
  resolve each hop once, validate every returned address, and pin the actual
  connection target while preserving the public hostname semantics each client
  needs for virtual hosting and TLS. Browser-backed Chromium tiers now pin the
  initial hostname with Chromium resolver rules and force browser traffic
  through a local loopback egress proxy. The proxy validates each HTTP request
  or HTTPS CONNECT target, dials the validated IP literal, and tunnels TLS
  without terminating it, while Playwright-compatible route guards remain as
  defense-in-depth. QUIC is disabled for proxied browser launches so browser
  traffic stays on the TCP proxy path.
- **T8 Stages 1-3** are shipped for MCP tool dispatch and resource reads:
  per-tool scopes, server-issued approval tokens, and structured audit events. The
  first seven job-scoped artifact-resource slices are also shipped:
  `primr://output/artifacts/by_job/{job_id}` returns metadata only for an owned
  job, and `primr://output/qa_summary/by_job/{job_id}` returns compact QA
  score/status/count metadata without detailed QA body text, and
  `primr://output/usage_summary/by_job/{job_id}` returns compact manifest
  cost, timing, approval, execution, and artifact-count metadata without
  company URLs, approval tokens, manifest artifact lists, or full manifest
  content, and `primr://output/source_summary/by_job/{job_id}` returns compact
  citation/source appendix metadata without report body content, and
  `primr://output/trace_summary/by_job/{job_id}` returns compact scrape trace
  metadata without URLs, final URLs, raw trace entries, or page content, and
  `primr://output/verification_summary/by_job/{job_id}` returns compact claim
  verification trust score, claim counts, status counts, first-party downgrade
  counts, and source-reference counts without raw claims, source URLs, search
  queries, explanations, or report body content, and
  `primr://output/calibration_summary/by_job/{job_id}` returns compact
  label-calibration per-label counts, inference source-copy counts,
  evidence-review count buckets, judge provenance, and judge-agreement metadata
  without raw claims, source URLs, evidence reviews, rationales, or report body
  content. MCP report-body reads now use
  `primr://output/report/by_job/{job_id}` with ownership checks, explicit
  `report` scope for authenticated HTTP callers, and
  `content_mode` / `artifact_type` / `max_chars` output negotiation.
  `check_jobs`, `primr://output/latest`, and
  `primr://output/by_job/{job_id}` omit report bodies or previews for all
  authenticated HTTP callers, even when they hold `report`; A2A `check_jobs`
  returns compact artifact/report resource URIs instead of raw output paths.
  All hide unowned jobs behind the same response as missing jobs. Resource-read audit events record
  normalized resource kind, hashed URI, hashed result body, job id when
  present, granted scopes, request id, span-safe attributes, duration, and
  outcome without raw URI query values, raw resource bodies, or raw caller ids.
  A2A authenticated requests now share
  the MCP auth context, enforce `read`/`research` at skill dispatch, own jobs
  by token `client_id`, enforce `report` for `read_report_by_job`, and write
  skill-call audit events with hashed message/result payloads, hashed caller
  ids, granted scopes, request id, span-safe attributes, duration, outcome,
  and job id when present. A2A
  `estimate_research` now issues
  approval-token fields, and A2A `research_company` enforces
  `max_estimated_cost_usd` plus a matching token when cost-cap enforcement is
  active before job creation, then propagates the accepted cap into
  `PipelineRunner` as the runtime budget. Residual risk remains around required
  provider tasks that cannot be interrupted mid-flight after the user accepts
  the estimate. Approval tokens are single-use and process-instance-bound, so
  a restart requires a new estimate and fresh approval even when instances
  share a signing secret. Strategy generation validates the report as one
  stable, regular, non-linked file and gives providers only a verified private
  snapshot; a changed report fails before a provider call. Issue
  low-trust tokens with explicit `read` scopes rather than relying on legacy
  no-scope JWT defaults, and issue `report` only to clients that should consume
  report text.
- Chat logs and reports are persisted locally; protect `logs/` and working dirs
  with normal filesystem permissions.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.36.x  | Yes                |
| < 1.36  | No                 |

Requires Python 3.12+ (3.10/3.11 are past or nearing end-of-life).

## Reporting a Vulnerability

If you discover a security vulnerability in Primr, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. Email security concerns to the maintainers (see GitHub profile for contact)
2. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes (optional)

### What to Expect

- Acknowledgment within 48 hours
- Status update within 7 days
- Fix timeline depends on severity:
  - Critical: 24-48 hours
  - High: 7 days
  - Medium: 30 days
  - Low: Next release

### Scope

Security issues we care about:
- SSRF vulnerabilities
- Authentication/authorization bypasses
- Injection attacks (SQL, command, template)
- Path traversal
- Sensitive data exposure
- Denial of service

Out of scope:
- Rate limiting effectiveness (configurable by deployment)
- Issues requiring physical access
- Social engineering

## Security Measures

Primr implements several security controls:

- **SSRF Protection**: All outbound URLs are validated against private IP ranges, cloud metadata endpoints, and DNS rebinding; migrated helpers also validate every redirect hop before connecting, the shared safe HTTP, requests-family, httpx scraper, and curl_cffi scraper seams pin connections to the validated address, and Chromium-backed browser tiers force browser traffic through the local pinned egress proxy while route-guarding unsafe requests where supported
- **Input Sanitization**: Company names and URLs sanitized against injection attacks
- **JWT Authentication**: Signed token verification for MCP HTTP mode
- **Rate Limiting**: Per-client request limits
- **Security Headers**: OWASP-recommended headers on all API responses

See [SECURITY_OPS.md](SECURITY_OPS.md) for operational security guidance.

## Security Audits

- January 2026: Initial security review (XXE, SSRF fixes)
- February 2026: JWT verification, CORS hardening, input sanitization
- May 2026: AI/agent security posture - indirect prompt-injection fencing
  (`fence_untrusted`) at the insights-extraction, deep-research, and composer
  boundaries, sink-level secret redaction (`SecretMaskingFilter`) + chat-log
  redaction, egress-guardrail invariant tests across all fetch helpers,
  supply-chain gates (pip-audit, Trivy, bandit, SLSA provenance), and
  this scoped threat model.
- July 2026: fencing extended to the remaining fast-run scraped-text→prompt
  boundaries (workbook/section corpus blocks, hypothesis tree, gap-analysis
  summaries, regeneration evidence, hiring triage/extraction, `insights.txt`
  external block, strategy context artifacts); the T1 row now enumerates
  fenced vs sanitize-only boundaries instead of claiming blanket coverage.
- July 2026: all remote GitHub Actions are pinned to verified commit SHAs and
  shipped Python container bases are pinned to a verified multi-platform
  digest. Deterministic fitness tests reject moving action tags and unpinned
  base images before merge.
- July 2026: standalone strategy estimates, approval tokens, and usage records
  share the canonical Deep Research planning cost. Cost-gated strategy calls
  explicitly suppress environment-driven vendor refreshes so one approval
  cannot silently authorize a second paid research task.

## Acknowledgments

We appreciate responsible disclosure and will acknowledge security researchers who report valid vulnerabilities (with permission).
