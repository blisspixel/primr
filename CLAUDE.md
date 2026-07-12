# CLAUDE.md - the contract for building primr

You are working **on the primr codebase**. This file is the development
contract and context map: read it before writing code. It is the canonical
guide for any contributor (human or agent); Claude Code loads it natively, and
[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) points other tools here.

> **Not to be confused with [`AGENTS.md`](AGENTS.md)**, which is a *product*
> artifact: it tells agents how to *operate* the primr CLI/MCP for research.
> This file is about *changing primr's source*. If you are here to run
> research, you want AGENTS.md, not this.

The bar: code any human or AI could admire - tidy, consistent, secure,
well-tested. We are not making slopware. The rules below exist because
AI-assisted code reliably regresses on exactly these axes (duplication,
inconsistent patterns, stale APIs, silent insecurity) unless held to a
contract.

## Quick Start

primr turns a company URL into a sourced strategic brief. It is a CLI-first,
local-first Python package (`src/` layout), an LLM API **client** + adaptive
scraper + MCP/A2A agent - it trains and serves no models. To work on it:

1. Set up the dev env (`uv sync --locked --extra dev --extra api`, then
   `uv run playwright install chromium`) - see
   [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).
2. Put code in the package that owns it (see Architecture Pointers). Use the
   existing **seam** rather than inventing a second way to do the same thing.
3. Before opening a PR, run the Verification Commands and re-read the Negative
   Constraints. New code ships with tests; the coverage ratchet only rises.

Three rules in one breath: **one way to do each thing; no new giant files;
verify current APIs (never trust training memory).** Everything below expands
these.

## Language and runtime choices

Primr is Python-first, not Python-only. Python owns research orchestration,
provider integration, scraping policy, report generation, and the public
package because ecosystem leverage and iteration speed dominate there. A
different language or runtime is introduced only at a narrow, versioned seam
after an optimized Python baseline and production-shaped profile show a
material end-to-end benefit.

Use the smallest boundary that satisfies the requirement:

| Requirement | Preferred boundary |
|-------------|--------------------|
| Cancellation, crash containment, resource limits | Supervised Python child process or one-job container |
| Deterministic CPU or memory hotspot | Optional Rust accelerator after differential and packaging gates |
| Independently scaled multi-user admission | Service boundary; Go only after measured control-plane load |
| Local model execution | External OpenAI-compatible server; no embedded runtime without a measured kernel |

Do not add a language for architectural symmetry, popularity, or a
microbenchmark alone. A proposal must include the bounded capability, current
baseline, target, production-shaped corpus, correctness oracle, supported
platform artifacts, observability and failure semantics, fallback, rollback,
security review, and maintenance cost. Base Primr must remain installable and
functional without a native compiler. The binding decision record and current
adoption gates live in
[`docs/design/runtime-language-boundaries.md`](docs/design/runtime-language-boundaries.md).

## Architecture Pointers

