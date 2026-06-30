# Skill Pack - Generate Agent Skills for Claude + Microsoft 365 Copilot Cowork

`primr skills` produces a QA-refined draft Agent Skills pack for a target company. The same byte-identical `SKILL.md` files ship to both ecosystems: an unpacked `roles/<slug>/SKILL.md` tree (drop-in for Claude Code, Cursor, VS Code Copilot, Gemini CLI, JetBrains Junie) and a Microsoft 365 Copilot Cowork sideload `.zip` (Unified App Manifest v1.28, deterministic UUID v5). Cowork plugin packages cap `agentSkills` at 20 entries; when a generated pack is larger, the unpacked tree remains complete and the Cowork zip emits the first valid 20-skill manifest slice.

This guide covers the planning architecture, input layer, operator curation surface, output artifacts, authoring + validation, CLI + MCP reference, costs, and troubleshooting.

## Quick start

```bash
primr skills "ExampleCo" https://example.co
# default: 5 roles x 3 skills, ~$0.30, 60-120s
# emits:
#   output/ExampleCo_Skills_Pack_<YYYYMMDD>/roles/<slug>/SKILL.md      (Claude tree)
#   output/ExampleCo_Skills_Pack_<YYYYMMDD>/ExampleCo_Cowork_Pack.zip   (Cowork sideload)
#   output/ExampleCo_Skills_Pack_<YYYYMMDD>/ExampleCo_Skills_Pack_Report.md
#   working/ExampleCo/.../role_plan.md  +  role_plan.json
```

`primr skills` requires `company_url` (standalone evidence collection), `--from-report <dir>` (reuse evidence from an existing primr run), `--from-jd <path>` (use a local job description / role brief as operator-supplied hiring evidence), or at least one `--career-url <url>` (use exact career / ATS boards as hiring evidence).

## When to use it

- You ran `primr "Company" url` and have a strategic report - generate role-grounded skills from it for an account team.
- You need a Microsoft 365 Copilot Cowork plugin for a specific company without writing manifest JSON by hand.
- You're seeding a Claude Code or Cursor workspace with company-specific skill files.
- You want to give an agent (or a colleague) a curated skill set that reflects the company's actual practices and stack rather than generic role templates.

## Architecture overview

```
EVIDENCE         PLANNING                CURATION         AUTHORING         VALIDATION       PACKAGING
recon  ────┐
hiring ────┼───► industry classify ───┐
research ──┘                           ├─► plan_roles  ──► apply_curation ──► author_role_skills ──► validate_pack ──► package
                                       │   (Calls A+B)     (add/skip)         (provenance-branched)   (ASKILL-*)        (Claude + Cowork)
                                       └─► role_plan.md + role_plan.json
```

Job postings are the **primary input**. Operator-supplied JD / role brief files and explicit career URLs are treated as hiring evidence, not instructions or public-fact blocks. DNS recon and strategic research are supporting context. When posting or role-brief evidence and research evidence are empty the pipeline fails closed unless `--allow-recon-only` is set; recon alone is structurally incomplete for services / reseller / consultancy companies. For mid-market-or-larger organizations, the planner also emits a non-blocking `posting-incomplete` warning when observed postings cluster in one narrow band, such as only store/front-line roles, so operators know the roster is probably a partial career-site slice rather than full enterprise coverage.

### Phase 1 - Planning (`src/primr/skill_pack/planner.py`)

`plan_roles` runs three LLM calls in sequence and produces a `RolePlan`:

1. **Industry classification** (`industry.py`) - one cheap call. Returns `IndustryClassification` with `business_model`, `industry_vertical`, `company_stage`, `employee_estimate`, `confidence`, `cited_evidence`, `source`. Resolution order: parse structured fields from a primr strategic report if `--from-report` is set; otherwise call the LLM.
2. **Call A - observed roles** (`plan_observed_roles.yaml`) - extracts roles from hiring evidence only, including operator-provided JD / role-brief evidence when `--from-jd` is supplied. Every role MUST cite at least one verbatim phrase from the hiring evidence or it's dropped at parse time. Provenance: `posting`. Confidence: `Confirmed`.
3. **Call B - plausible roles** (`plan_plausible_roles.yaml`) - infers roles from research + recon + industry classification. Every role MUST cite either a specific research phrase OR a business-model + stage rationale. The call is instructed to cover BOTH (1) the company-specific named practices / services from the research (highest priority - these are listed first and are what make the pack about *this* company; a flagship branded offering named in the research always earns a role) AND (2) the universal go-to-market and back-office functions every org of this size runs (Sales, Marketing, Customer Success, HR/People, Operations, Finance, Legal/Compliance, IT) - so the roster doesn't collapse into only generic functions or only technical practices. Common org-shape functions are reasonable inferences only when `company_stage` is Mid-market or larger. Generic VP / Chief-X titles are forbidden without specific evidence. Provenance: `research` or `industry`. Confidence: `Inferred` or `Speculated`.

