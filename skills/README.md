# Primr Skills Directory

This directory contains agent-facing skill packages for Primr integrations.

These files are not runtime code. They are lightweight decision guides that help clients such as Claude-style skill loaders and OpenClaw pick the right MCP tools and resources.

## Design Rules

- Keep each skill narrow and intent-based.
- Treat MCP as the source of truth for current modes, defaults, and outputs.
- Keep volatile facts out of `SKILL.md` where possible.
- Use progressive disclosure: start with the skill, then read references or MCP resources only when needed.
- Duplicate as little product logic as possible across skills.

## Current Skills

| Skill | Purpose |
|-------|---------|
| `company-research` | Start and monitor research runs |
| `scrape-strategy` | Choose the right mode when scraping is weak |
| `hypothesis-tracking` | Manage durable company findings |
| `qa-iteration` | Review and improve reports or strategies |

## Structure

```text
skills/<skill-name>/
├── SKILL.md
└── references/
```

## Integration Guidance

- Repo skills should stay host-neutral and MCP-first.
- OpenClaw-specific packaging lives under `openclaw/skills/`.
- If Primr behavior changes, update MCP resources first, then adjust any skill text that still needs to mention the change.
