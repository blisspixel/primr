# Authoring custom strategy YAMLs

primr's built-in strategy types (`ai`, `customer_experience`, `modern_security_compliance`, etc.) are themselves YAML files under the install's `prompts/strategies/` directory. Custom strategies use the same shape and are auto-discovered when dropped into the override path.

## Where to put them

Run `primr keys path` to find the user's config directory. Custom strategies live alongside that file at `<config-dir>/strategies/<your-strategy>.yaml`. The directory is created on first write — `mkdir -p` it if missing.

Do not edit the built-in YAMLs in place. They live inside the installed package and get overwritten on `pip install -U primr`.

## Minimum viable schema

```yaml
meta:
  name: FinOps Assessment
  status: active                # 'active' or 'placeholder' (placeholders skipped at runtime)
  description: |
    FinOps maturity assessment for retail clients with multi-cloud spend.
    Produces: spend-pattern analysis, governance gaps, optimization roadmap.
  cli_description: |            # Short, one-line, used in --list-strategies
    FinOps maturity for retail multi-cloud

inputs:
  required:
    - company_name
    - corpus              # Site corpus from primr's scrape stage
    - external_sources    # Optional but recommended
  optional:
    - hypotheses          # Pulled from research memory if present

prompt:
  system: |
    You are a FinOps consultant writing for a CFO and a head of platform engineering.
    Use hedged language. Cite every quantitative claim. Avoid vendor-specific
    recommendations until the assessment section.

  sections:
    - id: spend_signals
      title: Observed Spend Signals
      description: |
        Extract every numeric or qualitative signal about cloud / SaaS spend
        from the corpus. Mark each with a source citation and a confidence level.
      min_words: 400

    - id: governance_gaps
      title: Governance Gaps
      description: |
        For each spend signal, identify the FinOps practice (allocation, reporting,
        forecasting, optimization) that would have caught or prevented it.
      min_words: 600

    - id: assessment
      title: Maturity Assessment
      description: |
        Score the org on the FinOps Foundation maturity model (Crawl/Walk/Run)
        per capability area. Be hedged — this is from public signals only.
      min_words: 500

    - id: roadmap
      title: 90-Day Roadmap
      description: |
        Three concrete initiatives, each with: outcome, owner, prerequisites,
        rough cost-savings range, sequencing rationale.
      min_words: 700

output:
  format: markdown
  filename_template: "{company_slug}_FinOps_Assessment_{date}.md"
  also_render: docx
```

## Field reference

- **meta.status**: `active` makes the strategy show up in `--list-strategies` and be selectable via `--strategy-type <name>`. `placeholder` keeps the file in the repo but hides it from the runtime — use this for drafts.
- **meta.cli_description**: keep under 80 characters. The `--list-strategies` table truncates after that.
- **inputs**: declares what the strategy expects. `corpus` and `external_sources` are produced by primr's pipeline; the strategy will receive them as text. `hypotheses` (if requested) comes from research memory.
- **prompt.system**: the system prompt used when generating sections. Keep it stylistic — voice, audience, evidence rules. Don't put the section content here.
- **prompt.sections**: ordered list. Each section is a separate LLM call (parallelized when independent). `id` is used internally; `title` is the rendered heading; `description` is the per-section instruction; `min_words` is a soft target the writer aims for.
- **output.filename_template**: supports `{company_slug}` (kebab-case company name), `{date}` (MM-DD-YYYY), and `{strategy_name}` (the file's stem).
- **output.also_render**: list of additional formats. `docx` is the most common; `pdf` is supported on installs with the optional `[pdf]` extra.

## Verifying a custom strategy

After dropping the file:

```bash
primr --list-strategies          # Yours should appear in the table
primr "Test Co" https://example.com --strategy-type your_strategy --dry-run
```

The dry run validates the YAML, reports estimated cost (with the strategy's section count factored in), and exits without spending money.

## Style guide

- One strategy = one deliverable. Don't try to combine FinOps + security + AI into one file; that produces 80-page reports nobody reads.
- 4-7 sections is the sweet spot. Fewer feels thin, more dilutes signal.
- Make at least one section explicitly *evidence* and at least one explicitly *recommendation*. Don't blur them into "analysis."
- Build the prompt to encourage hedging. primr reports always say "appears to," "suggests," "consistent with" — your custom strategy should match that voice.
- Test against a known company first. Pick someone you actually understand and check whether the output reads like an expert. If it reads like generic content marketing, tighten the section descriptions.

## When to ship it back

If the strategy works well and isn't client-specific, propose it as a built-in via PR to `src/primr/prompts/strategies/`. Built-ins ship to every primr install on the next release; custom YAMLs only help the one user who wrote them.
