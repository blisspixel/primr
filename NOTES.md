# Engineering Notes

Living scratchpad for findings worth fixing that are not yet scheduled. Keep
each item concrete enough to act on without re-deriving it. Remove an item when
it ships.

## Deferred bug-hunt findings (2026-06-25 adversarial sweep)

These were verified by adversarial review but are narrow / off-contract, so they
were deferred behind the HIGH/security fixes. They are real and should be fixed
when the surrounding code is next touched.

- **FIXED in local Unreleased -- scaffolding strips run inside fenced code
  blocks.** Final report and strategy cleanup now run writer-scaffolding strips,
  informal-cite cleanup, internal-source-placeholder cleanup, and unresolved
  section cross-reference cleanup only outside Markdown fenced code blocks. A
  literal marker shown inside a code example is preserved while the same marker
  in prose is still removed.
- **FIXED in local Unreleased -- informal-cite regex deletes bracketed prose
  containing `cite:`.** `report_cleanup.py` and `strategy_artifacts.py` now use
  one stricter helper that only rewrites brackets beginning with `cite:` or
  `cites:`, preserving prose like `[we cite: revenue doubled]`.

## Resource lifecycle warnings (2026-06-26 maintenance)

- **FIXED in local Unreleased -- SQLite-backed singleton resets leaked
  connections.** `reset_tenant_manager()`, `reset_knowledge_graph()`, and
  `reset_company_monitor()` now close existing global instances before clearing
  them. Their tests use yielding fixtures so per-test instances close in
  teardown.
- **FIXED in local Unreleased -- sync/async bridge left loop cleanup to GC.**
  `run_sync()` now uses `asyncio.run()` from synchronous code and closes
  rejected coroutine objects when called inside an async context. Focused tests
  promote `ResourceWarning` and pytest unraisable warnings to errors.
- The remaining full-suite warning is an external Starlette/httpx2 deprecation
  emitted by FastAPI's `TestClient` import, not a local resource leak.

## SSRF: validated thing != connected thing (2026-06-25 security review)

The per-URL filter (`utils/security.is_safe_url`, numeric-host backstop,
IPv6-mapped/ULA/link-local/metadata handling) is verified solid. The two gaps
are architectural and worth a dedicated, well-tested cycle.

- **FIXED in local Unreleased -- intermediate-redirect SSRF (systemic).**
  Every fetch seam set `follow_redirects=True` and validated only the FINAL url,
  so an attacker page could `302 -> http://127.0.0.1:...` (or `169.254.169.254`)
  and the internal hop was connected even though the final url was public
  (confirmed by repro). **Done:** new shared seam `data/safe_http.py:safe_http_get`
  follows redirects manually and runs `is_safe_url` on every hop before
  connecting; `fallback_sources._http_get` and `hiring_signals._http_get` (the
  two explicit mirror-duplicates, reachable from label-honesty / verifier /
  fallback fan-out / hiring) now delegate to it; `data/scraping/wayback.py`
  uses the same seam for CDX and replay fetches; `data/scraping/net.py` now
  validates every redirect hop manually while preserving its
  `requests.Response` return shape; `data/http_client.py` now validates every
  GET/HEAD redirect hop manually while preserving its pooled `requests.Session`
  behavior; `data/scraping/http_clients.py` now validates every redirect hop
  manually for the requests, httpx, and curl_cffi tiers while preserving each
  tier's transport behavior; `ai/citation_resolution.py` now resolves Google
  grounding redirects through `data/safe_http.py:async_safe_http_head()`, which
  validates the initial URL and each redirect target before connecting. The
  intermediate-redirect migration is complete.
- **PARTIALLY FIXED in local Unreleased -- DNS-rebind TOCTOU.**
  `is_safe_url` still returns only a boolean, but the shared safe HTTP seam now
  uses `resolve_safe_url_for_connect()` to resolve each hop once, validate every
  returned address, connect to the validated IP literal, and preserve the
  original Host header plus HTTPS SNI. This closes the check/connect DNS split
  for fallback, hiring, Wayback CDX/replay, and citation HEAD fetches.
  **Also done:** `scrape_with_httpx()` now uses the same resolver artifact for
  each hop, preserving HTTP/2, cookies, Host, HTTPS SNI, and the logical final
  URL. **Also done:** requests-family egress now uses
  `data.pinned_requests.PinnedHTTPAdapter`; pooled `HTTPClient` calls and the
  tiered requests scraper connect through urllib3 to the validated IP literal
  while preserving retries, pooling, Host, SNI, and response/result contracts.
  **Also done:** the curl_cffi scraper tier now resolves and validates each hop
  once, passes the vetted address to libcurl with `CurlOpt.RESOLVE`, disables
  environment proxy trust, and keeps the logical URL so TLS impersonation,
  Host, SNI, cookies, redirects, and final URL reporting stay intact.
  **Also done:** browser-backed Chromium seams now derive a browser egress plan
  from `resolve_safe_url_for_connect()`. Playwright, Playwright aggressive,
  vision, and Patchright launch Chromium with `--host-resolver-rules` for the
  validated initial hostname, block service workers where the Playwright API
  supports it, and install a route guard that aborts unsafe browser requests
  before continuing them. DrissionPage receives the same initial-host Chromium
  resolver pin.
  **Also done:** browser-backed Chromium tiers now launch through a local
  loopback egress proxy. The proxy validates each HTTP request or HTTPS CONNECT
  target with `resolve_safe_url_for_connect()`, dials the validated IP literal,
  and tunnels TLS without terminating it, so browser-discovered public redirect
  and subresource hosts are dynamically pinned too. Chromium is launched with a
  proxy bypass rule that keeps loopback targets inside the proxy path and with
  QUIC disabled to avoid UDP bypass.
  **Remaining:** no known DNS-rebind TOCTOU seams in the tracked scraper fetch
  paths. Future browser protocol additions must preserve the local proxy
  invariant or add equivalent connect-time pinning.

## Flaky: cross-directory test pollution hits a browser import test

`tests/test_data/test_scraping/test_browsers.py::TestScrapeWithDrissionpage::test_handles_import_error`
intermittently fails in the FULL suite (`-x` stops there) but passes in
isolation and when its whole directory runs (669 passed). So an earlier
directory leaves global state that breaks it. Prime suspects are tests that
patch import machinery and may not fully restore it: `test_ai/` runs before
`test_data/` and several files there patch `builtins.__import__` /
`sys.modules` (`test_preflight_coverage.py`, `test_anthropic_provider.py`,
`test_providers_openai_compatible_coverage.py`), plus the Playwright
`test_handles_import_error` in `test_browsers.py:236` does a raw
`sys.modules.pop` + `patch("builtins.__import__")`. Pre-existing (CI green on
the same test); not caused by the 1.34.0 work. Fix: bisect to the leaking test
and make it hermetic (restore `sys.modules`/`__import__` in a `finally`, or use
`monkeypatch`), then pin with a co-located ordering test. Until then it is a
known intermittent.

## Budget / cost-gate enforcement gaps (2026-06-25 review)

The `RunBudget` primitive, the MCP pre-flight cap, and approval-token binding are
verified correct. The gap is that mid-run *actual-spend* enforcement is wired
into only the CLI fast path. Triaged for upcoming cycles:

- **FIXED in local Unreleased -- MCP runner sets no run budget.**
  `research_company` now passes the approved `max_estimated_cost_usd` into
  `PipelineRunner`, which activates `set_run_budget()` for the fast path and
  clears it in a `finally`.
- **HIGH -- premium/deep/scrape/non-fast paths have limited mid-run gates.**
  PARTIALLY FIXED in local Unreleased. `--budget` is set for all modes,
  `perform_fast_research` consults it at optional fast stages, and
  `perform_deep_research` now consults it before and between optional strategy
  documents after the required Deep Research task completes. **Done:** CLI help,
  human dry-runs, `--dry-run --json`, MCP `estimate_run`, README, ROADMAP, and
  SECURITY state the selected runtime behavior without overclaiming mid-flight
  control. **Remaining:** scrape is still estimate-gated only; required Deep
  Research tasks and structured fallback work still cannot be stopped after
  they start because no live cost state is exposed at that boundary.
- **MEDIUM -- `CostGuardHook` is inert.** Nothing calls `record_cost` against a
  live hook and the orchestrator passes no `estimated_cost_usd`, so `spent`
  stays 0 and it never blocks. Either wire real per-subagent cost in or drop the
  dead hook.
- **MEDIUM -- Phase 3/4 (workbook+writing, the biggest spend) has no checkpoint**
  between the Phase-2 and Phase-5 gates, so `--budget` bounds only optional
  stages, not total spend. Partly by design (writing is the deliverable); at
  minimum document it honestly.
- **FIXED in local Unreleased -- `num_vendors=0` zeroes AI-strategy cost.**
  CLI dry-run and `--budget` pre-flight estimates now clamp enabled AI-strategy
  runs to at least one vendor, even when an internal caller constructs
  `CLIConfig(platforms=())`.

## Multi-label-per-line (label_honesty / label_calibration)

`extract_labeled_claims` uses `_LABEL_RE.search` (first label per line), so a
line carrying two confidence labels yields one claim. Off-contract (the writer
emits one label per line), so left as-is; revisit only if the writer contract
changes.