`src/` layout, one package per concern. `config/` is close to a leaf (avoid
new `core/ai/data` imports). Design docs live in
[`docs/design/`](docs/design/README.md); the full standards are in
[ROADMAP → Engineering Standards](ROADMAP.md#engineering-standards--toolchain).

<details>
<summary>Package map - where things live</summary>

- `core/` - pipeline orchestration, CLI, research agent, strategy
- `ai/` - LLM clients, providers, routing, deep research
- `data/` - scraping engine (`data/scraping/`), hiring signals, fallback sources
- `pipeline/` - recovery policy, retries, failover, and model circuit breakers
- `prompts/` - YAML prompt composition, shared rules, and strategy registry
- `output/` - report/strategy rendering (MD/TXT/DOCX), validation
- `qa/` - report analysis, calibration, scoring
- `agentic/` - hypothesis tracking, hooks, subagents, orchestrator
- `skill_pack/` - skill-pack planning/authoring/validation
- `config/` - settings, env, model registry, validation (keep near-leaf)
- `utils/` - shared seams (below); not a dumping ground
- `mcp_server/`, `a2a/`, `api/` - agent / HTTP surfaces

</details>

## Use the one seam - don't invent a sixth way

The fastest way to rot a codebase is N ways to do one thing. Before reaching
for a library or pattern, use the existing seam.

<details>
<summary>Seam table - use these, not the alternatives</summary>

| Need | Use | Not |
|------|-----|-----|
| Run async from sync | `utils.async_utils.run_sync` | bare `asyncio.run` / `get_event_loop` |
| Console output | `utils.console.get_console()` | `print(` in library code |
| Logging | `utils.logging_config.get_logger(__name__)` | `logging.getLogger` / `print` |
| Config / settings | `config/` (`settings`, `env`, `models`) | ad-hoc `os.environ` reads |
| JSON | stdlib `json` | orjson / ujson / simplejson |
| Atomic file write | `utils.atomic_io` | raw `open(...,'w')` for state files |
| Model IDs / pricing | `config/models.py` registry | hardcoded model strings |
| Outbound HTTP | the scraping-tier clients / `data.http_client` | a *new* HTTP client |

HTTP is deliberately multi-client (browser → curl_cffi → httpx → requests →
urllib) for scrape-tier evasion - that set is **closed**. A sixth client is a
reviewed exception, not a default. If you genuinely need a new pattern, add the
seam *and* migrate callers - don't leave two ways behind.

</details>

## Negative Constraints

What NOT to do. These are gated or will fail review:

- **NEVER add a second way** to do something that already has a seam (above).
- **NEVER let a monster file grow.** A new file over ~800 lines needs a split
  plan; the large files (`research_agent.py`, `cli.py`, `deep_research.py`, …)
  are pinned by `tests/test_architecture.py` and may not grow - split instead
  of raising the ceiling.
- **NEVER trust training memory for "now."** Verify the current library
  version, API signature, and model ID (against `uv.lock` / `config/models.py`
  / current docs) before using them. Stale/deprecated APIs and hallucinated
  packages are a top AI-code failure mode - assume your recall is six months
  stale and confirm.
- **NEVER bypass the SSRF guard.** Every outbound URL goes through
  `utils.security.is_safe_url` (validated post-redirect); untrusted scraped
  text entering a prompt is fenced via `utils.content_sanitizer.fence_untrusted`.
  No secrets in code, logs, or fixtures.
- **NEVER launch a billable run without an estimate + explicit approval** -
  primr runs cost real money and time; the cost gate is non-negotiable (this is
  the operate-side contract in `AGENTS.md`, restated here as a design boundary).
- **NEVER turn primr into a daemon / always-on watcher** - it is **single-job**
  by design (URL in, artifact out). Loops and scheduling live on the consumer
  side; do not add a background watcher to the core.
- **NEVER put real company data** anywhere that ships (docs, fixtures, commit
  messages) - use `Acme Corp` / `ExampleCo` / `acme.example`. See CONTRIBUTING.
- **NEVER add non-human authorship or provenance lines** to commits, PR bodies, or
  comments. Avoid coauthor trailers, AI-generation credits, or tool-credit
  language for any AI, bot, or automation tool. Every commit reads as a human
  engineer's work.

## Verification Commands

Run what CI runs before opening a PR, and use `primr doctor` to check system
state.

```bash
primr doctor                 # system health: keys, browsers, providers, paths
uv run pytest tests/ -q      # the full suite
```

<details>
<summary>Full local pre-PR gate (mirrors the primary-interpreter CI gates)</summary>

```bash
uv run --no-sync ruff check src/primr/
uv run --no-sync ruff format --check src/ tests/
uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude 'src/primr/api/'
uv run --no-sync mkdocs build --strict
uv run --no-sync bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q
uv run --no-sync pip-audit
PRIMR_VALIDATE_SDIST=1 uv run --no-sync pytest tests/test_release_integrity.py::test_built_sdist_matches_release_inventory -q
GEMINI_API_KEY=fake-key-for-ci-tests uv run --no-sync pytest -q tests/test_core/test_resume_recovery.py tests/test_core/test_research_agent_resume.py tests/test_data/test_scrape_resume.py --cov=primr.core.cli --cov=primr.core.research_agent --cov=primr.data.scrape --cov-fail-under=13 --cov-report=term
GEMINI_API_KEY=fake-key-for-ci-tests uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81
```

The environment assignments above use POSIX shell syntax because CI runs on
Ubuntu. Use the equivalent environment syntax in PowerShell when validating on
Windows. The non-primary Python matrix legs run the same filtered test command
without the global coverage gate.

Then ask the slop question: **did this add a second way to do something that
already has a seam?** If yes, fix it before review. Don't lower the coverage
ratchet; don't add a new `ignore_errors` mypy module (the strict allowlist only
grows). Pin load-bearing invariants with Hypothesis property tests.

</details>

## CLI verb convention

New user-facing capabilities are **noun/verb subcommands**
(`primr <command> [args] [--modifiers]`), matching `recon`/`keys`/`mcp`/
`skills`/`update`. Flags are modifiers, not commands. Legacy flag-commands
(`--qa`, `--eval`, …) keep back-compat aliases; don't add new ones.

## Git / PR

Branch off `main`; keep PRs focused; update `docs/CHANGELOG.md` under
`[Unreleased]` for user-facing changes; keep the single version source of truth
consistent (`pyproject` ↔ `__init__.__version__` ↔ ROADMAP "Current State" ↔
`CITATION.cff`, pinned by `tests/test_release_integrity.py`).

`main` is the only long-lived branch. Feature branches are short-lived and
deleted on merge (the repo auto-deletes merged PR branches); don't leave stale
branches behind. Merge via PR, not direct pushes to `main`.
