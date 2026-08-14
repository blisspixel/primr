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
   uv sync --locked --extra dev --extra api   # validates and installs uv.lock
   uv run playwright install chromium
   # run tooling without activating a venv:
   uv run pytest tests/ -q
   uv run ruff check src/primr/
   uv run mypy src/primr/ --ignore-missing-imports
   ```
   `uv sync --locked` rejects a lockfile that is stale relative to
   `pyproject.toml`, then installs its exact pinned set so your environment
   matches CI and other contributors. After changing dependencies in
   `pyproject.toml`, run `uv lock` and commit the updated `uv.lock`. Install uv
   from https://docs.astral.sh/uv/ if you don't have it.

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
   py -3.13 setup_env.py           # Windows
   # or: python3.13 setup_env.py   # macOS/Linux
   ```
   `setup_env.py` auto-picks Python 3.12+ if your default is older, installs the editable package, downloads Playwright browsers, and adds the user Scripts dir to PATH on Windows. Useful for first-time contributors who hit the "which Python do I use?" issue.

4. Copy `.env.example` to `.env` and add your API keys (or run `primr init` to walk through it).

## Development Workflow

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

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
uv run --no-sync ruff check src/primr/ tests/

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
