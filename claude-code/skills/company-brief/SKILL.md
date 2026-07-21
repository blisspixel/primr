---
name: company-brief
description: Produce a primr-style strategic company brief using ONLY the host agent's own tools (web search, page fetch, shell DNS lookups) at subscription cost. No primr install, no API keys, no GPU. Use when the user wants a structured pre-discovery brief on a company but cannot or does not want to run the full primr pipeline. For the full pipeline (deeper scraping, 40+ sources, cross-validation, QA gates), use the primr skill instead.
argument-hint: "Company Name" https://company.url
---

# company-brief: the primr method, no install required

This skill encodes primr's research methodology so a capable agent host (Claude Code, Cursor, Copilot, or similar) can produce a useful subset of a primr brief using only its built-in tools. It costs the user nothing beyond their existing subscription. Expect a 2,000-5,000 word brief from 15-25 sources, taking roughly 10-25 minutes of agent time.

Be honest with the user about the trade: this is the lite method. The full primr pipeline does 9-tier adaptive scraping across ~50 pages, ATS-targeted hiring-signal extraction, research deepening, cross-validation, trust gates, and QA refinement. If the user wants that depth, point them to `pip install primr` (needs API keys) and the `primr` skill.

## Ground rules (read first, apply throughout)

1. **Never fabricate.** Every factual claim in the brief comes from something you fetched or a search result you can cite. If you cannot source it, either label it as inference or leave it out.
2. **Confidence labels on non-obvious claims**, using primr's vocabulary exactly:
   - `(Confirmed)` - stated by a primary source or by two independent third-party sources
   - `(Reported)` - stated by one third-party source (news, analyst, review site)
   - `(Estimated)` - your inference from evidence, e.g. headcount from posting volume; say what it is triangulated from
   - `(Hypothesis)` - a plausible reading of weak signals, framed as something to validate, never as fact
3. **Number your citations in the house format.** Mark citations inline as `[cite: 1]`, `[cite: 2]`; list the full URLs under a `## Sources` heading at the end as `[cite: N] Title — URL`. A bare inline `[1]` is not the scored format.
4. **Note absences.** What a company does not publish (no pricing page, no leadership page, no engineering blog) is itself a signal; say so rather than padding.
5. **Thin signal = thin brief.** If the company has a four-page website and no postings, deliver a short honest brief plus a list of what could not be determined. Do not inflate.

## Phase 1: DNS recon (2 minutes, shell)

DNS records reveal infrastructure choices that marketing pages never mention. Run these (use `nslookup` everywhere; `dig` also works on macOS/Linux):

```
nslookup -type=MX <domain>
nslookup -type=TXT <domain>
nslookup -type=NS <domain>
nslookup <domain>
nslookup -type=CNAME autodiscover.<domain>
```

Interpret with `references/recon-cheatsheet.md`. Headlines to extract: email/productivity platform (Microsoft 365 vs Google Workspace), cloud hints (nameservers, A-record ownership), SaaS tools visible in TXT verification records (CRM, HR, security, e-signature), and email security posture (SPF/DMARC presence and strictness). These become evidence for the Tech Stack section.

If shell access is unavailable, skip this phase and note "DNS recon unavailable in this environment" in the brief; do not guess.

## Phase 2: Site corpus (8-15 pages, not 50)

Fetch the homepage first, then pick the highest-signal pages from its navigation:

- About / company / story (positioning, founding, scale claims)
- Products / services / solutions (what they actually sell)
- Pricing (model and tiers; absence of a pricing page is a signal: sales-led motion)
- Customers / case studies (named accounts, verticals, concentration)
- Careers landing page (team scale, locations, hiring tone)
- News / press / blog (most recent 3-5 items; momentum and announcements)
- Leadership / team (org shape, where the executive bench is invested)
- Investor relations, if public (latest results summary)

Budget: 8-15 fetches. Prefer breadth over re-fetching. If a page fails or appears to be a bot-challenge shell (tiny body, "verifying your browser" text), record it as inaccessible; never summarize a block page as if it were content.

## Phase 3: Hiring signals (the highest-value external source)

Job postings are the most honest public statement of what a company is building right now. Search for current openings:

- `"<company>" jobs site:boards.greenhouse.io OR site:jobs.lever.co OR site:jobs.ashbyhq.com`
- `"<company>" careers <likely ATS host>` and the company's own careers page from Phase 2
- General: `"<company>" hiring <current year>`

Fetch 3-8 of the most signal-rich postings (engineering, data, security, and senior/strategic roles outrank retail/front-line duplicates). Extract: named technologies (count repeated mentions), seniority mix, new-function signals (first data hire, first compliance hire), and initiative language ("you will help us launch...", "as we expand into..."). If discovered postings cluster in one narrow band (all front-line roles for a large org), say the hiring view is likely incomplete rather than treating it as the whole picture.

## Phase 4: External research (5-8 sources)

Search and fetch, preferring third-party over the company's own domain:

- News and funding: `"<company>" funding OR acquisition OR layoffs OR partnership`
- Filings if public: latest 10-K/annual report summary (search `"<company>" 10-K <year>`)
- Customer voice: G2/Capterra/Trustpilot summaries where relevant
- Competitive frame: `"<company>" vs` and `"<company>" alternatives`

Cross-check: when a third-party claim contradicts the company's own framing, keep both and note the tension; contradictions are findings, not noise.

## Phase 5: Write the brief

Use the template in `references/report-template.md` (about 12 sections). Rules that make it primr-like rather than a generic summary:

- Lead the executive summary with a position statement (what they are, for whom, against whom) plus 3-5 key insights, each labeled and cited.
- The Tech Stack section triangulates Phase 1 (DNS) + Phase 3 (postings) + site claims; distinguish observed infrastructure from marketed capability.
- SWOT entries must each carry a citation or a label; an unsourced SWOT bullet is filler.
- Hypotheses Worth Testing: 2-4 non-obvious, falsifiable readings of the evidence, each with the validation question that would confirm or kill it.
- Discovery Questions: 5-10 questions an account team should actually ask, grounded in gaps you found, not generic.
- Close with Sources (numbered URLs) and a short Coverage Notes paragraph: what you could not access, what was thin, and what the full primr pipeline would add.

## Upgrade path

DOCX deliverables are free: `primr render report.md` produces DOCX and TXT at $0 with no API keys and no model calls. If the user wants more depth, blocked sites recovered, or the multi-platform AI strategy modules, the full pipeline is `pip install primr` + `primr init` (one or two API keys; the default `full` run is about $0.89 with the AI Strategy module, or about $0.79 for the base report only via `--no-ai-strategy`) and this host's `primr` skill handles the lifecycle. Mention this once at the end of a brief, not as a sales pitch mid-task.
