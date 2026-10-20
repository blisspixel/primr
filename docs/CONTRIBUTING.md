# Contributing to Primr

Thanks for your interest in contributing to Primr! This document provides guidelines for contributing.

## README demo screenshot

The root README uses a placeholder CLI screenshot (`docs/images/primr-demo.png`)
with ExampleCo demo data only—no real company content. To regenerate after
editing the HTML mockup:

```bash
uv run --no-sync python scripts/render_readme_demo.py
```

Source: `docs/images/primr-demo-terminal.html`. Requires Playwright Chromium
(`uv run playwright install chromium`). No network or model API calls.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/primr.git`
3. Set up the development environment. Three options:

   **Option A - uv (recommended, fastest, reproducible):**
   ```bash
   cd primr
   uv sync --locked --all-extras   # matches the primary CI environment
   uv run playwright install chromium
   # run tooling without activating a venv:
   uv run --no-sync pytest tests/test_architecture.py -q
   uv run --no-sync ruff check src/primr/
   # Complete verification: CLAUDE.md, including filtered tests and coverage.
   ```
   `uv sync --locked` rejects a lockfile that is stale relative to
   `pyproject.toml`, then installs its exact pinned set so your environment
   matches CI and other contributors. After changing dependencies in
   `pyproject.toml`, run `uv lock` and regenerate the container exports below.
   Use **uv 0.11.33**, the version pinned in CI; export formatting is part of
   the reproducibility check. Install uv from https://docs.astral.sh/uv/ if you
   don't have it.

   Transitive security floors in `[tool.uv].constraint-dependencies` protect
   locked source, development, and exported container environments. They do
   not become published wheel requirements; pip installations resolve their
   own transitive versions. Keep constraints, the lock, and container exports
   consistent when refreshing security dependencies.

   **Option B - manual pip (cross-platform):**
   ```bash
   cd primr
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # or: source .venv/bin/activate  # macOS/Linux
   pip install -e ".[dev]"
   playwright install chromium
   ```

   **Option C - guided bootstrap (Windows-friendly):**
   ```bash
   cd primr
   py -3.15 setup_env.py           # Windows
   # or: python3.15 setup_env.py   # macOS/Linux
   ```
   `setup_env.py` auto-picks Python 3.11+ if your default is older, installs the editable package, downloads Playwright browsers, and adds the user Scripts dir to PATH on Windows. Useful for first-time contributors who hit the "which Python do I use?" issue.

4. Copy `.env.example` to `.env` and add your API keys (or run `primr init` to walk through it).

## Development Workflow

### Dependency maintenance

`main` is the only long-lived branch. Review dependency updates together when
they share a resolver constraint, merge through a passing pull request, and
delete the completed feature branches. Scheduled pip-audit and Trivy checks
remain active; automatic dependency-fix PRs are disabled by repository policy.

After changing the dependency lock with uv 0.11.33, regenerate both checked-in
container exports before running the release gate:

```bash
uv export --locked --no-dev --extra api --no-emit-project --no-header --no-annotate --output-file deploy/runtime-requirements.lock
uv export --locked --only-group release --prune cyclonedx-bom --prune twine --no-emit-project --no-header --no-annotate --output-file deploy/build-requirements.lock
uv run --no-sync pytest tests/test_supply_chain_pins.py -q
```

Commit `pyproject.toml`, `uv.lock`, and any changed exports together. A lockfile
update alone can leave the container build on older dependencies and fail CI.

### Running Tests

```bash
# Run the ordinary local suite without manual or provider integration tests
uv run --no-sync pytest tests/ --ignore=tests/manual -m "not integration" -v

# Run a specific test file
uv run --no-sync pytest tests/test_core/test_cli.py -v

# Run the CI-scoped suite with branch coverage
uv run --no-sync pytest tests/ --ignore=tests/manual \
  -k "not test_wait_times_out_when_no_change" -m "not integration" \
  --cov=src/primr --cov-branch --cov-fail-under=81
```

### Code Quality

Before submitting a PR, ensure your code passes the relevant local gates. CI is
the authoritative gate, but these commands match the current shape closely for
ordinary code changes:

```bash
# Linting
uv run --no-sync ruff check src/primr/

# Formatting
uv run --no-sync ruff format --check src/primr/ tests/

# Type checking
uv run --no-sync mypy src/primr/ --ignore-missing-imports --disable-error-code=import-untyped --exclude "src/primr/api/"

# Tests and branch coverage
uv run --no-sync pytest tests/ --ignore=tests/manual -x --tb=short -q -k "not test_wait_times_out_when_no_change" -m "not integration" --cov=src/primr --cov-branch --cov-fail-under=81

# Security scan (gated at medium severity in CI)
uv run --no-sync bandit -r src/primr -c .bandit --severity-level medium --confidence-level medium -q

# Dependency vulnerability audit
uv run --no-sync pip-audit

