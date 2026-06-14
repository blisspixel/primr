# Design Docs

Breakdown documents for the [Version Plan](../../ROADMAP.md#version-plan-1x--20--30)
workstreams. The ROADMAP owns *what and in which order*; these docs own *how
and why* at one level more detail. Keep them in lockstep: when a workstream's
scope changes, update both.

Conventions:

- **No dates.** Bands are gated on exit criteria; sequencing is dependency
  order.
- **Validation cost is part of the design.** Every doc states what can be
  verified free (deterministic tests, mocks) vs what needs a paid run, and
  budgets the paid part.
- **Explicitly-not sections are binding.** They exist so scope doesn't get
  re-litigated; changing one is a deliberate decision, not drift.
- **No real company names** in examples — placeholders only (see
  `docs/CONTRIBUTING.md`).

| Doc | Workstream | Version band |
|-----|------------|--------------|
| [research-tradecraft.md](research-tradecraft.md) | Collection-first → hypothesis-first: framing, Day-1 hypothesis tree, plan checkpoint, argument-derived structure (deepens #4) | 1.x → 2.0 |
| [agentic-balance.md](agentic-balance.md) | Rule vs judgment: when a primr component stays a deterministic workflow vs becomes a Level-2 model decision; the keep-list and budget couplings under the tradecraft work | cross-cutting |
| [1x-completion.md](1x-completion.md) | Finishing the excellent single-shot brief | 1.x |
| [engineering-excellence.md](engineering-excellence.md) | Anti-slop enforcement layer: dev-facing CLAUDE.md contract, architectural fitness functions, file-size ratchet, CLI verb convention, toolchain currency | cross-cutting |
| [23-orchestrator-refactor-map.md](23-orchestrator-refactor-map.md) | Working map for the #23 orchestrator refactor (stages, tangles, batch order) | 1.x |
| [2.0-backend-freedom.md](2.0-backend-freedom.md) | Capability routing + local/hybrid inference | 2.0 |
| [provider-expansion.md](provider-expansion.md) | OpenAI/Anthropic recipes, Bedrock/Foundry gateways, $0 local profile (verified provider catalog, June 2026) | 1.x Phase A; 2.0 Phases B/C |
| [2.0-research-memory.md](2.0-research-memory.md) | Cross-run memory, company tracking, delta mode | 2.0 |
| [2.0-agent-control-plane.md](2.0-agent-control-plane.md) | Per-tool authz, approval tokens, audit log | 2.0 |
| [3.0-research-frontier.md](3.0-research-frontier.md) | VLM extraction, knowledge compounding, artifact handoff | 3.0 |