Merge (`_merge_and_cap`) runs archetype-based dedupe (observed wins; if both calls return roles matching the same archetype, the observed entry survives and the plausible entry is dropped). The split is signal-driven - no hard ratio between observed and plausible - but a **plausible reserve** (`PLAUSIBLE_RESERVE_FRACTION`, default 0.4) keeps a fraction of the roster available for plausible org-shape roles when eligible plausible roles are waiting, so a posting set dominated by one technical function can't crowd out the universal business functions. Observed roles still take the leading slots and win on ties; observed roles the reserve displaces flow to `gap_flagged` (a contiguous suffix of observed) rather than being silently dropped. Cap is `roles_count`; overflow also flows to `gap_flagged` so the plan artifact records what got dropped. After merge, a pure posting-coverage assessment records whether observed postings look broad enough for the organization's scale; it surfaces warnings in `role_plan.md` and the pack report but never blocks authoring.

### Phase 2 - Curation (`apply_curation`)

When `--roles-add` or `--roles-skip` are set, `apply_curation` runs after the merge. Skip pass runs first (so swap-style curation like `--roles-skip A --roles-add B` works), then add pass with name + archetype dedup, then a cap-aware trim. See [Operator curation](#operator-curation) below.

### Phase 3 - Authoring (`authoring.py`)

`author_role_skills` runs in parallel (ThreadPoolExecutor, max 4 concurrent) per role. The prompt (`author_skill.yaml`) branches on `RoleEvidence.provenance`:

- `posting` - emphasize "anchor every skill in the specific responsibilities and tools the postings name; cite postings."
- `research` - emphasize "this role isn't in posting data but is plausible because of these research citations; reference the named practice or program."
- `industry` - emphasize "this role reflects business-model typicality, tuned to the company's named stack; avoid claims about specific company programs not in the evidence."
- `override` - pass through; operator supplied the label, ground in the company's general recon + research context.

Every skill body must use at least 2 company-specific signals (DNS-confirmed tool, hiring-mentioned technology, named practice, etc.) as workflow details, input requirements, output fields, or validation checks per the `author_skill.yaml` system prompt. Skill bodies are procedural draft skills, not company reports or evidence dumps.

After authoring, the pipeline attaches a deterministic `references/role-family.md` file to every skill in the same role family. The file is built from sanitized role evidence, DNS signals, citations, and matched archetype capabilities. It is generated once per role family and reused across that role's skills so cross-skill terminology and evidence do not drift.

### Phase 4 - Validation (`validator.py`)

Deterministic checks against each `SKILL.md`. Codes prefixed `ASKILL-` (hard) and others (soft). Hard findings trigger per-skill refinement (capped); roles that still carry hard findings after refinement are dropped before packaging.

Key validators:
- `ASKILL-P006` - kebab-case `name` matches folder name
- `DESC-VOICE` - description is third-person
- `DESC-PUSHY` - description lists multiple trigger phrases
- `DESC-TRIG` - description includes explicit "Use when..." guidance
- `NAME-GERUND` - skill name uses gerund form (verb + -ing)
- `NAME-PRODUCT` - skill name reads as a bare product/feature (`azure-front-door`, `aks`) rather than a task; refinement re-scopes the title to the capability the product is used for (the product stays in the body). SOFT - fires only when the name carries a known brand token and no verb/task token
- `BODY-LEN` - body word count within target band (default 300-1500; under 300 is HARD)
- `BODY-QUALITY` - body includes intake, `Required inputs:`, `Produces:`, `Scope guardrail:`, `Human checkpoint:`, `Example input:`, and `Example output:` markers so thin role templates do not ship
- `SEC-INJECT` - body does not contain agent-instruction patterns (prompt-injection guard)
- `BUNDLE-PATH` - bundled progressive-disclosure files use safe paths (`references/*.md`, `scripts/*.py`, `evals/*.json`, single subdir, no traversal). SOFT; unsafe files are dropped at package time

### Phase 5 - Pack-level coherence (`refiner.py`)

One LLM pass over the assembled pack checks for cross-role inconsistencies:
- `PACK-TRIGGER` - two skills' descriptions would fire on overlapping intents
- `PACK-OVERLAP-LLM` - two skills semantically cover the same ground
- `PACK-STRAT` - roles assume contradicting tech stacks (e.g., one says Java/Spring, another says Python/AWS)

Findings are appended to the pack-level `ValidationReport` and rendered in the pack report. When `auto_resolve_overlaps` is on (default), `PACK-OVERLAP-LLM` / `PACK-TRIGGER` pairs are auto-resolved by re-scoping one skill of each pair (conservative: only the second skill is touched, reverted if it gains a HARD finding) rather than only reported; resolved entries are dropped from the report.

### Phase 5c - Trigger-description optimization (`trigger_eval.py`, opt-in)

Enabled with `--optimize-triggers`. For each skill: generate should/should-not-trigger queries, score the current description against a blind discovery simulator, and - when below `trigger_accuracy_threshold` - propose an improved description, keeping it only if it beats the original on a held-out split. The measured replacement for the `DESC-PUSHY` heuristic. Results render in the pack report.

### Phase 5d - Behavioral evaluation (`behavioral_eval.py`, opt-in)

Enabled with `--with-evals`. For each skill: generate task cases + objective assertions, run each task WITH the skill body as guidance vs WITHOUT it (baseline), grade both blind, and report the with-skill-vs-baseline pass-rate delta - proving the skill changes output. Also attaches `evals/evals.json` (Anthropic's published structure) so users can re-grade. Expensive (~3 LLM calls per case per skill); off by default.

### Anthropic Best Practices (enforced in generator)

The pipeline now bakes in the highest-leverage patterns:
- Gotchas section (highest-signal; seeded from evidence, living).
- Scripts/ for deterministic work (validation, extraction, formatting).
- At least one narrow verifier/check skill per role.
- Trigger-first descriptions ("Use when..." + real user phrasing).
- Progressive disclosure (lean SKILL.md + references/ + scripts/ + composition.md + gotchas.md).
- Narrow scope (one capability, one category).
- Small composable skills (name references, no giant orchestrators).

See the authoring prompt and pack report "Anthropic Best Practices Adherence" section for current signals.

### Phase 6 - Packaging (`packager.py`)

Emits both formats from one byte-identical `SKILL.md` set:
- Unpacked tree at `<output_dir>/<Company>_Skills_Pack_<date>/roles/<slug>/SKILL.md`
- Cowork sideload `.zip` containing `manifest.json` (UUID v5 deterministic on company name), `color.png` (192x192), `outline.png` (32x32), and up to 20 `skills/<slug>/SKILL.md` entries. Re-running against the same company produces the same UUID, so sideload **replaces** the previous install rather than creating a parallel one.

## Input layer

### Recon (`src/primr/core/recon_context.py` via the `recon-tool` package)

DNS intelligence pre-flight: detects cloud platforms (Azure / AWS / GCP), SaaS services (Salesforce, M365, Okta, Snowflake, ...), email security configuration (DMARC / DKIM / SPF / MTA-STS / BIMI), identity providers. Costs $0, takes 2-3s. The output (`_recon_context.txt`) seeds the plausible-roles call with verified tool presence.

### Hiring signals (`src/primr/data/hiring_signals.py`)

Eight ATS providers tried in parallel against slug candidates:

1. **Greenhouse** - `boards-api.greenhouse.io/v1/boards/{slug}/jobs`
2. **Lever** - `api.lever.co/v0/postings/{slug}`
3. **Ashby** - `api.ashbyhq.com/posting-api/job-board/{slug}`
4. **SmartRecruiters** - `api.smartrecruiters.com/v1/companies/{slug}/postings`
5. **Workday** - bounded blind probing across `wd1` / `wd3` / `wd5` / `wd103` × `External` / `Careers` / `External_Careers` / `External_Career_Site` / `Global_External`, plus **corpus-driven URL discovery** that scans the scraped corpus for canonical `myworkdayjobs.com` URLs and hits the exact endpoint
6. **Workable** - `apply.workable.com/api/v1/widget/accounts/{slug}`
7. **Recruitee** - `{slug}.recruitee.com/api/offers/`
8. **Jobvite** - `jobs.jobvite.com/{slug}/jobs?format=rss`

If every ATS misses, the **HTML careers-page fallback** crawls the company's `/careers` or `/jobs` page with a regex-based posting-link extractor. If that also misses, the **DuckDuckGo web-search fallback** sweeps across major job-board hosts (LinkedIn, Indeed, Glassdoor, Workday boards, the ATS hosts, ZipRecruiter, BuiltIn, Monster, Dice, iCIMS pattern) and returns metadata-only postings. Bodies are rarely recoverable from those hosts, so the downstream no-bodies branch populates `signals.roles` directly from posting titles.

Output persists to `<working>/_hiring/` (`hiring_signals.md` + `hiring_signals.json` + `postings_index.json` + `raw/jd_NNN_*.txt`). Skip with `PRIMR_SKIP_HIRING_SIGNALS=1`.

iCIMS and BambooHR are not covered as dedicated providers - they have no clean public JSON APIs, and the HTML fallback handles them.

### Explicit career / ATS URLs (`--career-url`)

Use `--career-url URL` when the company career site is segmented across multiple boards, subsidiaries, regions, or job families. The flag can be repeated:

```bash
primr skills "Co" \
  --career-url https://jobs.co.example/corporate \
  --career-url https://boards.greenhouse.io/co
```

Each URL is structurally validated, fetched through the existing hiring SSRF guard, and treated only as a source selector. Direct ATS board URLs are parsed by their provider adapter; vanity career pages that redirect to a known ATS are resolved to that provider; plain HTML pages use the posting-link extractor. Valid postings from repeated URLs are merged and deduped before planning. When no `company_url` is supplied, Primr skips DNS recon rather than treating the first career URL as a corporate domain.

### Research (when `--from-report` is set)

`load_full_evidence` reads `report.md`, `insights.txt`, `scraped_website_summary.txt`, or `analysis_workbook.md` from the working directory in that priority order. Trimmed to 18,000 chars before being passed to the plausible-roles call. The research stream is what enables strong inference for revenue-layer roles (consultants, account roles, practice leads) that DNS fingerprints can't reveal.

### Operator role brief / JD (`--from-jd`)

`--from-jd PATH` reads a local UTF-8 job description or role brief, sanitizes it for prompt-injection patterns, and writes it to `<working>/_hiring/operator_role_brief.md`. The evidence loader prepends that file to the hiring stream, so the JD remains visible even when scraped hiring evidence is broad, noisy, or dominated by unrelated front-line postings.

Use this when the best grounding for a draft skill is a specific role description:

```bash
primr skills "Co" --from-jd ./licensing-operations-jd.md \
  --roles-override "Licensing Operations Analyst"
```

The JD can also augment a normal company URL or `--from-report` run. It is treated as evidence, never as instructions. The generated `SKILL.md` should use it to choose the workflow, required inputs, output template, guardrails, and worked example; it should not copy the JD into the body or turn it into a company report.

## Operator curation

When the auto-discovery doesn't match what you want, four flags compose to give you full control:

| Flag | Effect | When to use |
|---|---|---|
| `--plan-only` | Plan, persist, exit before authoring | Inspect the plan before paying for skills |
| `--from-plan PATH` | Skip planning; load saved plan and author against it | Author a previously-reviewed plan |
| `--from-jd PATH` | Add a local JD / role brief to hiring evidence | Ground a specialized role that discovery missed |
| `--career-url URL` | Add an exact career / ATS board; repeatable | Merge segmented career-site slices before planning |
| `--roles-add "A, B"` | Append operator-supplied labels to the planned roster | Plan looked good but missed X |
| `--roles-skip "X, Y"` | Drop named roles from the planned roster | Plan looked good except for one role |
| `--roles-override "..."` | Bypass planning entirely; author exactly these roles | You know what you want, skip discovery |

All four compose. Common patterns:

```bash
# Plan + augment in one command
primr skills "Co" url --from-report dir --roles-add "Account Executive, Procurement Manager"

# Plan + prune
primr skills "Co" url --from-report dir --roles-skip "Marketing Manager"

# Plan + swap (drop one, add another)
primr skills "Co" url --from-report dir \
  --roles-skip "Marketing Manager" \
  --roles-add "Demand Generation Manager"

# Inspect → edit → author
primr skills "Co" url --from-report dir --plan-only
# inspect working/.../role_plan.md
primr skills "Co" url --from-report dir --from-plan working/.../role_plan.json \
  --roles-add "Cybersecurity Lead"

# Hand-curated set from scratch (bypasses planning)
primr skills "Co" url --from-report dir \
  --roles-override "Role A, Role B, Role C"

# Single-role draft grounded in a local JD
primr skills "Co" --from-jd ./role.md \
  --roles-override "Licensing Operations Analyst"

# Merge segmented career boards before planning
primr skills "Co" \
  --career-url https://jobs.co.example/corporate \
  --career-url https://jobs.lever.co/co
```

### Composition matrix (locked behavior)

| Flags | Behavior |
|---|---|
| `--roles-override` alone | Bypasses planning; the four other curation/plan flags are ignored if `--roles-override` is set (CLI warns) |
| `--from-jd PATH` alone | Uses the local JD / role brief as the hiring evidence source; no URL scrape required |
| `--from-jd PATH --roles-override "..."` | Bypasses planning but still grounds authoring in the supplied JD |
| `--career-url URL` alone | Collects hiring evidence from the supplied board(s), skips DNS recon, and plans from postings |
| `company_url --career-url URL` | Runs DNS recon against `company_url` and uses the explicit board(s) for hiring discovery before fallback |
| `--from-plan PATH` | Load plan, no planning LLM calls |
| `--from-plan PATH --roles-add "..."` | Load plan, append added |
| `--from-plan PATH --roles-skip "..."` | Load plan, drop skipped |
| `--from-plan PATH --roles-add "..." --roles-skip "..."` | Load plan, drop skipped first, then append added |
| `--roles-add "..."` (no `--from-plan`) | Plan normally, append added before cap |
| `--roles-skip "..."` (no `--from-plan`) | Plan normally, drop skipped after merge |
| `--plan-only` alone | Plan, persist, exit |
| `--plan-only --roles-add ... --roles-skip ...` | Plan, apply curation, persist the curated plan, exit |

### Cap-aware merge with operator priority

`MAX_ROLES = 15` is the global cap. When curation pushes the roster over the cap, the trim order is deterministic:

1. **Plausible roles trim first** (research / industry provenance)
2. **Observed roles trim next** (posting provenance)
3. **Operator-added roles never trim**

Trimmed entries flow to `gap_flagged` so the plan artifact records what got dropped. Operator added roles always survive - they're explicit intent and outweigh inference.

### Name + archetype dedup

When `--roles-add "Marketing Manager"` lands in a roster that already contains a role named `marketing-manager` OR a role with archetype `marketing-manager`, the **existing role wins** - its citations are richer than the bare operator label. The add is silently skipped with a one-line log entry. If you want to force a specific variant, combine `--roles-skip "Marketing Manager"` with `--roles-add "Demand Generation Manager"` to swap in one command.

### Hard failure modes

- **Clash between add and skip**: `SkillPackConfig.validate()` raises `ValueError` if the same name (normalized: lowercase, kebab-case) appears in both lists.
- **Curation leaves empty roster**: `apply_curation` raises `RuntimeError` rather than ship an empty pack.
- **Add list exceeds `MAX_ROLES` alone**: rejected at config validation.
- **No posting evidence and no research evidence**: pipeline fails closed with `EmptyHiringEvidenceError` unless `--allow-recon-only` is set.

## Output artifacts

Each `primr skills` run produces:

### `<output_dir>/<Company>_Skills_Pack_<YYYYMMDD>/`

- `roles/<skill-slug>/SKILL.md` - one folder per skill, the canonical Agent Skills layout. Drop into `~/.claude/skills/`, `.cursor/skills/`, `.vscode/skills/`, or any other Agent Skills host.
- `roles/<skill-slug>/references/role-family.md` - deterministic shared role-family grounding copied into every skill for the same role family.
- `<Company>_Cowork_Pack.zip` - the Microsoft 365 Copilot Cowork sideload. Upload via **M365 Admin Center → Manage Apps → Upload custom app**. Contents:
  - `manifest.json` - Unified App Manifest v1.28 with deterministic UUID v5 (the same company name always yields the same UUID, so re-installs replace rather than duplicate)
  - `color.png` (192x192) and `outline.png` (32x32) - icons. Generated locally by default via Pillow gradient+shape → solid PNG. Remote image APIs are used only when explicitly enabled via `--remote-icons` / `remote_icons`.
  - `skills/<skill-slug>/SKILL.md` plus safe companion files such as `skills/<skill-slug>/references/role-family.md` - byte-identical to the matching unpacked-tree files
- `<Company>_Skills_Pack_Report.md` - human-readable pack summary:
  - Configuration (target roles, skills per role, formats, coherence pass)
  - Cowork Packaging (manifest skill count and companion-file limits)
  - Role Composition (observed / plausible / operator-added counts; industry classification; posting-coverage warning when present; plan reference; gap-flagged count; operator-skipped names)
  - Per-role section showing confidence, provenance, archetype, citations, summary, and the skills authored
  - Validation Scorecard (HARD / SOFT counts + per-finding table)
  - Refinement Iterations used
  - Dropped Roles (roles that failed validation even after refinement)
  - Artifacts list
  - Sideload Instructions

### `<working>/role_plan.md` and `role_plan.json`

Written during planning **before** authoring begins. Inspect the markdown to see what the planner discovered + inferred + curated; pass the JSON to `--from-plan` on a subsequent run to author against it.

The markdown layout:
- `## Industry Classification` - business model, vertical, stage, employee estimate, confidence, cited evidence, source (report / llm)
- `## Evidence Summary` - character counts and per-stage counts
- `## Posting Coverage` - non-blocking warning when enterprise-scale observed postings cluster in one narrow band
- `## Observed Roles` - posting-grounded roles with verbatim posting citations
- `## Plausible Roles` - research/industry-grounded roles with citations
- `## Operator-Added Roles` (when `--roles-add` was used) - operator-supplied labels with `provenance: override`
- `## Operator-Skipped Roles` (when `--roles-skip` was used) - normalized skip keys
- `## Gap-flagged Roles` - plausible roles that didn't make the cap
- `## Final Roster` - numbered list with provenance + confidence per role
- `## How to act on this plan` - operator next-step hints

The JSON contains the full `RolePlan` shape (`observed`, `plausible`, `gap_flagged`, `operator_added`, `operator_skipped`, `final_roster`, `industry`, `evidence_summary`, `plan_md_path`, `plan_json_path`).

## SKILL.md structure

Authored bodies follow Anthropic's Agent Skills authoring conventions enforced by the validator. By default the frontmatter is clean Agent Skills standard frontmatter: `name` + `description` only. If you need machine-readable handoff metadata, pass `--emit-agent-metadata` or set `SkillPackConfig(emit_agent_metadata=True)` to add a primr-namespaced `metadata` block with role, provenance, confidence, approximate context-token budget, and refresh hints.

The generated files are draft skills. They use company context to make the task procedure specific, but the `SKILL.md` body should not become a mini report, evidence appendix, role profile, or company background document. Detailed role grounding lives in `references/role-family.md` and is loaded only when the downstream agent needs it.

```markdown
---
name: "facilitating-m365-customer-immersion-experiences"
description: "Facilitates 90-minute M365 Customer Immersion Experiences (CIEs) workshops for ExampleCo commercial accounts. Use when the user asks to schedule a CIE, prepare Modern Workplace demo content, align Intune scenarios, or document post-workshop outcomes."
---

## What This Skill Does

Use this skill to run a specific M365 Customer Immersion Experience workflow for ExampleCo commercial accounts.

Required inputs:
- Account name, target audience, workshop objective, available demo tenant, and any known Intune or Teams constraints.

Produces:
- A CIE preparation checklist, demo scenario map, stakeholder questions, and post-workshop follow-up table.

## Workflow

Progress:
- [ ] Intake: confirm the missing source artifact, account context, and decision owner.
- [ ] Evidence: gather the named systems and constraints.
- [ ] Draft: produce the requested artifact.
- [ ] Validate: check the output against evidence and scope.

1. First ask for any missing input that blocks the work.
2. <step that names a specific tool or system at this company>
3. <step that transforms evidence into the output>

Scope guardrail: <what this skill must not do or decide>.
Human checkpoint: <when the agent must pause for a person before finalizing>.

## Output Format

<concrete template - table, list, or document structure>

Example input: <small realistic request using this company's context>.
Example output: <small completed output in the required format>.
```

Hard rules (validator-enforced):
- `name` is kebab-case, 1-64 chars, matches folder name (ASKILL-P006)
- `description` is 1-1024 chars, third person, includes explicit "Use when..." trigger phrases
- Body contains exactly the three H2 sections in order
- Body target 300-1500 words (sweet spot 500-800); under 300 words is a hard failure
- Body includes intake, required inputs, produces, scope guardrail, human checkpoint, and worked input/output example markers
- No agent-instruction patterns, no hardcoded local paths, no fenced shell blocks, no credential references

## Cowork packaging limits

Primr validates Cowork sideload output against Microsoft 365 Copilot Cowork's current plugin limits before writing the zip:

- Manifest `agentSkills`: max 20 entries. Larger packs still write every skill to the unpacked tree, while the Cowork zip contains the first valid 20-skill slice.
- `SKILL.md`: max 1 MB per skill.
- Companion files: max 20 files per skill, max 5 MB per companion file, max 10 MB total companion bytes per skill.
- Companion paths must be relative, safe, and stay under allowed progressive-disclosure folders. Unsafe or over-limit companion files are dropped before packaging.

## CLI reference

```
primr skills <company_name> [company_url] [options]
```

Positional arguments:
- `company_name` - display name (quote multi-word names)
- `company_url` - required unless `--from-report`, `--from-jd`, or `--career-url` is provided

Planning + roster:
- `--roles N` - number of roles to generate (1-15, default 5)
- `--skills-per-role N` - skills per role (1-5, default 3)
- `--from-report PATH` - reuse evidence from an existing primr working dir
- `--from-jd PATH` - add a local job description / role brief as sanitized hiring evidence
- `--career-url URL` - exact career / ATS board to use as hiring evidence; repeat for segmented sites
- `--plan-only` - plan, persist, exit before authoring
- `--from-plan PATH` - author from a saved `role_plan.json`; skip planning
- `--roles-add "A, B"` - augment the discovered roster
- `--roles-skip "X, Y"` - prune from the discovered roster
- `--roles-override "A, B, C"` - bypass planning entirely (mutually exclusive with add/skip)
- `--allow-recon-only` - proceed when both posting and research evidence are empty

Output + validation:
- `--formats {claude,cowork,both}` - which artifact formats to emit (default `both`)
- `--output-dir PATH` - where the dated pack folder is written (default `output/`)
- `--max-refine-iterations N` - cap on per-skill refinement (default 2)
- `--no-coherence-pass` - skip the pack-level coherence LLM pass (saves ~$0.02)
- `--optimize-triggers` - measure + optimize each skill's trigger description against a discovery simulator (Phase 5c; adds LLM calls, off by default)
- `--with-evals` - behavioral eval: run each skill's task cases with vs without the skill, grade, report the delta, write `evals/evals.json` (Phase 5d; expensive, off by default)
- `--emit-agent-metadata` - add optional primr-namespaced metadata to each `SKILL.md` frontmatter; off by default
- `--remote-icons` - opt in to remote image-generation APIs for Cowork icons; off by default so configured provider keys do not create image API spend
- `--dry-run` - estimate cost + time, exit before running

## MCP reference

`primr-mcp` (and the bundled `primr mcp` subcommand) exposes two skill pack tools:

### `estimate_skill_pack`

Cost + time estimate. Call before `generate_skill_pack`. Required:
- `company_name`

Optional:
- `roles_count` (1-15, default 5)
- `skills_per_role` (1-5, default 3)
- `report_path` (skips standalone evidence collection)
- `from_jd_path` (adds local role-brief evidence; skips evidence collection when used without `company_url`)
- `career_urls` (array of exact career / ATS URLs; merged before planning)
- `remote_icons` (bool, default false; includes the explicit remote icon image-generation allowance)

Returns `{cost_usd, min_minutes, max_minutes}` plus the approval token fields when MCP cost-cap enforcement is enabled.

### `generate_skill_pack`

Synchronous (~30-120s). Required:
- `company_name`

Optional:
- `company_url` (required unless `report_path`, `from_jd_path`, or `career_urls` is set)
- `report_path` - reuse an existing primr working dir
- `from_jd_path` - local job description / role brief to sanitize and add to hiring evidence
- `career_urls: array[string]` - exact career / ATS URLs to merge as hiring evidence
- `roles_count`, `skills_per_role`, `formats`, `max_refine_iterations`, `destination`, `max_estimated_cost_usd`
- `allow_recon_only: bool` - fail-closed override
- `emit_agent_metadata: bool` - optional metadata block in `SKILL.md`; default false
- `remote_icons: bool` - opt in to remote image-generation APIs for Cowork icons; default false
- `plan_only: bool` - write plan, return without authoring
- `from_plan_path: string` - author against a saved plan
- `roles_override: array[string]` - bypass planning entirely
- `roles_add: array[string]` - augment discovered roster
- `roles_skip: array[string]` - prune from discovered roster

Mirrors the CLI flags. Returns the pack metadata + artifact paths.

## Cost + time

Cost is dominated by authoring (~$0.03 per role per skill). Planning adds ~$0.04 ($0.005 industry classification + $0.02 observed + $0.02 plausible). Coherence pass ~$0.02. Refinement ~$0.015 per failing skill (typically 30% of skills need at least one refinement pass).

Indicative numbers for a default run (5 roles × 3 skills = 15 skills):
- Pack with `--from-report`: ~$0.25-$0.35, 60-90s
- JD-only pack with `--from-jd` and `--roles-override`: skips standalone evidence collection; cost scales with planned roles/skills
- Career-URL-only pack with `--career-url`: includes standalone hiring evidence collection but skips DNS recon when no `company_url` is supplied
- Pack with standalone evidence collection (no `--from-report`): ~$0.30-$0.40, 90-150s
- Larger pack (10 roles × 3 skills = 30 skills): ~$0.55-$0.75, 120-240s
- `--plan-only`: ~$0.05, 10-30s

Use `--dry-run` for a per-run estimate that reflects your exact flag combination.

## Troubleshooting

**`EmptyHiringEvidenceError: no job-posting evidence and no research evidence were gathered`**

Both the posting layer and the research layer came up empty. Most often: the company uses an ATS provider primr doesn't support yet AND `--from-report` wasn't used. Options:
1. Run a full primr research run first, then pass `--from-report working/<company>/<timestamp>` so the strategic research grounds the plausible-roles call.
2. Pass `--allow-recon-only` to proceed with DNS-only role discovery (structurally incomplete for services / reseller / consultancy companies - the pack will skew toward IT-ops admin roles only).
3. Use `--from-jd path/to/role.md --roles-override "Role A"` when you have a specific job description / role brief.
4. Add repeated `--career-url` values when the company splits hiring across multiple boards and automatic discovery found only one slice.
5. Use `--roles-override "Role A, Role B, ..."` to supply roles manually without extra role evidence.

**`Curation left an empty roster`**

`--roles-skip` removed every role from the planned roster. Re-run with fewer skip names, or supply `--roles-add` to fill the roster.

**`roles_add and roles_skip share entries`**

A role name appears in both `--roles-add` and `--roles-skip` (normalized: case-insensitive, kebab-case). Pick one.

**Role dropped with `DESC-TRIG` / `SEC-INJECT` / other HARD finding**

The validator caught a quality issue that refinement couldn't recover within the cap. Pack ships with the surviving roles; the drop is logged in the pack report's "Dropped Roles" section. To author more aggressively, raise `--max-refine-iterations` (default 2). To investigate, re-run with `PRIMR_LOG_LEVEL=DEBUG` and inspect the per-skill validation findings in the pack report.

**Unexpected archetype in pack report**

`match_archetype` uses exact slugs, normalized aliases, strong display-name similarity, and multi-keyword evidence. Weak display-name similarity is no longer returned as usable grounding, so unknown roles author from company evidence only. The bundled catalog covers common business functions such as sales, marketing, people operations, finance, legal/compliance, and operations in addition to the technical archetypes. If a role still looks too broad, add a more specific role with `--roles-add`, force the roster with `--roles-override`, or add a focused role brief with `--from-jd`.

**Plan looks right but authoring produces generic skills**

Most often a result of thin research evidence. Re-run with `--from-report` pointing at a richer primr run (e.g., the standard `primr "Company" url` output rather than a `--mode scrape` run), or augment by running the full pipeline first.

**Role plan says `posting-incomplete`**

The planner found real postings, but they cluster in one narrow band for a mid-market-or-larger organization. Treat the observed roster as a partial career-site slice. Add exact segmented boards with repeated `--career-url`, add a corporate role brief with `--from-jd`, curate known specialized roles with `--roles-add` / `--roles-override`, or rerun from a richer report.

**Pack manifest UUID changed unexpectedly**

The UUID is deterministic on `(company name + primr namespace)`. Changing the case or punctuation of the company name changes the UUID. Re-installs land as new plugins instead of replacements. Keep `company_name` byte-identical across runs when iterating.

## Related

- [Architecture](ARCHITECTURE.md) - full system design including the planning architecture
- [Changelog](CHANGELOG.md) - v1.27.0 (input layer + planning rebuild) and v1.27.1 (operator curation)
- [API](API.md) - MCP server reference
- [Config](CONFIG.md) - environment variables, including `PRIMR_SKIP_HIRING_SIGNALS`
- [Copilot Cowork Guide](COPILOT_COWORK_GUIDE.md) - publishing the primr research agent itself to the M365 Agent Store (different from skill pack sideload)
