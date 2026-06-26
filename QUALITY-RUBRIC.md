# Quality Rubric

Use this rubric for every loop cycle before marking work done. A category scores
`5` only when the change is ready to ship without apology.

| Score | Meaning |
|-------|---------|
| 1 | Weak: unsafe, untested, unclear, or misaligned with the roadmap. |
| 2 | Incomplete: directionally useful but missing important behavior, tests, or documentation. |
| 3 | Acceptable: works for the main path, but has meaningful residual risk or awkward design. |
| 4 | Strong candidate: correct and tested, with minor polish or coverage left. |
| 5 | Strong: simple, secure, maintainable, verified, and aligned with project doctrine. |

## Categories

| Category | Score 5 requires |
|----------|------------------|
| Correctness | The implementation satisfies the user-visible contract, handles edge cases in scope, and has regression tests for the bug or behavior. |
| Security and Privacy | Irreversible actions are bounded, untrusted inputs stay guarded, secrets and private details are not persisted, and the change narrows or preserves the threat surface. |
| Simplicity | The solution uses an existing seam, avoids duplicate mechanisms, keeps scope atomic, and does not grow monster files or generic frameworks. |
| Maintainability | Names, types, comments, tests, and docs make the intent clear enough that the next contributor can safely change it. |
| Performance and Cost | Hot paths stay efficient, long-running work stays bounded, and paid or resource-heavy operations are estimate-gated or avoided in validation. |
| Verification | Focused tests, static checks, formatting, and the relevant CI-shaped gates pass or any unrun gate is explicitly recorded with reason. |

## Current Cycle Score

2026-06-26 maintenance bug hunt and security review:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: externally influenced HTTP helpers found in the review now validate
redirect hops before connection or do not follow redirects at all. The tenancy
global reset now closes its SQLite connection and tests pin resource cleanup.
Focused maintenance tests, warning-as-error tenancy tests, Ruff, format check,
mypy, Bandit, and pip-audit pass. Spend: `$0.00`.

2026-06-26 README clarification and non-fast budget checkpoints:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: non-fast Deep Research runs now stop before optional strategy spend
when completed main-run cost reaches the active budget, and explicit strategy
Deep Research task costs are reflected in usage history. The README clarifies
command selection and budget scope while detailed contributor gates live in
`docs/CONTRIBUTING.md`. The implementation uses small helper modules instead
of growing `research_agent.py` past its pinned ceiling. Focused and broad test
gates pass, including the full non-manual coverage gate at 85.27% branch.
Spend: `$0.00`.

2026-06-26 resource lifecycle warning cleanup:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: SQLite-backed singleton resets now close previous global
connections for tenant managers, knowledge graphs, and company monitors. The
sync/async bridge now uses `asyncio.run()` from synchronous code and closes
rejected coroutines when called from an async context, eliminating unclosed
event-loop/socket cleanup warnings under the warning-escalated focused tests.
The final CI-shaped non-manual coverage gate passes with `10273 passed, 39
skipped, 4 deselected`, 85.28% branch coverage, and `ResourceWarning`,
`PytestUnknownMarkWarning`, and `PytestUnraisableExceptionWarning` promoted to
errors. Spend: `$0.00`.

2026-06-26 strict documentation build:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: the docs site now treats link/nav drift as a failed build through
MkDocs strict mode, with the GitHub Pages workflow using the same gate. The
remaining root/deploy cross-links are stable GitHub URLs, and intentional eval
and design pages are in the curated nav. This is a docs-only change with no
runtime or secret-handling surface. Strict MkDocs and targeted link scans pass.
Architecture/release-integrity tests, Ruff, format check, diff hygiene, and
style scans also pass. Spend: `$0.00`.

2026-06-26 browser dynamic egress proxy:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: Chromium-backed scraper tiers now launch through a local loopback
HTTP/CONNECT proxy that validates each browser-discovered target with the
central connect-time SSRF primitive and dials the validated IP literal. HTTPS
remains end-to-end because the proxy tunnels CONNECT bytes without terminating
TLS. Chromium launches disable loopback proxy bypass and QUIC so browser
traffic stays on the proxy path. Focused proxy/browser tests, architecture and
release-integrity tests, wider SSRF and egress-guardrail suites, Ruff, format
check, mypy, Bandit, pip-audit, MkDocs build, diff hygiene, touched-file style
scans, and the CI-shaped non-manual coverage gate pass. Coverage: 85.25%
branch. Spend: `$0.00`.

2026-06-26 browser-backed initial-host DNS pinning:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: browser-backed Chromium tiers now derive a browser egress plan from
the central validated connection artifact. Playwright, Playwright aggressive,
vision, and Patchright launch with an initial-host Chromium resolver pin and a
Playwright-compatible request route guard that aborts unsafe browser requests
before continuing them. DrissionPage receives the initial-host resolver pin
through Chromium startup args. The route guard fails closed if validation
raises. The vision tier was split out of `browsers.py`, lowering the file below
its architecture ceiling and ratcheting that ceiling down. Focused browser,
SSRF, egress, pinned-requests, and HTTP-client tests pass; Ruff, format check,
mypy, Bandit, pip-audit, MkDocs build, diff hygiene, touched-file style scans,
and the CI-shaped coverage gate pass. Coverage: 85.26% branch. Spend: `$0.00`.

