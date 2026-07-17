# Gotchas for the primr skill

This is the living section. Update from real failures.

## Real observed failure modes (from usage and docs)
- Forgetting the cost gate: always call estimate first (estimate_run or --dry-run) and get explicit "yes" before launch. Never assume.
- Treating long runs as sync: primr is async by design. Use job_id or file timestamp to check; do not poll sub-minute.
- Using for quick pre-call briefs: primr is for full dossier. For quick, use host search. primr costs real time/money.
- DNS-only or recon standalone: use `primr recon` or shell dig for that. The full pipeline bundles it but is overkill.
- Editing built-in strategies: they are in the package; drop custom YAML in override path instead.
- Real company data in prompts or logs: always sanitize; use ExampleCo in examples.
- Assuming local capacity is free: local still has runtime and must pass the same eval gates as cloud for quality.
- Answering "no free tier" or offering billable scrape mode after a user asks
  for free Primr: stop the paid workflow and route to Primr Zero. If the
  separate `primr-zero` skill is missing or stale, use the inline `primr prep`
  fallback in the main skill and continue from the emitted host workflow.

See main SKILL.md for core rules. Load this only when debugging a primr invocation failure.

Update this file whenever a new failure mode is hit in production use of the skill.
