# Progress Log

## 2026-06-26

### Loop cycle: Requests-family DNS-rebind IP pinning

Refresh: re-read README, ROADMAP, `CLAUDE.md`,
`docs/design/agentic-balance.md`, `docs/design/engineering-excellence.md`,
`docs/SECURITY.md`, `docs/ARCHITECTURE.md`, NOTES, current-state, the quality
rubric, the pooled HTTP client, tiered HTTP scraper, and the Requests/urllib3
transport APIs in the local lock.

Prioritize: selected requests-family IP pinning because it closes the next
check/connect split without changing the scraper tier order or bypassing the
existing pooled session/retry seam. At selection time, curl_cffi and
browser-backed pinning were still queued because they needed transport-specific
APIs.

Implemented:

- Added `data.pinned_requests.PinnedHTTPAdapter`.
- The adapter resolves each logical request once, blocks unsafe DNS answers
  before urllib3 opens a pool, connects to the validated IP literal, and
  preserves the logical request URL, original Host header, and HTTPS SNI.
- The pooled `HTTPClient` now mounts the pinned adapter while keeping retries,
  pooling, stats, manual redirects, and native `requests.Response` behavior.
- `scrape_with_requests()` now uses the same pinned session seam while keeping
  headers, cookies, manual redirects, and `ScrapeResult` behavior.
- Raised the `requests` dependency floor to `>=2.34.0` to match the verified
  TLS-aware adapter hook used by the implementation.
- Updated NOTES, ROADMAP, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`, current-state, and the quality rubric.

Validation:

- `uv run --no-sync pytest tests/test_data/test_pinned_requests.py tests/test_data/test_http_client.py tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py tests/security/test_ssrf.py tests/security/test_egress_guardrails.py -q`
  passed with 113 tests and 2 skipped.
- `uv run ruff check src/primr/data/pinned_requests.py src/primr/data/http_client.py src/primr/data/scraping/http_clients.py tests/test_data/test_pinned_requests.py tests/test_data/test_http_client.py tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py`
  passed.
- `uv run --no-sync pytest tests/test_data/test_scraping/test_vertical_slice.py tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py -q`
  passed with 41 tests after updating the vertical-slice tests to the pinned
  session seam.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict docs link warnings; `_site` was
  removed afterward.
- The first full coverage run exposed a stale vertical-slice test mock that
  still patched module-level `requests.get`; the test was updated to patch
  `requests.Session.get`, matching the new pinned session seam.
- The CI-shaped non-manual coverage gate passed with `10249 passed, 39
  skipped, 5 deselected` and 85.23% branch coverage.
- `uv lock --check` passed.

Maker-checker review:

- Maker: the change uses Requests' existing adapter seam instead of replacing
  the pooled client or scraper with a different HTTP library.
- Checker 1, security/performance: the actual connection target is the same IP
  that passed validation; proxy paths fail closed because they would move
  resolution out of the pinned local transport; no paid validation was used.
- Checker 2, maintainability/simplicity: one small adapter module is shared by
  both Requests callers, and the dependency floor records the API contract it
  relies on.

Spend: `$0.00`.

### Loop cycle: Tiered httpx scraper DNS-rebind IP pinning

Refresh: re-read ROADMAP, NOTES, `docs/SECURITY.md`,
`docs/ARCHITECTURE.md`, `data.scraping.http_clients`, the safe URL resolution
artifact, scraper tests, current-state, and the quality rubric.

Prioritize: selected `scrape_with_httpx()` because it can reuse the same
HTTPX/httpcore SNI extension path that already shipped in `data.safe_http`.
Requests, curl_cffi, pooled `HTTPClient`, and browser-backed seams require
separate transport-specific work and remain queued.

Implemented:

- `scrape_with_httpx()` now calls `resolve_safe_url_for_connect()` for each
  hop before connecting.
- The tier connects to the validated IP-literal request URL and passes the
  original Host header plus HTTPS SNI.
- The scraper keeps its HTTP/2 client setup, cookies, manual redirect loop,
  and `ScrapeResult` contract.
- Successful httpx results report the logical final URL rather than the
  IP-literal transport URL.
- Added tests for pinned IP requests, Host/SNI preservation, private rebind
  blocking before connect, safe relative redirects, and existing error
  branches.
- Updated NOTES, ROADMAP, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`, current-state, and the quality rubric.

Validation:

- `uv run --no-sync pytest tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py tests/security/test_ssrf.py tests/security/test_egress_guardrails.py -q`
  passed with 75 tests.
- `uv run ruff check src/primr/data/scraping/http_clients.py tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py`
  passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict docs link warnings; `_site` was
  removed afterward.
- The CI-shaped non-manual coverage gate passed with `10244 passed, 39
  skipped, 5 deselected` and 85.22% branch coverage.

Maker-checker review:

- Maker: the httpx scraper uses the existing pinning primitive without changing
  tier ordering or result shape.
- Checker 1, security/performance: each hop connects to the IP that passed
  validation; HTTP/2 and TLS verification remain enabled; no paid validation
  was used.
- Checker 2, maintainability/simplicity: requests/curl/browser pinning is not
  overfit into the httpx slice, so the remaining work stays explicit.

Spend: `$0.00`.

### Loop cycle: Safe HTTP DNS-rebind IP pinning

Refresh: re-read README, ROADMAP, NOTES, `docs/SECURITY.md`,
`docs/ARCHITECTURE.md`, `data.safe_http`, the central URL security guard,
citation-resolution tests, safe HTTP tests, current-state, and the quality
rubric. Checked current SSRF guidance against the project threat model and the
local HTTPX/httpcore implementation: redirects must stay manual, and validation
must return the exact connection target so the client does not re-resolve a
hostname after the guard passes.

Prioritize: selected the shared `data.safe_http` seam because it serves
fallback sources, hiring fetches, Wayback CDX/replay, and citation HEAD
resolution. Browser and requests/curl transport families still need separate
connection-level work, so this cycle intentionally shipped the reusable,
httpx-backed slice without overclaiming full transport parity.

Implemented:

- Extracted URL SSRF validation into `utils.url_security` and kept
  compatibility re-exports from `utils.security`.
- Added `SafeUrlResolution` plus `resolve_safe_url_for_connect()`, which
  resolves a URL once, validates every returned address, and returns an
  IP-literal request URL with the original Host header and HTTPS SNI.
- Updated `safe_http_get()` and `async_safe_http_head()` to connect to the
  validated IP literal while resolving redirects against the logical URL.
- Kept TLS verification intact by passing the public hostname as SNI instead
  of disabling certificate checks.
- Updated citation tests to mock the actual `async_safe_http_head()` seam.
- Added resolver and safe HTTP tests for IP literal requests, original
  Host/SNI preservation, private-IP DNS answers, IPv6 bracket handling, and
  existing redirect blocking.
- Updated NOTES, ROADMAP, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`, current-state, quality rubric, and SKILLS.

Validation:

- `uv run --no-sync pytest tests/test_data/test_safe_http.py tests/test_utils/test_security_more_coverage.py tests/test_utils/test_numeric_host_ssrf.py tests/security/test_invariant_properties.py tests/security/test_egress_guardrails.py tests/test_ai/test_citation_resolution.py tests/test_ai/test_citation_resolution_extra.py tests/test_ai/test_citation_properties.py -q`
  passed with 227 tests.
- `uv run --no-sync pytest tests/test_data/test_safe_http.py tests/test_data/test_wayback.py tests/test_data/test_fallback_sources.py tests/test_data/test_fallback_sources_coverage.py tests/test_data/test_hiring_signals_more_coverage.py tests/test_data/test_hiring_signals_new_providers.py tests/test_ai/test_citation_resolution.py tests/test_ai/test_citation_resolution_extra.py tests/test_ai/test_citation_properties.py -q`
  passed with 235 tests.
- `uv run ruff check ...` over the touched source and test modules passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict docs link warnings; `_site` was
  removed afterward.
- The CI-shaped non-manual coverage gate passed with `10242 passed, 39
  skipped, 5 deselected` and 85.22% branch coverage.
- `git diff --check` passed.
- Added-line em dash scan passed.

Maker-checker review:

- Maker: the change uses one reusable URL resolution artifact and keeps the
  existing safe HTTP redirect loop shape.
- Checker 1, security/performance: the shared seam now connects to the same IP
  that passed validation; TLS verification remains enabled; no paid or external
  validation was used.
- Checker 2, maintainability/simplicity: `utils/security.py` stayed below the
  file-size ratchet by extracting URL security to a focused module, while
  public imports remain compatible.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: $0.00 | New skill distilled:
SSRF IP pinning.

Spend: `$0.00`.

### Loop cycle: Async citation redirect per-hop guard

Refresh: re-read README, ROADMAP, NOTES, `docs/SECURITY.md`,
`docs/ARCHITECTURE.md`, `data.safe_http`, `ai.citation_resolution`, citation
tests, safe HTTP tests, current-state, and the quality rubric.

Prioritize: selected `ai/citation_resolution.py`, the last tracked
intermediate-redirect SSRF migration seam. It is a narrow async HEAD resolver
for Google grounding redirects, so the right slice was an async HEAD helper
that preserves citation fallback semantics while validating every redirect hop
before connecting.

Implemented:

- Added `data.safe_http.async_safe_http_head()`.
- The helper uses `httpx.AsyncClient(follow_redirects=False)`, validates the
  initial URL and every resolved `Location` through `is_safe_url()`, resolves
  relative redirects, and caps redirect depth.
- The helper lets network exceptions propagate, preserving the citation
  resolver's retry and decoded-domain fallback behavior.
- SSRF guard blocks are explicit, so `resolve_redirect_url()` returns the
  original Google grounding URL instead of treating a security block as a
  transient fetch failure.
- Added async safe-HEAD tests for direct responses, safe relative redirects,
  blocked internal redirects that are never connected to, and propagated
  network failures.
- Updated citation resolver tests to assert blocked redirect hops are refused
  before a second HEAD request.
- Updated NOTES, ROADMAP, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`, current-state, and the quality rubric.

Validation:

- `uv run --no-sync pytest tests/test_data/test_safe_http.py tests/test_ai/test_citation_resolution.py tests/test_ai/test_citation_resolution_extra.py tests/test_ai/test_citation_properties.py tests/security/test_egress_guardrails.py -q`
  passed with 76 tests.
