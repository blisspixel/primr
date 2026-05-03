# Model Onboarding

How to add a new model to primr — Grok, Gemini, Claude, OpenAI, or any future
provider — without breaking the cost estimator, the pipeline circuit breakers,
or the eval harness.

The single source of truth for every model is `src/primr/config/models.py`.
Everything downstream — pricing, fallback chains, dry-run estimates, eval
profiles, doctor checks — derives from that file. If you only update one place,
update the registry there and let the rest follow.

This playbook is intentionally short. Each step is a checkbox you should be
able to tick off without guessing. The worked example at the bottom is the
April 2026 Grok 4.3 onboarding.

---

## The five-step process

### 1. Verify identity against the live provider API

Don't trust blog posts or third-party pricing pages. Hit the provider's
`/models` endpoint with a real API key and confirm the **exact model ID**,
plus whether reasoning / non-reasoning / fast variants exist.

For xAI:

```bash
curl -H "Authorization: Bearer $XAI_API_KEY" https://api.x.ai/v1/models
```

For Google:

```bash
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY"
```

Capture: model ID string, context window, max output tokens, multimodal
support, whether reasoning is always-on, and whether tiered or cached pricing
is published. If pricing isn't surfaced via the API, take it from the
provider's official docs page — never from third-party comparison sites.

### 2. Register the model in `ModelRegistry`

Add a `ModelConfig` entry alongside the existing siblings in
`src/primr/config/models.py`. Required fields:

- `name` — exact API ID returned by step 1
- `display_name` — human-friendly label used in dry-run output
- `provider` — `xai` / `google` / `anthropic` / `openai`
- `cost_per_1m_input_tokens`, `cost_per_1m_output_tokens` — base pricing
- `max_input_tokens`, `max_output_tokens`
- `supports_thinking`, `supports_tools`, `supports_multimodal`

Optional fields (use them when the provider publishes them — leave `None`
otherwise):

- `cost_per_1m_input_tokens_high`, `cost_per_1m_output_tokens_high`,
  `tier_threshold_tokens` — tiered pricing above a context threshold
- `cost_per_1m_input_tokens_cached` — discount rate for prompt-cache hits

Add the new entry to `PrimrModels.ALL_MODELS` in the same file so
`get_model_config`, `get_price`, and `calculate_cost` can find it.

If the new model is meant to **replace** an existing default, add a new
constant (e.g. `GROK_MODEL_43`) but keep the old constant
(`GROK_MODEL_420`) as a back-compat alias pointing at the legacy registration.
Don't delete the old registration — in-flight runs and resumed jobs read the
old model ID from `_run_state.json`.

### 3. Wire the model into the pipeline

Find every place the old model name is referenced and decide whether the new
model should replace it. The three routing surfaces are:

- `PrimrModels.get_grok_models(tier)` — returns `(reasoning_model, writing_model)`
  for `GrokTier.FAST` / `HYBRID` / `MAX`. Update this if the new model belongs
  in one of those tiers.
- `src/primr/pipeline/model_breaker.py::ANALYSIS_FALLBACK_CHAIN` (and
  `PREMIUM_FALLBACK_CHAIN`) — ordered tuples used by the model circuit breaker.
  Newer flagships go at the front, older flagships drop to the next position.
- **Utility-tier audit** — `src/primr/ai/llm.py::_get_model_for_type` resolves
  utility-tier calls (scraping summaries, link selection, generic "fast"
  tasks) based on which provider key is set. When you onboard a new
  flagship for the analysis tier, ask whether the new provider also has a
  cheap-and-cheerful SKU that could replace the utility-tier model from a
  different provider. A standard pipeline that requires keys from multiple
  providers is fragile: a hang on the cheap utility call stalls the whole
  run even when the flagship is healthy. The April 2026 Grok 4.3 onboarding
  surfaced exactly this — a stalled Gemini Flash link-selection call hung
  the rerun until utility-tier dispatch was rewired to use Grok 4.1 NR
  (cheaper than Gemini Flash anyway).

Also grep for the legacy model ID across the codebase:

```bash
grep -rn "grok-4\.20\|GROK_MODEL_420" src/ tests/ docs/
```

Decide for each hit whether it should switch. For test fixtures that just
need *a* registered model, leave them alone — they're testing breaker logic,
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

Decision criteria — write these down before you look at the scorecard:

- Utility-per-dollar must be ≥ the current default
- Hallucination rate (judge overlay) must be ≤ the current default
- Drift markers (`**What to validate:` leakage etc.) must not regress

Only flip the default in step 3 (or `PrimrModels.GROK_MODEL_43` etc.) once
those criteria pass. If they don't, leave the new model registered but not
default — the eval result is the artifact, the model stays available behind
an explicit flag for users who want to opt in.

---

## Adding a new provider (OpenAI, Ollama, Anthropic, …)

The five-step process above covers adding a *model* under a provider primr
already speaks. Adding a whole new *provider* is a different shape: it
goes through the provider abstraction in `src/primr/ai/providers/`. The
work splits into two cases.

