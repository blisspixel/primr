# Primr Documentation

The full documentation map. For an overview, install, and quickstart, start
with the [root README](../README.md). For the development contract (how to
change primr's source), see [CLAUDE.md](../CLAUDE.md); to operate the primr
CLI/MCP from an agent, see [AGENTS.md](../AGENTS.md).

Guides are grouped by what you are trying to do, following the
[Diataxis](https://diataxis.fr/) split: learning, doing, looking up, and
understanding.

## Getting started (tutorials)

| Document | Description |
|----------|-------------|
| [API_KEYS](API_KEYS.md) | API key setup, security, and troubleshooting |
| [CONFIG](CONFIG.md) | First-run configuration and the full settings reference |
| [AZURE_QUICKSTART](AZURE_QUICKSTART.md) | Stand up the team/org Azure deployment end to end |

## How-to guides (task-oriented)

| Document | Description |
|----------|-------------|
| [BATCH](BATCH.md) | Run primr across many companies from a CSV |
| [RECOVERY](RECOVERY.md) | Resume after a crash, reboot, or interrupted run |
| [IMPROVE](IMPROVE.md) | Improve and refine an existing report (`primr improve` / `refine`) |
| [SKILL_PACK](SKILL_PACK.md) | `primr skills` end to end: planning, curation, artifacts, CLI/MCP |
| [EVAL](EVAL.md) | Evaluate and compare models with the eval harness |
| [MODEL_ONBOARDING](MODEL_ONBOARDING.md) | Register and validate a new model |
| [OPENCLAW](OPENCLAW.md) | OpenClaw integration and governed workflows |
| [COPILOT_COWORK_GUIDE](COPILOT_COWORK_GUIDE.md) | Sideload a skill pack into Microsoft 365 Copilot Cowork |
| [COPILOT_STUDIO_GUIDE](COPILOT_STUDIO_GUIDE.md) | Use primr from Copilot Studio |
| [FOUNDRY_AGENT_GUIDE](FOUNDRY_AGENT_GUIDE.md) | Use primr from a Microsoft Foundry agent |
| [CLOUD_DEPLOYMENT](CLOUD_DEPLOYMENT.md) | Serverless deployment on AWS, Azure, and GCP |
| [SECURITY_OPS](SECURITY_OPS.md) | Key rotation, audit logs, operational security |

## Reference (look-up)

| Document | Description |
|----------|-------------|
| [API](API.md) | MCP server and A2A protocol, programmatic usage |
| [STRATEGY_PORTFOLIO](STRATEGY_PORTFOLIO.md) | Strategy document types and selection |
| [CHANGELOG](CHANGELOG.md) | Version history |
| [MIGRATION](MIGRATION.md) | Error-hierarchy migration notes |
| [ROADMAP](../ROADMAP.md) | Ordered development queue and version plan |

## Explanation (understanding why)

| Document | Description |
|----------|-------------|
| [ARCHITECTURE](ARCHITECTURE.md) | System design and the 9-tier scraping engine |
| [ARTIFACTS](ARTIFACTS.md) | The research-vs-shipping artifact pipeline and ship-time gates |
| [INTERNALS](INTERNALS.md) | Core algorithms and prompt strategy |
| [STATE_MACHINES](STATE_MACHINES.md) | Tier escalation and job lifecycle |
| [CONCURRENCY](CONCURRENCY.md) | Threading and concurrency model |
| [SECURITY](SECURITY.md) | Security policy and the scoped AI/agent threat model |
| [design/](design/README.md) | Per-workstream design docs and decision audits (incl. the v1.24.0 cross-provider eval) |

## Contributing

| Document | Description |
|----------|-------------|
| [CONTRIBUTING](CONTRIBUTING.md) | Dev environment setup and the contribution workflow |
| [CLAUDE.md](../CLAUDE.md) | The development contract: seams, constraints, verification gates |