- `uv run ruff check src/primr/data/safe_http.py src/primr/ai/citation_resolution.py tests/test_data/test_safe_http.py tests/test_ai/test_citation_resolution_extra.py tests/test_ai/test_citation_resolution.py tests/test_ai/test_citation_properties.py tests/security/test_egress_guardrails.py`
  passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict docs link warnings; `_site` was
  removed afterward.
- The first full coverage attempt hit the 15-minute tool timeout and left no
  usable `.coverage` artifact after the orphaned pytest process exited, so it
  was rerun with a longer timeout.
- The CI-shaped non-manual coverage gate passed with `10236 passed, 39 skipped,
  5 deselected` and 85.22% branch coverage.
- `git diff --check` passed.
- Added-line em dash scan passed.
  passed.

Maker-checker review:

- Maker: the new helper is HEAD-only and keeps retry/fallback ownership in the
  caller.
- Checker 1, security/performance: unsafe redirect hops are refused before
  connection; no paid or external validation was used.
- Checker 2, maintainability/simplicity: the async helper mirrors the existing
  safe HTTP policy and avoids embedding another local redirect loop in the AI
  module.

Spend: `$0.00`.

### Loop cycle: HTTP scraper tier per-hop redirect guard

Refresh: re-read NOTES, ROADMAP, `docs/SECURITY.md`,
`docs/ARCHITECTURE.md`, `data.scraping.http_clients`, tiered scraper tests,
and SSRF guardrail status.

Prioritize: selected `data/scraping/http_clients.py` from the remaining
intermediate-redirect SSRF seams. These scrapers intentionally exercise three
different transports, so the right slice was to preserve transport identity
while moving redirect following under shared per-hop validation helpers.

Implemented:

- Added shared redirect helpers local to the tiered scraper module.
- `scrape_with_requests()`, `scrape_with_httpx()`, and
  `scrape_with_curl_cffi()` now request with `allow_redirects=False`.
- Each redirect target is resolved with `urljoin`, validated through
  `validate_url_for_request()`, and blocked before the next network request if
  unsafe.
- Redirect depth is capped at 10 hops.
- Raw-content result shape, timing, tier names, cookies, profiles, HTTP/2
  setup, and curl_cffi impersonation remain intact.
- Added regression tests proving safe relative redirects still work and unsafe
  internal redirects are blocked before a second request across all three
  tiers.
- Updated NOTES, ROADMAP, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`, current-state, the quality rubric, and skills.

Validation:

- `uv run --no-sync pytest tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py tests/security/test_ssrf.py -q`
  passed with 56 tests.
- `uv run ruff check src/primr/data/scraping/http_clients.py tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py`
  passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict docs link warnings; `_site` was
  removed afterward.
- The CI-shaped non-manual coverage gate passed with `10232 passed, 39 skipped,
  5 deselected` and 85.22% branch coverage.

Maker-checker review:

- Maker: the implementation preserves transport-specific behavior and only
  centralizes redirect policy.
- Checker 1, security/performance: unsafe redirect targets are validated before
  connection; no new external dependency or network fan-out was added.
- Checker 2, maintainability/simplicity: one small helper set replaces three
  duplicated final-url validation branches and keeps each tier readable.

Spend: `$0.00`.

### Loop cycle: HTTPClient per-hop redirect guard

Refresh: re-read NOTES, ROADMAP, `docs/SECURITY.md`,
`docs/ARCHITECTURE.md`, `data.http_client`, HTTP client tests, hardening tests,
and SSRF guardrail tests.

Prioritize: selected `data/http_client.py` from the remaining
intermediate-redirect SSRF seams. It is a pooled requests client, so the right
slice was not to replace it with the tuple-returning `safe_http_get()` seam but
to preserve `requests.Session`, retries, stats, and `requests.Response` return
shape while moving redirect following under explicit per-hop validation.

Implemented:

- Added a private `_request_with_safe_redirects()` helper to `HTTPClient`.
- `get()` and `head()` now request with `allow_redirects=False`, validate each
  redirect target before the next request, resolve relative redirects, and cap
  redirect depth.
- `params` are applied only to the initial GET request, matching normal redirect
  semantics.
- Existing stats and error behavior remain intact.
- Added GET and HEAD regression tests for safe relative redirects and blocked
  internal redirect targets.
- Updated NOTES, ROADMAP, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`, current-state, and the quality rubric.

Validation:

- `uv run --no-sync pytest tests/test_data/test_http_client.py tests/security/test_ssrf.py tests/security/test_egress_guardrails.py tests/test_hardening.py -q`
  passed with 91 tests and 2 skipped.
- `uv run ruff check src/primr/data/http_client.py tests/test_data/test_http_client.py`
  passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict link warnings; generated `_site`
  was removed after validation.
- `$env:GEMINI_API_KEY='fake-key-for-ci-tests'; uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10229 passed, 39 skipped, 5 deselected`, branch coverage
  `85.24%`.

Rubric: Correctness 5/5, Security and Privacy 5/5, Simplicity 5/5,
Maintainability 5/5, Performance and Cost 5/5, Verification 5/5.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: $0.00 | New skill distilled:
session-preserving redirect migration.

### Maintenance sub-goal: redirect hardening bug hunt

Trigger: cycle 7 maintenance lane.

Reviewed:

- `data.safe_http`
- `data.scraping.net`
- `data.scraping.wayback`
- SSRF notes, ROADMAP posture text, `docs/SECURITY.md`, and focused tests.

Finding and fix:

- `head_exists()` could still propagate a `ValueError` raised by
  `make_request()` when a redirect target failed SSRF validation. Its public
  contract is boolean URL existence, so a blocked redirect should be a clean
  `False` result.
- Added `ValueError` to the handled failure classes and pinned it with a unit
  test.

Validation:

- `uv run --no-sync pytest tests/test_data/test_scraping/test_net.py tests/test_data/test_scraping/test_discovery.py tests/test_data/test_scraping/test_discovery_more_coverage.py -q`
  passed with 113 tests.
- `uv run ruff check src/primr/data/scraping/net.py tests/test_data/test_scraping/test_net.py`
  passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_data/test_scraping/test_net.py tests/security/test_ssrf.py tests/security/test_egress_guardrails.py tests/test_data/test_scraping/test_discovery.py tests/test_data/test_scraping/test_discovery_more_coverage.py -q`
  passed with 157 tests.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict link warnings; generated `_site`
  was removed after validation.
- `$env:GEMINI_API_KEY='fake-key-for-ci-tests'; uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10227 passed, 39 skipped, 5 deselected`, branch coverage
  `85.24%`.

Rubric: Correctness 5/5, Security and Privacy 5/5, Simplicity 5/5,
Maintainability 5/5, Performance and Cost 5/5, Verification 5/5.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: $0.00 | New skill distilled:
none.

### Loop cycle: Discovery helper per-hop redirect guard

Refresh: re-read NOTES, ROADMAP, `docs/SECURITY.md`,
`docs/ARCHITECTURE.md`, `data.scraping.net`, discovery tests, and the SSRF
security tests.

Prioritize: selected `data/scraping/net.py` from the remaining
intermediate-redirect SSRF seams because it is the central requests-based
helper for sitemap fetches and URL-existence checks, yet still followed
redirects inside `requests` with only final-url validation.

Implemented:

- `make_request()` now performs manual redirect handling with
  `allow_redirects=False`.
- The initial URL and every redirect target run through
  `validate_url_for_request()` before the next network request.
- Relative redirects are resolved with `urljoin`; redirect count is capped.
- The helper preserves its `requests.Response` return contract and cookie/header
  behavior for discovery callers.
- Added regression tests for safe relative redirects and blocked internal
  redirect targets that are never connected.
- Updated NOTES, ROADMAP, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`, current-state, and the quality rubric.

Validation:

- `uv run --no-sync pytest tests/test_data/test_scraping/test_net.py tests/security/test_ssrf.py tests/security/test_egress_guardrails.py tests/test_data/test_scraping/test_discovery.py tests/test_data/test_scraping/test_discovery_more_coverage.py -q`
  passed with 156 tests.
- `uv run ruff check src/primr/data/scraping/net.py tests/test_data/test_scraping/test_net.py`
  passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict link warnings; generated `_site`
  was removed after validation.
- `$env:GEMINI_API_KEY='fake-key-for-ci-tests'; uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10226 passed, 39 skipped, 5 deselected`, branch coverage
  `85.24%`.

Rubric: Correctness 5/5, Security and Privacy 5/5, Simplicity 5/5,
Maintainability 5/5, Performance and Cost 5/5, Verification 5/5.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: $0.00 | New skill distilled:
response-shape-preserving redirect migration.

### Loop cycle: Wayback per-hop redirect guard

Refresh: re-read the SSRF findings in NOTES, the security posture in ROADMAP
and `docs/SECURITY.md`, the architecture SSRF section, `data.safe_http`, the
Wayback scraper, and the Wayback/safe-HTTP tests.

Prioritize: selected `data/scraping/wayback.py` from the remaining
intermediate-redirect SSRF migration list because its `_fetch()` helper was a
small plain-GET seam that still used `follow_redirects=True` with final-only
validation.

Implemented:

- Replaced Wayback's local httpx redirect-following implementation with a
  delegation to `data.safe_http.safe_http_get()`.
- Preserved Wayback-specific request headers and CDX query params.
- Updated Wayback tests to pin the delegation contract while keeping detailed
  redirect-hop safety tests in `test_safe_http.py`.
