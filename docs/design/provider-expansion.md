# Provider Expansion: OpenAI, Anthropic, Billing-Verifiable Hosts, Gateways, and Local

Status: STARTED (provider pricing refreshed June 29, 2026; internal/eval-only
Codex transport and host-native plan handoff shipped)
ROADMAP anchor: Active Queue #26. Companion to
[`2.0-backend-freedom.md`](2.0-backend-freedom.md) (routing architecture);
this doc is the concrete provider catalog and delivery plan that routing
will route over.

## Principles (set by the operator, June 2026)

1. **No reason this must be Grok.** Grok + Gemini is the measured default,
   not a dependency. Every pipeline role (reasoning, writing, utility)
   should be servable by any provider whose models meet the role's bar.
2. **Support whatever someone has.** A user arrives with an OpenAI key, or
   an Anthropic key, or a corporate Bedrock/Foundry gateway, or sanctioned
   agent-host allocation, or just a gaming GPU and Ollama. Each of those should
   produce a report once its recipe is validated. Absence of any of them is
   silent, never an error.
3. **Account capacity is a first-class capacity source.** Sanctioned agent
   hosts should be evaluated as ways to spend capacity the user already has.
   They become Primr runners only through official automation, connector, CLI,
   hook, or agent-skill surfaces that can accept bounded stage packets and
   return structured outputs. They are never treated as hidden API keys or
   repo-owned accounts.
4. **Mac/Linux/Windows equally.** Local inference integrates over HTTP to
   OpenAI-compatible servers only; no platform-specific code. (vLLM has no
   Windows support; that is the server operator's concern, not primr's,
   because primr only speaks the protocol.)
5. **Latest models only.** June 2026 model generations below; never
   register a superseded model as a default. Re-verify IDs at
   implementation time against provider docs (the registry refresh is
   cheap; shipping stale defaults is not).
6. **Test the fit before the run.** Before any local model is used:
   verify the server is reachable, the model is actually installed, AND it
   fits currently-available memory (a one-token probe call; on a
   memory error, step down to the next-smaller candidate). Learned live:
   a 27B model that "exists" but needs 19.5 GiB when 11 GiB is free
   produces per-call failures, not a clean error.
7. **Default to least incremental spend that passes quality.** A free or
   billing-verifiable tier must exist, even if measurably worse and labeled that way.
   DDG search is already free, scraping is already local; with local inference
   the whole run is $0 API plus electricity, which changes what "run it on the
   whole portfolio" costs. For users already paying for an agent subscription,
   `primr-zero` is the supported plan-native path after the host is verified not
   to bill API usage or overages. An embedded host runner may join routing only
   when its billing basis can be proven or the operator explicitly acknowledges
   potentially metered API use. If no validated zero-incremental route is
   configured, the default should be the best validated sub-dollar direct API
   recipe. Premium recipes are opt-in and must document the marginal quality or
   coverage they buy.
8. **Caching must prove savings before it runs.** Provider prompt caching is a
   cost optimization only when a paid write is likely to be reused inside the
   provider's supported cache window. Do not enable cache writes, pre-warming,
   background refresh, keepalive requests, or long TTLs until the estimator
   accounts for write/read pricing and usage records expose cache reads and
   writes by provider.

## Current state (what already exists in the codebase)

- `Provider` ABC with xAI / Gemini / OpenAI / Anthropic / Ollama providers;
  `pick_model_for_role` falls through XAI > Gemini > OpenAI > Anthropic by
  key presence. OpenAI/Anthropic models ARE registered but from an older
  generation; they have never been validated as full-pipeline recipes.
- `OpenAICompatibleProvider` + `openai_compatible_client.chat_completion`
  (base-URL + key, retry/backoff): the seam Bedrock/Foundry/local all plug
  into.
- `ai/local_inference.py` (shipped with the calibration local judge):
  fail-open `/v1/models` detection, env-chain base URL, family-preference
  model pick. Missing: the memory fit-check from principle 5.
- Eval + calibration instruments (Version Plan step 1) to judge any new
  recipe honestly.
- `ai/capability_routing.py` now provides the first backend-freedom router
  slice: pure `StageRequirements` matching over supplied backend capability
  rows, profile-specific cloud/agent/hybrid/local ranking, host-runner opt-in
  checks, and API-credit handoff guards.
