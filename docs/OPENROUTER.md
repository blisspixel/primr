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

To route the standard pipeline to OpenRouter even when other provider keys
are configured in the environment, set:

```dotenv
PRIMR_PROVIDER=openrouter
```

Then inspect the exact plan before any billable run:

```bash
primr "ExampleCo" https://example.co --dry-run --budget 10
```

The dry run remains network-free and makes no model calls. Normal terminal
execution still asks for confirmation. Automation may use `--skip-confirm`
only after a person has reviewed and approved that fresh quote. MCP and A2A
use the same estimate-bound approval and cost-cap contract.

## Set a per-run ceiling

`--budget` is a maximum for one Primr run. It is not a spending target and does
not approve the run. For example:

```bash
primr "ExampleCo" https://example.co --dry-run --budget 10
```

The human preview shows the $10 ceiling, the estimate, and whether the plan is
within the ceiling. The JSON preview exposes the same decision:

```json
{
  "provider_ready": true,
  "execution_ready": true,
  "budget_enforcement": {
    "ceiling_usd": 10.0,
    "estimated_cost_usd": 1.05,
    "within_budget": true
  }
}
```

The shown cost is illustrative. The live dry run is authoritative. If the
estimate exceeds the ceiling, `execution_ready` and `within_budget` are false,
and launch refuses before model calls. A valid ceiling is a finite positive
number.

Primr rechecks the same estimate when execution begins and activates runtime
accounting at the supplied ceiling. Fast Standard runs checkpoint before
optional spend stages. A model request that has already started cannot be
stopped at an exact token boundary, so use a conservative ceiling and also put
an independent spending limit on the dedicated OpenRouter key. OpenRouter key
or organization limits reset according to their OpenRouter configuration and
are separate from Primr's per-run ceiling.

After reviewing the fresh estimate, launch in a foreground terminal by removing
`--dry-run`; Primr will still ask for confirmation. Approved noninteractive
automation may also add `--skip-confirm`. Never treat the key, the routing
opt-in, the ceiling, or an earlier quote as approval by itself.

## Curated model catalog and default recipe

The default OpenRouter route uses a balanced role recipe:

| Role | Default model | Input / output per 1M tokens |
|------|---------------|-------------------------------|
| Utility | `google/gemini-2.5-flash-lite` | `$0.10 / $0.40` |
| Writing | `openai/gpt-4.1-mini` | `$0.40 / $1.60` |
| Reasoning | `deepseek/deepseek-v3.2` | `$0.269 / $0.40` |

The default full report plus AI Strategy is currently estimated at about
`$1.05` on Primr's conservative static token plan. The command's live dry-run
is authoritative because selected features, token plans, pricing, and
historical floors can change.

### Expanded curated catalog

Primr supports an expanded set of pre-priced, verified models through OpenRouter:

| Provider / Family | Model identifier | Input / output per 1M tokens | Role suitability |
|---|---|---|---|
| Google | `google/gemini-3.8-flash` | `$0.75 / $3.75` | Writing, Reasoning |
| Google | `google/gemini-3.7-flash` | `$0.75 / $3.75` | Writing, Reasoning |
| Google | `google/gemini-3.1-flash-lite` | `$0.25 / $1.50` | Utility, Writing |
| Google | `google/gemini-2.5-flash-lite` | `$0.10 / $0.40` | Utility |
| OpenAI | `openai/gpt-5.4-mini` | `$0.75 / $4.50` | Writing, Utility |
| OpenAI | `openai/gpt-5.4-nano` | `$0.20 / $1.25` | Utility |
| OpenAI | `openai/gpt-4.1-mini` | `$0.40 / $1.60` | Writing |
| Anthropic | `anthropic/claude-sonnet-4.6` | `$3.00 / $15.00` | Reasoning |
| Anthropic | `anthropic/claude-haiku-4.5` | `$1.00 / $5.00` | Writing, Utility |
| DeepSeek | `deepseek/deepseek-v3.2` | `$0.269 / $0.40` | Reasoning |
| DeepSeek | `deepseek/deepseek-chat` | `$0.27 / $0.40` | Reasoning, Writing |
| DeepSeek | `deepseek/deepseek-r1` | `$0.55 / $2.19` | Reasoning |
| Meta | `meta-llama/llama-3.3-70b-instruct` | `$0.12 / $0.30` | Utility |

### Granular role overrides

You can configure specific models for individual pipeline roles without modifying code:

```dotenv
PRIMR_OPENROUTER_UTILITY_MODEL=google/gemini-3.1-flash-lite
PRIMR_OPENROUTER_WRITING_MODEL=google/gemini-3.8-flash
PRIMR_OPENROUTER_REASONING_MODEL=anthropic/claude-sonnet-4.6
```

All selected models must exist in Primr's catalog or be registered with explicit pricing.

## Request safeguards

Every OpenRouter generation request:

- applies the registered input and output rates as OpenRouter `max_price`
  ceilings;
- requires routed providers to support requested parameters by default;
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

### Privacy and parameter tuning

Some models may have no provider that satisfies both price and privacy policies
simultaneously, or may reject non-standard parameters:

- To allow non-ZDR providers explicitly while still denying providers that
  collect data, set `PRIMR_OPENROUTER_ZDR=0`. Review that privacy tradeoff
  before doing so.
- For models that ignore optional parameters (such as custom temperature on
  certain reasoning endpoints), set `PRIMR_OPENROUTER_REQUIRE_PARAMS=0` to
  prevent OpenRouter from dropping eligible endpoints.

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
