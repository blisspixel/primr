# Downstream handoff

A primr report is a starting point, not a destination. After a run completes, surface the obvious next step rather than letting the artifact sit unused. This file is the mapping from "what primr produced" to "what to offer the user next."

## Tool-neutral document handoff

Use the bounded artifact inventory before invoking a requested downstream skill
or document workflow. MCP hosts should read
`primr://output/artifacts/by_job/{job_id}`. CLI hosts should run
`primr --list-recent --json`. Both surfaces return content-free metadata.

Select the Markdown artifact with `artifact_role: primary_report` as the main
input. Add only relevant `artifact_role: strategy_module` paths and explicit
user-provided notes. Prefer exact paths over asking the downstream consumer to
search an account folder. Preserve citations, confidence labels,
contradictions, and evidence gaps in the handoff.

The downstream consumer owns its audience, schema, output destination,
rendering formats, approval gates, and final QA. Do not assume a particular
skill, brand, vendor, or HTML, PDF, slide, or spreadsheet output. Do not run an
unrequested downstream workflow.

## Strategic Overview (the primary deliverable)

What just landed: a 21k-word markdown + DOCX at `output/<company>/<Company>_Strategic_Overview_<date>.md`, with 23 structured sections, SWOT, competitive landscape, discovery questions, citation appendix.

Proactive offers (pick the one that matches the user's role / next visible meeting):

- **Discovery prep**: "Want me to extract the discovery questions section into a one-pager you can take into the meeting?"
- **Executive briefing**: "Want me to compress the executive summary plus top-3 strategic insights into a 2-minute spoken brief?"
- **Slide deck**: "Want a slide outline (8-12 slides) pulled from the SWOT, competitive landscape, and discovery questions?"
- **Email summary**: "Want a 4-5 sentence email summary suitable for forwarding to a sales lead or account team?"
- **Hypothesis review**: "primr saved N new hypotheses. Want to review which ones to validate in your discovery call?"

When the user says "yes" to any of these, do the work in-conversation. Don't re-run primr; you already have the artifact.

## AI Strategy module (when `--strategy-type ai` was used)

What just landed: a separate markdown / DOCX at `output/<company>/<Company>_AI_Strategy_<PLATFORM>_<date>.md`, structured from business strategy and value pools through industry possibilities, prioritized initiatives, economics, operating model, architecture, governance, and board decisions.

Proactive offers:

- **Executive decision brief**: "Want me to condense the business thesis, top initiatives, economics, and board decisions into one page?"
- **Initiative ROI write-up**: "The top three initiatives in this strategy - want me to draft the ROI / business case for each?"
- **Discovery questions specifically about AI**: "Want me to pull out the AI-specific discovery questions for your next conversation?"
- **Cross-platform comparison**: if multiple `--platform` runs exist for this company, offer to diff them ("Want me to compare the Azure AI Strategy and the AWS AI Strategy side-by-side?").

## Other strategy modules (CX, security, data, etc.)

Mostly the same shape as AI Strategy: extract the prioritized initiatives or recommendations, offer ROI write-ups, offer one-pagers. Match the *audience* the strategy targets:

- `customer_experience` → CX leader / CMO / VP Customer Success.
- `modern_security_compliance` → CISO / VP Security / Compliance lead.
- `data_fabric_strategy` / `data_strategy` → CDO / VP Data / Head of Analytics.
- `cloud_migration` → VP Infrastructure / Head of Platform.

Offer to "translate" the deliverable into the language of the audience the user is meeting with next.

## Hypothesis memory updates

What just landed (silently, unless the user asked): new hypotheses added to `logs/research_memory/<company>/`. Confidence levels: `untested` (most new ones), `validated` (corroborated by multiple sources during the run), occasionally `confirmed` (near-certain from primary sources).

Proactive offers when the run finishes:

- "primr saved N new hypotheses on Acme. Want me to list the top 5 by confidence?"
- "Of the new hypotheses, M are `untested` - these are the ones to validate in your discovery call. Want them?"
- After a customer conversation: "Want to update the hypothesis memory with what you learned? I can promote `untested` ones to `validated` or `invalidated` based on what they said."

When a user updates a hypothesis from a conversation, use `save_hypothesis` (MCP) or write directly to the memory file (CLI). Always include the evidence string - a one-line citation of where the new confidence level came from.

## Pipeline intermediates (mostly ignore unless asked)

`scraped_content.txt`, `insights.json`, `dossier.json`, `run_manifest.json` - these exist for debugging and re-runs, not for direct user consumption. Don't proactively offer to read them. If the user asks "how did primr arrive at X claim," the answer is in `run_manifest.json` (audit trail) plus the citation appendix in the main report.

## What NOT to do after a run

- **Do not re-run primr to "verify" findings.** The cost gate forbids this without a fresh estimate and approval, and the report's confidence annotations already convey uncertainty.
- **Do not paste the full markdown into the conversation.** It's 21k words; the conversation will OOM or the user will scroll past everything important. Always summarize.
- **Do not strip confidence annotations** when summarizing. "(Hypothesis)" is load-bearing - readers learn to trust the parts marked `(Confirmed)` / `(Reported)` more than the parts marked `(Estimated)` / `(Hypothesis)`.
- **Do not promise updates.** primr is a snapshot tool. If the user asks "will this update when news happens," the answer is no - they'd need to re-run periodically (and that's a fresh estimate + approval each time).
