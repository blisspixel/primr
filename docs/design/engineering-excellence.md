# Engineering Excellence: Enforcing the One Way (Anti-Slop)

Status: PROPOSED — additive to the
[Engineering Standards & Toolchain](../../ROADMAP.md#engineering-standards--toolchain)
section. That section already owns the deep ratchets (mypy strict expansion,
per-module coverage, parse-don't-validate, mutation testing, supply-chain
hardening). This doc owns the **net-new, enforcement-and-currency** layer:
keeping a largely AI-assisted codebase tidy, consistent, and current.

## Motivation

The 2026 literature on AI-assisted development is consistent and unflattering:
AI-assisted code ships roughly **2× the critical vulnerabilities** of
human-written code; about **a third of those flaws originate in the model**
(replicated insecure training patterns); only ~35% of AI-generated backend
code is both secure and correct; and the dominant maintainability failure is
*near-miss syndrome* — plausible code with subtle bugs, inconsistent naming,
**duplicate logic, no coherent architecture**, and **outdated APIs /
hallucinated packages**. Sources: OX Security; Kiuwan; DevOps.com; arXiv
2409.19182 ("AI-Generated Code Considered Harmful"); OWASP Top 10 2025 (new
A03 Software Supply Chain Failures, A10 Mishandling Exceptional Conditions).

The agreed mitigation is exactly primr's posture: **treat generated code as
hazardous until reviewed, statically scanned, and tested, behind hard
policy-as-code gates.** primr already has the gates (Ruff / mypy-ratchet /
bandit / pip-audit / Trivy / SBOM / SLSA / coverage-ratchet / Hypothesis).
What it lacks is (a) a contract that *steers the generator* before code is
written, (b) *enforcement* of the single seams it has by convention, and
(c) a currency cadence for the dev toolchain itself. This doc adds those.

**Decision principle:** make the one correct way the *easy and enforced* way;
make slop fail a gate, not a review comment.

## Where primr already stands (don't re-litigate)

Measured, not assumed. Already in place and load-bearing — see the ROADMAP
standards section for detail: uv.lock + `uv sync --frozen` + 3.12/3.13/3.14
hard matrix; Ruff (14 rule groups, line-length 100, `C901` budget 25); mypy
incremental strict allowlist; bandit + pip-audit + Trivy **hard** gates;
CycloneDX SBOM + SLSA provenance + OIDC publish per release; 81% branch
coverage ratchet (rise-only); Hypothesis property + stateful tests; SSRF guard
on every egress; secret-redaction log filter; injection red-team corpus;
scoped ATLAS threat model; single-version-truth test; no-real-company-data
rule; `docs/design/` ADR convention. This is already top-decile. The work
below is the last mile, not a turnaround.

## Net-new workstreams

### 1. `CLAUDE.md` — the anti-slop contract  (free)

A dev-facing spec (distinct from the user-facing `AGENTS.md`, which is about
*running* primr) that every coding agent and human reads before contributing.
The 2026 standard (agents.md; spec-driven development) is that the spec is the
*constraint the generator is held to*, not documentation written after.
Contents:

- **The single seams, named, with their allowed exceptions:** async via
  `utils.async_utils.run_sync` (not raw `asyncio.run`); outbound HTTP via the
  `data.http_client` / scraping-tier seams (the 5 clients are a *closed,
  documented* set — browser → curl_cffi → httpx → requests → urllib — not an
  open invitation); config via `config/`; console via `utils.console`; logging
  via `utils.logging_config.get_logger`; JSON via stdlib `json` only.
- **File-size rule:** no new file ships over ~800 lines without a split plan;
  no existing file may grow (see workstream 3).
- **Currency rule:** before using a library/API, verify the *current* version
  and signature (the hallucinated-package / stale-API guard) — never trust the
  model's training memory for versions, deprecations, or model IDs.
- **Verb convention** (workstream 4) and the **no-real-company-data** rule.
- **Pre-PR checklist:** the local gate commands (already in CONTRIBUTING) plus
  "did this add a new way to do something that already has a seam?"

Validation: free — it is documentation that the fitness functions (workstream
2) then *enforce*, so it cannot rot into aspirational prose.

### 2. Architectural fitness functions  (free)

Turn the single seams from convention into a gate. Add `import-linter`
contracts (or, if a new dep is unwanted, a deterministic AST test in
`tests/`) that fail CI when:

- `asyncio.run(` / `get_event_loop(` appears outside `utils/async_utils.py`
  (the `run_sync` seam) and a small allowlist.
- `import httpx` / `import requests` / `import urllib` / `from curl_cffi`
  appears outside the documented HTTP-seam allowlist.
- a module imports across a forbidden layer boundary (e.g. `config/` importing
  from `core/`).

Start with the async and HTTP contracts (the two the audit flagged as having
4–5 coexisting patterns), allowlisting today's legitimate sites so the gate
locks the *current* set and blocks *new* drift. New-dependency note: prefer the
AST-test approach over adding `import-linter` unless the contract set grows
enough to justify the dep (per the standing new-dependency policy).

Validation: free; the contracts are pure static checks with no paid calls.

### 3. Monster-file split ratchet  (free to gate)

The #23 refactor extracted `perform_fast_research`, but four files remain over
2,000 lines: `core/research_agent.py` (~5,265), `core/cli.py` (~4,276),
`ai/deep_research.py` (~3,892), `data/scraping/browsers.py` (~2,036), plus
~11 over 1,000. These are grandfathered, not fixed.

- **Gate:** a rise-only line-count ratchet (sibling to the coverage ratchet) —
  a per-file ceiling map; a file exceeding its ceiling fails CI. Ceilings only
  ratchet *down*. This stops the monsters from growing while splits proceed.
- **First split:** `research_agent.py` — it is also the coverage laggard
  (~30%), so splitting it serves the per-module coverage target in the
  standards section simultaneously. Mechanical now that the orchestrator is a
  thin coordinator; extract by responsibility (collection glue, strategy glue,
  doctor/utility) behind the existing injectable seams, **no behavior change**,
  eval scores unchanged.

Validation: the ratchet is free; each split is verified by the existing suite
(no behavior change) — no paid run.

### 4. CLI verb convention  (free, non-breaking)

The surface mixes subcommands (`primr recon|keys|mcp|skills|update`) with
flag-commands (`--qa --eval --improve --refine --calibrate --roadmap`) — the
"multiple ways to do the same kind of thing" smell, user-facing.

- **Convention:** noun/verb **subcommands** are canonical
  (`primr <subcommand> [args] [--modifiers]`); flags are modifiers, not
  commands. Document it in `CLAUDE.md` + the CLI help.
- **Migration is non-breaking:** *new* commands use the subcommand form; the
  existing flag-commands gain subcommand aliases over time while the flags stay
  as back-compat aliases (deprecation-noted, never removed in 1.x). No flag
  is broken.

Validation: free — a help-text/alias test pins both spellings dispatch
identically.

### 5. Toolchain & API currency cadence  (free)

primr already re-audits *product* model IDs ("Model landscape refresh"). The
*dev toolchain* needs the same discipline, because the model writing the code
has no reliable sense of "current." A standing checklist item per release
cycle (fold into the existing "Release Cadence → harden lane"):

- Confirm pinned `ruff` / `mypy` / `uv` against latest stable; bump by hand
  when a gate or this check flags it (no bot PRs, per standards). As of this
  writing: Ruff current (0.15.x line), **mypy 2.x has shipped** (primr targets
  1.x — evaluate the bump), and Astral **`ty` is beta, not GA** (so the
  standards section's "evaluate, do not gate on `ty` while preview" call is
  correct and stays).
- Spot-check that any newly-used third-party API matches current docs (the
  workstream-1 currency rule, applied at review).

Validation: free — it is a review-cadence checklist, not code.

## Exit criteria

1. `CLAUDE.md` exists and names every single seam + the file-size, currency,
   and verb rules; CONTRIBUTING links it.
2. Fitness functions enforce the async and HTTP seams (CI fails on new drift).
3. A rise-only per-file line-count ratchet is in CI; no monster file can grow;
   `research_agent.py` is split with coverage up and behavior unchanged.
4. The CLI verb convention is documented; new commands follow it; back-compat
   aliases are pinned by test.
5. The release harden lane includes a dev-toolchain currency check.

## Explicitly not

- **Not a rewrite.** No breaking CLI change, no dependency churn, no global
  mypy `--strict` flip, no blanket file-splitting sprint — everything is a
  rise-only ratchet or a non-breaking addition.
- **Not >95% coverage / NASA Power-of-10 literalism / Pydantic-everywhere /
  structlog-everywhere** — already rejected in the standards section; this doc
  does not reopen them.
- **Not a new linter stack.** Ruff + mypy stay authoritative; `ty` stays an
  evaluate-only local supplement until GA; fitness functions prefer an AST test
  over a new dependency.
- **No bot-authored dependency PRs** — currency stays manual review-and-bump.
