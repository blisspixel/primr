# Primr Documentation Index

Quick reference to all Primr documentation.

## Getting Started

| Document | Description |
|----------|-------------|
| [README](../README.md) | Installation, quick start, basic usage |
| [CONFIG](CONFIG.md) | Configuration reference, environment variables |

## Architecture & Design

| Document | Description |
|----------|-------------|
| [ARCHITECTURE](ARCHITECTURE.md) | System design, data flow, module structure |
| [STATE_MACHINES](STATE_MACHINES.md) | Tier escalation and job lifecycle state machines |
| [CONCURRENCY](../CONCURRENCY.md) | Threading model, async/sync boundaries, deadlock prevention |
| [INTERNALS](INTERNALS.md) | Prompt engineering, algorithms, implementation details |

## API & Integration

| Document | Description |
|----------|-------------|
| [API](API.md) | Programmatic usage, MCP server, tool reference |
| [OPENCLAW](OPENCLAW.md) | Open Claw integration, skills, workflows |

## Operations & Maintenance

| Document | Description |
|----------|-------------|
| [MIGRATION](MIGRATION.md) | Error hierarchy migration guide |
| [SECURITY_REVIEW](SECURITY_REVIEW_2026-01-21.md) | Security audit findings and mitigations |
| [CHANGELOG](../CHANGELOG.md) | Version history and changes |
| [ROADMAP](../ROADMAP.md) | Development roadmap and planned features |

## Strategy Documents

| Document | Description |
|----------|-------------|
| [STRATEGY_PORTFOLIO](STRATEGY_PORTFOLIO.md) | Available strategy types and usage |

## By Topic

### Scraping & Data Collection
- [ARCHITECTURE](ARCHITECTURE.md) → "8-Tier Scraping Engine" section
- [SCRAPING_IMPROVEMENTS](SCRAPING_IMPROVEMENTS_2026-01-23.md) → Recent enhancements

### Error Handling
- [MIGRATION](MIGRATION.md) → Typed error hierarchy
- Source: `src/primr/utils/errors.py`

### Testing
- Source: `tests/` directory
- Property tests: `tests/property_tests/`

### Configuration
- [CONFIG](CONFIG.md) → Full reference
- Source: `src/primr/utils/config_validation.py`
