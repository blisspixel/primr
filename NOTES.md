# Engineering Notes

Living scratchpad for findings worth fixing that are not yet scheduled. Keep
each item concrete enough to act on without re-deriving it. Remove an item when
it ships.

## Deferred bug-hunt findings (2026-06-25 adversarial sweep)

These were verified by adversarial review but are narrow / off-contract, so they
were deferred behind the HIGH/security fixes. They are real and should be fixed
when the surrounding code is next touched.

- **Scaffolding strips run inside fenced code blocks** (`core/report_cleanup.py`,
  the `[workbook]` / informal-cite / `[Analysis: ...]` / `[External Sources]`
  strips). The interior-space collapse is already fence-protected (it splits on
  ```` ``` ```` fences), but the earlier marker strips run over the whole string,
  so a literal scaffolding token shown *inside* a code-block example is silently
  deleted. Fix: apply the same fence-split protection to the marker strips, or
  run all strips through one fence-aware pass. Medium; only bites when a report
  embeds those literal tokens in a code block.
- **Informal-cite regex deletes bracketed prose containing `cite:`**
  (`report_cleanup.py` and the shared regex in `strategy_artifacts.py`):
  `\[([^\]]*cites?:\s*[^\]]+)\]` matches any bracketed span containing the
  substring `cite:`; when it has no digits, the whole bracket is removed, so
  prose like `[we cite: revenue doubled]` is silently deleted. Fix: only treat a
  bracket as an informal citation when it begins with a `cite`/`source` keyword,
  not merely contains `cite:`. Low/medium; requires a literal `cite:` inside
  prose brackets.

## SSRF: validated thing != connected thing (2026-06-25 security review)

The per-URL filter (`utils/security.is_safe_url`, numeric-host backstop,
IPv6-mapped/ULA/link-local/metadata handling) is verified solid. The two gaps
are architectural and worth a dedicated, well-tested cycle.

- **HIGH, intermediate-redirect SSRF (systemic). PARTIALLY FIXED in 1.34.1.**
  Every fetch seam set `follow_redirects=True` and validated only the FINAL url,
  so an attacker page could `302 -> http://127.0.0.1:...` (or `169.254.169.254`)
  and the internal hop was connected even though the final url was public
  (confirmed by repro). **Done:** new shared seam `data/safe_http.py:safe_http_get`
  follows redirects manually and runs `is_safe_url` on every hop before
  connecting; `fallback_sources._http_get` and `hiring_signals._http_get` (the
  two explicit mirror-duplicates, reachable from label-honesty / verifier /
  fallback fan-out / hiring) now delegate to it. **Remaining seams to migrate to
  the same helper:** `data/http_client.py`, `data/scraping/net.py`,
  `data/scraping/http_clients.py`, `data/scraping/wayback.py` (each may need a
  per-client variant), and `ai/citation_resolution.py` (async `HEAD`, narrowly
  gated to `vertexaisearch.cloud.google.com` so low-risk; needs an async
  variant of the helper).
- **MED/HIGH -- DNS-rebind TOCTOU.** `is_safe_url` resolves + validates IPs but
  returns the hostname; the client re-resolves at connect time, so a low-TTL
  attacker domain can answer public to the check and internal to the connect.
  Fix: resolve once, validate, connect to the validated IP literal with the
  hostname as SNI/Host (IP pinning). Harder (per-client transport work); after
  the redirect fix.

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

- **HIGH -- MCP runner sets no run budget.** `mcp_server/pipeline_runner.py` calls
  `perform_fast_research` without `set_run_budget`, so every
  `skip_stage_if_over_budget` checkpoint is a no-op on the networked MCP surface;
  `max_estimated_cost_usd` only gates the pre-flight estimate. Fix: have the MCP
  runner activate a run budget from the approved cap so actual spend is bounded
  on the fast path too. (Pairs with the SSRF/control-plane hardening.)
- **HIGH -- premium/deep/scrape/non-fast paths have no mid-run gate.** `--budget`
  is set for all modes but only `perform_fast_research` consults it.
  `perform_deep_research` and the structured fallback have zero budget refs, and
  the `--budget` help implies enforcement that does not happen in premium mode.
  Fix: either add checkpoints to those paths or make the help/pre-flight honest
  that premium is estimate-gated only.
- **MEDIUM -- `CostGuardHook` is inert.** Nothing calls `record_cost` against a
  live hook and the orchestrator passes no `estimated_cost_usd`, so `spent`
  stays 0 and it never blocks. Either wire real per-subagent cost in or drop the
  dead hook.
- **MEDIUM -- Phase 3/4 (workbook+writing, the biggest spend) has no checkpoint**
  between the Phase-2 and Phase-5 gates, so `--budget` bounds only optional
  stages, not total spend. Partly by design (writing is the deliverable); at
  minimum document it honestly.
- **LOW -- `num_vendors=0` zeroes AI-strategy cost** in the pre-flight estimate
  (`cli.py` uses `len(config.cloud_vendors)`); clamp to >=1 when
  `include_ai_strategy` so an empty-platform path cannot under-estimate.

## Multi-label-per-line (label_honesty / label_calibration)

`extract_labeled_claims` uses `_LABEL_RE.search` (first label per line), so a
line carrying two confidence labels yields one claim. Off-contract (the writer
emits one label per line), so left as-is; revisit only if the writer contract
changes.
