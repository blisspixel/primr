# Modes, tiers, platforms, and strategies

primr exposes four orthogonal levers. Picking the right combination keeps cost and runtime appropriate to the user's actual ask.

## Mode

`--mode` chooses the high-level pipeline shape.

| Mode | What it does | Time | Cost | Pick when |
|------|--------------|------|------|-----------|
| `full` (default) | Site corpus + external research + structured report + AI Strategy | 34-59 min | ~$0.89-$1.01 | Almost everything. The default for "research Acme." |
| `scrape` | Site corpus + insights only, no external research | 5-10 min | ~$0.10 | The user only cares what the company says about itself; external context not needed; cost-sensitive scoping pass. |
| `deep` | External research only (Gemini Deep Research), no site scrape | 10-15 min | ~$2.50 | Site is hard-blocked or actively hostile to scraping; user wants third-party / analyst / news-driven context. |
| `premium` | Gemini Pro + Deep Research + structured report | 50-75 min | ~$5 | User explicitly asked for board-grade depth and accepted the cost. Don't pick this default. |

Heuristics:

- "Quick brief" → not primr at all. Use the host's web search.
- "Build me the dossier" → `full`.
- "What's on their site?" → `scrape`.
- "Their website is broken / behind a login" → `deep`.
- "Make it really good, money no object" → `premium`, with explicit cost-gate confirmation.

## Grok tier

`--grok-tier` only applies when the standard (non-premium) pipeline is in play and `XAI_API_KEY` is set. It controls which Grok model handles which stage.

| Tier | What it does | Cost (full mode) |
|------|--------------|------|
| `fast` | Grok 4.3 (reasoning_effort=low) with the routed writing provider | Re-estimate |
| `hybrid` (default) | Grok 4.3 for reasoning + Gemini 3.1 Flash-Lite writing when Gemini is configured | ~$0.76-$1.01 |
| `max` | Grok 4.3 everywhere | ~$3.75 |

`fast` saves tokens on reasoning (low effort). `max` uses 4.3 for writing too and adds reasoning overhead on prose. Only pick it if the user has explicitly asked for "absolute best Grok output" and you've already cost-gated.

## Platform

`--platform` biases the AI strategy module toward a specific cloud's vendor lens. It does **not** change the core report.

| Value | Aliases | What it biases toward |
|-------|---------|----------------------|
| `aws` | `amazon` | AWS-native services, AWS partner programs |
| `azure` | `microsoft`, `ms` | Azure-native services, M365 / Copilot, Microsoft partner programs |
| `gcp` | `google` | GCP-native services, Google Cloud partner programs |
| `private` | `nvidia` | On-prem / NVIDIA private cloud / sovereign deployment |
| `agnostic` | (no alias) | Cloud-neutral analysis |

Multi-platform is supported: `--platform aws azure`. Each extra platform adds ~$0.07 (standard) or ~$2.50 (premium).

Heuristics:

- User isn't selling a specific cloud → omit the flag.
- "I'm on the Microsoft account team / Azure presales" → `--platform ms`.
- "Multi-cloud RFP" → list the clouds the user is responding to.
- "Private cloud / regulated industry" → `--platform private`.

## Strategy type

The default command produces the Strategic Overview plus the built-in AI Strategy module. `--no-ai-strategy` produces the Strategic Overview only. `--strategy-type` swaps or adds a specific structured deliverable (in its own markdown / DOCX file) when the user asks for something besides the default AI Strategy.

Built-in types (run `primr --list-strategies` to enumerate at the user's install):

| Type | What it produces |
|------|------------------|
| `ai` | AI Strategy module - adoption maturity, vendor recommendations, prioritized initiatives |
| `customer_experience` | CX strategy - journey maps, modernization opportunities, vendor fit |
| `modern_security_compliance` | Security + compliance posture, modernization roadmap |
| `data_fabric_strategy` | Data architecture, governance gaps, fabric/mesh recommendations |
| `cloud_migration` | Migration readiness, target architecture, phased plan |
| `data_strategy` | Analytics maturity, data product opportunities |
| `ai_first_transformation` | Org-wide AI transformation playbook |

Heuristics:

- User wants only the Strategic Overview -> `--no-ai-strategy`.
- User is positioning a specific deliverable type (CX, security, data) → match it.
- User just wants "the report" -> omit the flag and keep the default AI Strategy unless cost is a concern.
- Multiple modules at once: not supported in one command. Run primr once per strategy type, or use `primr --ai-strategy-only <existing-report>` to add modules to an existing report without re-paying for the corpus stage.

## Combining the levers

Cost compounding is roughly additive on the strategy lever, multiplicative on the mode/tier lever. Examples:

- `primr "Acme" url` -> ~$0.89-$1.01, ~34-59 min, Overview + AI Strategy.
- `primr "Acme" url --no-ai-strategy` -> ~$0.76-$0.79, ~31-47 min, Strategic Overview only.
- `primr "Acme" url --platform ms` -> re-estimate, Overview + Azure-biased AI Strategy.
- `primr "Acme" url --premium --platform ms` -> re-estimate, premium Overview + premium Azure-biased AI Strategy.

Always re-estimate when you add levers; don't assume a previous estimate covers a new combination.

## When to use `--lite`

`--lite` only applies in `--premium` mode. It substitutes Gemini Pro for Deep Research in the strategy module, dropping ~$1 off premium runs at a quality cost. Pick it when the user said "premium" but the budget conversation suggests they didn't really mean $5+. Surface it as "premium, but ~20% cheaper, slightly less depth in the strategy module" and let them choose.