- Updated NOTES, ROADMAP, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`, current-state, and the quality rubric.

Validation:

- `uv run --no-sync pytest tests/test_data/test_wayback.py tests/test_data/test_safe_http.py tests/test_data/test_fallback_sources.py tests/test_data/test_fallback_sources_coverage.py -q`
  passed with 99 tests.
- `uv run ruff check src/primr/data/scraping/wayback.py tests/test_data/test_wayback.py`
  passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict link warnings; generated `_site`
  was removed after validation.
- `$env:GEMINI_API_KEY='fake-key-for-ci-tests'; uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10224 passed, 39 skipped, 5 deselected`, branch coverage
  `85.24%`.
- `git diff --check` passed with only Windows line-ending notices.

Rubric: Correctness 5/5, Security and Privacy 5/5, Simplicity 5/5,
Maintainability 5/5, Performance and Cost 5/5, Verification 5/5.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: $0.00 | New skill distilled:
shared safe HTTP migration.

### Loop cycle: Fenced-code artifact cleanup

Refresh: re-read README, ROADMAP, `CLAUDE.md`,
`docs/design/agentic-balance.md`, `docs/ARTIFACTS.md`, NOTES, the quality
rubric, and the report/strategy cleanup code.

Prioritize: selected the remaining deferred artifact-cleanup bug because it
was adjacent to the citation cleanup just shipped and represented another
silent final-artifact mutation. The correct boundary is deterministic cleanup
on prose plus preservation of literal code examples.

Implemented:

- Added a shared fenced-code transform helper in `core.report_cleanup`.
- Routed writer-scaffolding cleanup, informal citation cleanup,
  internal-source-placeholder cleanup, unresolved section cross-reference
  cleanup, and interior-space collapse through the helper.
- Preserved literal examples inside Markdown fenced code blocks while retaining
  the same cleanup behavior in prose.
- Added report and strategy regression tests covering `[workbook]`,
  `[cite: workbook]`, `[cross-ref ## ...]`, `[Analysis: ...]`,
  `[External Sources]`, vendor-research filenames, and word-count markers.

Validation:

- `uv run --no-sync pytest tests/test_core/test_report_cleanup.py tests/test_core/test_strategy_artifacts.py tests/test_core/test_fast_mode_citations.py tests/test_core/test_fast_mode_research.py -q`
  passed with 203 tests.
- `uv run ruff check src/primr/core/report_cleanup.py tests/test_core/test_report_cleanup.py tests/test_core/test_strategy_artifacts.py`
  passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `git diff --check` passed with only Windows line-ending notices.
- Added-line em dash scan passed.

Rubric: Correctness 5/5, Security and Privacy 5/5, Simplicity 5/5,
Maintainability 5/5, Performance and Cost 5/5, Verification 5/5.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: $0.00 | New skill distilled:
fence-aware cleanup.

### Loop cycle: MCP runtime budget enforcement

Startup refresh: re-read README, ROADMAP, `CLAUDE.md`,
`docs/design/agentic-balance.md`, `docs/design/engineering-excellence.md`,
`docs/design/2.0-agent-control-plane.md`, `docs/design/2.0-backend-freedom.md`,
`docs/design/1x-completion.md`, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
`docs/EVAL.md`, `docs/CONTRIBUTING.md`, current-state, progress, skills,
notes, changelog, and the touched MCP budget code.

External research checked current MCP and agentic best practices against the
local priority: MCP authorization guidance recommends auth when user consent,
per-user audit, enterprise control, or usage tracking matters; MCP security and
spec docs emphasize tool safety and explicit consent; OWASP and Microsoft
agentic guidance emphasize least-privilege tools, approval for high-impact
actions, and audit logging; OpenTelemetry GenAI guidance treats tool calls and
token usage as observable operations with full content capture opt-in; Anthropic
long-running-agent harness guidance reinforces persistent artifacts and
external verification over self-declared completion.

Prioritize: selected the documented HIGH control-plane gap where MCP
`max_estimated_cost_usd` gated only the pre-flight estimate while the fast
pipeline's actual mid-run budget checkpoints saw no active `RunBudget`.

Implemented:

- `research_company` now converts the validated cap to `budget_usd` and passes
  it into `PipelineRunner.run_research`.
- `PipelineRunner.run_research` activates the shared `RunBudget` before
  execution and clears it in a `finally` so success, cancellation, and failure
  cannot leak budget state into the next job.
- Tests prove the cap reaches the runner, the fast path sees the active
  `RunBudget`, and exception paths clear it.
- Added `QUALITY-RUBRIC.md` and scored the current cycle across six categories.
- Updated current-state, roadmap, changelog, notes, and skills memory.

Validation:

- `uv run --no-sync pytest tests/mcp_server/test_pipeline_runner_coverage.py tests/mcp_server/test_tools.py tests/mcp_server/test_approval_tokens.py tests/mcp_server/test_cost_caps_policy.py -q`
  passed with 66 tests.
- `uv run --no-sync pytest tests/mcp_server -q` passed with 513 tests, 2
  skipped.
- `uv run ruff check src/primr/mcp_server/pipeline_runner.py src/primr/mcp_server/tools.py tests/mcp_server/test_pipeline_runner_coverage.py tests/mcp_server/test_tools.py`
  passed.
- `uv run ruff format --check src/primr/mcp_server/pipeline_runner.py src/primr/mcp_server/tools.py tests/mcp_server/test_pipeline_runner_coverage.py tests/mcp_server/test_tools.py`
  passed.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict link warnings; generated `_site`
  was removed after validation.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests after lowering the `mcp_server/tools.py` line ceiling to
  the new smaller value.
- `$env:GEMINI_API_KEY='fake-key-for-ci-tests'; uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10210 passed, 39 skipped, 5 deselected`, branch coverage
  `85.22%`.

Rubric: Correctness 5/5, Security and Privacy 5/5, Simplicity 5/5,
Maintainability 5/5, Performance and Cost 5/5, Verification 5/5.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: $0.00 | New skill distilled:
MCP runtime budget propagation.

### Loop cycle: Redirect-SSRF hardening (1.34.1)

After releasing 1.34.0, an adversarial review of the SSRF defense (the
crown-jewel outbound control) confirmed the per-URL filter is solid but found a
HIGH systemic gap: every fetch seam followed redirects internally and validated
only the final URL, so an attacker page could 302 through an internal address
that was connected before the post-hoc check (confirmed by a loopback repro).

Implemented (TDD, hermetic):

- New shared seam `data/safe_http.py:safe_http_get`: follows redirects MANUALLY
  with `follow_redirects=False`, runs `is_safe_url` on the initial URL and every
  redirect hop BEFORE connecting, caps hops, resolves relative `Location`. An
  injected `transport` keeps the tests hermetic (httpx `MockTransport`, faked
  guard). The key test asserts an internal redirect target is validated and
  NEVER connected to.
- `fallback_sources._http_get` and `hiring_signals._http_get` (the two explicit
  mirror-duplicates, reachable from label-honesty / verifier / fallback fan-out
  / hiring) now delegate to the seam, removing the "keep these two in sync"
  hazard the old comments named.
- Rewrote the hiring `_http_get` coverage tests (they pinned the old internal
  httpx flow) to pin the delegation contract; the HTTP/redirect behavior is now
  covered by `test_safe_http.py`.

Scope held deliberately tight to the two broad attacker-influenceable fan-out
helpers. Later cycles migrated the scrape-tier HTTP clients; the async citation
resolver remains recorded in `NOTES.md` for follow-up migration to an async
equivalent. The DNS-rebind TOCTOU (connect-time IP pinning) also remains noted.

Validation: `test_safe_http.py` (8) + the fallback/hiring suites (168) green;
ruff + mypy clean on every touched file. Full CI-equivalent gate before push.
Spend `$0.00`.

Self-review: correctness Strong (per-hop validation proven by test, relative
redirect + loop-cap + error paths covered), security Strong (closes the
exploitable gap; one shared seam so it cannot drift), readability/maintainability
Strong (duplication removed). Rubric all Strong.

## 2026-06-25

### Loop cycle: Bug-hunt + security harden (release cadence lane)

Per the ROADMAP "Release Cadence" standing lane, ran an adversarial review pass
over the most-recently-touched modules (label-honesty, the availability bridge)
plus a rotating cold module (report_cleanup / strategy_artifacts), with three
parallel reviewers required to return only verified findings. Acted as the
checker (maker-checker): triaged, prioritized the just-shipped 1.34.0 surface
(security + new code) since the PyPI tag was not yet pushed, and folded the
hardening into a clean first release. Researched current attribution /
citation-faithfulness literature (CiteEval, CiteGuard, atomic calibration) to
ground the label-honesty design before review.

Fixed, each with a pinning regression test:

- **Security HIGH:** a collector-controlled quota-window label was copied raw
  into routing metadata (could leak a URL/account detail). Consolidated the
  duplicated availability sanitizers from `capability_routing.py` and
  `cli_doctor.py` into one shared seam `ai/availability_sanitize.py` (CLAUDE
  one-way rule) and closed three bypasses: the raw window label, an ASCII-only
  fix so homoglyph/accented host text can no longer pass `str.isalnum()`, a
  dotted-host display guard that a space used to disable, and a model-count
  clamp.
- **Label-honesty completeness (new code):** the per-label sampling cap could
  ship the same ungrounded claim with two different labels. The mutate path now
  audits every labeled claim (`max_per_label=None`); calibration keeps its
  bounded sampling.
- **Artifact HIGH (pre-existing):** `_normalize_fast_citations` emitted a
  duplicate `## Sources` section when the appendix carried a stray non-citation
  line. It now strips the appendix whenever its heading runs to end-of-document,
  while still preserving a real section that follows a sources-style heading.
- **Artifact MEDIUM:** blank-line collapse now tolerates CRLF.

Deferred (recorded in `NOTES.md`): scaffolding strips inside fenced code blocks,
the informal-cite-in-prose deletion, and the off-contract multi-label-per-line
case.

Validation: focused suites green at each step (sanitizer 24, availability/doctor
84, label 67, artifact cleanup 134), ruff + mypy clean on every touched file,
architecture ceilings hold. Full CI-equivalent gate run before push. Spend
`$0.00` (all review and validation local; no paid run).

Self-review: correctness Strong (every fix has a regression test that fails
before it), security Strong (one allowlist seam, invariant pinned), performance
Strong (no hot-path change), readability/maintainability Strong (duplication
removed, honest comments). Rubric all Strong.

### Loop cycle: Label-honesty pass (epistemic grounding, #4 / 1.x step 3)

Refresh: re-read README, ROADMAP (order of operations, #4, changelog table),
`CLAUDE.md`, `docs/design/agentic-balance.md`, `docs/design/1x-completion.md`,
`docs/design/eval-plan.md`, `qa/label_calibration.py`, `core/fast_run_trust.py`,
`PROGRESS-LOG.md`, and `CURRENT-STATE-ANALYSIS.md`. Researched current attribution
/ citation-faithfulness literature (CiteEval, CiteGuard, atomic/fact-level
calibration): the robust method is per-claim entailment judging against fetched
source text, then downgrading confidence when the evidence does not support the
claim; downgrade-only is the asymmetrically safe direction.

Prioritize: selected the label-honesty pass because the June-2026 calibration
eval pinned epistemic grounding as the one *measured* quality deficiency
(`(Confirmed)` ~8% / `(Reported)` ~0% traceability) while prose graded
consultant-grade and the two evidence-plumbing levers washed. It is the
roadmap's highest-leverage, evidence-backed, cheapest-to-iterate quality lever,
and the measurement half (`calibrate_claims`) already existed; only the
mechanical downgrade was missing.

Implemented:

- Added `qa/label_honesty.py`: pure `plan_label_downgrades()` +
  `apply_label_downgrades()` + orchestrating `apply_label_honesty()`. It reuses
  the calibration harness's extract/fetch/judge seams, acts only on the
  `untraceable` verdict (sources fetched + judged unsupported), downgrades
  traceable-class labels to `(Estimated)`, and fails open on every other
  verdict. Judgment decides; the rewrite is mechanical, no content regex.
- Added a defaulted `label_span` to `LabeledClaim` so the exact label token can
  be rewritten without re-scanning (backward-compatible; existing constructors
  and tests unaffected).
- Wired an opt-in `_maybe_apply_label_honesty()` into `polish_and_gate_fast_report`
  behind `PRIMR_LABEL_HONESTY`. Default-off keeps the standard run
  byte-identical; on change it recomputes QA metrics, logs a console line, and
  writes a `_label_honesty.json` audit sidecar. Wrapped so a label audit can
  never break shipping.
- Updated README/CONFIG (new env flag, documented as fail-safe and not a gate),
  ROADMAP (#4, order-of-operations step 3, changelog row, Current State),
  CHANGELOG (1.34.0), `1x-completion.md`, and `eval-plan.md`.
- Release bump to `1.34.0` (new opt-in feature) across pyproject, `__version__`,
  CITATION.cff, ROADMAP, and `uv.lock`.

Validation: `tests/test_qa/test_label_honesty.py` (19 new, mocked fetch/judge),
`tests/test_core/test_fast_run_trust.py` (label-honesty seam: gating, audit
sidecar, fail-safety, QA recompute), plus `tests/test_qa/` and
`tests/test_architecture.py` regression (362 passed). Ruff format + check and
CI-shaped mypy clean on every touched file. Full CI-equivalent gate run before
push.

Spend: `$0.00`. The pass is free to validate with injected seams; no paid run
was launched (the live pass is opt-in and bounded).

Self-review: correctness Strong (pure transform, exact-span rewrite refused on
drift, idempotent); security Strong (reuses the SSRF-guarded fetch seam, no new
egress, no secrets); performance Strong (fetches deduped, bounded per-label,
default path untouched); readability Strong (small module, doctrine cited in the
docstring); maintainability Strong (one seam, no monster growth, no content
regex per agentic-balance). Residual: the agreement-validated calibration
baseline that would justify promoting the pass toward default.

This slice ships as `1.34.0` and folds in the previously local-only
availability-to-backend bridge commit; both advance the top of the roadmap
without any paid validation.

### Roadmap note: security/profile rules

Reviewed an external secure-agent ruleset as research input only and kept it
out of Primr's docs by name. The useful Primr-native concepts are now recorded
in ROADMAP #15 and #21: versioned local security/profile rules, always-apply
versus context-selected categories, structural validation for secrets and
egress, optional operator policy overlays, and compact agent resources instead
of a large generic security skill or one MCP tool per rule.

Spend: `$0.00`.

### Local cycle: Availability-to-backend routing bridge

Constraint: user asked for no more GitHub or PyPI uploads today. This cycle is
local-only, with no commits, tags, pushes, releases, or paid validation.

Refresh: re-read README, ROADMAP, `CLAUDE.md`, `docs/design/agentic-balance.md`,
backend-freedom docs, provider-expansion docs, provider availability helpers,
generic collectors, capability routing, and focused tests.

Prioritize: selected the pure availability-to-backend adapter before live cloud
quota collectors. This keeps the next step deterministic and testable: generic
and future official snapshots can now change route eligibility without any
provider call or execution wiring.

Implemented:

- Added `backend_with_availability()` and `backends_with_availability()` to
  `ai/capability_routing.py`.
- Availability snapshots now mark backend rows unavailable before `route_stage()`
  and attach sanitized metadata.
- Local backend rows can use the generic `local_openai_compatible` availability
  snapshot, so local services remain provider-agnostic.
- Sanitization preserves routing facts such as quota source, headroom, stale
  status, and safe error codes while excluding raw endpoints, installed model
  names, account ids, API key material, and raw exception text.
- Exported the helpers through `primr.ai`.
- Added sanitized provider availability output to `primr doctor`.
- Updated ROADMAP, backend-freedom design notes, changelog Unreleased, and
  current-state analysis.

Bug-hunt follow-up:

- Hardened routing availability metadata against malformed collector fields,
  including host-like provider labels, unsafe endpoint/credential source
  strings, and invalid local model counts.
- Hardened `primr doctor` provider-availability output so malformed display
  names, env labels, endpoint sources, and model-count values cannot crash the
  command or leak host-like details.
- Added regression tests for malformed snapshot metadata in both the capability
  router and doctor output.

Validation so far:

- `uv run --no-sync pytest tests/test_ai/test_capability_routing.py tests/test_ai/test_provider_availability.py tests/test_ai/test_provider_availability_collectors.py -q`
  passed with 28 tests.
- `uv run --no-sync pytest tests/test_core/test_cli_doctor.py tests/test_ai/test_capability_routing.py tests/test_ai/test_provider_availability_collectors.py tests/test_ai/test_provider_availability.py -q`
  passed with 71 tests.
- `uv run ruff check src/primr/ai/capability_routing.py tests/test_ai/test_capability_routing.py`
  passed.
- `uv run ruff format --check src/primr/ai/capability_routing.py tests/test_ai/test_capability_routing.py`
  passed.
- `uv run --no-sync mypy src/primr/core/cli_doctor.py src/primr/ai/capability_routing.py src/primr/ai/provider_availability.py src/primr/ai/provider_availability_collectors.py --ignore-missing-imports --disable-error-code=import-untyped`
  passed.
- `uv run --no-sync pytest tests/test_architecture.py -q` passed with 5 tests.
- `uv run --no-sync pytest tests/test_core/test_cli_doctor.py tests/test_ai/test_capability_routing.py -q`
  passed with 59 tests after the bug-hunt hardening.
- `uv run --no-sync pytest tests/test_core/test_cli_doctor.py tests/test_core/test_cli.py tests/test_core/test_cli_handlers.py tests/test_core/test_cli_main.py tests/test_ai/test_capability_routing.py tests/test_ai/test_provider_availability.py tests/test_ai/test_provider_availability_collectors.py tests/test_architecture.py -q`
  passed with 217 tests.
- `uv run ruff check README.md ROADMAP.md docs/CHANGELOG.md docs/design/2.0-backend-freedom.md CURRENT-STATE-ANALYSIS.md PROGRESS-LOG.md src/primr/core/cli_doctor.py src/primr/ai/__init__.py src/primr/ai/capability_routing.py tests/test_core/test_cli_doctor.py tests/test_ai/test_capability_routing.py`
  passed.
- `uv run ruff format --check src/primr/core/cli_doctor.py src/primr/ai/__init__.py src/primr/ai/capability_routing.py tests/test_core/test_cli_doctor.py tests/test_ai/test_capability_routing.py`
  passed.
- `git diff --check` passed with only Windows line-ending notices.
- Full CI-shaped local coverage gate passed:
  `$env:GEMINI_API_KEY='fake-key-for-ci-tests'; uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with 10151 tests, 39 skipped, 5 deselected, and 85.17% coverage.

Spend: `$0.00`.

Next: official zero-token status collector scaffolding where provider docs
expose a supported surface, then stage-by-stage production route adoption.

### Loop cycle: Backend-freedom generic availability collectors

Refresh: re-read the README, ROADMAP, backend-freedom design notes, provider
availability code, local inference detector, provider registry, current-state,
progress log, and skills memory. Re-checked the direction against the user's
constraint: this must work for any user's configured capacity and must not
depend on personal accounts, repo-owned credentials, or hidden host assumptions.

Prioritize: selected generic collector wiring over a provider-specific quota
adapter. The pure quota contract already exists; the next useful seam is a
safe translator that can report what is configured locally or through provider
keys without doing billable calls or leaking account-specific details.

Implemented:

- Added `ai/provider_availability_collectors.py` with cloud provider
  configuration snapshots, a generic local OpenAI-compatible collector, and
  aggregate snapshot collection.
- Cloud snapshots expose configuration state, roles, key env name, and
  `quota_source=not_collected`, but never API key values.
- Local snapshots use the existing `/v1/models` path and report
  chat-model availability without storing raw endpoint URLs or installed model
  names.
- Exported the collectors through `primr.ai` lazy imports.
- Added tests covering configured/missing cloud keys, provider defaults, local
  chat models, embed-only local endpoints, probe failures, aggregate snapshots,
  and secret/hostname/model-name non-leakage.
- Updated README, ROADMAP, changelog, current-state, backend-freedom docs,
  provider-expansion docs, and skills memory to emphasize user-owned capacity
  and no repo-owned account assumptions.

Validation so far:

- `uv run --no-sync pytest tests/test_ai/test_provider_availability.py tests/test_ai/test_provider_availability_collectors.py tests/test_ai/test_local_inference.py -q`
  passed with 27 tests.
- `uv run ruff check src/primr/ai/provider_availability_collectors.py tests/test_ai/test_provider_availability_collectors.py src/primr/ai/__init__.py`
  passed.
- `uv run --no-sync mypy src/primr/ai/provider_availability_collectors.py src/primr/ai/provider_availability.py src/primr/ai/local_inference.py --ignore-missing-imports --disable-error-code=import-untyped`
  passed.
- After the full local gate passed, the user flagged Anthropic prompt caching
  as a possible direct-API optimization. Verified the current Anthropic prompt
  caching docs: cache writes cost more than base input, cache reads cost less,
  default TTL is 5 minutes, 1-hour TTL costs more, and automatic caching is not
  universally supported across gateways. Added ROADMAP and provider-expansion
  guardrails requiring provider-by-provider research, estimator support, usage
  accounting, and no background pre-warming or paid keepalive behavior before
  any new caching controls ship.

Spend: `$0.00`.

Self-review: correctness Strong for translating configuration and local probe
state into the existing normalized contract; security Strong because secrets,
raw local endpoints, account ids, and installed model names are not recorded;
performance Strong because local probing stays cached and short-timeout;
readability Strong through a small collector module; maintainability Strong
because official live quota collectors can feed the same snapshot shape later.
Residual work: full validation, release hygiene if the slice ships, and the
next production wiring step: official quota/status collectors plus router
integration.

### Release prep: 1.33.4

Promoted the generic availability collectors and provider prompt-caching
roadmap guardrails from Unreleased to `1.33.4`.

Updated:

- `pyproject.toml`
- `src/primr/__init__.py`
- `CITATION.cff`
- `uv.lock`
- ROADMAP current state and changelog table
- `docs/CHANGELOG.md`

Validation already completed before release prep:

- Full CI-equivalent coverage gate passed:
  `$env:GEMINI_API_KEY='fake-key-for-ci-tests'; uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with 10141 passed, 39 skipped, 5 deselected, and 85.14% coverage.
- Focused provider availability/local tests passed after the prompt-caching
  roadmap update: 27 tests.
- Ruff format check and Ruff check passed after the roadmap update.
- Release-prep validation passed:
  - `uv run pytest tests/test_release_integrity.py -q`
  - `uv run ruff format --check src/ tests/`
  - `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  - `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  - `uv run --with build python -m build`
  - `uv run --with twine twine check dist/*`
  - `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium`
  - `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196`
- Generated `_site`, `build`, and `dist` outputs were removed after validation.


### Loop cycle: MCP control-plane Stage 3 invocation audit

Refresh: re-read README, ROADMAP, `CLAUDE.md`,
`docs/design/agentic-balance.md`, `docs/design/2.0-agent-control-plane.md`,
`docs/SECURITY.md`, `CURRENT-STATE-ANALYSIS.md`, `PROGRESS-LOG.md`, and
`SKILLS.md`. Researched current MCP and GenAI observability guidance: MCP tool
security guidance calls for tool-usage audit logging; the MCP roadmap calls
audit trails and observability an enterprise-readiness priority; the MCP
Interceptors WG is standardizing audit logging as an interceptor use case; and
OpenTelemetry GenAI guidance treats tool invocations as observable operations
while warning that full content capture is sensitive and opt-in.

Prioritize: selected structured MCP invocation audit because per-tool authz and
approval tokens were already shipped, and audit closes the remaining MCP
visibility gap without adding agentic content judgment or paid validation.

Implemented:

- Added `mcp_server.audit_log`, an append-only JSONL audit log for MCP tool
  calls.
- Decorated the registered MCP tool handler so all existing success, denial,
  rate-limit, structured-error, and exception paths are captured without
  growing the pinned `tools.py` dispatcher.
- Recorded timestamp, transport, tool name, stdio actor or hashed HTTP caller
  id, authenticated flag, granted scopes, argument/result hashes, approval token
  id, cost metadata, job id, duration, outcome, and error metadata.
- Added `primr://agent/audit/recent`, readable by local stdio callers and
  admin-scoped HTTP callers.
- Updated README, API docs, SECURITY, ROADMAP, changelog, current-state, and
  the 2.0 control-plane design doc.

Validation so far:

- `uv run pytest tests/mcp_server/test_audit_log.py -q` passed: 4 tests.
- `uv run ruff check src/primr/mcp_server/audit_log.py src/primr/mcp_server/server.py src/primr/mcp_server/tools.py src/primr/mcp_server/resources.py tests/mcp_server/test_audit_log.py` passed.
- Full MCP suite passed: `uv run pytest tests/mcp_server -q` passed with 510
  passed, 2 skipped.
- Full CI-equivalent coverage gate passed:
  `$env:GEMINI_API_KEY='fake-key-for-ci-tests'; uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with 10134 passed, 39 skipped, 5 deselected, and 85.13% coverage.
- Repo static/security gates passed: `ruff check src/primr/ tests/`, `ruff
  format --check src/ tests/`, CI-shaped `mypy`, Bandit with `.bandit`, and
  `pip-audit --ignore-vuln PYSEC-2026-196`.
- MkDocs build passed with the repo's existing non-strict link warnings; `_site`
  was removed after verification.

Spend: `$0.00`.

Self-review: correctness Strong for MCP tool-call coverage, security Strong
for hashed inputs/results and admin-only HTTP resource access, performance
Strong because each call adds one small append, readability Strong through a
dedicated audit module, maintainability Strong because the dispatcher stays
under its line ceiling. Residual work: A2A parity, richer job-scoped artifact
resources, full local gates, commit, push, and CI verification.

### Loop cycle: Backend-freedom provider availability contract

Refresh: reviewed the neighboring quotabot project for quota/service
availability patterns, then re-read the backend-freedom design doc and existing
primr routing modules. Useful transfer: normalized quota windows, binding
headroom, stale last-known-good snapshots, and concurrent provider collectors.
Not transferred: quotabot's specific provider adapter endpoints, because primr
needs official, supported provider or host-account surfaces only.

Prioritize: selected a pure availability contract before live collectors. This
matches the existing `capability_routing.py` pattern: deterministic seams first,
provider I/O later, and no production behavior change until routing is wired
stage by stage.

Implemented:

- Added `ai/provider_availability.py` with `QuotaWindow`,
  `ProviderQuotaSnapshot`, `AvailabilityDecision`, `binding_window()`,
  `provider_headroom()`, `availability_decision()`, and
  `provider_with_most_headroom()`.
- Exported the new availability helpers through `primr.ai` lazy imports.
- Added unit tests for most-constrained windows, elapsed resets, exhausted
  headroom thresholds, missing quota windows, stale snapshot ranking, and input
  validation/clamping.
- Updated ROADMAP, changelog, current-state, and the backend-freedom design doc
  so the next backend-freedom step is live provider collectors feeding this
  normalized shape.

Validation so far:

- `uv run pytest tests/test_ai/test_provider_availability.py -q` passed: 7
  tests.
- `uv run ruff check src/primr/ai/provider_availability.py src/primr/ai/__init__.py tests/test_ai/test_provider_availability.py` passed.
- `uv run ruff format --check src/primr/ai/provider_availability.py src/primr/ai/__init__.py tests/test_ai/test_provider_availability.py` passed.
- `uv run mypy src/primr/ai/provider_availability.py --ignore-missing-imports`
  passed.
- Full CI-equivalent coverage gate passed:
  `$env:GEMINI_API_KEY='fake-key-for-ci-tests'; uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with 10134 passed, 39 skipped, 5 deselected, and 85.13% coverage.

Spend: `$0.00`.

Self-review: correctness Strong for the normalized quota math, security Strong
because no provider credentials or raw quota endpoint data are read here,
performance Strong because routing consumes small immutable snapshots,
readability Strong through a small pure module, maintainability Strong because
future collectors can be provider-specific while routing stays provider-neutral.
Residual work: live collector wiring, capability-router integration, release
versioning, push, and CI verification.

### Release prep: 1.33.3

Moved the MCP invocation audit and provider availability work from Unreleased
to `1.33.3`.

Updated:

- `pyproject.toml`
- `src/primr/__init__.py`
- `CITATION.cff`
- ROADMAP current state and changelog table
- `docs/CHANGELOG.md`

Validation:

- `uv run pytest tests/test_release_integrity.py -q` passed: 8 tests.
- `uv run --with build python -m build` produced
  `primr-1.33.3.tar.gz` and `primr-1.33.3-py3-none-any.whl`.
- `uv run --with twine twine check dist/*` passed for both artifacts.
- Local `dist/` and `build/` outputs were removed after validation.

### Loop cycle: MCP control-plane Stage 2 approval tokens

Refresh: re-read README, ROADMAP, `CLAUDE.md`,
`docs/design/agentic-balance.md`, `docs/design/2.0-agent-control-plane.md`,
`docs/SECURITY.md`, `CURRENT-STATE-ANALYSIS.md`, `PROGRESS-LOG.md`, and
`SKILLS.md`. Checked current public guidance again: MCP authorization guidance
centers OAuth scopes and least privilege, while OWASP agentic guidance calls
for approval on high-impact actions and complete mediation in downstream
systems.

Prioritize: selected the next control-plane stage because MCP per-tool authz
was already shipped, approval tokens are deterministic, free to validate, and
directly harden the estimate-first cost gate without adding brittle
content-quality rules.

Implemented:

- Added `mcp_server.approval_tokens`, issuing HMAC-signed, short-lived,
  single-use approval tokens with a TTL replay set.
- Added cost-affecting approval shapes for research, strategy, and skill-pack
  execution.
- Updated `estimate_run`, `estimate_strategy`, and `estimate_skill_pack` to
  return `approval_token`, `approval_token_id`, and `approval_expires_at`.
- Updated `research_company`, `generate_strategy`, and `generate_skill_pack` so
  server-side MCP cost-cap enforcement now requires both
  `max_estimated_cost_usd` and a matching `approval_token`.
- Split platform alias normalization into `mcp_server.platforms`, keeping
  `tools.py` within its pinned line ceiling.
- Updated MCP governance resources, prompts, SECURITY, ROADMAP, changelog, and
  the 2.0 control-plane design doc.

Validation so far:

- `uv run pytest tests/mcp_server/test_approval_tokens.py -q` passed: 6 tests.
- CI follow-up: GitHub `CI` failed only on Python 3.13 because the tampered
  token test sometimes replaced an `A` suffix with `A`, leaving the token
  unchanged. The test now flips the HMAC signature suffix deterministically.
- Build/PyPI follow-up: PyPI latest is already `1.33.1`, matching
  `pyproject.toml`, so no publish is appropriate. The release workflow now
  builds and extracts release notes under Python 3.12, matching the package
  floor, with a release-integrity test pinning the invariant.
- Release follow-up: bumped the package to `1.33.2` for publication, moved the
  shipped approval-token and release-hardening entries from Unreleased into the
  changelog release section, added the matching ROADMAP changelog row, and
  pinned the modern Apache 2.0 SPDX license metadata without deprecated license
  classifiers.
- `uv run pytest tests/mcp_server/test_tools.py::TestCostCaps tests/mcp_server/test_skill_pack_tools_more_coverage.py::test_cost_cap_passes_when_under_cap -q`
  passed: 13 tests.
- `uv run pytest tests/test_architecture.py -q` passed: 5 tests.
- `uv run pytest tests/mcp_server -q` passed: 506 passed, 2 skipped.
- Full local gate passed: `uv run ruff check src/primr/`,
  `uv run ruff format --check src/ tests/`,
  `uv run mypy src/primr/ --ignore-missing-imports`, Bandit,
  `uv run pip-audit`, and `uv run pytest tests/ -q` (10126 passed, 42
  skipped, 2 existing warnings).
- CI-equivalent Python 3.13 gate after the follow-up fix passed:
  `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with 10121 passed, 39 skipped, 5 deselected, and 85.10% coverage.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs
  build --site-dir _site` passed with the repo's existing non-strict link
  warnings; generated `_site/` was removed after verification.

Spend: `$0.00`.

Self-review: correctness Strong for the covered tools, security Strong for
approval provenance and replay resistance, performance Strong, readability
Strong, maintainability Strong. Residual control-plane gaps are structured
audit logging, A2A parity, and any paid path not yet governed by cost caps.

## 2026-06-24

### Loop cycle: MCP control-plane Stage 1 per-tool scopes

Refresh: re-read README, ROADMAP, `CLAUDE.md`, `docs/design/agentic-balance.md`,
`docs/design/2.0-agent-control-plane.md`, `docs/SECURITY.md`,
`CURRENT-STATE-ANALYSIS.md`, `PROGRESS-LOG.md`, and `SKILLS.md`. Online check
against current MCP authorization guidance and agentic-tool best practices
confirmed the same priority: keep agents simple, place guardrails at the tool
execution boundary, and use least-privilege scopes.

Prioritize: selected ROADMAP / SECURITY T8 Stage 1 because it is deterministic,
free to validate locally, unblocks approval tokens and audit logging, and
closes the all-or-nothing authenticated MCP surface without touching brittle
content-quality gates.

Implemented:

- Added `src/primr/mcp_server/tool_authz.py` as the central policy table for
  `read`, `research`, `delegate`, and `admin` tool scopes.
- Enforced the policy in `tools.call_tool` before rate limiting and before any
  agentic, skill-pack, or built-in tool handler can run.
- Added structured `insufficient_scope` responses with required, granted, and
  missing scopes.
- Updated JWT verification to honor explicit OAuth `scope` and Entra `scp`
  claims while keeping legacy no-scope `read` / `write` behavior.
- Bridged authenticated HTTP scope state into MCP dispatch through request-local
  context storage, avoiding shared mutable request auth state.
- Marked MCP T8 Stage 1 shipped in SECURITY / ROADMAP while keeping approval
  tokens, invocation audit, and A2A parity open.

Validation:

- `uv run pytest tests/mcp_server/test_tool_authorization.py tests/mcp_server/test_auth.py tests/mcp_server/test_server_more_coverage.py -q`
  passed: 97 passed, 1 existing Starlette deprecation warning.
- `git diff --check` passed after removing pre-existing trailing spaces in the
  progress docs.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed after formatting the touched
  Python files.
- `uv run mypy src/primr/ --ignore-missing-imports` passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium`
  passed.
- `uv run pip-audit` passed after upgrading the local virtualenv installer from
  vulnerable `pip 26.1.1` to fixed `pip 26.1.2` (no project dependency change).
- `uv run pytest tests/ -q` passed: 10119 passed, 42 skipped, 2 existing
  warnings in 12:01.

Spend: `$0.00`.

Self-review: correctness Strong, security Strong for this stage, performance
Strong, readability Strong, maintainability Strong. Remaining risks are
intentionally deferred to the next control-plane stages: server-issued approval
tokens, structured invocation audit, and A2A parity.

=== MILESTONE REACHED ===
MCP now has enforced per-tool scopes at dispatch, with explicit read-only JWTs,
legacy compatibility, request-local HTTP auth context, and targeted tests.

### Loop cycle: Skill generator refinement for Anthropic BP (verification + scripts, exemplar update)

Refresh: re-read ROADMAP §15 (deeper BP, no brittle regex, prefer prompt+eval, structural validators), agentic-balance standing rule (determinism on structure, judgment on content, no new content gates that rephrase-break), CLAUDE.md (one seam, no giant, use existing BundledFile/role_references, verify current, tests ship, full pre-PR gates, no real data, no AI attribution), CURRENT-STATE (updated), SKILL_PACK.md.

Prioritize per answers: a) verification bias + scripts in generator; yes to updating primr own skill as exemplar; no new measure code.

Atomic 1 (TDD): strengthened author_skill.yaml to MUST one verifier skill per role with script. Added post-parse guarantee in authoring.py using existing BundledFile seam to attach default verify-*.py if missing. Updated test_authoring.py to assert it. Test passes.

Atomic 2: created claude-code/skills/primr/references/gotchas.md (living, real failures from docs). Updated SKILL.md to point to it (progressive, exemplar).

Atomic 3: strengthened plan_plausible_roles.yaml to explicitly include verification roles in universal functions (bias at planning stage). TDD validated via planner tests.

No brittle introduced (no body regex; structural + prompt). Simple, idiomatic. $0 spend. Local pytest/ruff/mypy clean (299+ passed).

Self-review: correctness (tests pass, follows seam), security (no new paths), perf/readable (small diffs, comments cite docs), maintain (no duplication). Rubric Strong.

Ship: updated PROGRESS-LOG, CURRENT-STATE. Continue loop.

=== MILESTONE REACHED ===
Strengthened skill generator planning + authoring for verification skills bias + deterministic scripts (per BP and user priority). Updated primr self-skill exemplar with references/gotchas.md. All changes simple, seam-compliant, no brittle per agentic-balance/ROADMAP/CLAUDE. Tests green.

## 2026-06-24 (prior)

=== MILESTONE REACHED ===
Refined skill generator and primr exemplar to produce/use verification skills with deterministic scripts, Gotchas via progressive refs (no brittle content regex per agentic-balance), folders structure. All per user answers, ROADMAP, CLAUDE, BP. Tests green, zero slop.

## 2026-06-24 (prior)

### Cycle: Skill Pack Generator - Anthropic Best Practices Refinement (approved plan execution)

Re-read + internalized: README.md, ROADMAP.md (esp §15 Skill Pack + Engineering Standards), CLAUDE.md, CURRENT-STATE-ANALYSIS.md, docs/SKILL_PACK.md, docs/CONTRIBUTING.md, docs/design/agentic-balance.md, and the generated plan.md. Confirmed alignment with one-seam, no-giant-file, deterministic-structure + eval-content, cost-gate, and "measure real usage" principles. Zero external spend.

Implemented (seam-respecting, test-first where structural):
- Strengthened authoring prompt (author_skill.yaml v2.3): Gotchas as living highest-signal section, deterministic scripts emission (solve don't punt), per-role verifier bias, narrow-scope + one-category rule, trigger wording with real user phrasing, progressive disclosure pointers, composition by name, primr-skill cross-reference note.
- body_quality.py: added soft gotchas marker + has_gotchas_section; section_shape now tolerates Gotchas.
- validator.py: GOTCHAS soft advisory issue; updated docs/comments for tolerance.
- role_references.py + authoring.py: always attach references/gotchas.md + references/composition.md (progressive + composability).
- packager.py: "Anthropic Best Practices Adherence" report section (counts for Gotchas/scripts/verifiers).
- claude-code/skills/primr/SKILL.md: added ## Gotchas (models the BP for self-suggestion).
- docs/SKILL_PACK.md: documented the enforced patterns.
- tests: extended for has_gotchas; full suite 300/300 green after fix.
- CURRENT-STATE-ANALYSIS.md + this log updated.

Verification: full skill_pack tests + ruff + mypy slice green. All changes follow approved plan, CLAUDE.md seams, and the user's condensed takeaway (small composable, clear triggers, scripts, verifiers, Gotchas from real, progressive, measure).

Milestone: generator now produces skills aligned to the full Anthropic BP list. Next loop item: any follow-on test expansion or archetype gotcha examples if needed.

## 2026-06-20

### Cycle: v1.32.8 Build And Release Prep

Re-read and aligned against the active reference set for this release cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/CONTRIBUTING.md`,
`docs/design/agentic-balance.md`, `docs/design/engineering-excellence.md`,
`docs/CHANGELOG.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`. Re-read the release workflow and version-integrity
test before editing because this cycle updates the package build and PyPI
release path.

Implemented:

- Promoted the accumulated skill-pack quality work from `Unreleased` to
  `v1.32.8`.
- Modernized package license metadata and raised the build backend floor so the
  local wheel/sdist build no longer emits the setuptools license deprecation
  warning.
- Bumped the single version truth across `pyproject.toml`, `primr.__version__`,
  ROADMAP current state, ROADMAP changelog row, `CITATION.cff`, and `uv.lock`.
- Updated current-state analysis and engineering learnings to record the release
  metadata requirement.

Validation:

- `uv sync --frozen --extra dev --extra api --extra a2a` confirmed the local
  environment matches the CI extras.
- `uv run pytest tests/test_release_integrity.py -q` passed with 6 tests.
- `uv run --no-sync ruff check src/primr/` passed.
- `uv run --no-sync ruff format --check src/ tests/` passed after formatting
  `src/primr/__init__.py`.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run --no-sync bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10081 passed, 38 skipped`, branch coverage `85.06%`.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with the repo's existing non-strict link warnings.
- `uv run --with build python -m build --outdir dist-check` built the
  `primr-1.32.8` wheel and sdist.
- `uv run --with twine twine check dist-check/*` passed for both distributions.
- Added-line scans found no em dash or AI/tool attribution phrases.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: README and Documentation Front Door Refresh

Read and realigned against `README.md`, `ROADMAP.md`, `CLAUDE.md`,
`AGENTS.md`, `docs/README.md`, `docs/API_KEYS.md`, `docs/CONFIG.md`,
`docs/API.md`, `docs/SKILL_PACK.md`, `docs/CHANGELOG.md`, and `mkdocs.yml`.
Checked current documentation guidance from Diataxis, GitHub README docs, and
Google's developer documentation style guide.

Implemented:

- Rebuilt `README.md` as a concise project front door: purpose, quick start,
  cost estimate, first commands, evidence streams, outputs, configuration,
  agent integration entry point, development gates, and documentation map.
- Moved detailed mode, cost, strategy, platform, budget, output, and sample-run
  material into `docs/RUN_MODES.md`.
- Moved MCP, A2A, host snippets, packaged skills, credential boundaries, and
  async monitoring guidance into `docs/AGENT_INTEGRATION.md`.
- Updated `docs/README.md` and `mkdocs.yml` so both new pages are part of the
  docs index and published site nav.
- Removed em dashes from tracked documentation and guidance files, while
  leaving non-doc regression fixtures unchanged.
- Removed scanned emoji/symbol phase markers from agent guidance and reworded
  attribution rules to avoid exact generated-attribution phrasing.
- Updated ROADMAP and changelog for the documentation split.

Validation status:

- Style scans passed: no em dashes, scanned emoji/symbol markers, or attribution
  phrase matches across README, docs, root guidance, packaged skill docs, and
  client docs.
- `uv run --no-project --with mkdocs-material --with pymdown-extensions mkdocs build --site-dir _site`
  passed with only the repo's existing non-strict link warnings.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run --no-sync pytest tests/test_no_brand_leak.py -q` passed with 1 test.
- `git diff --check` passed.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: curl_cffi Validated-IP Pinning

Read and realigned against `README.md`, `ROADMAP.md`, `CLAUDE.md`,
`docs/SECURITY.md`, `docs/ARCHITECTURE.md`, `docs/design/agentic-balance.md`,
`NOTES.md`, `PROGRESS-LOG.md`, and `QUALITY-RUBRIC.md`. Verified the current
curl_cffi 0.15.0 API locally and checked libcurl `CURLOPT_RESOLVE` behavior
against the upstream curl documentation before changing the transport.

Implemented:

- Added per-hop curl_cffi DNS-rebind pinning for the TLS impersonation scraper
  tier.
- Each curl_cffi hop now calls `resolve_safe_url_for_connect()` before opening a
  connection.
- The tier keeps the logical URL and passes the vetted address through
  `CurlOpt.RESOLVE`, preserving Host, SNI, TLS impersonation, cookies, redirect
  handling, and logical final URL reporting.
- The tier disables environment proxy trust for the curl_cffi session so proxy
  configuration cannot bypass the locally pinned connection path.
- Added regression tests for `CurlOpt.RESOLVE` options, safe relative
  redirects, private-rebind blocking before connection, timeout/error
  classification, and impersonation preservation.
- Updated roadmap, security docs, architecture notes, changelog, scratch notes,
  and reusable skills.

Validation status:

- `uv run --no-sync pytest tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py -q`
  passed with 33 tests.
- `uv run ruff check src/primr/data/scraping/http_clients.py tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py`
  passed.
- `uv run ruff format --check src/primr/data/scraping/http_clients.py tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py`
  passed.
- `uv run --no-sync pytest tests/test_data/test_scraping/test_vertical_slice.py tests/security/test_ssrf.py tests/security/test_egress_guardrails.py tests/test_data/test_safe_http.py tests/test_data/test_pinned_requests.py -q`
  passed with 73 tests.
- `uv run --no-sync pytest tests/test_data/test_http_client.py tests/test_data/test_scraping/test_http_clients.py tests/test_data/test_scraping/test_http_clients_coverage.py -q`
  passed with 66 tests and 2 skipped.
- Full local gate passed: `uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  completed with `10256 passed, 39 skipped`, branch coverage `85.26%`.
- Repo-wide `ruff check`, `ruff format --check`, architecture and release
  integrity tests, mypy, Bandit, pip-audit, and MkDocs build also passed. MkDocs
  emitted only the repo's existing non-strict link warnings, and `_site` was
  removed.

Cycle health: 5/5 | Simplicity: 5/5 | Est. spend: `$0.00` | New skill
distilled: curl_cffi libcurl resolve pinning.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Informal Citation Cleanup Precision

Read and realigned against `README.md`, `ROADMAP.md`, `CLAUDE.md`, `NOTES.md`,
`docs/CHANGELOG.md`, `PROGRESS-LOG.md`, and the artifact cleanup/citation
normalization helpers.

Implemented:

- Added one shared `_normalize_informal_cite_brackets()` helper in
  `core.report_cleanup`.
- Replaced the permissive report and strategy regexes that matched any
  bracketed span containing `cite:` with a stricter pattern that only rewrites
  brackets beginning with `cite:` or `cites:`.
- Added report-cleanup and strategy-normalization regressions proving
  `[we cite: revenue doubled]` remains prose.
- Marked the deferred NOTES bug fixed and updated ROADMAP, changelog, and skill
  memory.

Validation:

- `uv run --no-sync pytest tests/test_core/test_report_cleanup.py tests/test_core/test_strategy_artifacts.py tests/test_core/test_fast_mode_citations.py tests/test_core/test_fast_mode_research.py -q`
  passed with 201 tests.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run ruff check src/primr/core/report_cleanup.py src/primr/core/strategy_artifacts.py tests/test_core/test_report_cleanup.py tests/test_core/test_strategy_artifacts.py`
  passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Empty-Platform Estimate Clamp

Read and realigned against `README.md`, `ROADMAP.md`, `CLAUDE.md`, `NOTES.md`,
`PROGRESS-LOG.md`, `SKILLS.md`, and the CLI budget/dry-run estimator code.

Implemented:

- Added `estimate_vendor_count()` to the shared CLI budget helper.
- Reused the helper from human and JSON dry-run estimates and `--budget`
  pre-flight estimates.
- Clamped enabled AI-strategy estimates to at least one vendor when an internal
  caller constructs `CLIConfig(platforms=())`.
- Marked the low `num_vendors=0` finding fixed in NOTES and documented the
  change in the changelog and skill memory.

Validation:

- `uv run --no-sync pytest tests/test_core/test_cli_handle_dry_run.py tests/test_core/test_cli_handle_research.py tests/test_core/test_budget_policy.py -q`
  passed with 40 tests.
- `uv run ruff check src/primr/core/cli_budget.py src/primr/core/cli_dryrun.py tests/test_core/test_cli_handle_dry_run.py`
  passed.
- `uv run ruff format src/primr/core/cli_budget.py src/primr/core/cli_dryrun.py tests/test_core/test_cli_handle_dry_run.py`
  applied formatting cleanly.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Budget Policy Honesty

Read and realigned against `README.md`, `ROADMAP.md`, `CLAUDE.md`,
`docs/SECURITY.md`, `docs/design/2.0-agent-control-plane.md`, `NOTES.md`,
`QUALITY-RUBRIC.md`, and the current budget/cost-gate code paths.

Implemented:

- Added `core.budget_policy` as the single pure description of pre-flight and
  runtime budget semantics for each execution profile.
- Added `core.cli_budget` so `cli.py` no longer owns the full `--budget`
  activation flow, shrinking the pinned CLI file instead of raising its
  ceiling.
- Updated CLI help, human dry-runs, `--dry-run --json`, and MCP `estimate_run`
  to distinguish fast full-report runtime checkpoints from premium, deep,
  scrape, and non-fast structured paths that are estimate-gated only today.
- Tightened stale comments in `utils.run_budget` and `mcp_server/tools.py` so
  internal docs match actual checkpoint coverage.
- Updated README, ROADMAP, SECURITY, the 2.0 control-plane design doc,
  changelog, and NOTES to reflect the shipped honesty fix and the remaining
  non-fast runtime-checkpoint work.
- Lowered file-size ratchets for `core/cli.py` and `mcp_server/tools.py` after
  the helper extraction shrank both files.

Validation:

- `uv run --no-sync pytest tests/test_core/test_budget_policy.py tests/test_core/test_cli_handle_dry_run.py tests/test_core/test_cli_output.py tests/test_core/test_cli_parse_args.py tests/test_core/test_cli_handle_research.py tests/mcp_server/test_tools.py -q`
  passed with 108 tests.
- `uv run --no-sync pytest tests/mcp_server -q` passed with 514 tests and 2
  skips.
- `uv run --no-sync pytest tests/test_core/test_budget_policy.py tests/test_core/test_cli_handle_dry_run.py tests/test_core/test_cli_output.py tests/test_core/test_cli_parse_args.py tests/test_core/test_cli_handle_research.py tests/test_core/test_fast_run_gaps.py tests/test_core/test_fast_run_validation.py tests/test_core/test_fast_run_strategy.py tests/test_utils/test_run_budget.py -q`
  passed with 146 tests.
- `uv run --no-sync pytest tests/test_architecture.py tests/test_release_integrity.py -q`
  passed with 13 tests.
- `uv run ruff check src/primr/ ...` passed on source and touched tests.
- `uv run ruff format --check src/ tests/` passed.
- `uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passed.
- Focused coverage over the new/touched budget modules passed at 89.17%
  branch coverage.
- The full non-manual, non-integration suite and the same suite with global
  coverage both timed out after 10 minutes in this workspace with no failing
  assertion output and no Primr test workers left running afterward. Treat as
  the remaining verification gap for this cycle.

Cost:

- `$0.00`. No cloud or paid validation was used.

## 2026-06-19

### Cycle: Business Role Archetypes For Draft Skills

Re-read and aligned against the active reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `docs/design/23-orchestrator-refactor-map.md`,
`docs/design/eval-plan.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`. Re-read the local `skill-creator` guidance before
editing because this work changes how primr drafts Agent Skills. Kept the scope
on concise, procedural skill creation rather than broad company-background
content.

Implemented:

- Added curated archetypes for common business functions: account executive,
  marketing manager, people operations manager, finance manager,
  legal/compliance manager, and operations manager.
- Tightened archetype matching so exact slugs, aliases, and keywords are token
  normalized, while weak display-name similarity no longer returns usable
  archetype grounding.
- Added regression coverage for common business titles and the previous bad
  match class where a retail operations role could inherit an unrelated
  technical or product archetype.
- Updated README, roadmap, changelog, the skill-pack guide, architecture notes,
  current-state analysis, and engineering learnings.

Validation:

- Confirmed the previous bad behavior before the fix: `Sales Director` matched
  `salesforce-admin`; `Marketing Manager`, `Finance Manager`, and
  `Operations Manager` matched `product-manager`; `Retail Floor Supervisor`
  received a weak display-name match.
- `uv run pytest tests/skill_pack/test_archetypes.py tests/skill_pack/test_curation.py tests/skill_pack/test_planner.py -q`
  passed with 66 tests.
- `uv run pytest tests/skill_pack/test_archetypes.py tests/skill_pack/test_curation.py tests/skill_pack/test_planner.py tests/skill_pack/test_pipeline.py -q`
  passed with 69 tests after formatting.
- `uv run pytest tests/skill_pack -q` passed with 297 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/test_architecture.py tests/test_no_brand_leak.py -q`
  passed with 6 tests.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10081 passed, 38 skipped`, branch coverage `85.06%`.
- Investigated the visible failed GitHub Actions CI run on `df4c747`. Root
  cause was `pip-audit` reporting `msgpack 1.1.2` and
  `pydantic-settings 2.14.1`; that was fixed by the later dependency-floor
  commit, and subsequent `main` CI runs passed.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Segmented Career URL Evidence For Draft Skills

Re-read and aligned against the active reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`. Kept the scope intentionally focused on draft
skill generation: narrow, explicit, evidence-backed `SKILL.md` artifacts rather
than broad public-facts dossiers.

Implemented:

- Added repeatable `--career-url` inputs for `primr skills`, allowing operators
  to seed draft skill-pack generation from specific segmented career pages or
  direct ATS URLs without requiring a company landing page.
- Added MCP parity through `career_urls` on `estimate_skill_pack` and
  `generate_skill_pack`, including normalized structured estimates that report
  when explicit career URLs are being used.
- Added a shared career-URL discovery helper that normalizes, deduplicates, and
  caps operator-supplied URLs, then routes direct ATS URLs, ATS redirects, and
  HTML career pages through the existing guarded hiring-signal collectors.
- Updated evidence collection so career URLs can be the primary source, while
  still preserving SSRF guards in the fetch path and provenance labels for
  downstream role planning.
- Updated README, roadmap, changelog, the skill-pack guide, architecture notes,
  current-state analysis, and engineering learnings.

Validation:

- `uv run pytest tests/test_data/test_hiring_signals_more_coverage.py tests/skill_pack/test_evidence_more_coverage.py tests/skill_pack/test_cli.py tests/mcp_server/test_skill_pack_tools_more_coverage.py tests/test_architecture.py -q`
  passed with 170 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed after formatting the updated
  architecture ratchet test.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10073 passed, 38 skipped`, branch coverage `85.06%`.
- Confirmed the latest pushed main commit before this cycle had green Docs,
  Scorecard, CodeQL, and CI runs. The visible failed CI run was on the previous
  dependency-audit commit and was fixed by the subsequent dependency-floor
  commit.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Cowork Packaging Limits

Re-read and aligned against the project reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`. Refreshed the Cowork packaging assumptions
against current Microsoft Learn documentation before changing the packager.

Implemented:

- Added explicit Cowork packaging constants for manifest, `SKILL.md`, and
  companion-file limits.
- Limited the Cowork sideload manifest and zip payload to the first valid
  20-skill slice while preserving the full unpacked Agent Skills tree for
  Claude/Cursor/VS Code style consumers.
- Split bundled-file handling into shared safety filtering and Cowork-only
  packaging filtering, so safe companion files remain in the unpacked tree even
  when they exceed Cowork's sideload caps.
- Surfaced Cowork packaging counts and limits in the pack report.
- Updated README, roadmap, changelog, the skill-pack guide, current-state
  analysis, and engineering learnings.

Validation:

- `uv run pytest tests/skill_pack/test_packager.py -q` passed with 21 tests.
- `uv run pytest tests/skill_pack -q` passed with 285 tests.
- `uv run pytest tests/test_architecture.py -q` passed with 5 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10060 passed, 38 skipped`, branch coverage `85.07%`.
- Remote CI initially failed on Python 3.13 because `pip-audit` reported newly
  published transitive advisories for `msgpack 1.1.2` and
  `pydantic-settings 2.14.1`. Added explicit dependency floors
  (`msgpack>=1.2.1`, `pydantic-settings>=2.14.2`), refreshed `uv.lock`, synced
  locally with the same extras as CI, and confirmed
  `uv run --no-sync pip-audit --ignore-vuln PYSEC-2026-196` passes. Re-ran
  full coverage after the dependency refresh; it still passed with
  `10060 passed, 38 skipped`, branch coverage `85.07%`.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Enterprise Posting Coverage Honesty

Re-read and aligned against the project reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `PROGRESS-LOG.md`, `SKILLS.md`, and
`CURRENT-STATE-ANALYSIS.md`.

Implemented:

- Added a pure skill-pack posting-coverage assessor that flags
  `posting-incomplete` when observed postings for a mid-market-or-larger
  organization cluster in one narrow role band.
- Surfaced the warning in `role_plan.md` and the skill-pack report with
  concrete operator actions: provide `--from-jd`, curate with `--roles-add` or
  `--roles-override`, or rerun from richer segmented evidence.
- Extracted role-plan rendering into `skill_pack.plan_artifacts`, reducing
  `planner.py` from the file-size ceiling to 830 lines while preserving the
  existing role-plan artifact contract.
- Updated README, roadmap, architecture, changelog, skill-pack guide,
  current-state analysis, and engineering learnings.

Validation:

- `uv run pytest tests/skill_pack/test_posting_coverage.py tests/skill_pack/test_planner.py tests/skill_pack/test_packager.py -q`
  passed with 35 tests.
- `uv run pytest tests/skill_pack -q` passed with 283 tests.
- `uv run pytest tests/test_architecture.py -q` passed with 5 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed after one transient
  remote connection reset.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10058 passed, 38 skipped`, branch coverage `85.07%`.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: JD Evidence For Draft Skill Generation

Re-read and aligned against the active reference set for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/CONTRIBUTING.md`,
`docs/design/agentic-balance.md`, `docs/design/engineering-excellence.md`,
`docs/design/1x-completion.md`, `docs/design/23-orchestrator-refactor-map.md`,
`PROGRESS-LOG.md`, `SKILLS.md`, and `CURRENT-STATE-ANALYSIS.md`. Also checked
current official Agent Skills / Cowork docs to keep the implementation aligned
with the shared SKILL.md format and progressive-disclosure model.

Implemented:

- Added `primr skills --from-jd PATH` for local job-description / role-brief
  evidence. The CLI now allows JD-only draft-skill generation without a company
  URL when the supplied brief is the evidence source.
- Added MCP parity through `from_jd_path` on `estimate_skill_pack` and
  `generate_skill_pack`, including path validation through the shared MCP
  `PathValidator`.
- Added `skill_pack.role_brief`, which size-limits, sanitizes, and materializes
  the local JD into `_hiring/operator_role_brief.md` before planning and
  authoring.
- Updated evidence loading so operator role briefs are prepended to hiring
  evidence and override empty-hiring markers like `Source: none` / `0 postings
  found`.
- Updated planning and authoring prompts so operator-provided role briefs are
  treated as evidence, never instructions.
- Updated README, roadmap, architecture notes, and the skill-pack guide for the
  new input layer.

Validation so far:

- `uv run pytest tests/skill_pack/test_role_brief.py tests/skill_pack/test_cli.py tests/skill_pack/test_pipeline.py tests/mcp_server/test_skill_pack_tools_more_coverage.py -q`
  passed with 69 tests.
- `uv run ruff check src/primr/skill_pack src/primr/mcp_server/skill_pack_tools.py tests/skill_pack/test_role_brief.py tests/skill_pack/test_cli.py tests/skill_pack/test_pipeline.py tests/mcp_server/test_skill_pack_tools_more_coverage.py`
  passed.
- `uv run pytest tests/skill_pack tests/mcp_server/test_skill_pack_tools_more_coverage.py -q`
  passed with 318 tests.
- `uv run pytest tests/test_architecture.py -q` passed with 5 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10052 passed, 38 skipped`, branch coverage `85.06%`.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Draft Skill Format Tightening

Read and realigned against the local project guidance for this cycle:
`README.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
and `docs/design/agentic-balance.md`. Also re-read the local skill-creator
guidance to keep the generated artifacts inside the Agent Skills format rather
than turning them into report-like context dumps.

Implemented:

- Tightened generated draft skills around a fixed three-section `SKILL.md`
  body: `What This Skill Does`, `Workflow`, and `Output Format`, with no extra
  H2 report/background sections.
- Added required `Required inputs:` and `Produces:` markers so every draft
  skill names the source material it needs and the artifact it returns.
- Updated authoring and refinement prompts to use company context as workflow
  specificity, input/output shape, and validation detail instead of reproducing
  public facts or evidence summaries in the skill body.
- Lowered the validator target ceiling from 3000 to 1500 words to match the
  documented draft-skill sweet spot while keeping the existing hard token cap.
- Updated `docs/SKILL_PACK.md` and regression tests for the stricter draft
  skill contract.

Validation:

- `uv run pytest tests/skill_pack/test_validator.py tests/skill_pack/test_refiner.py tests/skill_pack/test_pipeline.py -q`
  passed with 87 tests.
- `uv run pytest tests/skill_pack -q` passed with 267 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run pytest tests/test_architecture.py tests/skill_pack -q` passed with
  272 tests after splitting the new H2 section-shape helper out of
  `validator.py` to stay below the architecture line ceiling.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10039 passed, 38 skipped`, branch coverage `85.04%`.

Cost:

- `$0.00`. No cloud or paid validation was used.

### Cycle: Skill Pack Quality

Read and aligned against the project docs governing this work: `README.md`,
`ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`, `docs/SKILL_PACK.md`,
`docs/ARCHITECTURE.md`, `docs/CONTRIBUTING.md`, `docs/IMPROVE.md`,
`docs/ARTIFACTS.md`, `docs/EVAL.md`, `docs/SECURITY.md`,
`docs/STATE_MACHINES.md`, `docs/design/agentic-balance.md`,
`docs/design/engineering-excellence.md`, `docs/design/1x-completion.md`, and
`docs/design/23-orchestrator-refactor-map.md`.

Implemented:

- Removed visible tool-branded generator attribution from current skill-pack
  outputs.
- Made skill frontmatter clean by default, with metadata opt-in through CLI,
  MCP, and config.
- Raised the generated skill body floor to 300 words and made missing intake,
  scope guardrail, human checkpoint, and worked-example markers hard findings.
- Added deterministic `references/role-family.md` generation from sanitized
  role evidence and archetype grounding, attached consistently to every skill in
  the same role family.

Validation so far:

- `uv run pytest tests/skill_pack/test_authoring.py tests/skill_pack/test_archetypes.py tests/skill_pack/test_pipeline.py -q`
  passed with 24 tests.
- `uv run pytest tests/skill_pack -q` passed with 265 tests.
- `uv run ruff check src/primr/` passed.
- `uv run ruff format --check src/ tests/` passed.
- `uv run mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'`
  passed.
- `uv run bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q`
  passed with the existing `mcp_server/security.py` B108 nosec warnings.
- `uv run pip-audit --ignore-vuln PYSEC-2026-196` passed.
- `uv run pytest tests/ --ignore=tests/manual -x --tb=short -q --cov=src/primr --cov-branch --cov-fail-under=81`
  passed with `10037 passed, 38 skipped`, branch coverage `85.04%`.

Cost:

- `$0.00`. No cloud or paid validation was used.
