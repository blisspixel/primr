# Claude Code plugin — primr

This directory is the Claude Code plugin for [primr](https://github.com/blisspixel/primr). It bundles the primr MCP server and the primr skill into one install.

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

## Other hosts

For Cursor, Windsurf, Kiro, VS Code + Copilot, and others, see [`../clients/`](../clients/) for per-host MCP config snippets and skill / steering placement guidance.

## What's in here

- [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) — plugin manifest (name, version, metadata).
- [`.mcp.json`](.mcp.json) — MCP server registration (`primr mcp` over stdio).
- [`skills/primr/SKILL.md`](skills/primr/SKILL.md) — skill definition with frontmatter (cost gate, async handling, mode selection, hypothesis memory).
- [`skills/primr/references/`](skills/primr/references/) — three reference files (modes-and-strategies, custom-strategy-yaml, downstream-handoff) that the skill links to but Claude Code only loads when the skill actually navigates to them.

## Updating

The skill body and `AGENTS.md` at the repo root are kept in sync. If you change one, change the other.
