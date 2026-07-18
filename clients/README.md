# Per-client install snippets

Copy-pasteable MCP config fragments and agent guidance for AI clients other
than Claude Code. Claude Code users can install the plugin under
[`../claude-code/`](../claude-code/); it bundles the MCP server registration and
the `primr`, `primr-zero`, and `company-brief` skills.

All MCP clients here use the same `mcpServers` JSON shape; only the file
location and a few optional fields differ. Every snippet assumes `pip install
primr` is already done and `primr` is on `PATH`. Provider keys are needed for
the billable full pipeline, but not for `primr prep` or `primr recon`.

## Pick the integration

| Goal | Install |
|------|---------|
| Full provider-backed Primr | MCP snippet plus the full `primr` operating guidance |
| Hard-zero host-assisted dossier | Portable `primr-zero` skill; use `primr prep` when the launcher works and host-native research when it does not |
| Host has no local shell | Use host-native cited research, or import an existing prep bundle when one is available |

## Two pieces, every client

There are two things to wire up per client:

1. **The MCP server** - so the AI can call primr's structured tools. JSON snippet, dropped at the client's MCP config path.
2. **The agent guidance** - so the AI knows *when* to reach for primr, *how* to enforce the cost gate, and *how* to handle the long-running async lifecycle. Different clients support this differently; see the table below.

The hard-zero workflow is intentionally simpler: the host needs the
`primr-zero` skill. A working local launcher adds Primr's bounded prep bundle,
DNS evidence, scrape traces, and deterministic QA. Without one, the skill uses
the host's official web research and file surfaces, records the missing
deterministic coverage, and still produces the strongest honest dossier it
can. It never launches a Primr MCP research job or silently switches to API
billing.

## MCP config

| Client | Drop snippet at | Snippet |
|---|---|---|
| Kiro (workspace) | `.kiro/settings/mcp.json` | [`kiro/mcp.json`](kiro/mcp.json) |
| Kiro (global) | `~/.kiro/settings/mcp.json` | [`kiro/mcp.json`](kiro/mcp.json) |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` (Windows: `%USERPROFILE%\.codeium\windsurf\mcp_config.json`) | [`windsurf/mcp_config.json`](windsurf/mcp_config.json) |
| Cursor (project) | `.cursor/mcp.json` | same as Windsurf snippet |
| Cursor (global) | `~/.cursor/mcp.json` | same as Windsurf snippet |
| VS Code + Copilot | `.vscode/mcp.json` | same as Windsurf snippet |

For Claude Desktop, the path is `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows). Same snippet shape as Windsurf.

## Agent guidance

