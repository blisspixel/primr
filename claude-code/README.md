# Claude Code plugin - primr

This directory is the Claude Code plugin for
[primr](https://github.com/blisspixel/primr). It bundles the Primr MCP server
and three skills into one install:

- **primr** - routes a clean company-and-URL request to Primr Zero by default,
  or drives the metered pipeline after explicit paid intent, an estimate, and
  approval. Needs `pip install primr`; API keys are only for provider-backed
  runs.
- **primr-zero** - runs keyless `primr prep`, then uses Claude's existing plan allowance to research external gaps and write a substantial host-assisted dossier after the host is verified not to bill API usage or overages. Needs Primr, but no model API key or GPU.
- **company-brief** - the primr research method as a standalone skill. Uses only the host's own tools (web search, page fetch, shell DNS lookups) at subscription cost: no primr install, no API keys, no GPU. A lighter brief (15-25 sources vs 40-55, no cross-validation or QA gates), but a real one, for people who have a Claude/Copilot plan and nothing else.

## Install

```bash
pip install primr
# Optional for provider-backed runs only:
primr init
```

Then in Claude Code:

```
/plugin marketplace add blisspixel/primr
/plugin install primr@blisspixel-primr
```

That registers the MCP server (`primr mcp`, exposed as `mcp__primr__*` tools)
and all three skills, loaded on demand from their descriptions.

Then ask Claude:

```text
primr "ExampleCo" https://example.co
```

That bare request defaults to Primr Zero. Claude runs `primr prep` internally
and uses its current research and reasoning surface, so the user does not need
to choose an internal mode. Say "paid provider-backed Primr" or "premium
Primr" to select the metered pipeline; Claude must still show the estimate and
wait for approval. Configured API keys alone never select it.

## Skill-only install (no plugin)

If you only want the skill - not the MCP server - paste this to Claude Code:

> Fetch `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/primr/SKILL.md` and save it to `~/.claude/skills/primr/SKILL.md`. Then fetch the four files under `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/primr/references/` and save them under `~/.claude/skills/primr/references/`. Then run `pip install primr`. Run `primr init` only if you also want provider-backed runs.

The skill works fine without the MCP server - it just falls back to the `primr`
CLI for everything. It also contains an inline Primr Zero handoff, so a later
request for a free or existing-agent-plan run cannot be mistaken for the paid
`--mode scrape` path even when the separate `primr-zero` skill is not installed.
Install the full zero-cost skill below for its complete host research, report,
and subscription-boundary contracts.

## Zero-cost skill-only install

If Primr is installed but you do not have model API keys or a GPU, copy the
entire checked skill directory to Claude Code:

```bash
primr prep --install-skill ~/.claude/skills/primr-zero
```

The equivalent source-checkout copy is:

```text
Source: claude-code/skills/primr-zero/
Destination: ~/.claude/skills/primr-zero/
```

Then run:

```bash
primr prep "ExampleCo" https://example.co --dry-run
```

The dry run must report `$0.00`, zero model calls, and no host-plan use during
collection. The skill then uses Claude's supported research and reasoning
surface to synthesize from the emitted packet. Existing subscription terms and
limits still apply. See [`../docs/ZERO_COST.md`](../docs/ZERO_COST.md).

## No install at all (company-brief)

If you can't run primr - no API keys, no Python, locked-down machine - the `company-brief` skill gets you a useful subset of the output using only your agent subscription. Paste this to Claude Code:

> Fetch `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/company-brief/SKILL.md` and save it to `~/.claude/skills/company-brief/SKILL.md`. Then fetch the two files under `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/company-brief/references/` (`report-template.md`, `recon-cheatsheet.md`) and save them under `~/.claude/skills/company-brief/references/`.

Then: `"company-brief Acme Corp https://acme.example"`. The same SKILL.md content also works as custom agent instructions in hosts without a skills system (Microsoft 365 Copilot agents, Gemini CLI, etc.) - it's plain markdown with no primr-specific dependencies.

## Other hosts

For Cursor, Windsurf, Kiro, VS Code + Copilot, and others, see [`../clients/`](../clients/) for per-host MCP config snippets and skill / steering placement guidance.

## What's in here

- [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) - plugin manifest (name, version, metadata).
- [`.mcp.json`](.mcp.json) - MCP server registration (`primr mcp` over stdio).
- [`skills/primr/SKILL.md`](skills/primr/SKILL.md) - skill definition with frontmatter (cost gate, async handling, mode selection, hypothesis memory).
- [`skills/primr/references/`](skills/primr/references/) - four progressive-disclosure references (modes and strategies, custom strategy YAML, downstream handoff, and operational gotchas).
- [`skills/primr-zero/SKILL.md`](skills/primr-zero/SKILL.md) - checked mirror of the portable keyless, host-assisted workflow.
- [`skills/primr-zero/references/`](skills/primr-zero/references/) - host capability, report, subscription-boundary, and local-capacity contracts.
- [`skills/company-brief/SKILL.md`](skills/company-brief/SKILL.md) - the standalone lite-method skill (no primr dependency).
- [`skills/company-brief/references/`](skills/company-brief/references/) - report template + DNS recon cheatsheet.

## Updating

The full `primr` skill body and `AGENTS.md` at the repo root are manually kept
aligned. The canonical `primr-zero` skill lives at
`../.agents/skills/primr-zero/`; synchronize its Claude mirror with
`python scripts/sync_primr_zero_skill.py` and verify it with `--check`.
