# Engineering Learnings

## MCP Control Plane

- Enforce MCP authorization at the central `call_tool` dispatch boundary, before
  rate limiting and before agentic, skill-pack, or built-in handlers can run.
  Keep the policy table explicit by tool name and scope so roadmap changes are
  reviewable.
- Treat OAuth `scope` and Entra `scp` JWT claims as the path for new
  least-privilege clients. Preserve legacy `write` as a compatibility alias for
  old no-scope tokens, but prefer explicit `read`, `research`, `delegate`, and
  `admin` scopes for new integrations.
- Do not store HTTP request auth in a shared mutable server attribute. Bridge
  authenticated SDK scope state into request-local context, then let existing
  handlers read the current context through the established seam.
- Approval tokens should bind to a normalized cost-affecting approval shape, not
  raw tool arguments. Estimate and execution tools sometimes differ in harmless
  fields (`company_name`, `destination`, singular `platform` vs plural
  `platforms`), so the stable security boundary is target tool, canonical cost
  shape, approved max cost, expiry, and single-use token id.
- Keep approval-token enforcement adjacent to cost-cap enforcement. The cap
  answers "how much was approved"; the token answers "was this execution shape
  the one estimated and approved." Both are required when MCP cost enforcement
  is active.
- Audit MCP actions at the registered tool-dispatch seam, not inside each tool
  handler. Store hashes and governance metadata, not raw arguments, raw results,
  raw client ids, or full approval tokens. Expose recent events as a local or
  admin-scoped resource so operators can investigate without broadening normal
  read-scope visibility.
- When an MCP tool accepts an approved cost cap, bind that cap to the runtime
  budget seam as well as the estimate check. Pre-flight approval answers "may
  this run start"; `RunBudget` answers "should optional spend continue." Clear
  the process-global budget in a `finally` because the MCP server is single-job
  today but still long-lived.

## Backend Routing and Availability

- Treat quota and service availability as normalized routing data before adding
  provider I/O. Pure helpers should compute binding headroom from quota windows;
  provider collectors should only translate official status/quota surfaces into
  that shape.
- A provider is only as available as its most constrained quota bucket. Treat
  elapsed reset times as fresh, preserve stale last-known-good snapshots as
  fallback signal, and prefer fresh snapshots when ranking providers.
- Capacity discovery must meet the user where they are: environment keys,
  sanctioned host allocation, gateways, and local OpenAI-compatible services.
  Do not store API key values, raw local endpoint URLs, personal account ids,
  repo-owned credentials, or installed local model names in availability
  snapshots.
- Local availability is generic OpenAI-compatible probing through `/v1/models`,
  not an Ollama-only assumption. Report model count and chat-model availability;
  keep exact model names out of persisted routing metadata unless a future
  operator-visible diagnostic explicitly asks for them.

## Security and Egress

- Migrate outbound HTTP helpers to `data.safe_http.safe_http_get()` one seam at
  a time. Preserve caller-specific headers, params, and return shape at the
  edge, but keep redirect following and per-hop SSRF validation in the shared
  helper so intermediate-redirect safety cannot drift across modules.
- When a legacy fetch helper must keep returning a client-native response
  object, preserve that shape and replace only redirect following: request with
  `allow_redirects=False`, validate the next `Location`, resolve relative hops,
  cap redirects, then issue the next request.
- For pooled clients, keep the existing session and adapter path. Add manual
  redirect control inside the client instead of bypassing retry/pooling with a
  different HTTP library.
- For tiered clients that differ by protocol, fingerprinting, or impersonation,
  centralize only the redirect policy. Keep each transport in place, but make
  every tier use `allow_redirects=False`, validate each resolved `Location`
  before connecting, and pin tests that unsafe redirects are never fetched.
- For async metadata resolvers, keep retry and fallback semantics in the caller.
  Put only the bounded network primitive in the safe HTTP seam, return an
  explicit guard-block signal, and let ordinary network exceptions propagate to
  the caller's existing retry policy.

## Skill Pack Generation

- Do not ask the authoring model to produce the same role-level reference notes
  independently for every skill. Generate shared role-family context
  deterministically from structured evidence, sanitize snippets, and attach the
  same reference to each skill in the role family.
- Keep validator hard failures focused on stable structure and safety. Substance
  should be improved upstream through prompts and measured with evals, not
  judged with brittle prose matching.
- Clean Agent Skills frontmatter should be the default. Machine-readable
  handoff metadata is useful, but it should be opt-in so generated skills feel
  native in every host.
- A draft skill body is not the place for a company report. Use company context
  to choose specific inputs, outputs, workflow steps, guardrails, examples, and
  validation checks; keep deeper grounding in references loaded only when
  needed.
- When an operator has a specific JD or role brief, treat it as evidence, not
  as an instruction source or a report to summarize. Sanitize it, put it in the
  hiring evidence stream, prioritize it ahead of noisy scraped postings, and let
  the generated skill use it to shape workflow, inputs, outputs, guardrails, and
  examples.
- When observed job postings cluster in one narrow band for an enterprise-scale
  organization, surface that as a partial-coverage warning instead of blocking
  or over-correcting. The planner should preserve the real posting evidence,
  flag `posting-incomplete`, and point the operator toward better evidence or
  curation rather than inventing missing corporate roles.
