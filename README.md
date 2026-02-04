# Primr

AI-powered company research tool. Generates intelligence briefs by combining website scraping with Gemini's Deep Research for validated external sources.

Built for consultants and researchers who need company intelligence fast.

## What It Does

```
Website → Site Corpus → Deep Research → Structured Report
```

- **Scrape mode**: Build site corpus + extract insights (~5 min, ~$0.02)
- **Deep mode**: Gemini Deep Research with external sources (~10 min, ~$0.20)  
- **Full mode**: Both combined into comprehensive brief (~30 min, ~$0.35)

## Quick Start

```bash
# Requires Python 3.11+
git clone https://github.com/blisspixel/primr.git
cd primr
python setup_env.py    # Installs deps, sets up .env

# Configure API keys (see docs/API_KEYS.md)
primr doctor           # Verify setup

# Run research
primr "Acme Corp" https://acme.example
```

## Usage

```bash
primr "Company" https://company.com              # Full research (default)
primr "Company" https://company.com --mode scrape   # Site corpus only
primr "Company" https://company.com --mode deep     # External research only
primr "Company" https://company.com --dry-run       # Cost estimate

primr doctor                                     # System diagnostics
primr --check-jobs                               # Check pending jobs
```

## Configuration

Required in `.env`:
```
GEMINI_API_KEY=       # https://aistudio.google.com/apikey
SEARCH_API_KEY=       # Google Custom Search API
SEARCH_ENGINE_ID=     # Programmable Search Engine ID
```

→ [Full setup guide](docs/API_KEYS.md)

## Features

- **8-tier web scraping** with intelligent escalation (HTTP → browser → vision)
- **Gemini Deep Research** for autonomous multi-step external research
- **AI Strategy generation** with cloud vendor recommendations
- **MCP Server** for AI agent integration (Claude Desktop, etc.)
- **Quality assessment** with automatic grading
- **Cloud deployment** ready (AWS/Azure/GCP serverless)

## Documentation

| Document | Description |
|----------|-------------|
| [API_KEYS.md](docs/API_KEYS.md) | API key setup and security |
| [CONFIG.md](docs/CONFIG.md) | Full configuration reference |
| [API.md](docs/API.md) | MCP server and programmatic usage |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and scraping tiers |
| [CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md) | Serverless deployment guide |
| [SECURITY_OPS.md](docs/SECURITY_OPS.md) | Security operations |
| [ROADMAP.md](ROADMAP.md) | Development roadmap |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## MCP Server

For AI agent integration:

```bash
primr-mcp --stdio              # Claude Desktop
primr-mcp --http --port 8000   # HTTP mode
```

→ [MCP documentation](docs/API.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT
