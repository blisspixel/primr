# Primr portable Agent Plugin

This directory is an experimental distribution artifact for the Agent Plugins
v1.0.0 Working Draft. It packages two portable Agent Skills and Primr's local
MCP server:

- `primr` routes free and paid company-research requests and enforces the
  estimate-and-approval workflow for billable runs.
- `primr-zero` collects keyless evidence and hands research and writing to the
  current agent host without making Primr model API calls.
- `mcp.json` starts the installed `primr mcp` stdio server. Loading the server
  does not launch research or authorize provider spend.

## Compatibility scope

The package targets the published [Agent Plugins v1.0.0 Working
Draft](https://agent-plugins.org/specification), not a final standard. At the
time of use, consult the specification's
[compatible-client registry](https://agent-plugins.org/compatible-clients).
Clients can adopt skills and MCP transports incrementally, so a registry entry
does not mean that every component works in every client version.

Agent Plugins v1 standardizes exactly two portable component types: Agent
Skills and MCP servers. Primr's `mcp.json` uses a bare `primr` executable token,
so its MCP component requires Primr to be installed and discoverable through
the client's executable search rules. An unavailable MCP component does not
invalidate the packaged skills.

Claude Code is not claimed as a portable-v1 client here. Primr's existing
`claude-code/` plugin remains the supported Claude-specific package and is
maintained independently.

## Generation and drift control

Do not edit `plugin.json`, `mcp.json`, or `skills/` in this directory directly.
They are generated from `pyproject.toml`, `claude-code/skills/primr`, and the
canonical `.agents/skills/primr-zero` source:

```bash
uv run --no-sync python scripts/sync_agent_plugin.py
uv run --no-sync python scripts/sync_agent_plugin.py --check
```

The generator removes the Claude-specific `argument-hint` field and the
experimental Agent Skills `allowed-tools` field from the `primr` mirror.
`allowed-tools` is valid Agent Skills metadata, but support and preapproval
semantics vary by client, so Primr does not publish it as a portable guarantee.
The skill instructions and companion files otherwise remain byte-identical to
their source. Tests validate the generated identity, the pinned v1 JSON
schemas, Agent Skills frontmatter, path containment, package-version parity,
and source drift.

The source distribution includes this directory. The Python wheel continues to
carry the installed `primr-zero` resource used by `primr prep`; it is not a
second editable source for this plugin.

## Spend boundary

Installing or loading this package does not authorize a paid Primr run. A
provider-backed run still requires a fresh estimate and explicit approval.
Configured API keys are capability, not consent to spend.