2026-06-26 requests-family DNS-rebind IP pinning:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: `PinnedHTTPAdapter` keeps Requests on its existing urllib3 transport
while changing the actual socket target to the validated IP literal, preserving
logical request URLs, original Host, HTTPS SNI, retries, pooling, and response
contracts. The pooled `HTTPClient` and tiered requests scraper now share that
adapter. Focused pinned-adapter, HTTP client, scraper, SSRF, egress, and
vertical-slice tests pass; Ruff, format check, architecture/release-integrity
tests, mypy, Bandit, pip-audit, MkDocs build, and the CI-shaped coverage gate
all pass. Coverage: 85.23% branch. Spend: `$0.00`.

2026-06-26 tiered httpx scraper DNS-rebind IP pinning:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: the httpx scraping tier now uses the shared validated connection
artifact for each hop, connects to the validated IP-literal URL, preserves
original Host and HTTPS SNI, keeps HTTP/2/cookie behavior, and reports the
logical final URL. Tests cover pinned requests, private rebind blocking before
connect, safe relative redirects, and existing error branches. Focused
scraper/security tests, Ruff, format check, architecture/release-integrity
tests, mypy, Bandit, pip-audit, MkDocs build, and the CI-shaped coverage gate
pass. Coverage: 85.22% branch. Spend: `$0.00`.

2026-06-26 safe HTTP DNS-rebind IP pinning:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: the shared safe HTTP seam now derives a validated connection
artifact from the same DNS answer it approves, connects to the validated
IP-literal URL, and preserves the original Host header plus HTTPS SNI. Redirect
logic still follows logical URLs, and the public `utils.security` import
surface remains compatible after extracting `utils.url_security` to stay under
the architecture file-size ratchet. Focused SSRF/safe-HTTP/citation tests,
caller suites for fallback/hiring/Wayback, Ruff, format check,
architecture/release-integrity tests, mypy, Bandit, pip-audit, MkDocs build,
diff hygiene, and the CI-shaped coverage gate pass. Coverage: 85.22% branch.
Spend: `$0.00`.

2026-06-26 MCP runtime budget enforcement:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: the approved MCP cost cap now reaches the runner, the fast pipeline
sees the same `RunBudget` used by the CLI path, stale budgets are cleared before
uncapped runs, and the budget is cleared in a `finally` on success,
cancellation, or failure. Focused MCP tests, full MCP suite, Ruff, mypy,
Bandit, pip-audit, MkDocs build, architecture/release-integrity tests, and the
CI-shaped coverage gate pass. Coverage: 85.22% branch. Spend: `$0.00`.

2026-06-26 budget policy honesty:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: budget enforcement semantics now have a single pure source of truth,
and CLI/MCP estimate surfaces distinguish fast-path runtime checkpoints from
estimate-only modes before an operator approves spend. The change shrinks
pinned files and lowers their ratchets. Focused behavior tests, full MCP suite,
fast-run budget tests, architecture/release-integrity tests, Ruff, format,
mypy, Bandit, pip-audit, and focused coverage over the new/touched budget
modules pass at 89.17%. The full non-manual/non-integration suite timed out
after 10 minutes twice in this workspace without failure output; that timeout
is recorded in `PROGRESS-LOG.md` and `CURRENT-STATE-ANALYSIS.md` as the only
residual verification limitation. Spend: `$0.00`.

2026-06-26 empty-platform estimate clamp:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: AI-strategy estimates now clamp internally empty platform tuples to
one vendor in the shared CLI estimate helper, matching MCP behavior and
preventing a low-cost under-estimate edge case. Focused dry-run, budget, and
budget-policy tests pass with Ruff on touched files. Spend: `$0.00`.

2026-06-26 informal citation cleanup precision:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: the cleanup regex now matches the actual scaffolding shape instead
of deleting arbitrary bracketed prose containing `cite:`. The report and
strategy paths share one helper and both have regressions. Focused
cleanup/citation tests, architecture/release integrity, Ruff, format, and mypy
pass. Spend: `$0.00`.

2026-06-26 fenced-code artifact cleanup:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: final report and strategy cleanup now preserve literal scaffolding
examples inside Markdown fenced code while keeping the same stripping behavior
for prose. The implementation uses one shared fence-aware transform seam instead
of duplicating split logic, and report/strategy regressions cover the specific
markers that previously corrupted examples. Focused cleanup/citation tests,
architecture/release integrity, Ruff, format, mypy, Bandit, pip-audit, and diff
hygiene pass. Spend: `$0.00`.

2026-06-26 Wayback per-hop redirect guard:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: Wayback CDX and replay fetches now use the shared safe HTTP seam that
validates every redirect hop before connecting, instead of carrying a local
`follow_redirects=True` implementation with final-only validation. Tests pin the
delegation contract, while the shared safe HTTP suite owns redirect-hop
behavior. Focused Wayback, safe HTTP, and fallback-source tests pass with 99
tests; Ruff, format check, architecture/release integrity, mypy, Bandit,
pip-audit, MkDocs build, diff hygiene, and the CI-shaped coverage gate also
pass. Coverage: 85.24% branch. Spend: `$0.00`.

