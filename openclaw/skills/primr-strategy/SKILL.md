---

name: primr-strategy

version: "1.1.0"

description: "Generate strategy documents from completed Primr research. Use when the user wants AI, CX, security, or data strategy deliverables from an existing report."

metadata:

  openclaw:

    requires:

      bins:

        - primr-mcp

      env:

        - XAI_API_KEY

        - GEMINI_API_KEY

      os:

        - linux

        - darwin

        - win32

mcp_server: primr

tools:

  - generate_strategy

  - run_qa

resources:

  - primr://strategies/available

  - primr://output/latest

---



# Primr Strategy Skill



## Conceptual Framework



Strategy generation is a post-research step. The report is the evidence base; the strategy output is a structured interpretation of that evidence, not a substitute for validation.



Use `primr://strategies/available` to discover the current strategy set and requirements instead of relying on static tables.



## Operational Capabilities



### 1. Inspect strategy options



Read `primr://strategies/available` to confirm available strategy IDs, expected effort, and whether a platform is required.



### 2. Generate the requested strategy



Before `generate_strategy`, call `estimate_strategy`, tell the user it incurs real API cost, get explicit approval, and pass `max_estimated_cost_usd` when available. Then call `generate_strategy` with a concrete report path and strategy type.



```text

generate_strategy(report_path="output/exampleco/report.md", strategy_type="customer_experience", max_estimated_cost_usd=0.25)

```



### 3. Validate output quality



Offer `run_qa` on the generated strategy or source report when the user wants review.



## Constraints



- Verify the report exists before generation.

- Ask for `platform` when generating `ai_strategy`.

- Do not promise exact runtime or price from the skill text; Primr behavior can evolve.



## Error Handling



- `report_not_found`: locate the report first or run research.

- `invalid_strategy_type`: read `primr://strategies/available` and retry.

- `missing_platform`: ask for the target platform.

