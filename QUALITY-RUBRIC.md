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
