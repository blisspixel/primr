# Primr Strategy Document Portfolio

Primr strategy modules turn a completed Strategic Overview and its supporting
evidence into an executive decision document. They are outside-in analyses, not
substitutes for internal discovery, implementation design, legal advice, or an
approved investment case.

## Strategy Standards

Every strategy must:

1. Start from business outcomes, economics, customers, operating constraints,
   and accountable decisions.
2. Preserve the evidence strength of the Strategic Overview, discovery notes,
   recon signals, hiring signals, and current external research.
3. Distinguish observations, inferences, hypotheses, and recommendations.
4. Compare credible alternatives, including conventional process or software
   changes when AI or a large technology program is not the best first move.
5. Make assumptions, decision criteria, owners, validation actions, stop
   conditions, and unresolved questions visible.
6. Use transparent facilitation tools. Covert persuasion, manufactured urgency,
   misattributed authorship, and favored scoring criteria are not acceptable.

## Default AI Strategy

The provider-backed default uses
`src/primr/prompts/strategies/ai_strategy.yaml`. The historical
`ai_first_transformation.yaml` remains in the repository for compatibility and
reference, but it is not the default contract or a selectable CLI strategy.

The default document is designed for the CEO, CIO, board, executive team, and
accountable business owners. Its narrative order is deliberate:

1. Executive decisions and company business context.
2. Economic engine, enterprise performance agenda, strategic tensions, and
   ranked value pools across defend, improve, extend, and create choices.
3. Industry direction and art of the possible, separated into proven,
   emerging, frontier, and unsupported patterns.
4. Evidence basis, business readiness, and the complete observed technology
   and service stack.
5. Prioritized initiatives, explicit choices, quick wins, bigger bets, and
   places where AI is not the best first move.
6. Business case, fully loaded unit economics, operating model, and adoption.
7. Architecture and workload placement across embedded SaaS, public cloud,
   multicloud, private or on-premises accelerated infrastructure, edge, and
   hybrid options when material.
8. Governance, risk, learning gates, roadmap, and board actions.

Every prioritized initiative receives a decision card with an accountable
owner, evidence, baseline and target, stack fit, dependencies, architecture
options, build or buy rationale, fully loaded economics, a 30-day action, a
90-day test, success measures, risk controls, a kill criterion, and a revisit
trigger. Each initiative must also name the non-AI alternative and opportunity
cost. Missing internal inputs produce formulas and validation requests, not
fabricated precision.

The technology section uses a disposition ledger. Every material observed
ecosystem must be marked for use, integration, containment, replacement,
deferral, validation, or as immaterial. This keeps email, collaboration, SaaS,
cloud, data, security, model, and infrastructure signals connected to the
business portfolio without treating a DNS signal as proof of production use.
Infrastructure placement is workload-specific and must consider demand shape,
utilization, latency, sovereignty, integration, power, cooling, networking,
storage, hardware life, and refresh risk. Neither public cloud nor owned
accelerated infrastructure is the default answer.

### Platform Selection

The selected platform is an evaluation emphasis, not an exclusive answer.
Every relevant observed ecosystem remains in scope.

- No strong recon signal produces one vendor-neutral strategy.
- One strong infrastructure signal emphasizes that ecosystem in one strategy.
- Multiple strong infrastructure signals produce one integrated,
  vendor-neutral strategy.
- An explicit multi-platform command intentionally produces separate strategy
  artifacts for comparison.
- `--platform ms` remains an explicit shorthand for `azure private`.

DNS records can indicate configuration or integration, but they do not prove a
contract, active production use, license scope, primary cloud, maturity, or
spend. The strategy preserves those boundaries and names what must be
validated.

Vendor guidance does not pin a dated product catalog. Current service names,
lifecycle status, regional availability, pricing, architecture guidance, and
compliance claims must have official support. A run without that support must
leave the claim unasserted and state the evidence gap and validation action.

## Available Strategy Modules

Run `primr --list-strategies` for the installed catalog. The repository ships
these YAML-defined modules:

| Strategy type | Primary audience | Intended decision surface |
|---------------|------------------|---------------------------|
| `ai` | CEO, CIO, board, business owners | Business-first AI portfolio, economics, operating model, architecture, and governance |
| `customer_experience` | CMO, customer and service leaders | Customer journeys, experience priorities, investment choices, and measurement |
| `modern_security_compliance` | CISO, CIO, risk leaders | Security posture, compliance choices, priorities, and investment |
| `data_fabric_strategy` | CDO, CTO, data leaders | Data foundation, governance, architecture choices, and AI readiness |

The historical AI-first YAML and the cloud-migration and data-strategy
placeholder YAMLs are intentionally absent from the selectable catalog.
Skills generation is a separate workflow exposed through `primr skills`; it is
not available through `--ai-strategy-only`.

## Usage

Generate the Strategic Overview and default AI Strategy:

```bash
primr "ExampleCo" https://example.co
```

Generate only the Strategic Overview:

```bash
primr "ExampleCo" https://example.co --no-ai-strategy
```

Apply an explicit ecosystem emphasis:

```bash
primr "ExampleCo" https://example.co --platform azure
```

Generate a different strategy type:

```bash
primr "ExampleCo" https://example.co --strategy-type customer_experience
```

Quote a standalone strategy from an existing report without starting model
work:

```bash
primr --ai-strategy-only "output/ExampleCo_Strategic_Overview.md" --dry-run
```

Run the same command without `--dry-run` only after reviewing the emitted cost,
time, model-call, and platform estimate. Interactive runs require approval;
`--skip-confirm` is the explicit automation override. The report must be a
regular, non-linked file under the fixed `output/` or `working/` root. Primr
validates its content digest and generates from a private stable snapshot, so a
report changed during the approval window fails closed before any model call.

Standard strategy context retains up to 200,000 report characters. This covers
a normal full Strategic Overview instead of silently taking only its opening
50,000 characters, while preserving a deterministic bound for pathological
inputs.

## Implementation Contract

When adding or changing a strategy:

- Keep the YAML under `src/primr/prompts/strategies/`.
- Define a truthful audience, purpose, evidence limits, sections, and output
  contract.
- Use the shared epistemic and formatting rules, with bounded strategy-specific
  overrides where needed.
- Keep current vendor research dynamic rather than shipping dated product
  catalogs as authoritative context.
- Add contract tests for section order, evidence intake, platform variants,
  output requirements, and prohibited failure modes.
- Update README, run-mode guidance, this portfolio, roadmap, and changelog when
  public behavior changes.
- Validate with local tests and QA fixtures. Do not spend on a live model run
  without a fresh estimate and explicit approval.

## Source of Truth

- Default AI Strategy: `src/primr/prompts/strategies/ai_strategy.yaml`
- Strategy discovery: `src/primr/prompts/registry.py`
- Prompt composition: `src/primr/prompts/composer.py`
- Strategy evidence assembly: `src/primr/core/strategy_prompt_parts.py`
- Public strategy catalog: `primr --list-strategies`
