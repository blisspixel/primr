# Research Modes

Use `primr://research/modes` and `estimate_run` as the source of truth for current recommendations and estimates.

## Quick guidance

| Mode | Use when |
|------|----------|
| `scrape` | You want a first-party site overview only |
| `deep` | The target site is blocked, sparse, or not the main evidence source |
| `full` | You want the standard end-to-end Primr workflow |
| `premium` | You want maximum-depth research and accept longer runtime |

## Notes

- `full` is the standard recommended workflow for most end-to-end runs.
- `premium` is the explicit high-depth option.
- Do not rely on hardcoded cost or time numbers here; call `estimate_run` for the current estimate.