- `ai/stage_routing.py` now provides the first runtime bridge from declared
  production stages to the capability router. `fast.scrape_summary`,
  `fast.source_relevance`, and `fast.hiring_signals` use it behind
  `--inference cloud|hybrid`, append capped body-free `stage_routes` records
  to `_run_state.json`, and still execute through existing provider seams with
  the legacy utility models preserved as fallback.
- The typed host-account runner contract now exists in
  `ai/host_agent_runner.py`: bounded `HostAgentStagePacket`, billing policy,
  normalized result/provenance, and a prompt renderer that fences evidence with
  the existing content-sanitizer. The first concrete official-host process
  runner uses `codex exec` for an internal/eval-only
  `fast.source_relevance` pilot. The public CLI remains
  `--inference cloud|hybrid` because Codex authentication does not prove whether
  execution is plan-backed or API-key billed. Other stages still use their
  declared backends.
  Separately, `primr prep` plus `primr-zero` provides a host-native evidence
  handoff without passing subscription credentials into Primr. Neither path
  treats subscription credentials as interchangeable with API keys.

## Verified provider facts (June 29, 2026)

Full citations live in the research transcripts; key integration facts:

### OpenAI (direct)

- Models: `gpt-5.5` ($5/$30 per MTok, 1.05M ctx), `gpt-5.4` ($2.50/$15),
  `gpt-5.4-mini` ($0.75/$4.50), `gpt-5.4-nano` ($0.20/$1.25, 400K ctx).
  Registered GPT-5.x entries now include the current >270K long-context tier
  metadata so estimates can surface the surcharge. Reasoning depth via
  `reasoning.effort` (none..xhigh).
- Web search: `web_search` tool in the **Responses API**, $10 per 1k calls
  plus content tokens. Build new work on Responses; Chat Completions still
  supported, but the Assistants API retires 2026-08-26.
- Batch: flat 50%, 24h window, stacks with caching.
- Caching: automatic, cached input at 10% of base, no write surcharge,
  optional `prompt_cache_retention: "24h"`.
- Deep research: `o3-deep-research` / `o4-mini-deep-research` via Responses
  (a premium-mode alternative to Gemini Deep Research).

### Anthropic (direct)

- Models: `claude-fable-5` ($10/$50), `claude-opus-4-8` ($5/$25),
  `claude-sonnet-5` (Primr estimates $3/$15 post-intro; Anthropic launch
  pricing is $2/$10 through 2026-08-31), `claude-sonnet-4-6` ($3/$15,
  explicit back-compat only), and `claude-haiku-4-5` ($1/$5). 1M ctx on
  Fable, Opus, and both Sonnet generations with no long-context premium.
- Integration traps that MUST be capability-flagged in the registry:
  Fable 5 / Opus 4.7+ / Sonnet 5 **reject temperature/top_p/top_k**; Sonnet 5
  uses adaptive thinking by default, accepts `output_config.effort` values
  `low`, `medium`, `high`, `max`, and `xhigh`, allows explicit
  `thinking: {"type": "disabled"}`, and rejects legacy manual
  `thinking.budget_tokens`; Fable 5's new tokenizer uses ~30-35% more tokens
  (re-baseline cost estimates); Fable 5 can return `stop_reason: "refusal"`.
- Web search: server-side `web_search_20260209` ($10/1k) plus
  `web_fetch_20260209` (free per-call, token costs only). Both Messages-API
  tools.
- Batch: 50%, inline JSON (no file upload), most complete within 1 hour.
- Caching: explicit `cache_control`, reads at 0.1x, writes at 1.25x/2x;
  minimum cacheable prefix 2,048-4,096 tokens by model.
- No deep-research API product; the agentic loop equivalent is DIY or the
  Managed Agents beta.
- Prompt caching requires cost-aware handling. Anthropic's current docs price
  5-minute cache writes above normal input, 1-hour writes higher again, and
  cache hits lower than base input. Automatic caching exists on the Claude API,
  Claude Platform on AWS, and Microsoft Foundry beta; Bedrock and Vertex AI do
  not support automatic caching. Implementation must therefore model writes,
  reads, TTL choice, gateway support, and cache-hit expectations before enabling
  this for any Primr stage.

