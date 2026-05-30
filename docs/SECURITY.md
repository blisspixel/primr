# Security Policy & Threat Model

## What primr is (and isn't), security-wise

primr is an **LLM-API client + adaptive web scraper + MCP/A2A agent**. It does
**not** train, fine-tune, host, or serve models — the models are third-party
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
| T1 | Indirect prompt injection | Instructions embedded in scraped pages / postings / sitemaps | `sanitize_for_llm` (injection-pattern + control-char stripping) + `fence_untrusted` data-fencing at every external-content→prompt boundary ("data, never instructions") | Shipped |
| T2 | SSRF / internal pivot | Attacker page or redirect points primr at loopback / RFC1918 / link-local / cloud-metadata | `is_safe_url` + `validate_final_url_after_redirect` on every egress helper (`HTTPClient.get`, `fallback_sources._http_get`, `hiring_signals._http_get`); `SSRFGuardHook` on tool calls | Shipped |
| T3 | Secret leakage | API key in a log line, prompt, or persisted artifact | `SecretMaskingFilter` on all log handlers; `mask_sensitive_data` (incl. xAI) applied in `chat_logger` before persist; hardcoded-secret CI gate | Shipped |
| T4 | Cost / resource exhaustion | Runaway tool invocation | `CostGuardHook` budget; `estimate_run`-first; `PRIMR_ENFORCE_MCP_COST_CAPS`; single-job model; rate limiting | Shipped |
| T5 | Unauthorized tool access | Calling MCP/A2A tools without/with stale creds | JWT (HMAC-SHA256, constant-time, expiry/nbf/aud), admin-token hashing, loopback-only unauthenticated A2A | Shipped (all-or-nothing) |
| T6 | Output egress / scope expansion | Injected instruction tries to widen URL/tool scope or exfiltrate | All fetches gated by T2; the LLM cannot register tools or bypass `is_safe_url` (tested invariant) | Shipped |
| T7 | Supply-chain compromise | Vulnerable/malicious dep or tampered release | `pip-audit` + `bandit` gates; Dependabot; `uv.lock`; OIDC publishing; SLSA build-provenance | Shipped |
| T8 | Per-tool privilege separation | Low-trust client invokes a high-cost/admin tool | JWT `role` extracted but not yet enforced per-tool | **Planned** (ROADMAP "AI / agent security posture") |

### Residual risks (accepted)
- **T1** is mitigated, not eliminated — a novel phrasing could evade the pattern
  set; the data-fence is the backstop, and an injection red-team eval is tracked.
- **T5/T8** — tool authz is all-or-nothing today; treat any authenticated client
  as able to invoke any tool until capability scoping lands. Issue tokens
  accordingly.
- Chat logs and reports are persisted locally; protect `logs/` and working dirs
  with normal filesystem permissions.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.27.x  | Yes                |
| 1.24.x  | Yes                |
| < 1.24  | No                 |

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

- **SSRF Protection**: All URLs validated against private IP ranges, cloud metadata endpoints, and DNS rebinding
- **Input Sanitization**: Company names and URLs sanitized against injection attacks
- **JWT Authentication**: Signed token verification for MCP HTTP mode
- **Rate Limiting**: Per-client request limits
- **Security Headers**: OWASP-recommended headers on all API responses

See [SECURITY_OPS.md](SECURITY_OPS.md) for operational security guidance.

## Security Audits

- January 2026: Initial security review (XXE, SSRF fixes)
- February 2026: JWT verification, CORS hardening, input sanitization
- May 2026: AI/agent security posture — indirect prompt-injection fencing
  (`fence_untrusted`) at all external-content boundaries, sink-level secret
  redaction (`SecretMaskingFilter`) + chat-log redaction, egress-guardrail
  invariant tests across all fetch helpers, supply-chain gates (pip-audit,
  bandit, Dependabot, SLSA provenance), and this scoped threat model.

## Acknowledgments

We appreciate responsible disclosure and will acknowledge security researchers who report valid vulnerabilities (with permission).
