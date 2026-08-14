# Model Onboarding

How to add a new model to primr - Grok, Gemini, Claude, OpenAI, or any future
provider - without breaking the cost estimator, the pipeline circuit breakers,
or the eval harness.

The model data source of truth is `src/primr/config/model_registry.py`.
`src/primr/config/models.py` is the stable selection and cost facade and
re-exports registry symbols for compatibility. Pricing, fallback chains,
dry-run estimates, eval profiles, and doctor checks consume those two layers.

This playbook is intentionally short. Each step is a checkbox you should be
able to tick off without guessing. The worked example at the bottom is the
April 2026 Grok 4.3 onboarding.

---

## The five-step process

### 1. Verify identity against official provider sources

Do not trust blog posts, search snippets, or third-party pricing pages. Start
with the provider's current model page, pricing page, and API reference. Record
the exact canonical model ID, aliases, context and output limits, supported API
shape, reasoning controls, tool support, storage defaults, and all token, cache,
long-context, and tool-call prices.

An authenticated `/models` request is an optional availability check. It proves
what the current account can see, not the model's capabilities or pricing. It
must remain an auth-only preflight and must not generate tokens.

For xAI:

```bash
curl -H "Authorization: Bearer $XAI_API_KEY" https://api.x.ai/v1/models
```

For Google:

```bash
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY"
```

For OpenAI:

```bash
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
```

Capture: model ID string, context window, max output tokens, multimodal
support, whether reasoning is always-on, and whether tiered or cached pricing
is published. If pricing isn't surfaced via the API, take it from the
provider's official docs page - never from third-party comparison sites.

### 2. Register the model in `ModelRegistry`

Add a `ModelConfig` entry alongside the existing siblings in
`src/primr/config/model_registry.py`. Required fields:

- `name` - exact API ID returned by step 1
- `display_name` - human-friendly label used in dry-run output
- `provider` - `xai` / `google` / `anthropic` / `openai`
- `cost_per_1m_input_tokens`, `cost_per_1m_output_tokens` - base pricing
- `max_input_tokens`, `max_output_tokens`
- `supports_thinking`, `supports_tools`, `supports_multimodal`

Optional fields (use them when the provider publishes them - leave `None`
otherwise):

- `cost_per_1m_input_tokens_high`, `cost_per_1m_output_tokens_high`,
  `tier_threshold_tokens` - tiered pricing above a context threshold
- `cost_per_1m_input_tokens_cached` - discount rate for prompt-cache hits
- `price_change_date`, `cost_per_1m_input_tokens_after`,
  `cost_per_1m_output_tokens_after`, and
  `cost_per_1m_input_tokens_cached_after` - a provider-published future price
  change that must take effect by pricing date without a code release

The estimator consumes these fields through
`PrimrModels.calculate_cost_breakdown()`. Keep the registry explicit: if a
provider publishes long-context, cache-read, or cache-write economics, record
the read and tier metadata before using the model in a default route. Do not
assume prompt-cache savings in dry-run output unless historical usage records
show cached input tokens for that mode.

Add the new entry to `PrimrModels.ALL_MODELS` in
`src/primr/config/models.py` so
`get_model_config`, `get_price`, and `calculate_cost` can find it.

If the new model is meant to **replace** an existing default, add a new
constant (e.g. `GROK_MODEL_43`) but keep the old constant
(`GROK_MODEL_420`) as a back-compat alias pointing at the legacy registration.
Don't delete the old registration - in-flight runs and resumed jobs read the
old model ID from `_run_state.json`.

### 3. Wire the model into the pipeline

Find every place the old model name is referenced and decide whether the new
model should replace it. The three routing surfaces are:

- `PrimrModels.get_grok_models(tier)` - returns `(reasoning_model, writing_model)`
  for `GrokTier.FAST` / `HYBRID` / `MAX`. Update this if the new model belongs
  in one of those tiers.
- `src/primr/pipeline/model_breaker.py::ANALYSIS_FALLBACK_CHAIN` (and
  `PREMIUM_FALLBACK_CHAIN`) - ordered tuples used by the model circuit breaker.
  Newer flagships go at the front, older flagships drop to the next position.
- **Utility-tier audit** - `src/primr/ai/llm.py::_get_model_for_type` resolves
  utility-tier calls (scraping summaries, link selection, generic "fast"
  tasks) based on which provider key is set. When you onboard a new
  flagship for the analysis tier, ask whether the new provider also has a
  cheap-and-cheerful SKU that could replace the utility-tier model from a
  different provider. A standard pipeline that requires keys from multiple
  providers is fragile: a hang on the cheap utility call stalls the whole
  run even when the flagship is healthy. The April 2026 Grok 4.3 onboarding
  surfaced exactly this - a stalled Gemini Flash link-selection call hung
  the rerun until utility-tier dispatch was rewired to the then-current Grok
  4.1 NR. The current utility primary is the dated Grok 4.20 non-reasoning
  model, so treat the 4.1 example as onboarding history rather than live
  routing guidance.

