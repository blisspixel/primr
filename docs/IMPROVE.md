# Output Improvement

Use `primr improve` (or `--improve`) to run a post-generation quality pass on existing `.md` / `.txt` outputs.

## Commands

```bash
# Deterministic cleanup + QA metrics
primr improve "output/Company_Strategic_Overview_03-06-2026.md"

# Add an agentic review pass first (find weak sections, then tighten)
primr improve "output/Company_AI_Strategy_AZURE_03-06-2026.md" --improve-agentic

# Overwrite the original file instead of writing *_improved
primr improve "output/Company_Strategic_Overview_03-06-2026.md" --in-place
```

## What This Does

- Removes internal placeholder/source artifacts that should not ship (`Analysis Context`, `vendor-research`, `citation inventory`, etc.)
- Normalizes and validates citations for reports
- Applies strategy consistency checks (including budget-total mismatch detection)
- Runs a deterministic salvage pass before blocking output, so recoverable markdown issues are auto-cleaned
- Applies an artifact shipping gate before DOCX render and validates the rendered DOCX text afterward
- Holds back dirty DOCX files but still saves `.md` / `.txt` plus a validation sidecar when issues remain
- Prints deterministic QA summary (`gate=PASS|WARN`) before writing output
