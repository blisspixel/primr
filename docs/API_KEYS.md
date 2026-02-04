# API Key Setup Guide

This guide covers obtaining, configuring, and securing the API keys required for Primr.

## Required Credentials

| Credential | Purpose | Console |
|------------|---------|---------|
| `GEMINI_API_KEY` | Google AI for research & analysis | [Google AI Studio](https://aistudio.google.com/apikey) |
| `SEARCH_API_KEY` | Google Custom Search API | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| `SEARCH_ENGINE_ID` | Custom Search Engine config | [Programmable Search Engine](https://programmablesearchengine.google.com/) |

## Step-by-Step Setup

### 1. Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. **Immediately copy the key** - you won't see it again
5. Store securely (see [Secure Storage](#secure-storage) below)

**Pricing**: Free tier includes 60 requests/minute. See [pricing](https://ai.google.dev/pricing).

### 2. Google Custom Search API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (recommended: separate project for Primr)
3. Enable the Custom Search API:
   - APIs & Services → Library → Search "Custom Search API" → Enable
4. Create credentials:
   - APIs & Services → Credentials → Create Credentials → API Key
5. **Restrict the key immediately** (see [Key Restrictions](#key-restrictions))

**Pricing**: 100 free queries/day, then $5/1000 queries.

### 3. Search Engine ID

1. Go to [Programmable Search Engine](https://programmablesearchengine.google.com/)
2. Click "Add" to create a new search engine
3. Select "Search the entire web"
4. Name it (e.g., "Primr Research")
5. Copy the Search Engine ID from Control Panel

This is a configuration ID, not a secret - but still don't share publicly.

## Secure Storage

### Development: Environment File

```bash
cp .env.example .env
chmod 600 .env  # Restrict file permissions (Linux/macOS)
```

Edit `.env` with your keys. The file is gitignored by default.

**⚠️ Never use environment variables directly in shell** - they persist in shell history:
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

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| "API key expired" | Key revoked or project deleted | Create new key in Cloud Console |
| "Quota exceeded" | Hit rate/daily limit | Wait for reset, or use `--mode deep` (uses Gemini search) |
| "Invalid API key" | Typo, extra whitespace, or wrong key | Re-copy from console, check for spaces |
| "API not enabled" | Custom Search API not enabled | Enable in Cloud Console → APIs & Services |
| "Forbidden" | Key restrictions blocking request | Check IP/referrer restrictions |

## Key Rotation

### Google API Keys

Google API keys don't expire automatically, but rotate them:
- Every 90 days for production
- Immediately if potentially exposed
- When team members leave

**Rotation process:**
1. Create new key in Cloud Console
2. Update `.env` or secrets manager
3. Verify with `primr doctor`
4. Delete old key in Cloud Console

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

1. **Revoke the key** in Google Cloud Console (don't just rotate)
2. **Check usage logs** for unauthorized activity:
   - Cloud Console → APIs & Services → Metrics
3. **Create new key** with restrictions
4. **Audit access** - who had the key, how was it exposed?
5. **Review billing** for unexpected charges

If you see unauthorized usage, contact Google Cloud support.

## Cost Control

### Estimate Before Running

```bash
primr --dry-run "Company Name" https://company.com
```

### Typical Costs

| Mode | Gemini | Search | Total |
|------|--------|--------|-------|
| scrape | ~$0.01 | ~$0.07 | ~$0.10 |
| deep | ~$0.28 | ~$0.70 | ~$1.00 |
| full | ~$0.56 | ~$0.90 | ~$1.50 |

Search costs $0.035/query (Google Search grounding). Use `primr --dry-run` for estimates based on your actual usage history.

### Set Billing Alerts

In Google Cloud Console:
1. Billing → Budgets & alerts
2. Create budget with email alerts at 50%, 90%, 100%

## Security Checklist

- [ ] Keys stored in `.env` file (not shell history)
- [ ] `.env` has restricted permissions (`chmod 600`)
- [ ] `.env` is in `.gitignore`
- [ ] API keys restricted to Custom Search API only
- [ ] Separate keys for dev/staging/prod
- [ ] Billing alerts configured
- [ ] Key rotation scheduled (90 days)
- [ ] Team knows incident response process

## Related Documentation

- [CONFIG.md](CONFIG.md) - Full configuration reference
- [SECURITY_OPS.md](SECURITY_OPS.md) - Security operations guide
- [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) - Production deployment with secrets management