Also grep for the legacy model ID across the codebase:

```bash
rg -n "grok-4\.20|GROK_MODEL_420" src tests docs
```

Decide for each hit whether it should switch. For test fixtures that just
need *a* registered model, leave them alone - they're testing breaker logic,
not naming conventions.

### 4. Add validation tests

In `tests/test_utils/test_cost_estimator.py`, add (at minimum):

- A pricing assertion: `ModelRegistry.NEW_MODEL.cost_per_1m_input_tokens == X`
- An always-on / reasoning assertion if applicable
- A tiered-pricing assertion if the model is tiered
- A cache-discount assertion: `calculate_cost(name, ..., cached_input_tokens=N)
  < calculate_cost(name, ...)` if the model has a published cache rate
- A `get_grok_models(tier)` assertion for whichever tier the new model lives in
- An updated cost-range test for any tier whose price moved

Then run the focused suite:

```bash
python -m pytest tests/test_utils/test_cost_estimator.py \
                 tests/test_pipeline/test_model_breaker.py \
                 tests/test_ai/ -x --tb=short -q
```

A model upgrade should never need test changes outside cost / model_breaker /
ai tests. If it does, you're probably refactoring something else by accident.

### 5. Eval-gate the promotion

Don't promote a new model to default on vendor-recommendation alone. Run the
existing eval harness on the standard 3-5 company corpus and let the
scorecard decide.

```bash
# Generate reports under three labelled folders
primr "Acme Corp" https://acme.com --grok-tier hybrid --output-dir eval_corpus/hybrid
primr "Acme Corp" https://acme.com --grok-tier max --output-dir eval_corpus/max
# (after wiring the new model, regenerate the same companies)

# Score them
primr eval --eval-root eval_corpus
```

Decision criteria - write these down before you look at the scorecard:

- Utility-per-dollar must be ≥ the current default
- Hallucination rate (judge overlay) must be ≤ the current default
- Drift markers (`**What to validate:` leakage etc.) must not regress

Only flip the default in step 3 (or `PrimrModels.GROK_MODEL_43` etc.) once
those criteria pass. If they don't, leave the new model registered but not
default - the eval result is the artifact, the model stays available behind
an explicit flag for users who want to opt in.

For utility-stage backend-freedom work, route promotions should also flow
through `ai/stage_routing.py` and the declared row in
`core/stage_inventory.py`. The current runtime pilots are
`fast.scrape_summary`, `fast.source_relevance`, and `fast.hiring_signals`
behind `--inference cloud|hybrid`; they record capped body-free
`stage_routes` entries in `_run_state.json`. Do not add a stage-local provider
dispatch path to test a new model, and do not infer
actual token/cache/cost fields until provider usage seams expose stage-scoped
counters.

---

## Adding a new provider (OpenAI, Ollama, Anthropic, …)

The five-step process above covers adding a *model* under a provider primr
already speaks. Adding a whole new *provider* is a different shape: it
goes through the provider abstraction in `src/primr/ai/providers/`. The
work splits into two cases.

### Case A: OpenAI SDK-compatible endpoint

Primr supports two transport shapes through this family. Direct OpenAI and xAI
use `POST /v1/responses`; local Ollama, vLLM, llama.cpp, and similar servers use
`POST /v1/chat/completions` unless that backend has verified Responses support.
The normalized `messages` input is translated at the adapter boundary.

1. **Add a `ProviderEntry`** to `KNOWN_PROVIDERS` in
   `src/primr/ai/providers/registry.py` with the provider's name, env var,
   description, and roles.
2. **Add a branch to `build_provider`** that constructs an
   `OpenAICompatibleProvider` with the right `base_url`, `api_key_env`, and
   explicit `api_style`. Use `responses` only after the provider is verified to
   implement its request and response contract. For Ollama, set an
   `api_key_default` placeholder so the SDK does not reject an unset key.
3. **Add model entries** for each model you want to call in
   `src/primr/config/models.py` (`ModelRegistry`). Set `provider="openai"`
   /`"ollama"`/etc. and add the entry to `ALL_MODELS`.
4. **Add a routing branch** in `primr.ai.routing.get_provider_for_model`
   that maps the new provider name to the right singleton accessor.
5. **Decide role policy** in `pick_model_for_role` - should the utility
   tier prefer the new provider over Grok/Gemini when its key is set?
   This is where multi-provider preference order lives.

### Case B: Different SDK shape (Anthropic Claude)

Anthropic's Messages API uses different field names (`system` is
top-level, `cache_control` blocks, etc.). It needs its own provider class.

1. **Write `src/primr/ai/providers/anthropic.py`** with an
   `AnthropicProvider(Provider)` class that translates the OpenAI-shape
   `messages` list into Anthropic's format and calls the SDK.
2. **Implement `chat()`** to return a `ChatResponse`. Pass through
   provider-specific kwargs (`cache_control`, `extended_thinking_budget`)
   via `**provider_kwargs`. Don't try to flatten them into a generic
   shape - the abstraction is intentionally permissive.
