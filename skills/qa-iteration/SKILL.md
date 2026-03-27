---

name: qa-iteration

version: "1.1.0"

description: "Assess and improve Primr output quality. Use when the user asks to review, grade, refine, or troubleshoot a report or strategy document."

mcp_server: "primr"

tools:

  - run_qa

  - generate_strategy

resources:

  - primr://output/latest

  - primr://strategies/available

---



# QA Iteration



## Purpose



Use this skill after research or strategy generation to evaluate output quality and identify the next corrective action.



## Workflow



1. Read `primr://output/latest` when the user does not specify a path.

2. Run `run_qa` on the concrete report path.

3. Summarize the weakest sections first.

4. If the user wants a different deliverable rather than a rewrite, read `primr://strategies/available`, call `estimate_strategy`, and get approval before `generate_strategy`.



## Operating Rules



- Treat QA as a decision aid, not a final verdict.

- Prioritize factual gaps, missing citations, and thin strategic interpretation.

- Do not recommend regeneration until you can explain what is weak.

- Keep the follow-up action specific: rerun research, generate a strategy, or revise the report.



## Example



```text

run_qa(report_path="output/exampleco/report.md")

```

