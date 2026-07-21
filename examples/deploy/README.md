# Deployment examples: run primr against your own cloud AI

primr talks to seven providers. Most need only an API key (see
[`docs/API_KEYS.md`](../../docs/API_KEYS.md)). The two **deployment surfaces** —
Azure AI Foundry and Amazon Bedrock — let you run primr against models hosted in
*your own* Azure/AWS account, which is useful for cost, consolidation under one
cloud credential, and reaching cheap tiers (Phi-4, Nova, Gemma, DeepSeek).

Each folder has infrastructure-as-code plus a step-by-step README, all verified
end-to-end:

| Example | IaC | What it does |
|---|---|---|
| [`azure-foundry-grok/`](azure-foundry-grok/) | Bicep | Deploys an xAI Grok model on Azure AI Foundry; primr calls it through `AzureFoundryProvider` (OpenAI-compatible `/openai/v1/`). |
| [`aws-bedrock/`](aws-bedrock/) | CloudFormation | Least-privilege Bedrock invoke policy + a content-filter guardrail; primr calls Bedrock models on-demand through `BedrockProvider` (`converse`). |

Both READMEs include the deploy, `primr keys test`, and **clean-up** commands so
nothing lingers. A recurring lesson baked into both: **query the live catalog
for model ids rather than trusting docs/memory** — names drift and some go
deprecated.