| Client | What it supports | What to do |
|---|---|---|
| **Kiro** (recommended path) | Kiro Skills follow the open [agentskills.io](https://agentskills.io) standard - the same `SKILL.md` format Claude Code uses. | Copy [`../claude-code/skills/primr/SKILL.md`](../claude-code/skills/primr/SKILL.md) and the entire `references/` directory to `~/.kiro/skills/primr/` (global) or `.kiro/skills/primr/` (workspace). Kiro auto-loads it on-demand based on the description. |
| **Kiro** (alternative) | Steering files at `~/.kiro/steering/` or `.kiro/steering/`. AGENTS.md is auto-detected at workspace root. | Drop [`../AGENTS.md`](../AGENTS.md) at the user's workspace root. It loads always, not on-demand - fine for projects where primr is the main tool, heavier than needed for general-purpose workspaces. |
| **Windsurf** | `.windsurfrules` at project root, plain markdown, merged with global rules. No skill auto-loading. | Reference AGENTS.md from `.windsurfrules`: `See @AGENTS.md for primr usage guidance.` Or paste the AGENTS.md content directly into `.windsurfrules`. |
| **Cursor** | `.cursor/rules/*.md` with frontmatter (`description`, `globs`, `alwaysApply`). | Drop AGENTS.md content into `.cursor/rules/primr.md` with `description: ...` matching the skill description. |
| **VS Code + Copilot** | Project Agent Skills in `.github/skills`, `.claude/skills`, or `.agents/skills`; personal skills in `~/.copilot/skills` or `~/.agents/skills`. `.github/copilot-instructions.md` remains an always-loaded fallback. | Prefer the complete Agent Skill directory. Use `copilot-instructions.md` only when the selected Copilot surface does not support skills. |

## Primr Zero skill placement

The canonical skill is [`../.agents/skills/primr-zero/`](../.agents/skills/primr-zero/).
Copy the entire directory, not only `SKILL.md`, so the report, host-capability,
subscription-boundary, and local-capacity references remain available.

| Host shape | Placement |
|------------|-----------|
| Repository Agent Skills | `<workspace>/.agents/skills/primr-zero/` when the host supports repository skill discovery |
| Codex personal skills | `~/.agents/skills/primr-zero/` |
| Claude Code project or personal skills | `.claude/skills/primr-zero/` in this repository or `~/.claude/skills/primr-zero/`; the plugin mirror remains under `../claude-code/skills/primr-zero/` |
| GitHub Copilot personal skills | `~/.agents/skills/primr-zero/` or `~/.copilot/skills/primr-zero/` |
| Gemini CLI personal skills | `~/.agents/skills/primr-zero/` or `~/.gemini/skills/primr-zero/` |
| Kiro or another Agent Skills host | The host's documented global or workspace skill directory |
| Cursor, Windsurf, or Copilot instruction fallback | Reference the canonical `SKILL.md` from the host's project instructions and preserve the accompanying references |

For Cowork or another interactive research UI, do not automate the consumer
web application. Import the prep bundle through the official UI and use
`HOST_WORKFLOW.md` plus the skill content as supported instructions.

The provider-backed operating guidance currently lives in two manually aligned
forms:

- [`../claude-code/skills/primr/SKILL.md`](../claude-code/skills/primr/SKILL.md) - skill frontmatter and paths relative to its packaged references for Claude Code and Kiro skill auto-loading.
- [`../AGENTS.md`](../AGENTS.md) - aligned operating guidance with repository-root reference paths and no skill frontmatter, for tools that do not have a skill format.

If you contribute changes to one, mirror them into the other.

The zero-cost skill uses a stronger contract: `.agents/skills/primr-zero/` is
canonical; the repository Claude, Claude plugin, and Python-package copies are
byte-identical; and `python scripts/sync_primr_zero_skill.py --check` verifies
all mirrors. The full Claude operator skill is also mirrored into
`.claude/skills/primr/`; `python scripts/sync_primr_operator_skill.py --check`
verifies it. A wheel installation can place the Zero skill directly:

```bash
primr prep --install-skill ~/.agents/skills/primr-zero
```

## macOS PATH gotcha

Windsurf, Cursor, VS Code, and Claude Desktop are GUI Electron apps. On macOS they do not inherit your shell's PATH, so `command: "primr"` will fail to launch the MCP server even when `primr` works fine in your terminal. Two fixes:

1. **Use the absolute path to primr** - run `which primr` in your shell and substitute the full path:
   ```json
   { "command": "/Users/you/.local/bin/primr", "args": ["mcp"] }
   ```
2. **Use the Python module form** - works for any Python that has `primr` installed:
   ```json
   { "command": "/usr/local/bin/python3", "args": ["-m", "primr.mcp_server.cli", "--stdio"] }
   ```

Run `primr doctor` in your shell to confirm primr is reachable. Kiro is also a desktop app but its MCP loader has been more forgiving in practice. If `command: "primr"` fails on Kiro, fall back to the same fixes.

## Verifying the install

For the hard-zero path, first verify the local collection contract:

```bash
primr prep "ExampleCo" https://example.co --dry-run
```

The output must report `$0.00` incremental API spend, zero model calls, and no
host-plan use during collection. Then ask the client:

> Use primr-zero to prepare a sourced dossier for ExampleCo without model API spend.

The host should run `primr prep`, read the emitted manifest and packet, and use
its own research allowance for synthesis. It must not switch to provider API
billing silently.

For MCP, once configured, ask the AI client something like:

> Estimate a primr run on contoso.com - don't actually launch it.

If the client reports the primr MCP server is connected and tools enumerate (`mcp__primr__estimate_run` etc.), and it returns a structured estimate, you're done. If not, check:

- Is `primr` installed in the same Python environment the client launches?
- Does `primr doctor` succeed in your shell? Keys are required only for the
  provider-backed workflow you intend to launch.
- Are you hitting the macOS GUI PATH issue above?
