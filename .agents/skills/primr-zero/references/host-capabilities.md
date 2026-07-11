# Host Capability Selection

Use capabilities, not brand assumptions. Check whether the current host can:

- run local shell commands;
- read and write local files;
- search the public web with citations;
- fetch exact URLs;
- schedule a one-shot continuation;
- preserve task state across quota resets.

## Capability profiles

### Shell, files, and web research

Run `primr prep`, read the bundle, research external gaps, write the report,
and run deterministic QA. This is the preferred path for coding agents and
CLI-based hosts.

### Files and web research, no shell

Ask the user for a previously generated prep bundle. If none exists, use the
host-native research method and disclose that DNS, adaptive scraping, ATS
adapters, trace artifacts, and local QA were unavailable.

### Files only

Analyze the supplied packet and sources. Do not claim current external coverage.
Produce a gap list that a search-capable host or human can close.

### Interactive research UI

Use the UI's supported research mode and attach or import the prep bundle. Do
not automate the consumer web application or extract session credentials.

## Skill locations

The canonical repository skill is `.agents/skills/primr-zero`. Codex, GitHub
Copilot, and Gemini CLI can discover that shared location. The Claude plugin
ships a checked mirror under `claude-code/skills/primr-zero` because Claude's
native skill directory differs.

For personal installation, Codex uses `~/.agents/skills`, Copilot supports
`~/.agents/skills` or `~/.copilot/skills`, Gemini CLI supports
`~/.agents/skills` or `~/.gemini/skills`, and Claude Code uses
`~/.claude/skills`.

Do not hardcode plan quotas in the skill. Hosts change limits frequently. Read
the host's current usage display or official documentation when capacity
matters.
