# OpenRouter Preview

OpenRouter is an optional paid gateway for users who do not have quota with a
direct provider or want one key that can reach models from several vendors.
It is a preview route, not Primr's measured default. A configured key does not
enable it and never counts as approval to spend.

## Configure the key

Use Primr's hidden prompt so the secret does not enter shell history:

```bash
primr keys set openrouter
primr keys test openrouter
primr keys path
```

`primr keys test openrouter` performs an authenticated request to OpenRouter's
[current-key endpoint](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key).
It does not generate text or consume model tokens. The public model catalog is
not used as an authentication test because it also returns successfully for
invalid credentials. `primr keys path` prints the active user config file.
Typical locations are `%APPDATA%\primr\.env` on Windows and
`~/.config/primr/.env` on Linux. A project-local `.env` can override the user
file, but the user file is preferable for a reusable personal key.

The underlying variable is:

```dotenv
OPENROUTER_API_KEY=your-key
```

Do not commit either `.env` file.

For defense in depth, use a dedicated OpenRouter key with an
[account-side spending limit](https://openrouter.ai/docs/api/api-reference/api-keys/create-keys)
no higher than you are willing to authorize independently of Primr. Primr's
per-run approval and budget checks remain the primary gate.

## Enable paid routing

The key only enables validation and diagnostics. To make OpenRouter eligible
for a provider-backed run, add a separate opt-in:

```dotenv
PRIMR_OPENROUTER_ENABLED=1
```

Then inspect the exact plan before any billable run:

```bash
primr "ExampleCo" https://example.co --dry-run
```

The dry run remains network-free and makes no model calls. Normal terminal
execution still asks for confirmation. Automation may use `--skip-confirm`
only after a person has reviewed and approved that fresh quote. MCP and A2A
use the same estimate-bound approval and cost-cap contract.

## Curated preview recipe

The initial route uses a bounded role recipe whose catalog prices were audited
on September 1, 2026:

| Role | OpenRouter model | Input / output per 1M tokens |
|------|------------------|-------------------------------|
| Utility | `google/gemini-2.5-flash-lite` | `$0.10 / $0.40` |
| Writing | `openai/gpt-4.1-mini` | `$0.40 / $1.60` |
| Reasoning | `deepseek/deepseek-v3.2` | `$0.269 / $0.40` |

The default full report plus AI Strategy is currently estimated at about
`$1.05` on Primr's conservative static token plan. The command's live dry-run
is authoritative because selected features, token plans, pricing, and
historical floors can change.

Prices and model metadata come from OpenRouter's
[models API](https://openrouter.ai/docs/api/api-reference/models/get-models).
The role recipe is intentionally curated rather than accepting an unpriced
model name silently.

## Request safeguards

Every OpenRouter generation request:

- applies the registered input and output rates as OpenRouter `max_price`
  ceilings;
- requires routed providers to support the requested parameters;
- sets provider data collection to `deny`;
- requests zero-data-retention endpoints by default;
- records OpenRouter's response-level `usage.cost` as exact spend when present;
- caps the requested output at the selected model's live catalog limit;
- identifies the application as `Primr` through OpenRouter's optional app
  [attribution headers](https://openrouter.ai/docs/app-attribution); and
- retains conservative token-based accounting when exact cost is absent or
  invalid.

These controls use OpenRouter's documented
[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[zero-data retention](https://openrouter.ai/docs/guides/features/zdr), and
[usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
fields. Price ceilings limit rates, while Primr's estimate and approved budget
limit the planned run shape.

Some models may have no provider that satisfies both the price and privacy
policy at a given time. Primr fails the request instead of weakening those
controls. To allow non-ZDR providers explicitly while still denying providers
that collect data, set `PRIMR_OPENROUTER_ZDR=0`. Review that privacy tradeoff
before doing so.

## Custom OpenRouter model

An advanced user can select another OpenRouter model only with explicit,
finite, nonnegative prices in USD per one million tokens:

```dotenv
PRIMR_OPENROUTER_MODEL=vendor/model-slug
PRIMR_OPENROUTER_INPUT_PRICE=0.25
PRIMR_OPENROUTER_OUTPUT_PRICE=0.75
PRIMR_OPENROUTER_MAX_INPUT_TOKENS=128000
PRIMR_OPENROUTER_MAX_OUTPUT_TOKENS=16384
```

The input and output prices become both the cost-estimator rates and the
request's provider price ceilings. Missing, invalid, infinite, or negative
prices make the model unavailable before any provider request.

## Current boundaries

- OpenRouter is available to the Standard routed pipeline, including CLI,
  MCP, and A2A execution.
- `--grok-tier max` remains an explicit xAI route and still requires xAI.
- Deep and Premium remain Gemini Deep Research paths.
- Explicit vendor-research refreshes still require their supported direct
  provider path.
- The curated recipe is cost-governed and hermetically tested, but it remains
  labeled preview until representative full-report quality evaluation supports
  promotion.

For the general key and approval rules, see [API Key Setup](API_KEYS.md) and
[Run Modes and Costs](RUN_MODES.md).