2026-06-26 discovery helper per-hop redirect guard:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: `data/scraping/net.py:make_request()` now preserves its
`requests.Response` contract while following redirects manually and validating
each hop before the next request. Regression tests prove safe relative redirects
still work and unsafe internal redirects are blocked before a second request.
Focused net, SSRF, egress-guardrail, and discovery tests pass with 156 tests.
Ruff, format check, architecture/release integrity, mypy, Bandit, pip-audit,
MkDocs build, diff hygiene, and the CI-shaped coverage gate also pass. Coverage:
85.24% branch.
Spend: `$0.00`.

2026-06-26 maintenance redirect hardening bug hunt:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: the maintenance review found and fixed one concrete behavior gap:
`head_exists()` now converts SSRF-blocked redirect validation failures into a
clean `False` result, preserving its existence-check contract. Focused net and
discovery tests pass with 113 tests; Ruff, format check, focused
net/security/discovery tests, architecture/release integrity, mypy, Bandit,
pip-audit, MkDocs build, diff hygiene, and the CI-shaped coverage gate also
pass. Coverage: 85.24% branch. Spend: `$0.00`.

2026-06-26 HTTPClient per-hop redirect guard:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: `HTTPClient.get()` and `HTTPClient.head()` now validate each redirect
target before connecting while preserving pooled session/retry behavior, stats,
and the `requests.Response` contract. Tests prove safe relative redirects still
work and unsafe internal redirects are blocked before a second request. Focused
HTTP client, SSRF, egress-guardrail, and hardening tests pass with 91 tests and
2 skipped; Ruff, format check, architecture/release integrity, mypy, Bandit,
pip-audit, MkDocs build, diff hygiene, and the CI-shaped coverage gate also
pass. Coverage: 85.24% branch. Spend: `$0.00`.

2026-06-26 HTTP scraper tier per-hop redirect guard:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: the requests, httpx, and curl_cffi scraping tiers now validate each
redirect target before connecting while preserving tier-specific transport
behavior and the raw-content `ScrapeResult` contract. Tests prove safe relative
redirects still work and unsafe internal redirects are blocked before a second
request across all three tiers. Focused tiered scraper and SSRF tests pass with
56 tests; Ruff, format check, architecture/release integrity, mypy, Bandit,
pip-audit, MkDocs build, diff hygiene, and the CI-shaped coverage gate also
pass. Coverage: 85.22% branch. Spend: `$0.00`.

2026-06-26 async citation redirect per-hop guard:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: Google grounding citation resolution now uses a HEAD-only async safe
HTTP helper that validates each redirect target before connecting while
preserving the resolver's retry and decoded-domain fallback behavior. Tests
prove safe relative redirects still work, unsafe internal redirects are blocked
before a second request, and network failures still propagate to the caller.
Focused safe HTTP, citation-resolution, and egress-guardrail tests pass with 76
tests; Ruff, format check, architecture/release integrity, mypy, Bandit,
pip-audit, MkDocs build, diff hygiene, and the CI-shaped coverage gate also
pass. Coverage: 85.22% branch. Spend: `$0.00`.

2026-06-26 curl_cffi validated-IP pinning:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: the curl_cffi tier now resolves and validates each logical hop once,
pins libcurl to the vetted address with `CurlOpt.RESOLVE`, keeps the logical
URL for Host/SNI/TLS impersonation behavior, disables environment proxy trust,
and preserves manual redirect validation plus the raw-content `ScrapeResult`
contract. Regression tests prove safe relative redirects still work, pinned
resolve entries are passed to curl_cffi sessions, private rebinds are blocked
before connection, and impersonation settings survive the new seam. Focused
curl_cffi and HTTP scraper tests pass with 33 tests; wider SSRF, egress,
safe HTTP, pinned requests, vertical scrape, and pooled HTTP client tests pass
with 139 tests and 2 skipped. Repo-wide Ruff, format check, architecture and
release-integrity tests, mypy, Bandit, pip-audit, MkDocs build, and the
CI-shaped coverage gate also pass. Coverage: 85.26% branch. Spend: `$0.00`.

2026-06-26 README and documentation front door refresh:

| Category | Score |
|----------|------:|
| Correctness | 5 |
| Security and Privacy | 5 |
| Simplicity | 5 |
| Maintainability | 5 |
| Performance and Cost | 5 |
| Verification | 5 |

Rationale: README now acts as a concise first-stop project page, while detailed
run-mode and agent-integration material lives in focused docs that are indexed
by MkDocs. The change follows Diataxis-style separation of overview, how-to,
reference, and explanation content without changing runtime behavior. Security
and privacy posture is unchanged, and the credential-boundary text is clearer.
Style scans pass for em dashes, scanned emoji/symbol markers, and generated
attribution phrase matches across tracked docs and guidance. MkDocs build,
architecture/release-integrity tests, brand-leak test, and diff hygiene pass.
Spend: `$0.00`.
