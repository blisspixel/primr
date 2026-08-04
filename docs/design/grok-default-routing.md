# Grok default routing (4.3 hybrid vs 4.5 flagship)

Decision record for which xAI model primr uses by default, and when operators
opt into Grok 4.5.

## Context

xAI shipped **Grok 4.5** (API id `grok-4.5`, July 2026) as its coding/agentic
flagship. Primr had already standardized on **Grok 4.3** for hybrid reasoning
after the v1.24.0 cross-provider eval (sub-$1 default with Gemini writing).

The README demo shows a dry-run for **“Grok 4.3 hybrid”**. That is intentional:
it matches the default CLI path, not the newest marketing model.

## Measured dry-run (local estimator, Aug 2026)

Keys = `XAI_API_KEY` + `GEMINI_API_KEY`, mode = complete/full, no historical cache:

| Tier | Model shape | Approx total |
|------|-------------|--------------|
| `fast` / `hybrid` (default) | 4.3 reasoning + Gemini Flash-Lite writing + Gemini Flash utility | **~$0.76** |
| `max` | 4.5 for every Grok-priced stage | **~$8.53** |

xAI-only (no Gemini) hybrid is ~$1.03; max is still ~$8.53.

Published list prices (docs.x.ai):

| Model | In / out (per 1M) | Context | Cached in (base) |
|-------|-------------------|---------|------------------|
| `grok-4.3` | $1.25 / $2.50 (≥200k: $2.50 / $5.00) | 1M | $0.20 |
| `grok-4.5` | $2.00 / $6.00 (≥200k: $4.00 / $12.00) | 500k | $0.30 |

4.5 is roughly **1.6× input / 2.4× output** versus 4.3 at the standard tier,
with a **smaller** context window. MAX is expensive mainly because it routes
**writing** through Grok as well, not only reasoning.

## Decision (binding until an eval flips it)

1. **Default hybrid/fast reasoning stays `grok-4.3`.** The product promise is a
   cost-aware brief with an honest dry-run, not “always the newest flagship.”
2. **`--grok-tier max` uses `grok-4.5` everywhere.** Explicit opt-in for latest
   flagship quality; re-estimate before spend.
3. **Do not promote 4.5 to hybrid default without an eval gate.**
   [`MODEL_ONBOARDING.md`](../MODEL_ONBOARDING.md) step 5 still applies:
   utility-per-dollar ≥ current default, hallucination/drift not worse.
4. **Demo / README** keep “Grok 4.3 hybrid.” Showing 4.5 on the default demo
   would misrepresent cost and routing.

## Why this is not “stale”

xAI’s own lineup treats 4.5 as the **coding/agent** flagship and 4.3 as the
**value** reasoning SKU. Primr’s heavy stages are long-form research writing
and cross-validation with large prompts—not interactive coding. Paying 4.5
rates on writing stages by default would abandon the measured sub-$1 recipe
for a model family xAI prices as a premium tier.

## Promotion path (when quality justifies it)

1. Add or reuse an eval profile (e.g. `grok45-flashlite`: 4.5 reasoning +
   Gemini Flash-Lite writing — **not** max-everywhere).
2. Run the standing company corpus: hybrid (4.3) vs candidate (4.5 reasoning)
   with the same keys and mode; score with `primr eval`.
3. Pre-commit criteria:
   - End-to-end dry-run still within the product’s “default under ~$1”
     envelope **or** a deliberate, documented price floor change.
   - Trust / calibration / leakage metrics ≥ current hybrid.
4. Only then flip `GROK_MODEL` / hybrid `get_grok_models` and refresh the demo.

Until that passes, 4.5 remains **registered + MAX tier + analysis fallback
after 4.3**, not the silent default.

## Explicitly not

- Silent default swap because a screenshot said “4.3.”
- Treating “newest xAI model” as the hybrid default without cost evidence.
- Using MAX-everywhere cost (~$8+) as the public default estimate.
- EU-only or region-gated assumptions without checking the operator’s key
  (4.5 availability can lag 4.3 in some consoles).

## Validation cost

- Free: registry unit tests, estimator tier labels, architecture ceilings.
- Paid: any hybrid-vs-4.5-reasoning eval on real companies (budget per
  [`eval-plan.md`](eval-plan.md); do not run without explicit approval).
