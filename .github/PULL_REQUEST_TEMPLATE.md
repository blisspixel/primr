<!--
Thanks for contributing to primr. Keep PRs focused. See CONTRIBUTING.md and
CLAUDE.md (the development contract) for the full bar.
-->

## What and why

<!-- What does this change and why? Link any related issue or ROADMAP item. -->

## Pre-PR checklist (matches CI)

- [ ] `uv run ruff check src/primr/`
- [ ] `uv run ruff format --check src/ tests/`
- [ ] `uv run mypy src/primr/ --ignore-missing-imports`
- [ ] `uv run pytest tests/ -q` (new code ships with tests; the coverage ratchet only rises)
- [ ] The slop question: did this add a second way to do something that already has a seam? If yes, it's fixed.
- [ ] `docs/CHANGELOG.md` updated under `[Unreleased]` for any user-facing change.
- [ ] Version sources stay consistent (`pyproject` <-> `__init__.__version__` <-> ROADMAP "Current State"), if touched.

## Notes for the reviewer

<!-- Anything non-obvious: tradeoffs, follow-ups, areas to look at closely. -->
