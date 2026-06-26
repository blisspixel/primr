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

- **HIGH, NEXT CYCLE -- intermediate-redirect SSRF (systemic).** Every fetch
  seam sets `follow_redirects=True`/`allow_redirects=True` and validates only the
  FINAL url. httpx/requests connect to each intermediate redirect target before
  primr re-validates, so an attacker page can `302 -> http://127.0.0.1:...` (or
  `169.254.169.254`) and the internal hop is connected even though the final url
  is public. Confirmed by repro (loopback server recorded the internal hit).
  Affected: `data/fallback_sources.py:_http_get`, `data/hiring_signals.py` (two
  spots), `data/http_client.py`, `data/scraping/net.py`,
  `data/scraping/http_clients.py`, `data/scraping/wayback.py`. Fix: a single
  shared helper that disables auto-redirects and follows manually, calling
  `is_safe_url` on each hop's `Location` before connecting (cap hops); migrate
  the seams to it (one-seam, kills the "mirror changes in N files" comment).
- **MED/HIGH -- DNS-rebind TOCTOU.** `is_safe_url` resolves + validates IPs but
  returns the hostname; the client re-resolves at connect time, so a low-TTL
  attacker domain can answer public to the check and internal to the connect.
  Fix: resolve once, validate, connect to the validated IP literal with the
  hostname as SNI/Host (IP pinning). Harder (per-client transport work); after
  the redirect fix.

## Multi-label-per-line (label_honesty / label_calibration)

`extract_labeled_claims` uses `_LABEL_RE.search` (first label per line), so a
line carrying two confidence labels yields one claim. Off-contract (the writer
emits one label per line), so left as-is; revisit only if the writer contract
changes.
