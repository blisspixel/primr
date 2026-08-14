# Modes, tiers, platforms, and strategies

primr exposes four orthogonal levers. Picking the right combination keeps cost and runtime appropriate to the user's actual ask.

## Mode

`--mode` chooses the high-level pipeline shape.

| Mode | What it does | Time | Cost | Pick when |
|------|--------------|------|------|-----------|
| `full` (default) | Site corpus + external research + structured report + one integrated AI Strategy | 34-53 min | ~$0.89 | Almost everything. The default for "research Acme." |
| `scrape` | Site corpus + provider-synthesized insights, no external research | 2-5 min | ~$0.10 | The user only cares what the company says about itself; external context not needed; cost-sensitive scoping pass. |
| `deep` | Hiring evidence + Deep Research dossier + sequential Flash report + one AI Strategy | 32-62 min | Current static plan ~$5.38; use dry-run | Site is hard-blocked or the user wants third-party, analyst, and news-driven context without the Premium collection stage. |
| `premium` | Structured evidence + Deep Research dossier + sequential Flash report + one AI Strategy | 74-132 min | Current static plan ~$6.71; use dry-run | User explicitly asked for maximum provider-backed depth and accepted the live quote. Do not pick this by default. |

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
| `hybrid` (default) | Grok 4.3 for reasoning + Gemini 3.1 Flash-Lite writing when Gemini is configured | ~$0.76-$0.89 by default |
| `max` | Grok 4.5 everywhere (version-pinned high-cost tier; re-estimate) | ~$9.93 with the default strategy |

`fast` saves tokens on reasoning (low effort). `max` uses the version-pinned
Grok 4.5 route for every Grok stage and costs materially more than hybrid.
Grok 4.6 is registered for evaluation but is not silently promoted into this
product tier. Only pick `max` when the user explicitly requests it and has
approved the exact quote.

## Platform

`--platform` biases the AI strategy module toward a specific cloud's vendor lens. It does **not** change the core report.

| Value | Aliases | What it biases toward |
|-------|---------|----------------------|
| `aws` | `amazon` | AWS-native services, AWS partner programs |
| `azure` | `microsoft` | Microsoft ecosystem evaluation emphasis |
| `gcp` | `google` | GCP-native services, Google Cloud partner programs |
| `private` | `nvidia` | On-prem / NVIDIA private cloud / sovereign deployment |
| `agnostic` | (no alias) | Cloud-neutral analysis |
| `ms` | (shorthand) | Explicit `azure private` fan-out, producing two strategy artifacts |

Without an explicit platform, no strong recon signal produces one agnostic
strategy, one strong signal emphasizes that ecosystem, and multiple strong
signals produce one integrated vendor-neutral strategy. Multi-platform fan-out
is explicit: `--platform aws azure`. A second standard strategy adds about
$0.12 in the common xAI plus Gemini recipe; premium additions cost more and
must be re-estimated.

Heuristics:

- User isn't selling a specific cloud → omit the flag.
- "Evaluate the Microsoft ecosystem" → `--platform azure`.
- "Compare Microsoft cloud and private accelerated infrastructure" → `--platform ms`.
- "Multi-cloud RFP" → list the clouds the user is responding to.
- "Private cloud / regulated industry" → `--platform private`.

## Strategy type

The default command produces the Strategic Overview plus the built-in AI Strategy module. `--no-ai-strategy` produces the Strategic Overview only. `--strategy-type` swaps or adds a specific structured deliverable (in its own markdown / DOCX file) when the user asks for something besides the default AI Strategy.

Built-in types (run `primr --list-strategies` to enumerate at the user's install):

| Type | What it produces |
|------|------------------|
| `ai` | Business-first AI portfolio, economics, operating model, architecture, and governance |
| `customer_experience` | CX strategy - journey maps, modernization opportunities, vendor fit |
| `modern_security_compliance` | Security + compliance posture, modernization roadmap |
| `data_fabric_strategy` | Data architecture, governance gaps, fabric/mesh recommendations |

Historical and placeholder YAML files that are absent from
`primr --list-strategies` are not selectable strategy types.

Heuristics:

- User wants only the Strategic Overview -> `--no-ai-strategy`.
- User is positioning a specific deliverable type (CX, security, data) → match it.
- User just wants "the report" -> omit the flag and keep the default AI Strategy unless cost is a concern.
- Multiple modules at once: not supported in one command. Use the normal
  estimated pipeline for each requested strategy. For post-report recovery,
  quote the exact standalone path with `--ai-strategy-only REPORT --dry-run`,
  report the estimate, and get explicit approval before execution. The command
  repeats the estimate and fails closed if the validated report changes before
  its private snapshot is created.

## Combining the levers

Cost compounding is roughly additive on the strategy lever, multiplicative on the mode/tier lever. Examples:

- `primr "Acme" url` -> ~$0.89, ~34-53 min, Overview + one integrated AI Strategy.
- `primr "Acme" url --no-ai-strategy` -> ~$0.76-$0.79, ~31-47 min, Strategic Overview only.
- `primr "Acme" url --platform ms` -> re-estimate, Overview + separate Azure and private-infrastructure AI Strategies.
- `primr "Acme" url --premium --platform ms` -> re-estimate, premium Overview + separate premium Azure and private-infrastructure AI Strategies.

Always re-estimate when you add levers; don't assume a previous estimate covers a new combination.

## When to use `--lite`

`--lite` only applies in `--premium` mode. It replaces the strategy module's
Deep Research workflow with the configured `Role.REASONING` route, so the
provider and model can vary. It usually reduces the live quote at a quality
cost. Pick it when the user said "premium" but wants a cheaper strategy stage.
Surface the exact dry-run comparison and let them choose.
