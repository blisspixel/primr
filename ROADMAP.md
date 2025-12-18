Primr – Roadmap
Current State: v1.0.0 (December 2025)

Primr is a CLI-first, local research tool designed to support company intelligence research, strategic sensemaking, and AI roadmap development. It supports a structured research process while trying to stay honest about uncertainty and maintain a subject-positive posture.

Primr is intentionally opinionated, local-first, and analysis-driven.

What’s Working Today
Research Engines

Scrape Mode: 4-tier web scraping (requests, httpx, Playwright, aggressive browser), section-by-section extraction, quality grading

Deep Mode: Gemini Deep Research Agent with autonomous multi-step search and synthesis

Full Mode: Sequential scrape + deep research pipeline

Report Generation

Professional TXT, DOCX, and PDF outputs

Citation styles: numbered, inline, sidecar

Automatic citation URL resolution (Google redirect URLs resolved to final destinations)

Structured report sectioning

Internal analysis-first orientation with downstream translation guidance

AI Strategy

AI strategy and roadmap generation

Explicit distinction between AI-enabled vs AI-native

Confidence labeling, deprioritization, governance, and ROI framing

Cloud vendor support: Azure, AWS, GCP, agnostic

Operational Maturity

Cost estimation with confirmation (--dry-run)

Usage tracking and job recovery

System diagnostics (primr doctor)

Strong test coverage (2,200+ tests)

Design Philosophy (Locked)

Primr is optimized for:

Internal prep, not client-ready delivery

Hypothesis generation, not premature conclusions

Helping strong teams move faster and smarter

Delivering most of the value through thinking, framing, and structure

Primr is not:

A generic research scraper

A SaaS collaboration platform

A presentation builder

A “share with the client” tool

These constraints are intentional.

Completed Work
v1.0.0 – Primr Release (Complete)

Rebrand from company_researcher to primr

CLI usage: primr "Company" https://company.com

Simplified research modes: scrape, deep, full

primr doctor system diagnostics

pip-installable via pyproject.toml

Input validation for company name and URL

Stable output directory and artifact structure

v1.1.0 – Code Quality and Hardening (In Progress)

Type guards and runtime validation

Improved error handling with retries, jitter, and backoff

Resource cleanup and cache hygiene

Observability primitives (correlation IDs, structured logging)

Configuration validation and safer defaults

Citation URL resolution (redirect URLs resolved to readable final destinations)

Enhanced prompt engineering for Company Overview and AI Strategy reports

Near-Term Roadmap
v1.2.0 – Stability and Maintainability (Planned)

Goal: Make Primr boringly reliable.

Static analysis compliance (mypy, ruff)

Additional property-based tests

Performance profiling and bottleneck identification

Documentation cleanup and developer guidance

Refined error messages for failed research stages

This phase intentionally adds no new user-facing features.

Medium-Term Roadmap: Make Primr Iterative
v1.3.0 – Research State and Iteration (Planned)

Goal: Move from “generate once” to “think over time.”

Research State Artifacts

Introduce a lightweight local research state file (YAML or JSON)

Track:

initial hypotheses

assumptions

confidence levels

open questions

Persist state across runs for the same company

Explicit Hypothesis Tracking

Clearly separate:

facts

inferences

hypotheses

Mark hypotheses as:

untested

partially validated

invalidated

confirmed

This mirrors how consultants actually work after discovery conversations.

v1.4.0 – Refinement and Learning Loop (Planned)

Goal: Support post-discovery learning without re-running everything from scratch.

Potential capabilities:

primr refine command that accepts:

discovery notes

meeting summaries

client feedback

Re-synthesize insights with:

updated confidence

revised hypotheses

adjusted recommendations

Outputs evolve from:

pre-meeting prep

to post-discovery POV

to proposal-grade thinking

Still local. Still internal.

v1.5.0 – POV and Narrative Evolution (Planned)

Goal: Make Primr the system of record for how thinking evolves.

Versioned research artifacts (v1 prep, v2 post-discovery, v3 POV)

Explicit “what changed and why” sections

Stronger alignment between company overview and AI strategy

Optional narrative framing outputs for internal deck creation

At this point, Primr becomes less a one-shot tool and more a structured research workflow.

Scale Readiness (Intentional, Not Yet Implemented)

Primr is currently optimized for individual and small-team use, running locally with user-provided API keys. This is intentional so the focus remains on output quality, honest uncertainty handling, and usefulness in real consulting workflows.

That said, Primr is being designed with a clear and realistic path to scale if organizational adoption increases.

If Primr were to support hundreds or thousands of internal users, the expected evolution would be:

Execution model
Transition from local execution to centralized, container-based job execution to support long-running scraping and research jobs reliably.

Interface model
Preserve the CLI as the primary interface, with local vs remote execution as an implementation detail rather than a product shift.

Reliability and cost control
Centralized execution would enable shared caching, retries, scheduling, and predictable cost governance that are impractical across individual laptops.

Governance
Centralized prompt versions, configuration defaults, and guardrails to ensure consistent outputs and maintain trust at scale.

This evolution would position Primr as an internal research and strategy platform, not a public SaaS product. Any move in this direction would be driven by demonstrated usage and clear internal demand, not speculative scaling.

Explicitly Deferred (By Design)

These are not “missing features.” They are conscious non-goals for now.

Centralized Execution Infrastructure

Docker, Cloud Run, Container Apps

Async job queues

Multi-tenant execution

Deferred until:

Iterative workflow is proven indispensable

Reliability or throughput becomes a real constraint

Web Interface

Browser-based submission

Job dashboards

Report downloads

Deferred because:

It adds UX, auth, and infra complexity

It risks turning Primr into “just another research app”

Collaboration and Sharing

Accounts, permissions, comments

Sharing reports externally

Deferred because:

Primr’s value is thinking quality, not collaboration mechanics

Sharing comes after POV clarity, not before

Long-Term Possibilities (Non-Commitments)

Only to be explored if usage patterns justify them:

Read-only web viewer for generated artifacts

Webhooks or notifications on job completion

CRM or document system integration

Programmatic API for embedding Primr into larger workflows

These are downstream enablers, not core value drivers.

Usage Reference
# Basic usage
primr "Tesla" https://tesla.com

# Research modes
primr "Tesla" https://tesla.com --mode scrape
primr "Tesla" https://tesla.com --mode deep
primr "Tesla" https://tesla.com --mode full

# AI Strategy
primr "Tesla" https://tesla.com --cloud-vendor azure
primr "Tesla" https://tesla.com --no-ai-strategy

# Operations
primr doctor
primr "Tesla" https://tesla.com --dry-run
primr --check-jobs

Version History
Version	Date	Highlights
0.1.0	Nov 2025	Core research pipeline
0.2.0	Nov 2025	Deep Research integration
0.3.0	Dec 2025	Full mode (two-step)
0.4.0	Dec 2025	AI Strategy generation
0.5.0	Dec 2025	Cost tracking, job recovery
1.0.0	Dec 2025	Rebrand to Primr, pip installable
1.1.0	Dec 2025	Code quality hardening
1.2.0	Early 2026	Stability and reliability
1.3.0	TBD	Research state and hypothesis tracking
1.4.0	TBD	Iterative refinement loop
1.5.0	TBD	POV evolution and narrative continuity
Final Framing

Primr is not trying to scale users yet.
It is trying to scale clarity, judgment, and preparedness.