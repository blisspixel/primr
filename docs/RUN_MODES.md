# Run Modes and Costs

This guide explains how to choose a Primr run mode, estimate cost, and understand which artifacts each command produces.

Always run `--dry-run` before billable work:

```bash
primr "Company" https://company.com --dry-run
```

Dry-run output is the source of truth for the next run. The numbers below are current guideposts for the common xAI plus Gemini setup, not guarantees.

## Mode Matrix

| Mode | Command shape | Output | Typical time | Typical cost |
|------|---------------|--------|--------------|--------------|
| Default | `primr "Company" url` | Strategic Overview plus AI Strategy | 34-59 min | ~$0.89-$1.01 |
| Base report only | `primr "Company" url --no-ai-strategy` | Strategic Overview | 31-47 min | ~$0.76-$0.79 |
| XAI-only default | `primr "Company" url` with no Gemini key | Strategic Overview plus AI Strategy | 37-59 min | ~$5.76 |
| XAI-only base | `primr "Company" url --no-ai-strategy` with no Gemini key | Strategic Overview | 31-47 min | ~$4.36 |
| Scrape | `primr "Company" url --mode scrape` | Site corpus plus insights | 5-10 min | ~$0.10 |
| Deep | `primr "Company" url --mode deep` | External research only | 10-15 min | ~$2.50 |
| Premium | `primr "Company" url --premium` | Deep Research plus strategy | 50-75 min | ~$5 |
| Premium lite | `primr "Company" url --premium --lite` | Premium strategy with lighter model path | 50-80 min | ~$4 |
| Recon | `primr recon company.com` | DNS intelligence | 2-3 sec | $0.00 |
| Skill pack | `primr skills "Company" url` | Agent Skills tree plus Cowork zip | ~3 min | ~$0.30 |

## Default Provider Recipe

When both `XAI_API_KEY` and `GEMINI_API_KEY` are configured, Primr uses:

- Grok for reasoning-heavy stages.
- Gemini for bulk writing and utility stages.
- DuckDuckGo search by default, which does not require a search API key.

This measured recipe is much cheaper than the older xAI-only path while preserving the trust gate used in evaluation. XAI-only runs still work and keep the legacy writing and utility path.

OpenAI, Anthropic, and local OpenAI-compatible endpoints are wired into the provider layer for fallback, utility, evaluation, and planned backend-freedom routing. Full-report execution still uses the supported direct provider path described in [API Key Setup](API_KEYS.md).

## Strategy Generation

The default command includes AI Strategy. Disable it when you only need the Strategic Overview:

```bash
primr "Company" https://company.com --no-ai-strategy
```

Platform targeting:

```bash
primr "Company" https://company.com --platform ms
primr "Company" https://company.com --platform aws azure
```

When `--platform` is omitted, Primr runs DNS recon first and uses strong cloud infrastructure signals to choose a strategy platform. If recon is unclear, the default posture is Azure plus private cloud and NVIDIA.

Strategy types are YAML-defined and discovered at runtime:

```bash
primr --list-strategies
primr "Company" https://company.com --strategy-type customer_experience
```

Common strategy families include AI, customer experience, modern security and compliance, data fabric, cloud migration, data strategy, AI-first transformation, and skills.

## Cost Controls

Use the built-in control path:

```bash
primr "Company" https://company.com --dry-run
primr "Company" https://company.com --budget 1.25
primr show-usage
```

Cost behavior:

- Dry-run estimates the run before model calls.
- `--budget` refuses to start if the estimate exceeds the cap.
- Fast full-report runs also consult runtime budget checkpoints before optional stages.
- Premium, deep, and non-fast complete or hybrid runs checkpoint before and between optional strategy documents after the required Deep Research task completes.
- Required Deep Research tasks cannot be stopped mid-flight by `--budget`; scrape remains estimate-gated only.
- MCP HTTP tools can enforce server-side cost caps and approval tokens.

## Output Locations

Default output:

```text
output/<company>/
working/<company>/<timestamp>/
```

Common files:

```text
<Company>_Strategic_Overview_<date>.md
<Company>_Strategic_Overview_<date>.docx
<Company>_AI_Strategy_<date>.md
run_manifest.json
scraped_content.txt
insights.json
dossier.json
```

Use `--output-dir` when you want client-facing deliverables in a specific folder:

```bash
primr "Company" https://company.com --output-dir "C:\Clients\Company"
```

With a custom output directory, Markdown and DOCX deliverables go there. TXT mirrors and validation diagnostics stay in the run diagnostics folder.

## Example Run

```text
Grok 4.3 hybrid, recon auto-detected Azure

PHASE 0/6: Recon
Done: 14 services, 8 insights, platform azure

PHASE 1/6: Data collection
Done: 251 links, 50 selected
Done: 48 of 50 pages scraped
Done: 31 external sources

PHASE 2/6: Research deepening
Done: 8 gaps identified, 12 additional sources

PHASE 3/6: Analysis
Done: structured workbook built

PHASE 4/6: Report writing
Done: 23 sections, 21,500 words

PHASE 5/6: Cross-validation
Done: 3 contradictions resolved
Trust: PASS, citations clean

PHASE 6/6: AI Strategy
Done: strategy generated

Complete in 38m
output/ExampleCo_Strategic_Overview_04-10-2026.docx
PASS, 23 chapters, 48 citations, about $0.89
```

## Related Docs

- [API Key Setup](API_KEYS.md)
- [Configuration Reference](CONFIG.md)
- [Artifact Pipeline](ARTIFACTS.md)
- [Evaluation Guide](EVAL.md)
- [Skill Pack Guide](SKILL_PACK.md)