# Documentation
uv run --no-sync mkdocs build --strict
```

For narrow fixes, run the focused tests for the touched behavior first, then
run the broader gates before opening the PR.

### URL parser fuzzing

The primary Linux Python 3.13 CI job runs a 30-second coverage-guided
[Atheris](https://github.com/google/atheris) smoke test against the existing
`primr.utils.validators.validate_url` boundary used by single and batch CLI
requests. This uses Atheris's bundled libFuzzer engine, separately from the
Hypothesis property suite. It makes no HTTP or model calls. The target permits
only documented `InputValidationError` failures and checks accepted schemes,
authority and hostname, absent credentials, valid ports, unchanged content, and
idempotence.
A network audit hook fails attempted connections or DNS lookups.

The checked-in corpus covers valid HTTPS, IPv6 and Unicode hosts plus malformed
ports, brackets, NFKC authority delimiters, credentials, schemes, and injection
patterns, including an empty hostname with a port. Deterministic tests check
each seed's expected acceptance and prove
that the oracle catches a permissive validator. Fuzzing consumes arbitrary
bytes with surrogate escaping and additionally exercises an HTTPS authority
shape. Inputs are bounded to 4 KiB in CI; a smoke run is not exhaustive parser,
SSRF, native-extension, or end-to-end research coverage.

The engine is a hash-pinned, binary-only CI tool in
`tests/fuzz/requirements.txt`, intentionally outside the application dependency
lock. Its single wheel supports Linux x86_64 CPython 3.13. No runtime package,
compiler, OSS-Fuzz enrollment, external account, or corpus-storage service is
required. CI installs it into a temporary target directory, reuses the already
locked application environment, copies seeds before mutation, and retains
crashing inputs and the engine log as a seven-day failure artifact. Update the
version and the matching wheel hash together when maintaining this tool.
The dependency-audit step checks this separate tool requirement as well.
The isolated tool install uses `--no-config` so application resolver constraints
are not interpreted as extra hash-locked tool requirements; the application
install continues to use `uv sync --locked --all-extras`.

To reproduce on that platform after setting up the usual development environment:

```bash
mkdir -p .agent/fuzz/tools .agent/fuzz/corpus .agent/fuzz/artifacts
uv pip install --no-config --python .venv/bin/python --target .agent/fuzz/tools \
  --only-binary=:all: --require-hashes --no-deps -r tests/fuzz/requirements.txt
cp tests/fuzz/corpus/url/* .agent/fuzz/corpus/
PYTHONPATH="$PWD/.agent/fuzz/tools:$PWD/src:$PWD" PYTHONHASHSEED=0 \
  uv run --no-sync python -m tests.fuzz.url_fuzzer \
    -max_total_time=30 -timeout=5 -rss_limit_mb=512 -max_len=4096 -seed=150 \
    -print_final_stats=1 -artifact_prefix="$PWD/.agent/fuzz/artifacts/" \
    .agent/fuzz/corpus
uv run --no-sync pytest tests/test_fuzz_url_contract.py -q
```

Pass a saved crash file in place of the corpus directory to replay it. Review
and minimize confirmed failures before adding permanent regression seeds.
[Scorecard v5.3.0's Python detector](https://github.com/ossf/scorecard/blob/v5.3.0/checks/raw/fuzzing.go)
recognizes the target's actual Atheris import; detection alone does not prove a
run passed. CI engine results provide that evidence.

Optionally install the pre-commit hooks so ruff + mypy run automatically on
each commit (CI is still the authoritative gate):

```bash
uv run pre-commit install
```

### Code Style

The canonical development contract - the single seams to use, the
no-new-giant-file rule, the verify-current-APIs rule, the CLI verb convention,
and the pre-PR slop check - lives in
[`CLAUDE.md`](https://github.com/blisspixel/primr/blob/main/CLAUDE.md) at the
repo root. Claude Code loads it automatically; for other tools, read it
directly.
The essentials:

- Follow PEP 8 guidelines
- Use type hints for all function signatures
- Write docstrings for public functions and classes
- Keep functions focused and under 50 lines when possible
- Use the existing seam (async/console/logging/config/json/http) rather than
  introducing a second way to do the same thing

### No Real Company Data in the Repo

Primr is a company-research tool, which makes it tempting to use real company names when writing examples, fixtures, eval results, sample reports, or commit messages. **Don't.** This applies to docs, code comments, test fixtures, prompt templates, eval artifacts, debug scripts, and git commit messages - anywhere that gets pushed to GitHub.

Use these placeholders instead:

| Use case | Placeholder |
|---|---|
| Generic example company name | `Acme Corp` |
| Domain for examples | `acme.example` or `example.com` |
| Alternate company (multi-company snippets) | `ExampleCo` |
| Fictional product / brand | `Cirrus Fleet` (or any made-up name) |

Vendor/technology names referenced as **first-class product features** are fine - Cloudflare in bot-protection detection, Snowflake / Databricks / Microsoft Fabric in the data-fabric strategy, AWS / Azure / GCP / NVIDIA as `--platform` options. The line is: real names as *technical references* OK; real names as *research-subject examples* not OK.

When in doubt, grep your PR before opening it:

```bash
git diff main...HEAD | grep -i -E "\\b(real|actual)\\b.*\\binc\\.|<real-company-name>"
```

If a real name slips into a commit message, fix it before the commit lands - rewriting messages after a tagged release means rewriting tags too.

## Pull Request Process

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Make your changes with clear, atomic commits
3. Ensure all tests pass and code quality checks succeed
4. Update documentation if needed
5. Submit a PR with a clear description of changes

### PR Guidelines

- Keep PRs focused on a single feature or fix
- Include tests for new functionality
- Update CHANGELOG.md for user-facing changes
- Reference any related issues

## Reporting Issues

When reporting bugs, please include:

- Python version (`python --version`)
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant error messages or logs

## Feature Requests

Feature requests are welcome! Please:

- Check existing issues first to avoid duplicates
- Describe the use case and expected behavior
- Explain why this would be useful

## Collaboration

Keep collaboration respectful and focused on technical quality.

## Questions?

Feel free to open an issue for questions or discussions about the project.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
