# Progressive early artifacts (time-to-first-useful)

Status: design only. Not scheduled as a release gate. Complements the 1.x
quality and 2.0 memory workstreams; does not replace either.

## Problem

Full provider-backed runs are often 30–120 minutes. Chat deep-research products
often surface a usable narrative in tens of minutes. Primr already has useful
early signals (`recon`, scrape progress, prep bundles), but the default
operator experience still feels like “wait for the whole brief.”

That gap is real. Closing it should improve usability without weakening the
full Strategic Overview / AI Strategy contract.

## Goal

Ship intermediate, honest artifacts during a run so operators and agents can
act earlier, while the full report remains the primary deliverable.

Success looks like:

- Something useful appears well before the final MD/DOCX.
- Early artifacts are clearly labeled incomplete (not final).
- No extra billable model work unless the operator opted in.
- Agents can discover early paths via existing body-free inventory resources.

## Non-goals

- Matching chat UX or continuous streaming of the full report.
- Replacing the full brief with a short summary as the default product.
- Always-on monitoring or background company watchers.
- New regex content-quality gates on partial drafts.

## Proposed layers (dependency order)

### Layer 0 — already available (document, do not re-build)

| Timing | Artifact | Cost |
|--------|----------|------|
| Seconds | `primr recon` | $0 model |
| Minutes | `primr prep` evidence bundle + host workflow | $0 Primr model |
| Mid-run | Working folder scrapes, stage progress, run events | included in run |

Action: make these more visible in RUN_MODES / README “first useful output”
without implying they are the full dossier.

### Layer 1 — free progressive skeleton (first implementation slice)

During a paid or free collection path, write a **working** markdown file once
enough structured evidence exists:

Suggested path (illustrative):

```text
output/<company>/<Company>_Working_Brief_<date>.md
```

Contents (deterministic assembly first; no new model call):

1. Company name, URL, run id, timestamp  
2. Status banner: `WORKING BRIEF — incomplete; not the Strategic Overview`  
3. Recon / DNS summary when present  
4. Scraped page inventory (counts, top URLs, access notes)  
5. Hiring signal counts when present  
6. Source index excerpt (domains, not full bodies)  
7. Explicit “still running” section list  

Exit criteria for Layer 1:

- File appears after scrape (+ recon) complete, before long reasoning finishes  
- Zero additional model tokens beyond the run’s existing stages  
- Final Strategic Overview remains unchanged  
- Inventory / MCP artifact listing can classify it as intermediate (not
  `primary_report`)

Validation: free offline fixtures + hermetic unit tests for assembly and
classification.

### Layer 2 — optional early executive sketch (opt-in)

Only if Layer 1 is stable and operators ask for prose earlier:

- Optional flag or mode, e.g. `--early-sketch` (name TBD)  
- One bounded writing call on collected evidence only  
- Same confidence discipline: hedge, no fake Confirmed density  
- Must not auto-promote sketch claims into the final report without the normal
  pipeline

Validation: small paid eval budget only after free assembly tests pass; compare
sketch vs final for contradiction rate, not eloquence.

### Layer 3 — progressive agent handoff

- Body-free resource or status field: `early_artifact_paths`, stage, completeness  
- Primr Zero path already checkpoints host writing inside prep; align naming so
  agents do not confuse working brief with `primary_report`

## Placement in the pipeline

Prefer hooks at existing seams:

1. After recon + scrape inventory is durable  
2. After `fast` collection stages that already write working-folder state  
3. Never block the main pipeline if early write fails (log + continue)

Do not introduce a second orchestrator or a DAG framework for this.

## Artifact contract

| Role | Final SO | Working brief |
|------|----------|---------------|
| Inventory class | `primary_report` | intermediate / working |
| QA gates | existing shipping gates | structural only (path, header, non-empty) |
| DOCX | default for final | optional later via `primr render` |
| Overwrite | dated final | may refresh in place during the run |

## Risks

| Risk | Mitigation |
|------|------------|
| Operators ship the working brief as final | Loud incomplete banner; inventory role |
| Extra cost | Layer 1 is free; Layer 2 opt-in |
| Scope creep into chat streaming | Keep discrete files + phase markers |
| Stale mid-run files after failure | Status field + run events |

## Relation to other workstreams

- **Epistemic quality (#1):** early artifacts stay thinner; do not lower Confirmed
  standards on the final report to feel faster.  
- **Backend freedom (#2):** early assembly should work for cloud, host, and local
  collection the same way.  
- **Memory (2.0):** later, a working brief can seed delta mode; do not wait for
  memory to land Layer 1.  
- **Competitive positioning:** this is a usability answer to chat speed, not a
  claim that Primr is faster overall.

## Suggested first PR shape (when implementing)

1. Pure assembler + classification + tests (no CLI flag change if a default
   mid-run write is safe).  
2. Wire write after scrape/recon in one path (fast first).  
3. Docs: RUN_MODES “what you get while waiting.”  
4. Optional: MCP inventory field only after CLI path is proven.

## Validation cost

- Free: unit tests, fixture working folders, dry-run path checks.  
- Paid (later): one cheap live run to confirm timing of the working brief vs
  final SO on ExampleCo-style placeholder targets only.

## Explicitly not in v1 of this design

- Streaming tokens to the terminal as the product surface  
- Auto-email / Slack of partial drafts  
- Treating prep-only output as a full paid Strategic Overview  