### Case A: OpenAI-compatible endpoint (OpenAI itself, Ollama, vLLM, llama.cpp)

These providers all expose `POST /v1/chat/completions` with the OpenAI
message schema. Onboarding is mostly registry edits, no new client class:

1. **Add a `ProviderEntry`** to `KNOWN_PROVIDERS` in
   `src/primr/ai/providers/registry.py` with the provider's name, env var,
   description, and roles.
2. **Add a branch to `build_provider`** that constructs an
   `OpenAICompatibleProvider` with the right `base_url`,  `api_key_env`,
   and (for Ollama) an `api_key_default` placeholder so the SDK doesn't
   reject unset keys.
3. **Add model entries** for each model you want to call in
   `src/primr/config/models.py` (`ModelRegistry`). Set `provider="openai"`
   /`"ollama"`/etc. and add the entry to `ALL_MODELS`.
4. **Add a routing branch** in `primr.ai.routing.get_provider_for_model`
   that maps the new provider name to the right singleton accessor.
5. **Decide role policy** in `pick_model_for_role` — should the utility
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
   shape — the abstraction is intentionally permissive.
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
- Returns `ChatResponse(text, input_tokens, output_tokens)`
- Retry/backoff on transient errors
- `QuotaExhausted` for daily quota
- `is_available()` reports whether the env key is set
- Per-model usage accounting via `get_usage_by_model()`

Not normalized — passed through as `**provider_kwargs`, providers ignore
what they don't recognize:

- Gemini `thinking_level` (low/high)
- Anthropic `cache_control` blocks, `extended_thinking_budget`
- OpenAI `reasoning_effort`, `response_format`
- xAI / OpenAI-compatible: `top_p`, `seed`, `stop`, etc.

This is deliberate: a lowest-common-denominator API would lose features
that matter (Gemini's deep thinking, Anthropic's cache control). Callers
that need a provider-specific feature pass the kwarg; callers that don't
care get a clean, uniform interface.

## Doc updates

When the default changes, update these in the same PR so the docs stay
coherent with the code:

- `README.md` — modes table cost figures, headline cost in the lede
- `CLAUDE.md` — Quick Start cost line, agent-facing cost guidance
- `ROADMAP.md` — strike through the "evaluate new model" entry, add a
  `Changelog` line
- `docs/ARCHITECTURE.md` — model-pricing table if present

---

## Worked example: Grok 4.3 (April 2026)

xAI released `grok-4.3` on 2026-04-30 with always-on reasoning, $1.25/$2.50
pricing, $0.20 cached input, 1M context, multimodal input. No `-fast` or
non-reasoning variant.

**Step 1 — verify**: `GET https://api.x.ai/v1/models` confirmed the API ID is
literally `grok-4.3`. The list contained no `grok-4.3-fast` or
`grok-4.3-non-reasoning`, validating the always-on-reasoning claim.

**Step 2 — register**: Added `GROK_4_3 = ModelConfig(...)` in
`src/primr/config/models.py`, including `cost_per_1m_input_tokens_cached=0.20`
and a placeholder high-tier (>200k) at 2× base until xAI publishes confirmed
rates. Added to `ALL_MODELS`. New constant `GROK_MODEL_43` introduced;
`GROK_MODEL_420` kept as legacy alias.

**Step 3 — wire**: `get_grok_models()` updated so `HYBRID = (4.3, 4.1-NR)` and
`MAX = (4.3, 4.3)`. `FAST` stays on 4.1. `ANALYSIS_FALLBACK_CHAIN` reordered
to `(4.3 → 4.20 → 4.1 → Flash)`. Cost-estimator labels updated from
"Grok 4.20 hybrid/max" to "Grok 4.3 hybrid/max".

**Step 4 — tests**: `test_cost_estimator.py` got six new assertions
(`test_grok_43_pricing`, `_tiered_pricing`, `_always_on_reasoning`,
`_in_all_models`, `_cache_discount`, plus updated tier-routing and
cost-range tests). Existing 4.20 tests rewritten to assert legacy behavior
(still registered, still works) rather than current default.

**Step 5 — eval**: Pending. Default flipped to 4.3 on vendor recommendation +
mechanical wiring; eval sweep is the next ROADMAP item before treating the
flip as confirmed. If the eval shows regression, revert the
`get_grok_models()` change and leave the registration in place.

**Open items**:

- High-tier (>200k) pricing for 4.3 is a placeholder. Confirm against
  console.x.ai billing and update.
- Hybrid still uses 4.1-NR for writing because 4.3 has no cheap NR variant
  and bulk-writing on 4.3 would multiply the per-token cost ~6×. Revisit
  when xAI ships a 4.3 fast or non-reasoning SKU.
- Prompt caching at $0.20/M is now wired into `calculate_cost` via
  `cached_input_tokens`, but the Grok client doesn't yet thread cache-hit
  counts back from the API response. Wiring that through is what makes the
  cache discount actually show up in `primr show-usage`.
