# Provider Expansion: OpenAI, Anthropic, Account-Capacity Agents, Gateways, and Local

Status: PLANNED (provider research verified June 12, 2026; account-capacity
agent runner research refreshed June 17, 2026)
ROADMAP anchor: Active Queue #26. Companion to
[`2.0-backend-freedom.md`](2.0-backend-freedom.md) (routing architecture);
this doc is the concrete provider catalog and delivery plan that routing
will route over.

## Principles (set by the operator, June 2026)

1. **No reason this must be Grok.** Grok + Gemini is the measured default,
   not a dependency. Every pipeline role (reasoning, writing, utility)
   should be servable by any provider whose models meet the role's bar.
2. **Support whatever someone has.** A user arrives with an OpenAI key, or
   an Anthropic key, or a Codex/Claude Code subscription, or a corporate
   Bedrock/Foundry gateway, or just a gaming GPU and Ollama. Each of those
   should produce a report once its recipe is validated. Absence of any of
   them is silent, never an error.
3. **Account capacity is a first-class capacity source.** Codex, Claude Code,
   Kiro CLI, Copilot Cowork, Claude/Cowork-style hosts, and comparable agent
   products should be evaluated as ways to spend capacity the user already has.
   They become Primr runners only through official automation, connector, CLI,
   hook, or agent-skill surfaces that can accept bounded stage packets and
   return structured outputs. They are never treated as hidden API keys.
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
   already-paid tier must exist, even if measurably worse and labeled that way.
   DDG search is already free, scraping is already local; with local inference
   the whole run is $0 API plus electricity, which changes what "run it on the
   whole portfolio" costs. For users already paying for an agent subscription,
   an official host-account runner should let compatible LLM stages draw from
   plan allocation rather than separate API credits. If no validated zero-
   incremental route is configured, the default should be the best validated
   sub-dollar direct API recipe. Premium recipes are opt-in and must document
   the marginal quality or coverage they buy.

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
  checks, and API-credit handoff guards. It is planning infrastructure only
  until production stages are wired to it.
- The typed host-account runner contract now exists in
  `ai/host_agent_runner.py`: bounded `HostAgentStagePacket`, billing policy,
  normalized result/provenance, and a prompt renderer that fences evidence with
  the existing content-sanitizer. No concrete Codex/Claude Code process runner
  is wired yet. Claude Code and Codex integrations today operate primr through
  MCP/skills, while the full internal report pipeline still uses provider keys.
  The seam below is a stage runner, not a claim that subscription credentials
  are interchangeable with API keys.

## Verified provider facts (June 12, 2026)

Full citations live in the research transcripts; key integration facts:

### OpenAI (direct)

- Models: `gpt-5.5` ($5/$30 per MTok, 1.05M ctx), `gpt-5.4` ($2.50/$15),
  `gpt-5.4-mini` ($0.75/$4.50), `gpt-5.4-nano` ($0.20/$1.25, 400K ctx).
  Reasoning depth via `reasoning.effort` (none..xhigh).
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
  `claude-sonnet-4-6` ($3/$15), `claude-haiku-4-5` ($1/$5). 1M ctx on the
  big three with no long-context premium.
- Integration traps that MUST be capability-flagged in the registry:
  Fable 5 / Opus 4.7+ **reject temperature/top_p/top_k** (primr sets
  temperature generically today); Fable 5's new tokenizer uses ~30-35% more
  tokens (re-baseline cost estimates); Fable 5 can return
  `stop_reason: "refusal"`.
- Web search: server-side `web_search_20260209` ($10/1k) plus
  `web_fetch_20260209` (free per-call, token costs only). Both Messages-API
  tools.
- Batch: 50%, inline JSON (no file upload), most complete within 1 hour.
- Caching: explicit `cache_control`, reads at 0.1x, writes at 1.25x/2x;
  minimum cacheable prefix 2,048-4,096 tokens by model.
- No deep-research API product; the agentic loop equivalent is DIY or the
  Managed Agents beta.

### Account-capacity agent runners (Codex / Claude Code / Kiro / Cowork)

These are not provider SDKs. They are host-agent execution surfaces that can
consume already-paid or already-allocated capacity when official auth and
automation support it.

- OpenAI Codex supports ChatGPT sign-in for subscription access and API-key
  sign-in for usage-based access. Codex CLI and IDE support both; Codex cloud
  requires ChatGPT sign-in. API-key auth uses standard API pricing. Enterprise
  Codex access tokens are intended for trusted local automation and represent a
  ChatGPT workspace user.
- Claude Code authentication prioritizes API-key/helper modes before
  subscription OAuth; `/login` subscription credentials are the default for Pro,
  Max, Team, and Enterprise users. `claude setup-token` can create a
  `CLAUDE_CODE_OAUTH_TOKEN` for CI/scripts where browser login is unavailable.
  Claude Code's `/usage` view distinguishes API token costs from subscription
  plan usage, and Pro/Max transitions to API credit usage require explicit user
  consent.
- Kiro CLI and Cowork-style products are tracked as candidate host surfaces, not
  provider APIs. Kiro-style hooks/agent configuration can host Primr control
  flows if they expose a stable CLI or connector seam. Copilot Cowork,
  Claude/Cowork-style connector surfaces, and similar workplace agents can be
  Primr runners only where they provide an official task, connector, action, or
  skill interface that can be invoked with a bounded packet and audited result.
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
  writing" per principle 6.
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
  Viable everywhere; the free tier is real.

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

### Phase B: account-capacity host runners (Codex, Claude Code, Kiro, Cowork)

1. **Foundation seam - STARTED:** `HostAgentRunner` accepts a typed stage
   packet (`role`, prompt, evidence bundle, output schema, budget/plan policy)
   and returns structured text plus runner metadata. It is covered with fake
   runner tests. Remaining: concrete process runners and explicit
   `--inference agent` opt-in.
2. Codex runner: use official Codex CLI authentication modes
   (ChatGPT sign-in locally, `CODEX_ACCESS_TOKEN` for trusted Enterprise
   automation, API-key sign-in only when the operator explicitly chose
   usage-based billing). Probe with `codex login status`; fail open to other
   configured profiles when unavailable.
3. Claude runner: use official Claude Code subscription OAuth or
   `CLAUDE_CODE_OAUTH_TOKEN` where available. Respect Anthropic's credential
   precedence, especially that `ANTHROPIC_API_KEY` can take precedence over
   subscription auth. Surface `/status` and `/usage` guidance rather than
   guessing billing state.
4. Kiro and Cowork pilots: add capability probes before runners. A surface is
   eligible only if it can be invoked through official automation, returns or
   stores schema-constrained output, exposes enough provenance to stamp the
   sidecar, and can be bounded by wall-clock plus task-count policy. If any of
   those are missing, it remains an operating host for Primr, not an internal
   stage runner.
5. Budget model: API dollars are unknown for account-capacity stages, so the
   preflight estimate must show "host plan usage" with bounded stage count,
   wall-clock cap, and optional token/task ceilings. Any handoff to API credits
   must remain explicit in the host, never hidden by primr.
6. Validation: one cheap or plan-backed recipe eval per runner on the standing
   corpus. It must pass the same label calibration and trust checks as direct
   provider recipes before README promotion. Once promoted and explicitly
   enabled, compatible host-runner stages should beat paid API stages in default
   routing because their incremental API cost is zero; wall-clock and plan-limit
   behavior still appears in the estimate.

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
   any paid fallback is a separate operator choice.

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
