# Claude Code plugin — primr

This directory is the Claude Code plugin for [primr](https://github.com/blisspixel/primr). It bundles the primr MCP server and two skills into one install:

- **primr** — drives the full installed pipeline (cost gate, async lifecycle, mode selection). Needs `pip install primr` + API keys.
- **company-brief** — the primr research method as a standalone skill. Uses only the host's own tools (web search, page fetch, shell DNS lookups) at subscription cost: no primr install, no API keys, no GPU. A lighter brief (15-25 sources vs 40-55, no cross-validation or QA gates), but a real one, for people who have a Claude/Copilot plan and nothing else.

## Install

```bash
pip install primr
primr init       # configures API keys (Gemini and/or Grok)
```

Then in Claude Code:

```
/plugin marketplace add blisspixel/primr
/plugin install primr@blisspixel-primr
```

That registers both the MCP server (`primr mcp`, exposed as `mcp__primr__*` tools) and the skill (loaded on-demand based on its description).

## Skill-only install (no plugin)

If you only want the skill — not the MCP server — paste this to Claude Code:

> Fetch `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/primr/SKILL.md` and save it to `~/.claude/skills/primr/SKILL.md`. Then fetch the four files under `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/primr/references/` and save them under `~/.claude/skills/primr/references/`. Then run `pip install primr && primr init`.

The skill works fine without the MCP server — it just falls back to the `primr` CLI for everything.

## No install at all (company-brief)

If you can't run primr — no API keys, no Python, locked-down machine — the `company-brief` skill gets you a useful subset of the output using only your agent subscription. Paste this to Claude Code:

> Fetch `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/company-brief/SKILL.md` and save it to `~/.claude/skills/company-brief/SKILL.md`. Then fetch the two files under `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/company-brief/references/` (`report-template.md`, `recon-cheatsheet.md`) and save them under `~/.claude/skills/company-brief/references/`.

Then: `"company-brief Acme Corp https://acme.example"`. The same SKILL.md content also works as custom agent instructions in hosts without a skills system (Microsoft 365 Copilot agents, Gemini CLI, etc.) — it's plain markdown with no primr-specific dependencies.

## Other hosts

For Cursor, Windsurf, Kiro, VS Code + Copilot, and others, see [`../clients/`](../clients/) for per-host MCP config snippets and skill / steering placement guidance.

## What's in here

- [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) — plugin manifest (name, version, metadata).
- [`.mcp.json`](.mcp.json) — MCP server registration (`primr mcp` over stdio).
- [`skills/primr/SKILL.md`](skills/primr/SKILL.md) — skill definition with frontmatter (cost gate, async handling, mode selection, hypothesis memory).
- [`skills/primr/references/`](skills/primr/references/) — three reference files (modes-and-strategies, custom-strategy-yaml, downstream-handoff) that the skill links to but Claude Code only loads when the skill actually navigates to them.
- [`skills/company-brief/SKILL.md`](skills/company-brief/SKILL.md) — the standalone lite-method skill (no primr dependency).
- [`skills/company-brief/references/`](skills/company-brief/references/) — report template + DNS recon cheatsheet.

## Updating

The skill body and `AGENTS.md` at the repo root are kept in sync. If you change one, change the other.
