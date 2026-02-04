# API Key Setup Guide

This guide walks you through obtaining and configuring the API keys required to run Primr.

## Required Keys

Primr requires three credentials:

| Key | Purpose | Where to Get |
|-----|---------|--------------|
| `GEMINI_API_KEY` | Google AI for research & analysis | [Google AI Studio](https://aistudio.google.com/apikey) |
| `SEARCH_API_KEY` | Google Custom Search for web queries | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| `SEARCH_ENGINE_ID` | Custom Search Engine configuration | [Programmable Search Engine](https://programmablesearchengine.google.com/) |

## Step-by-Step Setup

### 1. Gemini API Key (Required)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key (starts with `AIza...`)

**Cost**: Free tier includes 60 requests/minute. See [pricing](https://ai.google.dev/pricing).

### 2. Google Custom Search API Key (Required)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the "Custom Search API":
   - Go to APIs & Services → Library
   - Search for "Custom Search API"
   - Click Enable
4. Create credentials:
   - Go to APIs & Services → Credentials
   - Click "Create Credentials" → "API Key"
   - Copy the key

**Cost**: 100 free queries/day, then $5 per 1000 queries. See [pricing](https://developers.google.com/custom-search/v1/overview#pricing).

### 3. Search Engine ID (Required)

1. Go to [Programmable Search Engine](https://programmablesearchengine.google.com/)
2. Click "Add" to create a new search engine
3. Configure:
   - **Sites to search**: Select "Search the entire web"
   - **Name**: "Primr Research" (or any name)
4. Click "Create"
5. Go to "Control Panel" for your new engine
6. Copy the "Search engine ID" (format: `abc123...`)

## Configuration

### Option 1: Environment File (Recommended)

Create a `.env` file in your project root:

```bash
# Copy from .env.example
cp .env.example .env

# Edit with your keys
GEMINI_API_KEY=AIza...your-key-here
SEARCH_API_KEY=AIza...your-key-here
SEARCH_ENGINE_ID=abc123...your-id-here
```

### Option 2: Environment Variables

```bash
# Linux/macOS
export GEMINI_API_KEY="AIza...your-key-here"
export SEARCH_API_KEY="AIza...your-key-here"
export SEARCH_ENGINE_ID="abc123...your-id-here"

# Windows (PowerShell)
$env:GEMINI_API_KEY="AIza...your-key-here"
$env:SEARCH_API_KEY="AIza...your-key-here"
$env:SEARCH_ENGINE_ID="abc123...your-id-here"
```

## Verify Setup

Run the doctor command to verify all keys are configured correctly:

```bash
primr doctor
```

Expected output for a healthy setup:
```
Primr Doctor

> Environment
+ Python 3.10+

> API Configuration
+ GEMINI_API_KEY configured (valid format)
+ Google Search API working

> Dependencies
+ Playwright browsers available

> File System
+ Output directory writable
+ Working directory writable
+ Cache directory ready

> API Connectivity
+ Gemini API responding

✓ All checks passed - Primr is ready to use
```

## Troubleshooting

### "API key expired"

Google API keys can expire or be revoked. To fix:

1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Find the expired key
3. Either regenerate it or create a new one
4. Update your `.env` file

### "Quota exceeded"

**Gemini API**: Wait for quota reset (usually 1 minute) or upgrade your plan.

**Custom Search API**: Free tier is 100 queries/day. Options:
- Wait until tomorrow
- Enable billing for more queries ($5/1000)
- Use `--mode deep` which uses Gemini's built-in search instead

### "Invalid API key"

1. Verify the key is copied correctly (no extra spaces)
2. Check the key hasn't been deleted in Google Cloud Console
3. Ensure the Custom Search API is enabled for your project

### "Search Engine ID not found"

1. Go to [Programmable Search Engine](https://programmablesearchengine.google.com/)
2. Verify your search engine exists
3. Copy the ID from the Control Panel (not the name)

## Key Rotation

For production deployments, rotate keys periodically:

```python
from primr.api.auth import create_api_key, rotate_api_key

# Create a new key with 90-day expiration
key = create_api_key("production-app", expires_in_days=90)

# Rotate with 24-hour grace period (both keys work during transition)
new_key = rotate_api_key(old_key, grace_hours=24)
```

See [SECURITY_OPS.md](SECURITY_OPS.md) for full operational guidance.

## Cost Estimation

Before running research, estimate costs:

```bash
primr --dry-run "Company Name" https://company.com
```

Typical costs per research run:
- **Scrape mode**: ~$0.01-0.05 (minimal AI usage)
- **Deep mode**: ~$0.10-0.30 (Gemini Deep Research)
- **Full mode**: ~$0.15-0.50 (scrape + deep + AI strategy)

## Security Best Practices

1. **Never commit `.env` to git** - it's in `.gitignore` by default
2. **Use separate keys for dev/prod** - easier to rotate and audit
3. **Set API key restrictions** in Google Cloud Console:
   - Restrict by IP address for servers
   - Restrict by HTTP referrer for web apps
4. **Monitor usage** in Google Cloud Console for unexpected spikes
5. **Rotate keys** every 90 days for production systems

## Related Documentation

- [CONFIG.md](CONFIG.md) - Full configuration reference
- [SECURITY_OPS.md](SECURITY_OPS.md) - Security operations guide
- [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) - Cloud deployment with secrets management
