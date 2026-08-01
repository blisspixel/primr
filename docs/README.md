# Primr Documentation

Company URL → sourced strategic brief. Primr is a local-first CLI and agent
tooling stack for discovery, account planning, diligence, and strategy work.

![Illustrative primr CLI session for ExampleCo: dry-run cost estimate and completed report artifacts](images/primr-demo.png){ width="920" }

*Illustrative demo with placeholder company data. Not a live capture of a real
target. Source and regenerate notes live in the root README and
[`CONTRIBUTING.md`](CONTRIBUTING.md).*

For install and the shortest path in, start with the
[root README](https://github.com/blisspixel/primr/blob/main/README.md). For the
development contract (how to change primr's source), see
[CLAUDE.md](https://github.com/blisspixel/primr/blob/main/CLAUDE.md). To operate
the primr CLI/MCP from an agent, see
[AGENTS.md](https://github.com/blisspixel/primr/blob/main/AGENTS.md).

Guides are grouped by what you are trying to do, following the
[Diataxis](https://diataxis.fr/) split: learning, doing, looking up, and
understanding.

> **Index currency:** reviewed against primr **1.39.0** on **2026-08-01**. The
> *Updated* column is each document's last substantive revision (git
> `last-commit` date). `tests/test_docs_index.py` fails CI if a doc under
> `docs/` is missing from this map or an index link does not resolve, so the
> map and the tree cannot silently drift apart.

## Getting started (tutorials)

| Document | Description | Updated |
|----------|-------------|---------|
| [ZERO_COST](ZERO_COST.md) | Run keyless collection and finish a sourced dossier with an existing agent plan | 2026-07-18 |
| [API_KEYS](API_KEYS.md) | API key setup, validation (`primr keys test`), security, and troubleshooting | 2026-07-21 |
| [CONFIG](CONFIG.md) | First-run configuration and the full settings reference | 2026-07-21 |
| [RUN_MODES](RUN_MODES.md) | Run modes, costs, strategy selection, output locations, and zero-cost `primr render` (Markdown to DOCX/TXT) | 2026-08-01 |
| [AZURE_QUICKSTART](AZURE_QUICKSTART.md) | Stand up the team/org Azure deployment end to end | 2026-07-18 |

## How-to guides (task-oriented)

| Document | Description | Updated |
|----------|-------------|---------|
| [BATCH](BATCH.md) | Run primr across many companies from a CSV | 2026-07-18 |
| [RECOVERY](RECOVERY.md) | Resume after a crash, reboot, or interrupted run | 2026-07-17 |
| [IMPROVE](IMPROVE.md) | Improve and refine an existing report (`primr improve` / `refine`) | 2026-04-10 |
| [SKILL_PACK](SKILL_PACK.md) | `primr skills` end to end: planning, curation, artifacts, CLI/MCP | 2026-07-17 |
| [EVAL](EVAL.md) | Evaluate and compare models with the eval harness | 2026-07-17 |
| [MODEL_ONBOARDING](MODEL_ONBOARDING.md) | Register and validate a new model | 2026-06-29 |
| [AGENT_INTEGRATION](AGENT_INTEGRATION.md) | Operate Primr from MCP, A2A, skills, and agent hosts | 2026-07-21 |
| [OPENCLAW](OPENCLAW.md) | OpenClaw integration and governed workflows | 2026-07-17 |
| [COPILOT_COWORK_GUIDE](COPILOT_COWORK_GUIDE.md) | Sideload a skill pack into Microsoft 365 Copilot Cowork | 2026-07-21 |
| [COPILOT_STUDIO_GUIDE](COPILOT_STUDIO_GUIDE.md) | Use primr from Copilot Studio | 2026-07-21 |
| [FOUNDRY_AGENT_GUIDE](FOUNDRY_AGENT_GUIDE.md) | Use primr from a Microsoft Foundry agent | 2026-07-21 |
| [CLOUD_DEPLOYMENT](CLOUD_DEPLOYMENT.md) | Serverless deployment on AWS, Azure, and GCP | 2026-07-18 |
| [SECURITY_OPS](SECURITY_OPS.md) | Key rotation, audit logs, operational security | 2026-07-17 |

## Reference (look-up)

| Document | Description | Updated |
|----------|-------------|---------|
| [API](API.md) | MCP server and A2A protocol, programmatic usage | 2026-07-18 |
| [Job Status](JOB_STATUS.md) | Versioned CLI, MCP, A2A, and API lifecycle contract | 2026-07-10 |
| [STRATEGY_PORTFOLIO](STRATEGY_PORTFOLIO.md) | Strategy document types and selection | 2026-07-21 |
| [NEXT_STEPS](NEXT_STEPS.md) | What to build next, why it comes next, and what not to do yet | 2026-08-01 |
| [CHANGELOG](CHANGELOG.md) | Version history | 2026-07-21 |
| [MIGRATION](MIGRATION.md) | Error-hierarchy migration notes | 2026-02-02 |
| [EVAL_V1_24_0](EVAL_V1_24_0.md) | Historical decision record: the v1.24.0 cross-provider eval plan | 2026-06-26 |
| [ROADMAP](https://github.com/blisspixel/primr/blob/main/ROADMAP.md) | Ordered development queue and version plan | — |

## Explanation (understanding why)

| Document | Description | Updated |
|----------|-------------|---------|
| [ARCHITECTURE](ARCHITECTURE.md) | System design and the 9-tier scraping engine | 2026-07-21 |
| [ARTIFACTS](ARTIFACTS.md) | The research-vs-shipping artifact pipeline and ship-time gates | 2026-07-21 |
| [INTERNALS](INTERNALS.md) | Core algorithms and prompt strategy | 2026-07-21 |
| [STATE_MACHINES](STATE_MACHINES.md) | Tier escalation and job lifecycle | 2026-02-02 |
| [CONCURRENCY](CONCURRENCY.md) | Threading and concurrency model | 2026-07-12 |
| [SECURITY](SECURITY.md) | Security policy and the scoped AI/agent threat model | 2026-07-21 |
| [design/](design/README.md) | Per-workstream design docs and decision audits | — |

## Contributing

| Document | Description | Updated |
|----------|-------------|---------|
| [CONTRIBUTING](CONTRIBUTING.md) | Dev environment setup and the contribution workflow | 2026-08-01 |
| [CLAUDE.md](https://github.com/blisspixel/primr/blob/main/CLAUDE.md) | The development contract: seams, constraints, verification gates | — |