### Billing-verifiable agent runners

These are not provider SDKs. They are host-agent execution surfaces that can
consume already-paid or already-allocated capacity only when official auth,
automation, and trustworthy billing provenance support that claim. Otherwise
the operator must explicitly acknowledge that metered API billing may apply.

- Candidate host surfaces are tracked as sanctioned execution hosts, not
  provider APIs. A host can become a Primr runner only where it provides an
  official task, connector, action, CLI, hook, or skill interface that can be
  invoked with a bounded packet and audited result.
- Authentication must come from the user's own configured host surface. Primr
  must not ship repo-owned tokens, account ids, private endpoint knowledge, or
  hidden credential reuse. Authentication type alone is not billing proof. If a
  host can transition from plan allocation to API credit spend, that transition
  must remain explicit in the host and visible in Primr's estimate.
- Integration shape for primr: emit a bounded stage packet, call the host runner
  through its official CLI/SDK/automation surface, parse structured output, and
  validate with the same structural checks and semantic evals as direct API
  recipes. The host runner never owns the pipeline loop, URL fetch policy, disk
  writes, or completion decision.
- Non-goals: no unofficial Max/ChatGPT proxies, browser-session scraping,
  reverse-engineered endpoints, or "subscription as hidden API key" behavior.
  If an official surface cannot run a stage reliably, use direct API, gateway,
  or local inference instead.

### AWS Bedrock (gateway)

- The `bedrock-mantle.{region}.api.aws` endpoint (console GA June 2026)
  serves OpenAI Chat Completions + Responses AND native Anthropic Messages.
  Auth: a plain Bedrock API key (`AWS_BEARER_TOKEN_BEDROCK` for boto3, or
  as the `api_key` against the OpenAI-compatible endpoint). No SigV4 needed
  for primr's path.
- Claude Fable 5 was day-one on Bedrock; GPT-5.4/5.5 are GA (Responses
  only). Whether Claude works through the Chat Completions shape is
  contradicted within AWS's own docs: TEST EMPIRICALLY, else use the
  `anthropic` SDK against mantle's `/anthropic/v1/messages`.
- Pricing: provider list price on global endpoints, ~10% premium regional.
- Gaps that shape the recipe: **no Anthropic web_search through Bedrock**
  (Nova-only web grounding); batch lags newest models (no Fable 5 /
  Opus 4.7+ / GPT-5.5 batch yet).

### Microsoft Foundry (gateway)

- The `/openai/v1/` endpoint (GA, no api-version param) works with the
  stock `openai` SDK: set base URL + API key, done. DeepSeek/Grok/MAI
  models route through the same endpoint; Claude (preview) uses a separate
  `/anthropic/v1/messages` endpoint billed via Marketplace at Anthropic
  list prices.
- Web search: `web_search` tool in the plain Responses API, $14/1k
  (Bing-grounded; data leaves the compliance boundary).
- Do NOT adopt `azure-ai-inference` (retires 2026-08-26); Microsoft's own
  recommendation is the stock `openai` package.
- Batch: Azure Global Batch 50% but gpt-5.4/5.5 not yet in the batch table;
  no batch for non-OpenAI models.

### Local (Ollama / LM Studio / llama.cpp / vLLM)

- 2026 reality: small-active-parameter MoE models give ~30B quality at
  ~3-4B decode speed. Role fits on the 16-24 GB tier:
  reasoning `qwen3.6:35b` (3B active) or `gpt-oss:20b`; writing
  `gemma4:31b` or `qwen3.6:27b`; utility `qwen3.5:4b`/`:9b`; judging
  `granite4.1-guardian:8b` (purpose-built yes/no judge). All Apache 2.0.
- Honest quality bar: best 24 GB-runnable models measure roughly HALF of
  frontier on long-form writing (EQ-Bench Longform ~40-42 vs ~79-80), with
  repetition/slop growth past a few thousand words. primr's
  section-by-section writing + refine loop is the right shape to partially
  compensate, and the free tier ships labeled as "free, slower, weaker
  writing" for this measured hardware/model generation. That label is not a
  permanent product judgment: as desk-side AI appliances and workstation-class
  local models improve, local profiles should be re-evaluated and promoted
  stage by stage when they meet the same quality bar as paid routes.
