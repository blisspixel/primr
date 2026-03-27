---

name: primr-qa

version: "1.1.0"

description: "Review Primr outputs and diagnose integration issues. Use when the user wants report quality assessment, output review, or system health checks."

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

  - run_qa

  - doctor

resources:

  - primr://output/latest

  - primr://config

---



# Primr QA Skill



## Conceptual Framework



Use QA to judge research usefulness and trustworthiness, not just formatting. Use diagnostics when the failure is operational rather than editorial.



This skill should stay close to MCP outputs. Avoid embedding fixed provider assumptions in the skill body.



## Operational Capabilities



### 1. Run quality assessment



Read `primr://output/latest` when no path is specified, then call `run_qa` on the concrete report file.



```text

run_qa(report_path="output/exampleco/report.md")

```



### 2. Run diagnostics



Call `doctor` when the issue looks like environment, API, or runtime configuration rather than report quality.



### 3. Interpret results



Focus on factual gaps, weak evidence, and thin strategic interpretation before cosmetic issues.



## Error Handling



- QA failures: run `doctor` and confirm the report path.

- Low scores: identify the weakest sections and recommend one next action.

- Config issues: use `primr://config` and `doctor` to explain what is missing.