- Cowork sideload packages and unpacked Agent Skills trees do not have the
  same capacity shape. Preserve the full unpacked tree for large packs, but
  keep the Cowork zip manifest valid: max 20 `agentSkills`, max 1 MB
  `SKILL.md`, and companion files capped at 20 files / 5 MB each / 10 MB total
  per skill.
- When CI `pip-audit` fails on a transitive package, add an explicit security
  floor in `pyproject.toml` as well as refreshing `uv.lock`. To reproduce the
  CI audit locally, run `uv sync --frozen --extra dev --extra api --extra a2a`
  before `uv run --no-sync pip-audit ...`; otherwise the local virtualenv can
  still contain the old vulnerable resolution.
- Segmented career-site inputs should be modeled as deterministic hiring-source
  selectors, not as company context to paste into skills. Validate URL shape,
  rely on the existing SSRF-guarded fetch boundary, merge/dedupe the resulting
  postings, and keep role planning grounded in the postings rather than the URL
  list itself.
- A wrong archetype is worse than no archetype. For skill generation, common
  business-role scaffolds should be explicit bundled archetypes, while weak
  fuzzy matches should return no grounding so authoring relies on the actual
  company evidence instead of a misleading template family.

## Agent Skills Best Practices (Anthropic-aligned refinement)

- Skills are folders (SKILL.md + references/ + scripts/ + evals/). Progressive disclosure; SKILL.md lean.
- Narrowly scoped to one capability/category.
- Verification skills high leverage; generator must bias for >=1 per role.
- Scripts for deterministic (validate/extract/format); ship code ("solve, don't punt").
- Gotchas highest-signal: seed real failures in references/gotchas.md; living.
- Descriptions as triggers ("Use when..."), third-person, pushy, concrete phrasing.
- Compose by name reference; small skills, not giant.
- Measure via evals + structural counts in report. No brittle content regex (agentic-balance).
- Update own exemplars (primr skill) when refining generator. Use existing seams only.

## Release Hygiene

- Release only after the package metadata, ROADMAP current state, ROADMAP
  changelog row, `CITATION.cff`, and `primr.__version__` all agree. Let
  `tests/test_release_integrity.py` be the release-preflight witness before
  tagging for PyPI.

## Artifact Cleanup

- Cleanup regexes that strip writer scaffolding must be anchored to the
  scaffolding marker shape, not to a keyword anywhere inside a bracket. A
  bracket containing `cite:` can still be legitimate prose unless it starts
  with `cite:` or `cites:`.
- Cleanup regexes that repair prose must not mutate fenced code examples.
  Route marker stripping through a shared outside-fences helper so the same
  token can be stripped from prose and preserved when the report is teaching or
  documenting literal syntax.

## Budget Control Surfaces

- Keep budget semantics in one pure, machine-readable helper instead of
  repeating prose across CLI, MCP, and docs. Approval prompts need to know
  whether a mode is pre-flight estimate-gated only or has runtime
  optional-stage checkpoints.
- Do not claim runtime spend enforcement until the execution path actually
  consults `RunBudget` before optional spend. Honest estimate-only messaging is
  safer than a fictional guardrail.
- When moving behavior out of pinned files, lower the architecture line
  ceilings immediately. The ratchet should preserve every shrink.
- For AI-strategy estimates, clamp empty platform tuples to one vendor. Empty
  `platforms=()` can occur through tests or internal callers even when CLI
  parsing normally supplies a default.

## SSRF IP Pinning

- Boolean URL validation is not enough when the client later resolves the same
  hostname again. Return a connection artifact that contains the validated IP
  literal, original Host header, and HTTPS SNI hostname, then make the fetch
  seam use that artifact for the actual request.
- Redirect loops should track the logical URL for relative `Location`
  resolution and final reporting, while each hop derives a fresh pinned request
  URL immediately before connecting.
- Do not disable TLS verification to make IP pinning work. Use the HTTP
  client's SNI extension or transport hook so certificate verification still
  checks the public hostname.
- For Requests, use a custom `HTTPAdapter` rather than rewriting callers around
  another client. Override the TLS-aware connection hook, point urllib3 at the
  validated IP literal, set `Host` plus `server_hostname` / `assert_hostname`,
  and fail closed on proxies because proxy resolution would bypass the pinned
  local transport.
- For curl_cffi/libcurl, keep the logical URL and pass the vetted address with
  `CurlOpt.RESOLVE` on a per-hop `Session(curl_options=...)`. That preserves
  TLS fingerprint impersonation, Host, and SNI semantics. Disable
  `trust_env` so environment proxies cannot replace the locally pinned
  connection path.

## Documentation Front Door

- Keep the root README as an entry point, not the full manual. It should answer
  what the project is, how to install, what the first safe command is, what it
  costs, where outputs go, and where deeper docs live.
- Move long mode matrices, integration setup, subsystem internals, and advanced
  workflows into focused docs that appear in `docs/README.md` and `mkdocs.yml`.
- Run style scans for em dashes, emoji-like symbols, and generated-attribution
  phrases before committing documentation refreshes.