3. **Raise `QuotaExhausted`** for daily-limit errors so callers can add
   UI without reaching into provider internals.
4. **Wire into the registry** the same way as Case A: a `ProviderEntry`,
   a `build_provider` branch, and a routing branch.
5. **Add a test file** alongside `test_providers.py` covering message
   translation, retry behavior, and quota classification.

### What the abstraction normalizes vs. doesn't

Normalized (every provider returns the same shape, supports the same
interface):

- `chat(messages, *, model, temperature, max_tokens, retries, **kwargs)`
- Returns `ChatResponse` with text, input/output tokens, cached input, and any
  available exact cost or response-status metadata
- Retry/backoff on transient errors
- `QuotaExhausted` for daily quota
- `is_available()` reports whether the env key is set
- Per-model usage accounting via `get_usage_by_model()`

Not normalized - passed through as `**provider_kwargs`, providers ignore
what they don't recognize:

- Gemini `thinking_level` values supported by the selected model
- Anthropic `cache_control` blocks, `extended_thinking_budget`
- OpenAI/xAI `reasoning_effort`, tools, storage policy, and normalized
  `response_format` (translated to Responses `text.format` on the wire)
- Chat Completions backends: `top_p`, `seed`, `stop`, and related controls

This is deliberate: a lowest-common-denominator API would lose features
that matter (Gemini's deep thinking, Anthropic's cache control). Callers
that need a provider-specific feature pass the kwarg; callers that don't
care get a clean, uniform interface.

Request compatibility is still model-specific. Every selectable Gemini path
must use the shared sampling-capability policy so 3.5 Flash-Lite, 3.6 Flash,
3.7 Flash, and later families do not receive removed `temperature`, `top_p`,
or `top_k` fields. Convert only model-supported thinking levels through the
SDK enum and test direct clients as well as the provider adapter before adding
an eval profile.

## Doc updates

When the default changes, update these in the same PR so the docs stay
coherent with the code:

- `README.md` - modes table cost figures, headline cost in the lede
- `CLAUDE.md` - Quick Start cost line, agent-facing cost guidance
- `ROADMAP.md` - strike through the "evaluate new model" entry, add a
  `Changelog` line
- `docs/ARCHITECTURE.md` - model-pricing table if present

---

## Worked example: Grok 4.3 (April 2026)

xAI released `grok-4.3` on 2026-04-30 with configurable reasoning effort,
$1.25/$2.50 pricing, $0.20 cached input, 1M context, and multimodal input.

**Step 1 - verify**: xAI's official
[Grok 4.3 model page](https://docs.x.ai/developers/models/grok-4.3) and
[pricing table](https://docs.x.ai/developers/pricing) confirm the API ID,
reasoning-effort controls, context, and current pricing. Model availability in
a specific account remains a credential-scoped preflight fact.

**Step 2 - register**: Added `GROK_4_3 = ModelConfig(...)` in
`src/primr/config/model_registry.py`, including the published $0.20 cached-input
rate and inclusive >=200k prices of $2.50 input, $0.40 cached input, and $5.00
output per million tokens. Added it to `ALL_MODELS` and introduced
`GROK_MODEL_43`; `GROK_MODEL_420` remains a compatibility constant for the
dated Grok 4.20 reasoning ID.

**Step 3 - wire**: `get_grok_models()` now maps FAST and HYBRID to Grok 4.3
reasoning plus `grok-4.20-non-reasoning` writing, while MAX maps to
`(4.5, 4.5)` as a version-pinned opt-in. FAST uses lower reasoning effort. See
`docs/design/grok-default-routing.md`. `ANALYSIS_FALLBACK_CHAIN` reordered
to `(4.3 → 4.20 → 4.1 → Flash)` historically; current analysis fallback prefers
`4.3 → 4.5 → 4.20` (see `docs/design/grok-default-routing.md`). Cost-estimator
labels: hybrid stays **Grok 4.3 hybrid**; `--grok-tier max` is **Grok 4.5 max**.

**Step 4 - tests**: `test_cost_estimator.py` got six new assertions
(`test_grok_43_pricing`, `_tiered_pricing`, `_always_on_reasoning`,
`_in_all_models`, `_cache_discount`, plus updated tier-routing and
cost-range tests). Existing 4.20 tests rewritten to assert legacy behavior
(still registered, still works) rather than current default.

**Step 5 - eval**: Pending. Default flipped to 4.3 on vendor recommendation +
mechanical wiring; eval sweep is the next ROADMAP item before treating the
flip as confirmed. If the eval shows regression, revert the
`get_grok_models()` change and leave the registration in place.

**Current follow-up**:

- The published inclusive >=200k tier is represented in the registry and cost
  tests.
- Hybrid writing uses the current `grok-4.20-non-reasoning` alias when Gemini
  is unavailable. With Gemini configured, routed Flash-Lite writing remains
  the measured lower-cost path.
- The Responses adapters normalize cached-input usage. xAI's
  `cost_in_usd_ticks` is the exact-cost authority when present; registry token
  pricing remains the conservative fallback.
