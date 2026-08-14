# Host-Assisted Strategic Overview Contract

Target the full 23-section structure when evidence and host capacity support
it. Keep each insight in one best section and cross-reference rather than
repeating it.

1. Executive Summary
2. Products and Services
3. Target Customers
4. Competitive Differentiation
5. Financial Profile
6. Company History and Evolution
7. Leadership and Organization
8. Industry Dynamics
9. Industry Outlook
10. Competitive Landscape
11. Business Model and Value Creation
12. SWOT Analysis
13. Strategic Tensions
14. Constraints and Degrees of Freedom
15. Narrative Gap Analysis
16. Areas of Potential Fragility
17. Patterns Worth Exploring
18. Discovery Questions
19. Strategic Leadership Perspective
20. Where They Are Likely to Say Yes
21. Porter's Five Forces Assessment
22. Value Chain Analysis
23. Strategic Positioning Hypothesis

Finish with a source appendix and coverage notes. The appendix is not counted
as one of the 23 analytical sections.

## Evidence rules

- Cite every material factual claim near the claim.
- Use official or first-party evidence for `Confirmed` claims.
- Use `Reported` for a credible third-party claim that is not independently
  verified.
- Show the basis for estimates and use ranges when inputs are uncertain.
- Give each hypothesis supporting evidence, a counter-hypothesis, and a
  falsification test.
- Treat repeated syndicated coverage as one underlying source.
- Name blocked, missing, partial, and stale coverage.

## Citation format

`primr --analyze-report` scores citations by inline numeric markers resolved
against a source appendix. Follow this exact format so a contract-compliant
report also passes the QA gate:

- Put an inline `[cite: N]` marker right after each material claim, where `N` is
  the source number.
- Finish with a `## Sources` appendix (`## References` or `## Citations` also
  work) listing each numbered source on its own line as `[cite: N] Title — URL`.
- A plain Markdown hyperlink alone is not counted by the gate. Pair it with a
  `[cite: N]` marker and a numbered `## Sources` entry.

Worked example:

```
Acme grew headcount 40% in 2025 [cite: 1] and now lists a dedicated AI
platform team [cite: 2].

## Sources
[cite: 1] Acme FY2025 report — https://acme.example/annual
[cite: 2] Acme careers, AI Platform — https://acme.example/careers
```

## Depth rules

Prioritize executive summary, products, customers, finances, leadership,
industry, competition, business model, hiring and technology signals, SWOT,
discovery questions, and the final positioning hypothesis. If host allowance
or evidence is thin, compress lower-confidence framework sections and explain
the gap. Never fill a section with generic category advice.

## Review rules

Run a separate review pass that asks:

- Does each conclusion follow from the cited evidence?
- Are contradictions visible?
- Are sources independent, current, and authoritative enough?
- Are confidence labels honest?
- Are strategic recommendations framed as conditional hypotheses?
- Does the report clearly distinguish internal IT from product technology?
- Does the coverage note explain what full provider-backed Primr would add?