- Integration footguns to handle in code:
  - Ollama's `/v1` endpoint cannot set context per request and **silently
    front-truncates** beyond the loaded context. The local profile must
    verify effective context (instruct users on `OLLAMA_CONTEXT_LENGTH`,
    or create a model variant with `num_ctx` baked in) and refuse
    corpus-stage calls when the window is too small to be honest.
  - Synthesis-usable context is far below advertised for most local models
    (NoLiMa); keep primr's chunk-summarize-then-synthesize shape, never one
    giant prompt.
  - Prefill dominates on Mac/CPU (minutes for a 60K-token corpus);
    progress display should set expectations per stage.
  - KV-cache memory: recommend `OLLAMA_KV_CACHE_TYPE=q8_0` +
    `OLLAMA_FLASH_ATTENTION=1` in docs.
- Throughput envelope (Q4, 20k-word report): ~2-3 min decode on a 4090
  with a 30B-A3B MoE; ~5-6 min on an M4 Max; 20-40 min CPU-only MoE.
  Viable everywhere; the free tier is real, and its quality should be treated
  as a moving benchmark rather than a fixed ceiling.

## Delivery plan (phased, each phase independently shippable)

### Phase A: first-class OpenAI and Anthropic recipes (1.x)

1. **Registry refresh to June-2026 generations** (gpt-5.5/5.4 family;
   claude-fable-5/opus-4-8/sonnet-4-6/haiku-4-5) with current prices and
   NEW capability flags: `supports_temperature`, `tokenizer_multiplier`,
   `web_search_tool` (none | openai_responses | anthropic_messages |
   xai_browse), `requires_responses_api`.
2. **Sampling-param guard**: the LLM call seam consults
   `supports_temperature` before setting sampling params (Fable 5 /
   Opus 4.7+ reject them).
3. **Web-search capability routing**: the browse/search stage dispatches to
   the provider-native tool (OpenAI Responses `web_search`, Anthropic
   `web_search_20260209`) when the recipe's provider has one; DDG remains
   the free default everywhere.
4. **Recipe validation**: one cheap live run per recipe (openai-only key,
   anthropic-only key), eval-scored with the step-1 instruments, before
   the README/dry-run advertise them. Estimator entries for both. Each recipe
   exits validation with a default class: sub-dollar default candidate,
   specialty fallback, or premium-only.

### Phase A.1: provider prompt-caching research and cost-safe design

1. Research current provider behavior for Anthropic, OpenAI, Gemini, xAI,
   Bedrock, Foundry, and Vertex. Capture which APIs support explicit
   breakpoints, automatic caching, cache TTLs, cache diagnostics, and gateway
   parity.
2. Add model/provider metadata for cache write multiplier, cache read
   multiplier, minimum cacheable prefix, supported TTLs, breakpoint limits, and
   automatic-caching availability.
3. Extend estimates and usage records before enabling cache controls. A route
   must show projected savings from repeated static prefixes; otherwise caching
   stays off.
4. Disallow paid background cache pre-warming, keepalive refresh loops,
   max-token workarounds, and 1-hour TTL defaults. Long TTLs require explicit
   operator opt-in and a cost estimate.
5. Add tests proving cost accounting covers cache writes and reads, and proving
   caching is disabled for one-off or volatile prompts that would pay repeated
   writes without hits.

### Phase B: billing-verifiable host runners

1. **Foundation seam - SHIPPED:** `HostAgentRunner` accepts a typed stage
   packet (`role`, prompt, evidence bundle, output schema, budget/plan policy)
   and returns structured text plus runner metadata. It is covered with fake
   runner tests.
2. **First official-host transport - INTERNAL/EVAL-ONLY:** the Codex CLI adapter
   handles `fast.source_relevance` through documented `codex exec` automation.
   It fails closed against silent API fallback when the eval harness selects the
   internal agent profile. It is not exposed by the CLI because Primr cannot
   prove whether Codex auth is plan-backed or API-key billed. Additional hosts
   and stages remain eval-gated.
3. **Host-native handoff - SHIPPED:** `primr prep` emits a bounded evidence
   packet under a hard no-model-call policy, and `primr-zero` lets the
   surrounding host research and synthesize from its own plan allowance after
   the host is verified not to bill API usage or overages. This is not an
   internal stage runner and is labeled host-assisted.
