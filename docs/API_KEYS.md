# API Key Setup Guide

This guide covers obtaining, configuring, and securing the API keys used by
Primr. Agent-host authentication remains inside the official host. A host can
operate Primr, but Primr does not accept or relay host OAuth credentials as
provider API keys.

## Recommended Credentials

| Credential | Purpose | Console |
|------------|---------|---------|
| `XAI_API_KEY` | Grok standard reasoning, strategy, and XAI-only writing fallback | [xAI Console](https://console.x.ai/) |
| `GEMINI_API_KEY` | Low-cost writing/utility with XAI, premium mode, and Gemini-backed stages | [Google AI Studio](https://aistudio.google.com/apikey) |

Grok + Gemini is the measured default, but it is not the only supported provider mix. A single usable cloud LLM provider key is enough for provider diagnostics.

## Optional Credentials

| Credential | Purpose | Console |
|------------|---------|---------|
| `OPENAI_API_KEY` | Optional OpenAI GPT/o-series fallback for routed utility, writing, reasoning, and registered premium-research candidates; the current full launch path still requires xAI or Gemini | [OpenAI Platform](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | Optional Claude fallback for writing, reasoning, and pro roles | [Anthropic Console](https://console.anthropic.com/settings/keys) |
| `OLLAMA_API_KEY` | Optional local/OpenAI-compatible endpoint key; Ollama uses `ollama` by default | Local runtime |
| `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_BASE_URL`/`AZURE_OPENAI_ENDPOINT` | Microsoft Foundry / Azure OpenAI via the OpenAI-compatible `/openai/v1/` endpoint (Phi-4, GPT, Llama, DeepSeek) | [Azure AI Foundry](https://ai.azure.com/) |
| `AWS_BEARER_TOKEN_BEDROCK` *or* AWS credential chain (`AWS_ACCESS_KEY_ID`/`AWS_PROFILE` + `AWS_REGION`) | Amazon Bedrock via `converse` (Claude, Nova, Llama, Gemma, DeepSeek); needs `pip install 'primr[bedrock]'` | [AWS Bedrock](https://console.aws.amazon.com/bedrock/) |
| `SEARCH_API_KEY` | Google Custom Search API (only if `SEARCH_PROVIDER=google`) | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| `SEARCH_ENGINE_ID` | Custom Search Engine config (only if `SEARCH_PROVIDER=google`) | [Programmable Search Engine](https://programmablesearchengine.google.com/) |

Primr uses DuckDuckGo for web search by default, so no search API key is needed unless you opt into `SEARCH_PROVIDER=google`.

### Deployment surfaces: Foundry and Bedrock

Microsoft Foundry and Amazon Bedrock let you run primr against models hosted in
your own Azure/AWS account (good for cost, single-cloud consolidation, and cheap
tiers like Phi-4, Nova, Gemma, DeepSeek). They lag the model vendors' own APIs
by weeks, so use them for cost/consolidation and first-party APIs for the newest
models. End-to-end infrastructure-as-code with deploy/verify/clean-up steps
lives in the repo under
[`examples/deploy/`](https://github.com/blisspixel/primr/tree/main/examples/deploy):
Azure Foundry (Bicep) and AWS Bedrock (CloudFormation).

### Validate that keys actually work

`primr keys test` runs a free, auth-only check (a `models.list`-style call — no
model generation, no token spend) against every configured provider and reports
per-provider OK/FAIL with latency. `primr keys test <provider>` checks just one.
This is separate from `primr doctor`, which never makes a live model call.

## Subscription-Backed Agent Hosts

Some users already pay for Codex, Claude Code Pro/Max, or enterprise agent
seats. The intended Primr model is:

- Use provider API keys for the supported direct full-report path today.
- Use Codex/Claude Code/Cursor/VS Code MCP integrations to operate Primr from
  those tools today.
- Use `primr-zero` inside a verified plan-backed host for the supported
  plan-native path. Before describing the result as zero incremental spend,
  confirm that the host will not bill API usage or overages.

Do not paste ChatGPT or Claude web-session credentials into Primr. Do not route
through unofficial subscription proxies. An unpromoted Codex adapter uses
official `codex exec` with a read-only sandbox, disabled web search and shell
tools, no approvals, no persisted history, and schema-constrained output.
For controlled single-company testing, it is gated behind `--inference hybrid
--acknowledge-host-agent-may-bill` and is limited to
`fast.source_relevance`. Codex can authenticate through a ChatGPT plan or an
API key, and Primr cannot determine which billing mode an installed session
uses. Primr therefore records the route as `potentially_metered`, excludes any
host charge from its estimate and budget, and rejects batch fan-out. The
adapter neither reads nor stores the credential, has not cleared its promotion
eval, and must not be advertised as a zero-cost or validated route.

| Host | Supported boundary | Notes |
|------|--------------------|-------|
| Codex | Use `primr-zero` inside an authenticated Codex host after verifying that the session is plan-backed and will not incur API usage or overages | Primr neither reads nor stores the host credential. The in-pipeline source-relevance route is an explicit, unpromoted pilot, and API-key sign-in can mean usage-based OpenAI API billing. |
| Claude Code | Use `primr-zero` inside the authenticated Claude Code host | Primr has no Claude Code in-pipeline runner and must never receive or relay Claude subscription OAuth credentials. Direct Anthropic calls require `ANTHROPIC_API_KEY`. |

This keeps billing honest: API-keyed stages show estimated dollars, local stages
show $0 API plus runtime, and a host route claims plan usage only when that
billing basis is proven. Explicitly acknowledged but unverified execution is
reported as potentially metered instead.

### Search Provider Configuration

Primr defaults to DuckDuckGo for web search, which requires no API keys. If you have a grandfathered Google Custom Search Engine with whole-web search, you can use it instead:

```bash
# In your .env file:
SEARCH_PROVIDER=google          # Use Google Custom Search
SEARCH_API_KEY=your_key_here
SEARCH_ENGINE_ID=your_id_here
```

> **Note:** Google deprecated "Search the entire web" for new Programmable Search Engines in January 2026. New CSEs are limited to 50 domains, making them unsuitable for Primr's use case. Only use `SEARCH_PROVIDER=google` if you have an existing whole-web CSE.

## Step-by-Step Setup

### 1. Store Keys With Primr

For a PyPI install, use the guided setup:

```bash
primr init
```

For scripting or direct key management, use Primr's user-level key store:

```bash
primr keys set gemini
primr keys set xai
primr keys set openai
primr keys set anthropic
primr keys set foundry
primr keys set bedrock
primr keys list
primr keys path
```

`primr init` and `primr keys set ...` prompt for keys without echoing them. Primr reads keys in this order:

1. Shell environment variables
2. The nearest local `.env`
3. The per-user Primr config file shown by `primr keys path`

### 2. xAI API Key

1. Go to [xAI Console](https://console.x.ai/)
2. Create or select a project
3. Create an API key
4. Run `primr keys set xai`

`XAI_API_KEY` enables Grok standard reasoning and strategy stages. With `GEMINI_API_KEY`, Primr uses Gemini for low-cost bulk writing.

### 3. Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. **Immediately copy the key** - you won't see it again
5. Run `primr keys set gemini`

Gemini rate limits are model-, project-, and usage-tier-specific. Check the
active limits for the project in AI Studio rather than assuming a fixed free
tier RPM. See Google's [rate-limit guide](https://ai.google.dev/gemini-api/docs/rate-limits)
and [pricing](https://ai.google.dev/pricing).

### 4. OpenAI API Key

1. Go to [OpenAI Platform API keys](https://platform.openai.com/api-keys)
2. Create or select a project
3. Create an API key
4. Run `primr keys set openai`

### 5. Anthropic API Key

1. Go to [Anthropic Console API keys](https://console.anthropic.com/settings/keys)
2. Create or select a workspace
3. Create an API key
4. Run `primr keys set anthropic`

### 6. Local/OpenAI-Compatible Endpoint

Ollama does not need a real API key, but local and self-hosted endpoints can require one:

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1
primr keys set ollama
```

### 7. Google Custom Search API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (recommended: separate project for Primr)
3. Enable the Custom Search API:
   - APIs & Services → Library → Search "Custom Search API" → Enable
4. Create credentials:
   - APIs & Services → Credentials → Create Credentials → API Key
5. **Restrict the key immediately** (see [Key Restrictions](#key-restrictions))

**Pricing**: 100 free queries/day, then $5/1000 queries.

### 8. Search Engine ID

1. Go to [Programmable Search Engine](https://programmablesearchengine.google.com/)
2. Click "Add" to create a new search engine
3. Select "Search the entire web"
4. Name it (e.g., "Primr Research")
5. Copy the Search Engine ID from Control Panel

This is a configuration ID, not a secret - but still don't share publicly.

## Secure Storage

### Development: Primr User Config

```bash
primr keys set gemini
primr keys set xai
primr keys set openai
primr keys set anthropic
primr keys path
```

This writes a gitignored per-user config file outside your project checkout.

### Project-Specific Environment File

```bash
cp .env.example .env
chmod 600 .env  # Restrict file permissions (Linux/macOS)
```

Edit `.env` with your keys. The file is gitignored by default.

**Never use environment variables directly in shell** - they persist in shell history:
```bash
# BAD - logged in shell history
export GEMINI_API_KEY="your-key"

# GOOD - use .env file or prompt
read -s GEMINI_API_KEY  # Prompts without echo
```

### Production: Secrets Manager

For production deployments, use a secrets manager instead of `.env` files:

| Platform | Service | Documentation |
|----------|---------|---------------|
| AWS | Secrets Manager | [docs](https://docs.aws.amazon.com/secretsmanager/) |
| GCP | Secret Manager | [docs](https://cloud.google.com/secret-manager) |
| Azure | Key Vault | [docs](https://docs.microsoft.com/azure/key-vault/) |
| Self-hosted | HashiCorp Vault | [docs](https://www.vaultproject.io/) |

See [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) for integration examples.

## Key Restrictions

**Always restrict API keys** - an unrestricted key is a liability.

### Google Cloud Console Restrictions

1. Go to APIs & Services → Credentials
2. Click on your API key
3. Under "API restrictions": Select "Restrict key" → Custom Search API only
4. Under "Application restrictions":
   - **Servers**: Restrict by IP address
   - **Web apps**: Restrict by HTTP referrer
   - **Local dev**: Can leave unrestricted, but use a separate dev key

### Gemini API Key Restrictions

Currently limited options, but:
- Use separate keys for dev/staging/prod
- Monitor usage in AI Studio dashboard
- Set up billing alerts

## Verify Setup

```bash
primr doctor
```

Healthy output shows all checks passing. If keys are invalid or expired, doctor will identify which one.
For interactive recovery, run:

```bash
primr doctor --fix
```

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| "API key expired" | Key revoked or project deleted | Create new key in Cloud Console |
| "No cloud LLM provider key configured" | No Gemini, xAI, OpenAI, or Anthropic key is configured | Run one of `primr keys set gemini`, `primr keys set xai`, `primr keys set openai`, or `primr keys set anthropic` |
| "XAI_API_KEY not set" | Grok standard mode is disabled | Run `primr keys set xai` if you want the measured default reasoner |
| "GEMINI_API_KEY not set" | Gemini writing/premium stages are disabled | Run `primr keys set gemini` if you want the cheapest measured writer or premium mode |
| "Quota exceeded" | Provider RPM, token, daily, or spend-rate limit | Check the provider's current project limits, honor retry guidance for transient 429s, and wait for reset when the quota is exhausted. Choose another configured route only after a fresh dry-run and approval. |
| "Invalid API key" | Typo, extra whitespace, or wrong key | Re-copy from console, check for spaces |
| "API not enabled" | Custom Search API not enabled | Enable in Cloud Console → APIs & Services |
| "Forbidden" | Key restrictions blocking request | Check IP/referrer restrictions |

## Key Rotation

### API Keys

Provider API keys do not all expire automatically, but rotate them:
- Every 90 days for production
- Immediately if potentially exposed
- When team members leave

**Rotation process:**
1. Create a new key in the provider console
2. Update `.env` or secrets manager
3. Verify with `primr doctor`
4. Delete the old key in the provider console

### MCP Server Keys (if using HTTP mode)

For the MCP server's own authentication (separate from Google keys):

```python
from primr.api.auth import create_api_key, rotate_api_key

# Create key with expiration
key = create_api_key("client-name", expires_in_days=90)

# Rotate with grace period
new_key = rotate_api_key(old_key, grace_hours=24)
```

## If a Key is Compromised

**Act immediately:**

1. **Revoke the key** in the provider console (don't just rotate)
2. **Check usage logs** for unauthorized activity:
   - Provider usage dashboard or Cloud Console metrics
3. **Create new key** with restrictions
4. **Audit access** - who had the key, how was it exposed?
5. **Review billing** for unexpected charges

If you see unauthorized usage, contact the provider's support team.

## Cost Control

### Estimate Before Running

```bash
primr "Company Name" https://company.com --dry-run
# Machine-readable (includes execution_ready for full-mode recipes):
primr "Company Name" https://company.com --dry-run --json
```

Dry-run and `--budget` use `max(planning, historical)` so cheap past runs
cannot understate the approval floor. Full-mode quotes with only OpenAI or
Anthropic keys (or with no XAI/Gemini key) are **planning-only**: the dollars
are the XAI/Gemini full-recipe floor, JSON sets `execution_ready: false`, and
launch still requires `XAI_API_KEY` or `GEMINI_API_KEY`.

### Typical Costs

| Mode | Tokens | Deep Research | Search | Total |
|------|--------|---------------|--------|-------|
| scrape | ~$0.05 | -- | ~$0.04 | ~$0.10 |
| deep | Sequential Flash writing and strategy included | ~$2.50 planning point | -- | ~$5.38 with one integrated AI Strategy; ~$2.88 base |
| full, xAI plus Gemini | provider-token based | -- | DuckDuckGo default | ~$0.89 with one integrated AI Strategy |
| full, xAI only | provider-token based | -- | DuckDuckGo default | ~$5.84 with one integrated AI Strategy |
| premium | Structured collection, sequential Flash writing, and strategy included | ~$2.50 planning point | DuckDuckGo default | ~$6.71 with one integrated AI Strategy |

Gemini Deep Research is billed from the underlying model tokens and tools, so
the final charge varies by task. Google currently describes a typical standard
task as roughly $1-$3; Primr uses $2.50 as its conservative planning point.
See [Google's Deep Research pricing guidance](https://ai.google.dev/gemini-api/docs/deep-research#availability-and-pricing).
Deep Research is mainly used by deep and premium paths. DuckDuckGo search is
the default for standard runs; Google Custom Search costs apply only when
`SEARCH_PROVIDER=google`. Use `primr --dry-run` for estimates based on your
actual provider configuration and usage history.

### Set Billing Alerts

In Google Cloud Console:
1. Billing → Budgets & alerts
2. Create budget with email alerts at 50%, 90%, 100%

## Security Checklist

- [ ] Keys stored with `primr keys set ...` or in a protected `.env` file
- [ ] Project `.env` has restricted permissions (`chmod 600`)
- [ ] Project `.env` is in `.gitignore`
- [ ] API keys restricted to Custom Search API only
- [ ] Separate keys for dev/staging/prod
- [ ] Billing alerts configured
- [ ] Key rotation scheduled (90 days)
- [ ] Team knows incident response process

## Related Documentation

- [CONFIG.md](CONFIG.md) - Full configuration reference
- [SECURITY_OPS.md](SECURITY_OPS.md) - Security operations guide
- [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) - Production deployment with secrets management
