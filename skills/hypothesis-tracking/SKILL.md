---
name: hypothesis-tracking
version: "1.1.0"
description: "Retrieve and update company hypotheses in Primr. Use when the user asks what is already known, wants to validate a claim, or wants to persist a research finding."
mcp_server: "primr"
tools:
  - get_hypotheses
  - save_hypothesis
resources:
  - primr://context
---

# Hypothesis Tracking

## Purpose

Use this skill to manage durable research memory for a company. Hypotheses are a working memory layer, not final truth.

## Workflow

1. Retrieve hypotheses before starting duplicate research.
2. Present confidence clearly: untested, validated, invalidated, or confirmed.
3. Update confidence only when new evidence exists.
4. Keep evidence strings short, factual, and source-oriented.

## Operating Rules

- Distinguish known facts from open hypotheses.
- Preserve the evidence trail when confidence changes.
- Prefer updating an existing hypothesis over creating duplicates.
- Expired or weak hypotheses should be re-validated before being presented as current.

## Example

```text
get_hypotheses(company="ExampleCo", topic="technology")
save_hypothesis(company="ExampleCo", hypothesis_id="h_001", confidence="validated", evidence="CTO interview confirms AWS usage")
```