4. Add capability probes before any runner. A surface is eligible only if it can
   be invoked through official automation, returns or stores schema-constrained
   output, exposes enough provenance to stamp the sidecar, and can be bounded by
   wall-clock plus task-count policy. If any of those are missing, it remains an
   operating host for Primr, not an internal stage runner.
5. Budget model: API dollars are unknown unless the host exposes trustworthy
   billing provenance. The preflight estimate may show "host plan usage" only
   when that basis is proven; otherwise it must show unknown or potentially
   metered billing, bounded stage count, wall-clock cap, optional token/task
   ceilings, and an acknowledgment gate. Any handoff to API credits must remain
   explicit in the host, never hidden by primr.
6. Validation: one cheap or verified plan-backed recipe eval per runner on the
   standing corpus. It must pass the same label calibration and trust checks as
   direct provider recipes before README promotion. A promoted runner may outrank
   paid API stages only when zero incremental API spend is proven. An explicitly
   acknowledged, potentially metered runner remains a distinct opt-in route;
   wall-clock, plan-limit, and billing uncertainty still appear in the estimate.

### Phase C: gateway support (Bedrock + Foundry)

Near-zero new code by design: both are base URL + API key against the
existing OpenAI-compatible provider.

1. Env plumbing + docs: `PRIMR_GATEWAY=bedrock|foundry` style profile (or
   plain `LOCAL_LLM_BASE_URL`-pattern envs) mapping to the right base URL
   shape, key env, and model-ID dialect (deployment names on Foundry,
   `anthropic.`-prefixed IDs on Bedrock).
2. Doctor checks: reachability + a one-token probe per configured gateway.
3. Honest docs on gateway gaps: no Anthropic web_search through either
   (those recipes run DDG-only browse or pair a direct key for search);
   batch lag on newest models; Bedrock Claude-via-ChatCompletions must be
   verified empirically per AWS's self-contradictory docs.

### Phase D: the $0 local profile (with 2.0 backend freedom)

1. `--inference local` execution profile per the backend-freedom design:
   local models for every stage with a local equivalent; stages with none
   (Deep Research) are skipped with clear logging.
2. **Fit-check before use** (principle 5), generalizing what the
   calibration local judge needs today: model installed (from `/v1/models`),
   memory headroom (one-token probe; on the Ollama out-of-memory error,
   step down to the next-smaller installed candidate), effective context
   window adequate for the stage.
3. Context guard for corpus stages (refuse silent truncation).
4. Role mapping defaults from the June-2026 research (MoE-first), but
   ALWAYS selected from what is actually installed; nothing hardcoded.
5. Eval the local recipe with the step-1 instruments and publish the
   honest quality delta next to the $0 API price tag. Local mode is allowed to
   be slower or weaker, but it must never silently upgrade itself to paid cloud;
   any paid fallback is a separate operator choice. Re-run the local eval when
   new local model generations or desktop-class AI hardware materially change
   the capability envelope, and let passing stages move up the default route.
6. For a single RTX 4090 or comparable 24 GB GPU, run the focused
   `4090-report-race` stage eval before the broader `4090-top10` sweep. The
   first question is pragmatic: does the user's local box already clear the
   local-vs-sub-dollar bar for a production-adjacent stage?

### Sequencing vs the Version Plan

Phase A is 1.x-compatible incremental work (registry + flags + one stage
dispatch). Phase B can start behind a fake-runner seam once the stage-packet
contract is designed; it should not block direct API recipes. Phase C is
config/docs heavy and can land any time after A. Phase D is the backend-freedom
pillar (2.0) and depends on the step-1 instruments (shipped) plus #18 routing
for per-stage requirements.

## Validation protocol (cost-disciplined)

- Everything testable offline stays offline: registry flags, sampling
  guards, dispatch seams, fit-check logic all get injected-seam unit tests.
- One cheap live run per new recipe, ever, before it is advertised
  (precedent: the v1.24.0 cross-provider eval).
- Local recipes validated with agreement-style checks against a cloud
  reference (the calibration `--judge-compare` pattern) before being
  trusted for judge/utility roles, and with the eval scorecard for
  writing roles.
