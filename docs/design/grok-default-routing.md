# Default model routing (current flagships)

Decision record for which models Primr uses by default, why each tier stays
version-pinned, and how the defaults move when providers ship new models.

## Decision update (2026-10-28, supersedes the binding decision below)

The project owner directed that defaults track each provider's current
flagship instead of waiting for a paid quality comparison per release. This is
an owner decision, not a measured promotion: report quality on the new
defaults has not been scored against the previous ones.

Sources checked on 2026-10-28: the xAI, Gemini, OpenAI, and Claude model
catalogs, OpenAI pricing and deprecations, and the OpenRouter models API.

| Role | Previous default | Current default |
|------|------------------|-----------------|
| Grok reasoning, every tier | `grok-4.3` (MAX: `grok-4.5`) | `grok-4.7` |
| Grok writing, FAST and HYBRID | `grok-4.20-non-reasoning` | unchanged (xAI's only non-reasoning model) |
| Gemini Flash (utility) | `gemini-3-flash-preview` | `gemini-3.8-flash` (stable) |
| Gemini Pro (reasoning, premium) | `gemini-3.1-pro-preview` | `gemini-4-argon` (stable) |
| Gemini writing | `gemini-3.1-flash-lite` | `gemini-3.5-flash-lite` |
| OpenAI utility and writing | `gpt-5.4-nano` | `gpt-6-luna` |
| OpenAI reasoning | `gpt-5.6-terra` | `gpt-6.1-terra` |
| Anthropic utility and writing | `claude-haiku-4-5` | `claude-haiku-5-5` |
| Anthropic reasoning | `claude-sonnet-5` | `claude-sonnet-5-5` |
| OpenRouter utility / writing / reasoning | `google/gemini-3.1-flash-lite` / `openai/gpt-4.1-mini` / `deepseek/deepseek-v3.2` | `google/gemini-3.5-flash-lite` / `openai/gpt-6-luna` / `deepseek/deepseek-v4.1-flash-1017` |
| LLM judge | `grok-4.3` | `grok-4.7` |

Free estimator dry-runs (complete mode, no historical cache), before and after:

| Keys | Before | After |
|------|--------|-------|
| xAI + Gemini, HYBRID | $0.76 ($0.89 with AI Strategy) | $1.05 ($1.24) |
| xAI + Gemini, MAX | $8.53 ($9.93) | $8.53 ($9.93) |
| xAI only | $5.09 | $5.18 |
| Gemini only | $0.89 | $1.07 |
| OpenAI only | $1.05 | $1.24 |
| Anthropic only | $4.71 | $3.20 |
| Premium | $4.21 | $4.14 |

This is the documented price-floor change the promotion path below allows:
the HYBRID default moves from about $0.76 to about $1.05. About $0.20 comes
from Gemini 3.5 Flash-Lite writing output ($2.50 versus $1.50 per 1M) and
about $0.11 from Grok 4.7 reasoning. Gemini 4 Argon rates rise to $4/$20 on
2026-12-01 and Gemini 3.8 Flash to $1.50/$7.50 on 2027-01-01; estimates now
disclose such scheduled changes so an approval made before the date is not
silently repriced. Grok 4.7 has a 500k context window, half of Grok 4.3's,
so the analysis fallback chain keeps Grok 4.3 as its 1M-context second step.

Rules that still hold: tiers name exact versions, never provider aliases;
superseded models stay registered and priced for historical accounting and
explicit selection; retired models are marked unavailable with their
replacement; and `tests/test_ai/test_routing.py` fails if any key combination
routes a default role to a model outside the current flagship set. The
historical record below explains the earlier eval-gated policy.

## Context

xAI shipped **Grok 4.6** (API id `grok-4.6`) on August 12, 2026 as its current
flagship. Primr had already standardized on **Grok 4.3** for hybrid reasoning
after the v1.24.0 cross-provider eval (sub-$1 default with Gemini writing), and
had pinned the explicit MAX tier to **Grok 4.5**.

The README demo shows a dry-run for **“Grok 4.3 hybrid”**. That is intentional:
it matches the default CLI path, not the newest marketing model.

## API currency checkpoint (2026-08-13)

Official sources reviewed before any paid comparison:

- [xAI model catalog](https://docs.x.ai/developers/models) and
  [Grok 4.6 model card](https://docs.x.ai/developers/grok-4-6)
- [xAI pricing](https://docs.x.ai/developers/pricing),
  [cost tracking](https://docs.x.ai/developers/cost-tracking), and
  [rate limits](https://docs.x.ai/developers/rate-limits)
- [Responses migration](https://docs.x.ai/developers/model-capabilities/text/comparison),
  [prompt cache affinity](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/maximizing-cache-hits),
  and [data retention](https://docs.x.ai/developers/faq/security)
- [Gemini latest models](https://ai.google.dev/gemini-api/docs/latest-model),
  [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview),
  and [Deep Research](https://ai.google.dev/gemini-api/docs/deep-research)
- [OpenAI model catalog](https://developers.openai.com/api/docs/models),
  [GPT-5.6 guidance](https://developers.openai.com/api/docs/guides/latest-model),
  and the [Responses API](https://developers.openai.com/api/docs/guides/responses)

The resulting transport contract is explicit:

1. Normal xAI text generation uses Responses, not deprecated Chat
   Completions. Independent calls set `store=false`; Primr does not need
   provider-side response retrieval for them.
2. Continuous sessions send full explicit history and a per-session
   `prompt_cache_key`. They do not depend on server-side state, so local run
   artifacts remain the recovery authority.
3. xAI `cost_in_usd_ticks` is recorded as exact billed cost. Token pricing is
   retained as the conservative fallback if any call omits exact cost.
4. Primr honors provider retry guidance with bounded exponential backoff,
   jitter, and `Retry-After`; billing exhaustion remains non-retryable.
5. Gemini Deep Research already uses background Interactions and File Search.
   Direct Gemini generation may migrate from supported legacy
   `generateContent` separately, with behavior tests rather than as an
   incidental change to the paid quality baseline.
6. OpenAI text generation uses Responses with `store=false`. GPT-5.6
   Sol/Terra/Luna and the `gpt-5.6` Sol alias are registered at current pricing
   as evaluation candidates; existing OpenAI production routing remains pinned
   until a representative comparison supports promotion.

## Measured dry-run (local estimator, Aug 2026)

Keys = `XAI_API_KEY` + `GEMINI_API_KEY`, mode = complete/full, no historical cache:

| Tier | Model shape | Approx total |
|------|-------------|--------------|
| `fast` / `hybrid` (default) | 4.3 reasoning + Gemini Flash-Lite writing + Gemini Flash utility | **~$0.76** |
| `max` | 4.5 for every Grok-priced stage | **~$8.53** |

xAI-only (no Gemini) hybrid is ~$5.09; max is still ~$8.53.

Published list prices (docs.x.ai):

| Model | In / out (per 1M) | Context | Cached in (base) |
|-------|-------------------|---------|------------------|
| `grok-4.3` | $1.25 / $2.50 (≥200k: $2.50 / $5.00) | 1M | $0.20 |
| `grok-4.20` variants | $1.25 / $2.50 (>=200k: $2.50 / $5.00) | 1M | $0.20 (>=200k: $0.40) |
| `grok-4.5` | $2.00 / $6.00 (>=200k: $4.00 / $12.00) | 500k | $0.30 (>=200k: $0.60) |
| `grok-4.6` | $2.00 / $6.00 (>=200k: $4.00 / $12.00) | 500k | $0.50 (>=200k: $1.00) |

4.5 is roughly **1.6× input / 2.4× output** versus 4.3 at the standard tier,
with a **smaller** context window. MAX is expensive mainly because it routes
**writing** through Grok as well, not only reasoning.

## Decision (2026-08, superseded on 2026-10-28)

1. **Default hybrid/fast reasoning stays `grok-4.3`.** The product promise is a
   cost-aware brief with an honest dry-run, not “always the newest flagship.”
2. **`--grok-tier max` remains pinned to `grok-4.5`.** MAX is an explicit,
   versioned production route, not an alias that changes when a provider ships
   a model. Re-estimate before spend.
3. **`grok-4.6` is registered as available but is not routed automatically.**
   This keeps dry-run and output behavior stable while making the current model
   available to the evaluation harness.
4. **Do not promote 4.5 or 4.6 to hybrid or MAX without an eval gate.**
   [`MODEL_ONBOARDING.md`](../MODEL_ONBOARDING.md) step 5 still applies:
   utility-per-dollar ≥ current default, hallucination/drift not worse.
5. **Demo / README** keep “Grok 4.3 hybrid.” Showing a flagship on the default demo
   would misrepresent cost and routing.

## Why this is not “stale”

xAI recommends 4.6 for general code and knowledge work, but provider recency is
not evidence of Primr report quality. Primr's heavy stages are long-form
research writing and cross-validation with large prompts. The 4.6 cached-input
rate is higher than 4.5, and both become substantially more expensive at the
200k boundary. Silent model aliases would make estimates and reproducibility
less trustworthy.

## Promotion path (when quality justifies it)

1. Use the registered `grok46-flashlite` profile: 4.6 reasoning plus Gemini
   Flash-Lite writing, not max-everywhere.
2. Run the standing company corpus: hybrid (4.3) vs candidate (4.6 reasoning)
   with the same keys and mode; score with `primr eval`.
3. Pre-commit criteria:
   - End-to-end dry-run still within the product’s “default under ~$1”
     envelope **or** a deliberate, documented price floor change.
   - Trust / calibration / leakage metrics ≥ current hybrid.
4. Only then flip `GROK_MODEL` / hybrid `get_grok_models` and refresh the demo.

Until that passes, 4.6 remains a registered candidate. Grok 4.5 remains the
MAX and analysis-fallback pin, not a claim that it is the newest model.

## Explicitly not

- Silent default swap because a screenshot said “4.3.”
- Treating "newest xAI model" as the hybrid or MAX route without cost evidence.
- Using MAX-everywhere cost (~$8+) as the public default estimate.
- Region or account availability assumptions without checking the operator's
  visible model list.

## Validation cost

- Free: registry unit tests, estimator tier labels, architecture ceilings.
- Paid: any hybrid-versus-4.6 reasoning eval on real companies. It shares the
  current $25 aggregate evaluation ceiling unless the operator explicitly
  authorizes a later, separate campaign. Never run it merely because the model
  was registered.
